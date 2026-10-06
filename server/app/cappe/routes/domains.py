"""Cappe domain reselling — search, buy (Porkbun), connect-your-own, lifecycle.

We resell Porkbun-registered domains to tenants at wholesale + a flat markup,
charged on OUR platform Stripe account (not a Connect storefront sale). Flow:

  search → purchase (creates a 'pending' row + platform Checkout Session)
         → [Stripe paid] webhook marks it 'registering' + kicks off finalize
         → finalize: Porkbun register + CloudFront tenant + point DNS at the
                     tenant's routing endpoint → 'active' / edge 'pending_dns'
         → edge sync sees the certificate issued → edge 'live', and only THEN
                     sets cappe_sites.custom_domain so the renderer resolves it
         → on failure: 'failed' + refund the customer's charge

Charge-then-register ordering means a failed card never leaves us holding a
registration; a failed registration after payment is auto-refunded.

TLS: each custom domain is a CloudFront **distribution tenant** of one
tenant-only distribution, and CloudFront issues + renews its certificate itself
(`services/cloudfront_tenants.py`). There is no Caddy and no ask-endpoint. The
whole surface is gated on `settings.cappe_custom_domains_enabled` until the
AWS-side setup in `docs/ops/CAPPE_CUSTOM_DOMAINS.md` is done.
"""
from __future__ import annotations

import asyncio
import logging

import asyncpg
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import dns.asyncresolver
import dns.exception
import dns.resolver

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, Request, status

from app.core.services.stripe_events import (
    CONSUMER_CAPPE_PLATFORM,
    claim_stripe_event,
    release_stripe_event,
)

from ...config import get_settings
from ..services.billing import dispatch_billing_event
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeDnsRecord,
    CappeDnsRecordInput,
    CappeDomain,
    CappeDomainAutoRenewUpdate,
    CappeDomainCheckoutResponse,
    CappeDomainConfig,
    CappeDomainConnectRequest,
    CappeDomainPurchaseRequest,
    CappeDomainRenewRequest,
    CappeDomainSearchResult,
)
from ..services.email import dashboard_url
from ...core.services.porkbun import PorkbunError, get_porkbun
from ..services.stripe_connect import CappeStripeError, get_cappe_stripe
from ..services.domain_register import (
    PURCHASE_SESSION_SECONDS,
    begin_registration,
    finalize_domain_registration,
    provision_domain_edge,
    retry_domain_edge,
)
from .payments import _own_dashboard_url

logger = logging.getLogger("cappe.domains")

router = APIRouter()

# TLDs offered when the user types a bare name (no dot). Kept small — each is a
# rate-limited Porkbun checkDomain call.
_SEARCH_TLDS = ["com", "co", "shop", "store", "io", "site"]
_DOMAIN_COLS = (
    "id, site_id, domain, kind, status, retail_cents AS price_cents, "
    "auto_renew, expires_at, failure_reason, verification_token, transfer_requested_at, "
    "edge_status, edge_error, cf_routing_endpoint, renewal_failed_at, renewal_error, created_at"
)
# A domain can be renewed by hand once it is this close to expiry (or past it).
_MANUAL_RENEW_WINDOW_DAYS = 60
# Statuses in which a domain is really held — these block a second claim.
# `pending` deliberately does not: an unpaid checkout or an unverified connect
# must never be able to lock a name away from whoever actually owns or buys it.
_HELD_STATUSES = ("registering", "active", "transfer_requested")
# ICANN locks a freshly registered domain from transferring out for 60 days.
_TRANSFER_LOCK_DAYS = 60
# Host prefix where a connect domain must publish its ownership TXT record.
_VERIFY_PREFIX = "_cappe-verify"
# Checkout events that can move a domain purchase forward. `completed` alone is
# not enough — a delayed-notification method fires it before the money settles.
_DOMAIN_CHECKOUT_EVENTS = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
}


async def _require_owned_site(conn, account_id: UUID, site_id: UUID) -> None:
    owns = await conn.fetchval(
        "SELECT 1 FROM cappe_sites WHERE id = $1 AND account_id = $2", site_id, account_id
    )
    if not owns:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")


