"""Cappe domain reselling — search, buy (Porkbun), connect-your-own, lifecycle.

We resell Porkbun-registered domains to tenants at wholesale + a flat markup,
charged on OUR platform Stripe account (not a Connect storefront sale). Flow:

  search → purchase (creates a 'pending' row + platform Checkout Session)
         → [Stripe paid] webhook marks it 'registering' + kicks off finalize
         → finalize: Porkbun register + point DNS at the app → 'active'
                     (sets cappe_sites.custom_domain so the renderer resolves it)
         → on failure: 'failed' + refund the customer's charge

Charge-then-register ordering means a failed card never leaves us holding a
registration; a failed registration after payment is auto-refunded. TLS for the
live domain is issued on-demand by Caddy, gated by GET /tls/authorize.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status

from ...config import get_settings
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeDomain,
    CappeDomainCheckoutResponse,
    CappeDomainConnectRequest,
    CappeDomainPurchaseRequest,
    CappeDomainSearchResult,
)
from ..services.email import dashboard_url
from ..services.porkbun import PorkbunError, get_porkbun
from ..services.stripe_connect import CappeStripeError, get_cappe_stripe
from .render import invalidate_render_cache

logger = logging.getLogger("cappe.domains")

router = APIRouter()

# TLDs offered when the user types a bare name (no dot). Kept small — each is a
# rate-limited Porkbun checkDomain call.
_SEARCH_TLDS = ["com", "co", "shop", "store", "io", "site"]
_DOMAIN_COLS = (
    "id, site_id, domain, kind, status, retail_cents AS price_cents, "
    "auto_renew, expires_at, failure_reason, created_at"
)


async def _require_owned_site(conn, account_id: UUID, site_id: UUID) -> None:
    owns = await conn.fetchval(
        "SELECT 1 FROM cappe_sites WHERE id = $1 AND account_id = $2", site_id, account_id
    )
    if not owns:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")


# ── Search ────────────────────────────────────────────────────────────────
@router.get("/domains/search", response_model=list[CappeDomainSearchResult])
async def search_domains(
    q: str = Query(..., min_length=1, max_length=63),
    account: CappeAccount = Depends(require_cappe_account),
):
    """Availability + resale price for the query. A bare name fans out to a few
    common TLDs; a full domain (has a dot) is checked exactly."""
    q = q.strip().lower().rstrip(".")
    if "." in q:
        candidates = [q]
    else:
        base = "".join(c for c in q if c.isalnum() or c == "-").strip("-")
        if not base:
            return []
        candidates = [f"{base}.{tld}" for tld in _SEARCH_TLDS]

    pb = get_porkbun()
    results: list[dict] = []
    for domain in candidates:
        try:
            r = await pb.check_domain(domain)
            results.append(
                {"domain": r["domain"], "available": r["available"], "price_cents": r["retail_cents"]}
            )
        except PorkbunError as exc:
            # One TLD failing (rate limit / unsupported) shouldn't sink the search.
            logger.warning("cappe domain check failed for %s: %s", domain, exc)
    if not results and len(candidates) == 1:
        # Single exact check failed outright — surface configuration/availability errors.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Domain lookup failed")
    return results


# ── Purchase (register via Porkbun, charged on the platform) ───────────────
@router.post("/domains/purchase", response_model=CappeDomainCheckoutResponse)
async def purchase_domain(
    body: CappeDomainPurchaseRequest, account: CappeAccount = Depends(require_cappe_account)
):
    """Re-check availability + price, create a pending domain row, and return a
    platform Checkout Session. Registration happens in the webhook after payment."""
    pb = get_porkbun()
    try:
        check = await pb.check_domain(body.domain)
    except PorkbunError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    if not check["available"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That domain is not available")
    wholesale = check["wholesale_cents"]
    retail = check["retail_cents"]
    if not wholesale or not retail:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not price that domain")

    async with get_connection() as conn:
        await _require_owned_site(conn, account.id, body.site_id)
        try:
            row = await conn.fetchrow(
                """INSERT INTO cappe_domains
                       (account_id, site_id, domain, kind, status, wholesale_cents, retail_cents)
                   VALUES ($1, $2, $3, 'register', 'pending', $4, $5)
                   RETURNING id""",
                account.id, body.site_id, body.domain, wholesale, retail,
            )
        except Exception as exc:  # unique domain collision, etc.
            if "cappe_domains_domain_key" in str(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="That domain is already being set up"
                )
            raise
    domain_id = row["id"]

    cs = get_cappe_stripe()
    success = body.success_url or dashboard_url(f"/sites/{body.site_id}?domain=success")
    cancel = body.cancel_url or dashboard_url(f"/sites/{body.site_id}?domain=canceled")
    try:
        session = await cs.create_platform_checkout_session(
            currency="usd",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"Domain registration — {body.domain} (1 year)"},
                    "unit_amount": retail,
                },
                "quantity": 1,
            }],
            success_url=success,
            cancel_url=cancel,
            metadata={"type": "cappe_domain", "domain_id": str(domain_id)},
            customer_email=account.email,
        )
    except CappeStripeError as exc:
        async with get_connection() as conn:
            await conn.execute("DELETE FROM cappe_domains WHERE id = $1 AND status = 'pending'", domain_id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    async with get_connection() as conn:
        await conn.execute(
            "UPDATE cappe_domains SET stripe_session_id = $1, updated_at = NOW() WHERE id = $2",
            session["id"], domain_id,
        )
    return {"domain_id": domain_id, "checkout_url": session["url"]}


# ── Connect a domain you already own (BYO — no registration) ───────────────
@router.post("/domains/connect", response_model=CappeDomain)
async def connect_domain(
    body: CappeDomainConnectRequest, account: CappeAccount = Depends(require_cappe_account)
):
    """Attach a tenant-owned domain. The tenant points DNS (A → our IP) at us;
    Caddy then issues TLS on first request. We record it active and set it as the
    site's custom_domain so the renderer resolves it."""
    if not body.domain:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enter a domain")
    async with get_connection() as conn:
        await _require_owned_site(conn, account.id, body.site_id)
        async with conn.transaction():
            try:
                row = await conn.fetchrow(
                    f"""INSERT INTO cappe_domains
                            (account_id, site_id, domain, kind, status)
                        VALUES ($1, $2, $3, 'connect', 'active')
                        RETURNING {_DOMAIN_COLS}""",
                    account.id, body.site_id, body.domain,
                )
            except Exception as exc:
                if "cappe_domains_domain_key" in str(exc):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT, detail="That domain is already connected"
                    )
                raise
            await conn.execute(
                "UPDATE cappe_sites SET custom_domain = $1, updated_at = NOW() WHERE id = $2",
                body.domain, body.site_id,
            )
    await invalidate_render_cache(body.site_id)
    return dict(row)