def _require_custom_domains_enabled() -> None:
    """Every path that can create a new custom domain is dark until the edge is
    configured. Without it a tenant can buy or connect a domain that resolves to
    a certificate error — the state this gate exists to prevent."""
    if not get_settings().cappe_custom_domains_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Custom domains are not available yet",
        )


# ── Config (does the UI show the panel, and where does DNS point?) ─────────
# Declared BEFORE /domains/{domain_id}: that route parses a UUID, so a later
# declaration would make this path a 422 instead of a match.
@router.get("/domains/config", response_model=CappeDomainConfig)
async def domains_config(account: CappeAccount = Depends(require_cappe_account)):
    settings = get_settings()
    enabled = settings.cappe_custom_domains_enabled
    return {
        "enabled": enabled,
        "routing_endpoint": settings.cappe_cf_routing_endpoint if enabled else None,
    }


# ── Search ────────────────────────────────────────────────────────────────
@router.get("/domains/search", response_model=list[CappeDomainSearchResult])
async def search_domains(
    q: str = Query(..., min_length=1, max_length=63),
    account: CappeAccount = Depends(require_cappe_account),
):
    """Availability + resale price for the query. A bare name fans out to a few
    common TLDs; a full domain (has a dot) is checked exactly."""
    _require_custom_domains_enabled()
    q = q.strip().lower().rstrip(".")
    if "." in q:
        candidates = [q]
    else:
        base = "".join(c for c in q if c.isalnum() or c == "-").strip("-")
        if not base:
            return []
        candidates = [f"{base}.{tld}" for tld in _SEARCH_TLDS]

    pb = get_porkbun()
    # Check the candidate TLDs concurrently: a bare-name search fans out to ~6
    # TLDs, each a Porkbun round-trip with a 30s timeout, so doing them serially
    # made a single autocomplete wait on the sum (worst case ~180s) instead of the
    # slowest one.
    checked = await asyncio.gather(
        *(pb.check_domain(domain) for domain in candidates), return_exceptions=True
    )
    results: list[dict] = []
    for domain, r in zip(candidates, checked):
        if isinstance(r, PorkbunError):
            # One TLD failing (rate limit / unsupported) shouldn't sink the search.
            logger.warning("cappe domain check failed for %s: %s", domain, r)
            continue
        if isinstance(r, BaseException):
            raise r
        results.append(
            {"domain": r["domain"], "available": r["available"], "price_cents": r["retail_cents"]}
        )
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
    _require_custom_domains_enabled()
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
        if await conn.fetchval(
            "SELECT 1 FROM cappe_domains WHERE domain = $1 AND status = ANY($2::text[])",
            body.domain, list(_HELD_STATUSES),
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="That domain is already being set up"
            )
        # No unique-violation handler: the only unique indexes on this table
        # are partial (`WHERE status = 'active'`), so a `pending` INSERT cannot
        # collide. The handler that used to sit here matched a constraint name
        # (`cappe_domains_domain_key`) that no migration ever created.
        row = await conn.fetchrow(
            """INSERT INTO cappe_domains
                   (account_id, site_id, domain, kind, status, wholesale_cents, retail_cents)
               VALUES ($1, $2, $3, 'register', 'pending', $4, $5)
               RETURNING id""",
            account.id, body.site_id, body.domain, wholesale, retail,
        )
    domain_id = row["id"]

    cs = get_cappe_stripe()
    # Stripe renders these as links on its own hosted page, so a caller-supplied
    # URL is only honoured when it points back at our app — otherwise a real
    # Stripe checkout becomes a springboard to any address the caller picks.
    # Billing and storefront checkout already filtered theirs; this did not.
    success = _own_dashboard_url(body.success_url) or dashboard_url(f"/sites/{body.site_id}?domain=success")
    cancel = _own_dashboard_url(body.cancel_url) or dashboard_url(f"/sites/{body.site_id}?domain=canceled")
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
            save_card=True,  # store the card so the renewal cron can charge off-session
            # A short-lived session: the pending row is a claim on the name for
            # as long as it can still be paid (see `reap_abandoned_purchase`).
            expires_in_seconds=PURCHASE_SESSION_SECONDS,
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


# ── Connect a domain you already own (BYO — verify control, then activate) ──
@router.post("/domains/connect", response_model=CappeDomain)
async def connect_domain(
    body: CappeDomainConnectRequest, account: CappeAccount = Depends(require_cappe_account)
):
    """Start connecting a tenant-owned domain. Creates a PENDING claim with a
    verification token — the caller must add a TXT record at
    `_cappe-verify.<domain>` and call /verify before it activates. We never write
    custom_domain (or authorize TLS) for an unverified claim, so a domain can't be
    hijacked/squatted by someone who doesn't control it."""
    _require_custom_domains_enabled()
    if not body.domain:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enter a domain")
    token = secrets.token_urlsafe(24)
    async with get_connection() as conn:
        await _require_owned_site(conn, account.id, body.site_id)
        # `domain` is globally unique across cappe_domains, so a plain INSERT
        # blows up with an unhandled unique-constraint 500 whenever any row for
        # this domain already exists (a prior connect click, a pending purchase,
        # or another account's claim). Resolve it explicitly: reuse THIS account's
        # own still-pending connect claim (repeat clicks become a no-op), else 409.
        # Repeat clicks reuse THIS account's own still-pending connect claim.
        mine = await conn.fetchrow(
            f"SELECT {_DOMAIN_COLS} FROM cappe_domains "
            "WHERE domain = $1 AND account_id = $2 AND site_id = $3 "
            "AND kind = 'connect' AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
            body.domain, account.id, body.site_id,
        )
        if mine is not None:
            return dict(mine)
        # Only a domain that is really HELD blocks a new claim. This used to
        # 409 on ANY existing row for the name — so one account starting (and
        # abandoning) a purchase, or filing an unverified connect, locked the
        # real owner out indefinitely. Pending claims are harmless: nothing is
        # served or certified until one of them is verified, and the partial
        # unique index lets only one go active.
        if await conn.fetchval(
            "SELECT 1 FROM cappe_domains WHERE domain = $1 AND status = ANY($2::text[])",
            body.domain, list(_HELD_STATUSES),
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That domain is already connected or being set up",
            )
        row = await conn.fetchrow(
            f"""INSERT INTO cappe_domains
                    (account_id, site_id, domain, kind, status, verification_token)
                VALUES ($1, $2, $3, 'connect', 'pending', $4)
                RETURNING {_DOMAIN_COLS}""",
            account.id, body.site_id, body.domain, token,
        )
    return dict(row)