# ── List / get ──────────────────────────────────────────────────────────
@router.get("/domains", response_model=list[CappeDomain])
async def list_domains(
    site_id: Optional[UUID] = None, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        if site_id is not None:
            rows = await conn.fetch(
                f"SELECT {_DOMAIN_COLS} FROM cappe_domains WHERE account_id = $1 AND site_id = $2 "
                "ORDER BY created_at DESC",
                account.id, site_id,
            )
        else:
            rows = await conn.fetch(
                f"SELECT {_DOMAIN_COLS} FROM cappe_domains WHERE account_id = $1 ORDER BY created_at DESC",
                account.id,
            )
    return [dict(r) for r in rows]


@router.get("/domains/{domain_id}", response_model=CappeDomain)
async def get_domain(domain_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"SELECT {_DOMAIN_COLS} FROM cappe_domains WHERE id = $1 AND account_id = $2",
            domain_id, account.id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
    return dict(row)


# ── Caddy on-demand TLS ask-endpoint (public) ──────────────────────────────
@router.get("/tls/authorize")
async def tls_authorize(domain: str = Query(..., max_length=255)):
    """Caddy on-demand TLS gate: 200 → issue a cert for this host, 404 → refuse.
    Only hosts we serve (an active custom domain) are authorized, so Let's Encrypt
    issuance can't be triggered for arbitrary hostnames."""
    host = domain.strip().lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    async with get_connection() as conn:
        ok = await conn.fetchval(
            "SELECT 1 FROM cappe_sites WHERE custom_domain = $1 "
            "UNION SELECT 1 FROM cappe_domains WHERE domain = $1 AND status = 'active' LIMIT 1",
            host,
        )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown host")
    return Response(status_code=status.HTTP_200_OK)


# ── Platform webhook (domain purchases; OUR account, no event.account) ─────
@router.post("/domains/webhook")
async def domains_webhook(request: Request, background: BackgroundTasks):
    """Stripe PLATFORM webhook for domain purchases. On checkout.session.completed
    for a 'cappe_domain' session: mark the row registering + kick off Porkbun
    registration. Distinct endpoint/secret from the Connect storefront webhook."""
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    cs = get_cappe_stripe()
    try:
        event = await cs.verify_platform_webhook(payload, signature)
    except CappeStripeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if event.get("type") == "checkout.session.completed":
        obj = event.get("data", {}).get("object", {}) or {}
        meta = obj.get("metadata") or {}
        if meta.get("type") == "cappe_domain":
            try:
                did = UUID(str(meta.get("domain_id")))
            except (ValueError, TypeError):
                did = None
            if did is not None:
                payment_intent = obj.get("payment_intent")
                async with get_connection() as conn:
                    row = await conn.fetchrow(
                        """UPDATE cappe_domains
                              SET status = 'registering', stripe_payment_intent = $2, updated_at = NOW()
                            WHERE id = $1 AND status = 'pending'
                            RETURNING id""",
                        did, payment_intent,
                    )
                if row is not None:
                    background.add_task(finalize_domain_registration, did)
                    logger.info("cappe domain %s paid; registering", did)

    return {"received": True}


# ── Registration finalizer (background; runs after the webhook 200) ────────
async def finalize_domain_registration(domain_id: UUID) -> None:
    """Register the domain at Porkbun and point its DNS at the app. On success,
    set it active + as the site's custom_domain. On failure, mark failed and
    refund the customer's platform charge."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, site_id, domain, wholesale_cents, stripe_payment_intent "
            "FROM cappe_domains WHERE id = $1 AND status = 'registering'",
            domain_id,
        )
    if row is None:
        return

    pb = get_porkbun()
    try:
        await pb.register(
            row["domain"], cost_cents=int(row["wholesale_cents"] or 0), idempotency_key=str(domain_id)
        )
        # Best-effort DNS — a record failure shouldn't fail the registration we
        # already paid for; the owner can re-point in the registrar later.
        try:
            await pb.point_at_app(row["domain"])
        except PorkbunError as exc:
            logger.warning("cappe domain %s registered but DNS pointing failed: %s", domain_id, exc)
    except PorkbunError as exc:
        logger.error("cappe domain %s registration failed: %s", domain_id, exc)
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE cappe_domains SET status = 'failed', failure_reason = $2, updated_at = NOW() "
                "WHERE id = $1",
                domain_id, str(exc)[:500],
            )
        pi = row["stripe_payment_intent"]
        if pi:
            try:
                await get_cappe_stripe().refund(pi)
                logger.info("cappe domain %s charge refunded", domain_id)
            except CappeStripeError as rexc:
                logger.error("cappe domain %s refund failed: %s", domain_id, rexc)
        return

    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE cappe_domains SET status = 'active', "
                "expires_at = NOW() + INTERVAL '1 year', updated_at = NOW() WHERE id = $1",
                domain_id,
            )
            await conn.execute(
                "UPDATE cappe_sites SET custom_domain = $1, updated_at = NOW() WHERE id = $2",
                row["domain"], row["site_id"],
            )
    await invalidate_render_cache(row["site_id"])
    logger.info("cappe domain %s active → %s", domain_id, row["domain"])