@router.post("/domains/{domain_id}/verify", response_model=CappeDomain)
async def verify_domain(domain_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Resolve the ownership TXT record for a pending connect domain; on a match,
    activate it and attach it to the CloudFront tenant distribution.

    `cappe_sites.custom_domain` is NOT written here — the edge sweeper writes it
    once the certificate is issued, so a verified domain never goes live ahead of
    its TLS."""
    _require_custom_domains_enabled()
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"SELECT {_DOMAIN_COLS} FROM cappe_domains "
            "WHERE id = $1 AND account_id = $2 AND kind = 'connect'",
            domain_id, account.id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
    if row["status"] == "active":
        return dict(row)
    if not row["verification_token"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to verify")

    fqdn = f"{_VERIFY_PREFIX}.{row['domain']}"
    try:
        answers = await dns.asyncresolver.resolve(fqdn, "TXT")
        values = {txt.strip('"') for r in answers for txt in [b"".join(r.strings).decode("utf-8", "ignore")]}
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        values = set()
    except dns.exception.DNSException as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"DNS lookup failed: {exc}")

    if row["verification_token"] not in values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"TXT record not found yet. Add a TXT record at {fqdn} with the token, then retry.",
        )

    async with get_connection() as conn:
        try:
            async with conn.transaction():
                if await conn.fetchval(
                    "SELECT 1 FROM cappe_domains WHERE domain = $1 AND status = 'active' AND id <> $2",
                    row["domain"], domain_id,
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT, detail="That domain is already connected"
                    )
                await conn.execute(
                    "UPDATE cappe_domains SET status = 'active', updated_at = NOW() WHERE id = $1",
                    domain_id,
                )
        except asyncpg.UniqueViolationError:
            # A concurrent claim activated the same domain between the SELECT
            # and the UPDATE. Caught by type, not by index name: two partial
            # unique indexes guard this (cappe_domains_active_domain_uniq and
            # uq_cappe_domains_lower_active) and string-matching the wrong one
            # turned this race into a 500.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="That domain is already connected"
            )

    # Attach it to the edge. A failure is recorded on the row (edge_status
    # 'failed') rather than raised: ownership IS verified at this point, and the
    # tenant can retry provisioning without redoing the TXT dance.
    await provision_domain_edge(domain_id, row["domain"])

    async with get_connection() as conn:
        updated = await conn.fetchrow(
            f"SELECT {_DOMAIN_COLS} FROM cappe_domains WHERE id = $1", domain_id
        )
    return dict(updated)


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


# ── Manage DNS records (register-kind domains only — they live in our account) ──
async def _owned_register_domain(conn, account_id: UUID, domain_id: UUID):
    row = await conn.fetchrow(
        "SELECT id, domain, kind, status FROM cappe_domains WHERE id = $1 AND account_id = $2",
        domain_id, account_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
    if row["kind"] != "register":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DNS for a connected domain is managed at your own registrar",
        )
    if row["status"] == "transfer_requested":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This domain is being transferred out; DNS is frozen",
        )
    # Only a domain that is actually registered in our Porkbun account has DNS
    # to manage. A 'pending'/'registering'/'failed'/'expired' row would send
    # writes to Porkbun for a name we do not hold.
    if row["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This domain is not active yet",
        )
    return row


@router.get("/domains/{domain_id}/dns", response_model=list[CappeDnsRecord])
async def list_dns(domain_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        row = await _owned_register_domain(conn, account.id, domain_id)
    try:
        records = await get_porkbun().list_dns_records(row["domain"])
    except PorkbunError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return [
        {
            "id": str(r.get("id")), "type": r.get("type", ""), "name": r.get("name", ""),
            "content": r.get("content", ""), "ttl": r.get("ttl"), "prio": r.get("prio"),
        }
        for r in records
    ]


@router.post("/domains/{domain_id}/dns", status_code=status.HTTP_201_CREATED)
async def create_dns(
    domain_id: UUID, body: CappeDnsRecordInput, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        row = await _owned_register_domain(conn, account.id, domain_id)
    try:
        await get_porkbun().create_dns_record(
            row["domain"], record_type=body.type, name=body.name, content=body.content,
            ttl=body.ttl, prio=body.prio,
        )
    except PorkbunError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return {"ok": True}


@router.put("/domains/{domain_id}/dns/{record_id}")
async def edit_dns(
    domain_id: UUID,
    body: CappeDnsRecordInput,
    record_id: str = Path(..., pattern=r"^[0-9]{1,20}$"),
    account: CappeAccount = Depends(require_cappe_account),
):
    """`record_id` is interpolated into the outbound Porkbun URL, so it is
    constrained to the digits Porkbun actually issues — not free text."""
    async with get_connection() as conn:
        row = await _owned_register_domain(conn, account.id, domain_id)
    try:
        await get_porkbun().edit_dns_record(
            row["domain"], record_id, record_type=body.type, name=body.name,
            content=body.content, ttl=body.ttl, prio=body.prio,
        )
    except PorkbunError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return {"ok": True}


@router.delete("/domains/{domain_id}/dns/{record_id}")
async def delete_dns(
    domain_id: UUID,
    record_id: str = Path(..., pattern=r"^[0-9]{1,20}$"),
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        row = await _owned_register_domain(conn, account.id, domain_id)
    try:
        await get_porkbun().delete_dns_record(row["domain"], record_id)
    except PorkbunError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return {"ok": True}


# ── Auto-renew toggle ──────────────────────────────────────────────────────
@router.patch("/domains/{domain_id}/auto-renew", response_model=CappeDomain)
async def set_auto_renew(
    domain_id: UUID, body: CappeDomainAutoRenewUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Toggle renewal for a registered domain. Mirrors the flag to Porkbun so we
    stop being billed when a tenant turns it off (best-effort)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"UPDATE cappe_domains SET auto_renew = $3, updated_at = NOW() "
            f"WHERE id = $1 AND account_id = $2 AND kind = 'register' RETURNING {_DOMAIN_COLS}",
            domain_id, account.id, body.auto_renew,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
    try:
        await get_porkbun().set_auto_renew(row["domain"], body.auto_renew)
    except PorkbunError as exc:
        logger.warning("cappe domain %s auto-renew sync to Porkbun failed: %s", domain_id, exc)
    return dict(row)


# ── Renew by hand (the retry path when the automatic renewal can't collect) ──
@router.post("/domains/{domain_id}/renew", response_model=CappeDomainCheckoutResponse)
async def renew_domain(
    domain_id: UUID, body: CappeDomainRenewRequest,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Pay for another year through Checkout.

    The automatic renewal charges a saved card, and there was no way forward
    when that failed, when there was no card, or when auto-renew was off: the
    domain simply lapsed. This is that way forward. The card used here is
    saved and becomes the one future renewals charge (see the webhook).
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT id, site_id, domain, kind, status, retail_cents,
                      (expires_at IS NULL OR expires_at < NOW() + ($3 || ' days')::interval) AS due
                 FROM cappe_domains WHERE id = $1 AND account_id = $2""",
            domain_id, account.id, str(_MANUAL_RENEW_WINDOW_DAYS),
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
    if row["kind"] != "register":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A connected domain is renewed at your own registrar",
        )
    if row["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only an active domain can be renewed"
        )
    if not row["retail_cents"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This domain has no renewal price on file"
        )
    if not row["due"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This domain isn't due for renewal yet — it can be renewed within "
                   f"{_MANUAL_RENEW_WINDOW_DAYS} days of its expiry date.",
        )
    back = dashboard_url(f"/sites/{row['site_id']}")
    try:
        session = await get_cappe_stripe().create_platform_checkout_session(
            currency="usd",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"Domain renewal — {row['domain']} (1 year)"},
                    "unit_amount": int(row["retail_cents"]),
                },
                "quantity": 1,
            }],
            success_url=_own_dashboard_url(body.success_url) or f"{back}?domain=renewed",
            cancel_url=_own_dashboard_url(body.cancel_url) or back,
            metadata={"type": "cappe_domain_renewal", "domain_id": str(domain_id)},
            customer_email=account.email,
            save_card=True,
            expires_in_seconds=PURCHASE_SESSION_SECONDS,
        )
    except CappeStripeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return {"domain_id": domain_id, "checkout_url": session["url"]}


# ── Transfer-out request (Porkbun has no auth-code API → manual fulfillment) ─
@router.post("/domains/{domain_id}/transfer-request", response_model=CappeDomain)
async def request_transfer(domain_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Tenant requests to move the domain to their own registrar. Enforces the
    60-day ICANN transfer lock, records the request, and flags it for an operator
    to retrieve + send the auth/EPP code (Porkbun exposes no auth-code endpoint)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"SELECT {_DOMAIN_COLS} FROM cappe_domains "
            "WHERE id = $1 AND account_id = $2 AND kind = 'register'",
            domain_id, account.id,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
        if row["status"] != "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Domain is not active")
        locked = await conn.fetchval(
            "SELECT created_at > NOW() - ($2 || ' days')::interval FROM cappe_domains WHERE id = $1",
            domain_id, str(_TRANSFER_LOCK_DAYS),
        )
        if locked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Domains can't be transferred within {_TRANSFER_LOCK_DAYS} days of registration",
            )
        # 'transfer_requested' is a real status, not just a timestamp: it takes
        # the domain out of the renewal sweep and freezes in-app DNS edits. It
        # does NOT take the site offline — a transfer takes days and may never
        # complete, so the edge keeps serving until the registration actually
        # lapses (`expired`). Reversible via /transfer-request/cancel.
        updated = await conn.fetchrow(
            f"UPDATE cappe_domains SET transfer_requested_at = NOW(), "
            f"status = 'transfer_requested', updated_at = NOW() "
            f"WHERE id = $1 RETURNING {_DOMAIN_COLS}",
            domain_id,
        )
    # Operator action: retrieve the auth code from the Porkbun dashboard + unlock,
    # then email it to the tenant. Surfaced in logs until an email/admin queue exists.
    logger.warning(
        "cappe TRANSFER-OUT requested: domain=%s account=%s — provide auth code from Porkbun",
        row["domain"], account.email,
    )
    return dict(updated)


@router.post("/domains/{domain_id}/transfer-request/cancel", response_model=CappeDomain)
async def cancel_transfer_request(
    domain_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    """Withdraw a transfer-out request: the domain goes back to `active`, which
    puts it back in the renewal sweep and unfreezes DNS. Without this a tenant
    who clicked "Transfer out" by mistake sat outside renewals until the
    registration lapsed."""
    async with get_connection() as conn:
        updated = await conn.fetchrow(
            f"UPDATE cappe_domains SET status = 'active', transfer_requested_at = NULL, "
            f"updated_at = NOW() WHERE id = $1 AND account_id = $2 "
            f"AND status = 'transfer_requested' RETURNING {_DOMAIN_COLS}",
            domain_id, account.id,
        )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="No transfer request to cancel"
        )
    logger.warning("cappe TRANSFER-OUT cancelled: domain=%s account=%s", updated["domain"], account.email)
    # The renewals task switches Porkbun auto-renew off for a domain that is
    # leaving; put it back the way the tenant had it (best-effort, like the
    # auto-renew toggle itself).
    if updated["kind"] == "register" and updated["auto_renew"]:
        try:
            await get_porkbun().set_auto_renew(updated["domain"], True)
        except PorkbunError as exc:
            logger.warning("cappe domain %s auto-renew re-enable failed: %s", domain_id, exc)
    return dict(updated)


# ── Edge (CloudFront tenant) retry ─────────────────────────────────────────
@router.post("/domains/{domain_id}/edge/retry", response_model=CappeDomain)
async def retry_edge(domain_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Re-attempt edge provisioning for an active domain that is not serving:
    never provisioned (`none`), creation failed, or its certificate died
    (`failed` with a tenant — replaced). A healthy or still-validating tenant is
    left alone; `retry_domain_edge` owns those rules."""
    _require_custom_domains_enabled()
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, status, cf_tenant_id FROM cappe_domains WHERE id = $1 AND account_id = $2",
            domain_id, account.id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
    if row["status"] != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Domain is not active")
    await retry_domain_edge(domain_id)
    async with get_connection() as conn:
        updated = await conn.fetchrow(
            f"SELECT {_DOMAIN_COLS} FROM cappe_domains WHERE id = $1", domain_id
        )
    return dict(updated)


async def _apply_manual_renewal(event_type: str, obj: dict, meta: dict) -> dict:
    """A `POST /domains/{id}/renew` checkout reached a terminal event."""
    try:
        did = UUID(str(meta.get("domain_id")))
    except (ValueError, TypeError):
        return {"received": True, "status": "ignored"}
    if event_type == "checkout.session.async_payment_failed":
        logger.info("cappe domain %s manual renewal payment failed", did)
        return {"received": True, "status": "payment_failed"}
    if obj.get("payment_status") != "paid":
        return {"received": True, "status": "unpaid"}

    payment_intent = obj.get("payment_intent")
    cs = get_cappe_stripe()
    payment_method_id = None
    if payment_intent:
        try:
            payment_method_id = await cs.payment_method_for_intent(payment_intent)
        except CappeStripeError as exc:
            logger.warning("cappe domain %s: could not read the renewal payment method: %s", did, exc)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """UPDATE cappe_domains
                  SET expires_at = GREATEST(COALESCE(expires_at, NOW()), NOW()) + INTERVAL '1 year',
                      stripe_customer_id = COALESCE($2, stripe_customer_id),
                      stripe_payment_method_id = COALESCE($3, stripe_payment_method_id),
                      renewal_attempted_at = NOW(), renewal_failed_at = NULL,
                      renewal_notified_at = NULL, renewal_error = NULL, updated_at = NOW()
                WHERE id = $1 AND kind = 'register' AND status = 'active'
            RETURNING domain""",
            did, obj.get("customer"), payment_method_id,
        )
    if row is None:
        # Paid for a domain that lapsed or was removed while the page was open.
        # The year can't be applied, so the money goes back.
        try:
            if payment_intent:
                await cs.refund(payment_intent, idempotency_key=f"cappe-domain-renewal-unapplied-{payment_intent}")
            logger.error(
                "cappe domain %s: manual renewal paid (intent %s) but the domain is no longer "
                "active — refunded automatically", did, payment_intent,
            )
        except CappeStripeError as exc:
            logger.error(
                "cappe domain %s: manual renewal paid (intent %s) for an inactive domain and the "
                "refund FAILED: %s — MANUAL REFUND REQUIRED", did, payment_intent, exc,
            )
        return {"received": True, "status": "renewal_unapplied"}
    # Our charge only recoups the registrar's renewal; Porkbun's own auto-renew
    # is what actually extends the registration. It is switched off for a
    # domain that was lapsing or had auto-renew off, so put it back on.
    try:
        await get_porkbun().set_auto_renew(row["domain"], True)
    except PorkbunError as exc:
        logger.error(
            "cappe domain %s renewed and paid, but Porkbun auto-renew could not be switched on: "
            "%s — renew it at the registrar by hand", did, exc,
        )
    logger.info("cappe domain %s renewed by hand (+1yr)", did)
    return {"received": True, "status": "renewed"}


async def _sync_platform_refund(obj: dict) -> Optional[str]:
    """`charge.refunded` on OUR account. Returns a status when the charge was
    a domain's, None when it is somebody else's (subscription billing follows
    the subscription's own status and needs nothing here).

    A full refund of a domain's purchase or renewal means nobody is paying for
    it any more, so every future charge stops — ours and the registrar's. The
    domain is NOT torn down: it keeps serving to the end of the term already
    bought, then lapses with the same notice as any other unrenewed domain.
    Before this a refunded domain stayed `active` and Porkbun kept renewing it
    on our account for good.
    """
    intent = obj.get("payment_intent")
    amount = int(obj.get("amount") or 0)
    refunded = int(obj.get("amount_refunded") or 0)
    if not (bool(obj.get("refunded")) or (amount > 0 and refunded >= amount)):
        return None  # a partial (goodwill) refund changes nothing
    refunds = ((obj.get("refunds") or {}).get("data") or []) if isinstance(obj.get("refunds"), dict) else []
    refund_id = refunds[0].get("id") if refunds else None
    meta = obj.get("metadata") or {}

    row = None
    async with get_connection() as conn:
        if isinstance(intent, str) and intent:
            row = await conn.fetchrow(
                """UPDATE cappe_domains
                      SET refund_status = 'refunded',
                          refunded_at = COALESCE(refunded_at, NOW()),
                          stripe_refund_id = COALESCE($2, stripe_refund_id),
                          auto_renew = false,
                          status = CASE WHEN status IN ('pending', 'registering') THEN 'failed' ELSE status END,
                          failure_reason = CASE WHEN status IN ('pending', 'registering')
                                                THEN 'Refunded before registration' ELSE failure_reason END,
                          updated_at = NOW()
                    WHERE stripe_payment_intent = $1
                RETURNING id, domain, kind, status""",
                intent, refund_id,
            )
        if row is None and meta.get("type") == "cappe_domain_renewal":
            try:
                did = UUID(str(meta.get("domain_id")))
            except (ValueError, TypeError):
                did = None
            if did is not None:
                row = await conn.fetchrow(
                    "UPDATE cappe_domains SET auto_renew = false, updated_at = NOW() "
                    "WHERE id = $1 RETURNING id, domain, kind, status",
                    did,
                )
    if row is None:
        return None
    if row["kind"] == "register" and row["status"] in ("active", "transfer_requested"):
        try:
            await get_porkbun().set_auto_renew(row["domain"], False)
        except PorkbunError as exc:
            logger.error(
                "cappe domain %s refunded, but Porkbun auto-renew could not be switched off: %s",
                row["id"], exc,
            )
    logger.error(
        "cappe domain %s (%s) was refunded in Stripe — auto-renew switched off; it will lapse at "
        "the end of its current term", row["id"], row["domain"],
    )
    return "domain_refunded"


# ── Platform webhook (domain purchases; OUR account, no event.account) ─────
@router.post("/domains/webhook")
async def domains_webhook(request: Request, background: BackgroundTasks):
    """Stripe PLATFORM webhook — the single endpoint for everything charged to
    OUR account: domain purchases AND subscription billing.

    One endpoint, one secret. Two endpoints would mean two `whsec_` values and
    an event-type split configured in the Stripe dashboard, where an unticked
    checkbox silently drops subscription events with no local signal. (The path
    is named for domains only because that is what it originally carried and
    what is already registered in Stripe; renaming it is a follow-up that has to
    be coordinated with the dashboard.)

    Distinct endpoint/secret from the Connect storefront webhook, which carries
    the tenants' own sales.
    """
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    cs = get_cappe_stripe()
    try:
        event = await cs.verify_platform_webhook(payload, signature)
    except CappeStripeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    event_id = event.get("id") or ""
    event_type = event.get("type") or ""
    obj = event.get("data", {}).get("object", {}) or {}
    meta = obj.get("metadata") or {}
    event_at = (
        datetime.fromtimestamp(int(event["created"]), tz=timezone.utc)
        if event.get("created") else None
    )

    # Dedupe under our OWN consumer key. Core's webhook handles invoice.* and
    # customer.subscription.* on this same Stripe account; a globally-keyed
    # ledger would let whichever endpoint claimed first silently starve the other.
    if event_id and not await claim_stripe_event(
        event_id, event_type, consumer=CONSUMER_CAPPE_PLATFORM
    ):
        return {"received": True, "status": "duplicate"}

    try:
        if meta.get("type") == "cappe_domain" and event_type in _DOMAIN_CHECKOUT_EVENTS:
            try:
                did = UUID(str(meta.get("domain_id")))
            except (ValueError, TypeError):
                did = None
            if did is None:
                return {"received": True, "status": "ignored"}

            if event_type == "checkout.session.async_payment_failed":
                # A delayed method (ACH/SEPA/Klarna) that ultimately bounced.
                # Nothing was registered — the row never left 'pending'.
                async with get_connection() as conn:
                    await conn.execute(
                        """UPDATE cappe_domains
                              SET status = 'failed', failure_reason = $2, updated_at = NOW()
                            WHERE id = $1 AND status IN ('pending', 'registering')""",
                        did, "Payment failed",
                    )
                logger.info("cappe domain %s payment failed", did)
                return {"received": True, "status": "payment_failed"}

            # `checkout.session.completed` fires for delayed-notification payment
            # methods with payment_status 'unpaid'; the money lands (or doesn't)
            # later via async_payment_succeeded/failed. Registering on that event
            # would debit our Porkbun balance for a payment that may never clear.
            if obj.get("payment_status") != "paid":
                logger.info(
                    "cappe domain %s checkout completed but unpaid (%s); waiting",
                    did, obj.get("payment_status"),
                )
                return {"received": True, "status": "unpaid"}

            # `customer` is the saved-card Customer; the payment method itself
            # is read and stored inside begin_registration (renewals need it).
            if await begin_registration(did, obj.get("payment_intent"), obj.get("customer")):
                background.add_task(finalize_domain_registration, did)
                logger.info("cappe domain %s paid; registering", did)
            return {"received": True}

        if meta.get("type") == "cappe_domain_renewal" and event_type in _DOMAIN_CHECKOUT_EVENTS:
            return await _apply_manual_renewal(event_type, obj, meta)

        if event_type == "charge.refunded":
            refund_status = await _sync_platform_refund(obj)
            if refund_status:
                return {"received": True, "status": refund_status}

        # Everything else that could be ours: subscription billing. The handler
        # resolves the subscription against our own tables and returns
        # "ignored" for anything it does not own (i.e. Matcha's), so an event
        # belonging to another product 200s instead of being retried forever.
        # It takes no connection — it opens its own around each Stripe call so
        # a slow round-trip never pins one from the pool.
        result = await dispatch_billing_event(event_type, obj, event_at)
        return {"received": True, **result}
    except Exception:
        # Release the claim so Stripe's retry can re-process; without this a
        # transient failure would permanently strand a paid customer.
        await release_stripe_event(event_id, consumer=CONSUMER_CAPPE_PLATFORM)
        raise
