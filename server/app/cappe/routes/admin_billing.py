"""Cappe platform admin — the plan catalog, prices, take rates and comps.

Mounted behind `require_cappe_platform_admin`, so this is Cappe staff acting on
a Cappe identity (`scope=cappe`) — distinct from matcha's `/admin/*`, which is a
different auth realm entirely.

Every mutating endpoint audits to `cappe_admin_audit` and invalidates the
entitlement cache: these are live money knobs, and a fee edit that takes a TTL
to apply is a fee edit somebody will change twice.
"""
import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...database import get_connection
from ..dependencies import require_cappe_platform_admin
from ..models.cappe import (
    CappeAccount,
    CappeAdminAccount,
    CappeCompRequest,
    CappePlanCreate,
    CappePlanUpsert,
    CappePlatformAdminRequest,
    CappePriceCreate,
    CappePriceOut,
)
from ..services import billing as billing_svc
from ..services.entitlements import decode_features, invalidate_catalog_cache
from ..services.stripe_connect import CappeStripeError, get_cappe_stripe

logger = logging.getLogger(__name__)

router = APIRouter()

_EDITABLE = (
    "name", "description", "status", "sort_order", "can_sell", "platform_fee_bps",
    "allowed_fulfillment", "site_limit", "mailbox_quota_included",
    "features", "unit_label", "max_quantity",
)

# The only editable columns that are actually nullable. Every field on
# CappePlanUpsert is Optional (that is how PATCH semantics are expressed), and
# `model_fields_set` counts an explicitly-sent `null` as sent — so without this
# check, `{"can_sell": null}` builds `can_sell = NULL` and surfaces a raw
# NotNullViolationError as an opaque 500 on a money-knob endpoint.
_NULLABLE_FIELDS = {"description", "site_limit"}


async def _audit(conn, actor: CappeAccount, action: str, target: str, payload: dict) -> None:
    await conn.execute(
        "INSERT INTO cappe_admin_audit (actor_account_id, action, target, payload) "
        "VALUES ($1, $2, $3, $4)",
        actor.id, action, target, json.dumps(payload, default=str),
    )


# ── Catalog ───────────────────────────────────────────────────────────────

@router.get("/admin/billing/products")
async def list_products(
    kind: Optional[str] = Query(default=None, pattern="^(plan|addon)$"),
    _admin: CappeAccount = Depends(require_cappe_platform_admin),
):
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM cappe_billing_products "
            "WHERE ($1::text IS NULL OR kind = $1) ORDER BY sort_order, code",
            kind,
        )
        prices = await conn.fetch(
            "SELECT * FROM cappe_billing_prices WHERE is_current ORDER BY product_code, interval"
        )
    by_code: dict[str, list] = {}
    for p in prices:
        by_code.setdefault(p["product_code"], []).append(dict(p))
    # `features` is decoded here too — returning it raw would hand the admin UI
    # a JSON *string* for the same column the tenant catalog returns as an
    # object, i.e. two shapes for one field.
    return [
        {**dict(r), "features": decode_features(r["features"]),
         "prices": by_code.get(r["code"], [])}
        for r in rows
    ]


@router.post("/admin/billing/products", status_code=status.HTTP_201_CREATED)
async def create_product(
    body: CappePlanCreate, admin: CappeAccount = Depends(require_cappe_platform_admin)
):
    async with get_connection() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM cappe_billing_products WHERE code = $1", body.code
        )
        if exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="That code already exists"
            )
        row = await conn.fetchrow(
            """
            INSERT INTO cappe_billing_products
                (code, kind, name, description, status, sort_order, can_sell,
                 platform_fee_bps, allowed_fulfillment, site_limit,
                 mailbox_quota_included, features, unit_label, max_quantity)
            VALUES ($1,$2,$3,$4,COALESCE($5,'active'),COALESCE($6,0),COALESCE($7,false),
                    COALESCE($8,200),COALESCE($9,'{}'::text[]),$10,
                    COALESCE($11,0),COALESCE($12,'{}'::jsonb),
                    COALESCE($13,'unit'),COALESCE($14,100))
            RETURNING *
            """,
            body.code, body.kind, body.name, body.description, body.status,
            body.sort_order, body.can_sell, body.platform_fee_bps,
            body.allowed_fulfillment, body.site_limit, body.mailbox_quota_included,
            json.dumps(body.features) if body.features is not None else None,
            body.unit_label, body.max_quantity,
        )
        await _audit(conn, admin, "product.create", body.code, body.model_dump(mode="json"))
    invalidate_catalog_cache()
    return dict(row)


@router.patch("/admin/billing/products/{code}")
async def update_product(
    code: str,
    body: CappePlanUpsert,
    admin: CappeAccount = Depends(require_cappe_platform_admin),
):
    """Only the fields actually sent are written, so an edit to one knob can't
    silently reset another."""
    sent = [f for f in _EDITABLE if f in body.model_fields_set]
    if not sent:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to update")

    nulled = [f for f in sent if getattr(body, f) is None and f not in _NULLABLE_FIELDS]
    if nulled:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"These fields cannot be null: {', '.join(sorted(nulled))}",
        )

    sets, args = [], []
    for i, field in enumerate(sent, start=2):
        value = getattr(body, field)
        if field == "features" and value is not None:
            value = json.dumps(value)
            sets.append(f"{field} = ${i}::jsonb")
        else:
            sets.append(f"{field} = ${i}")
        args.append(value)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"UPDATE cappe_billing_products SET {', '.join(sets)}, updated_at = NOW() "
            f"WHERE code = $1 RETURNING *",
            code, *args,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown product")
        await _audit(conn, admin, "product.update", code,
                     {f: getattr(body, f) for f in sent})
    invalidate_catalog_cache()
    return dict(row)


# ── Prices ────────────────────────────────────────────────────────────────

@router.get("/admin/billing/products/{code}/prices", response_model=list[CappePriceOut])
async def list_prices(
    code: str, _admin: CappeAccount = Depends(require_cappe_platform_admin)
):
    """Full history, not just current — an old row is what a grandfathered
    subscriber is actually paying."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM cappe_billing_prices WHERE product_code = $1 "
            "ORDER BY created_at DESC",
            code,
        )
    return [CappePriceOut(**dict(r)) for r in rows]


@router.post("/admin/billing/products/{code}/prices", status_code=status.HTTP_201_CREATED)
async def create_price(
    code: str,
    body: CappePriceCreate,
    admin: CappeAccount = Depends(require_cappe_platform_admin),
):
    """Change a price.

    Stripe Prices are IMMUTABLE, so this mints a NEW one and supersedes the
    current row. **Existing subscribers keep paying the old price** — they are
    grandfathered by default, and migrating them is a separate, explicit action.
    That is the safe default: an admin typo here should not re-price the book.
    """
    # Validate BOTH directions of the intro/intro_days pairing. Only checking
    # the intro direction lets `role='standard'` through with intro_days set,
    # which violates `CONSTRAINT cappe_prices_intro_days
    # CHECK ((role = 'intro') = (intro_days IS NOT NULL))` at INSERT time —
    # after the Stripe Price has already been minted.
    if body.role == "intro":
        if body.interval != "once":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An intro price must be one-time ('once').",
            )
        if not body.intro_days:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An intro price needs intro_days.",
            )
    elif body.intro_days is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="intro_days is only valid on an intro price.",
        )

    # Reserve the DB row FIRST, then mint the Stripe Price against its id.
    #
    # Minting first was wedge-able: the `lookup_key` was derived from COUNT(*),
    # so if the INSERT failed the Stripe Price (and its globally-unique
    # lookup_key) survived while the count did not advance — retrying computed
    # the identical key, Stripe rejected it as a duplicate, and that
    # (product, role, interval) could never be priced again without a SQL
    # console. Keying on the row's own UUID means every attempt is unique.
    #
    # The reserved row is created NOT current and with a NULL stripe_price_id,
    # so it is invisible to `resolve_price` until the Stripe call succeeds.
    async with get_connection() as conn:
        product = await conn.fetchrow(
            "SELECT code, name, description, stripe_product_id FROM cappe_billing_products "
            "WHERE code = $1",
            code,
        )
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown product")
        stripe_product_id = product["stripe_product_id"]

        pending_id = await conn.fetchval(
            """
            INSERT INTO cappe_billing_prices
                (product_code, role, interval, unit_amount_cents, currency,
                 intro_days, is_current, active)
            VALUES ($1,$2,$3,$4,$5,$6,false,false)
            RETURNING id
            """,
            code, body.role, body.interval, body.unit_amount_cents,
            body.currency.upper(), body.intro_days,
        )

    cs = get_cappe_stripe()
    lookup_key = f"cappe_{code}_{body.role}_{body.interval}_{str(pending_id).replace('-', '')[:12]}"

    if not stripe_product_id:
        try:
            stripe_product_id = await cs.ensure_product(
                code=code, name=product["name"], description=product["description"]
            )
        except CappeStripeError as exc:
            async with get_connection() as conn:
                await conn.execute("DELETE FROM cappe_billing_prices WHERE id = $1", pending_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Stripe: {exc}"
            ) from exc
        # Persisted immediately, separate from the price attempt below. If a
        # freshly-minted Product's Price then fails, the product id must
        # already be on the row — otherwise the next retry sees
        # stripe_product_id IS NULL again and mints ANOTHER Stripe Product,
        # leaking one per failed attempt with the catalog eventually pointing
        # at whichever one happened to win.
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE cappe_billing_products SET stripe_product_id = $1, updated_at = NOW() "
                "WHERE code = $2 AND stripe_product_id IS NULL",
                stripe_product_id, code,
            )

    try:
        stripe_price_id = await cs.ensure_price(
            product_id=stripe_product_id,
            unit_amount_cents=body.unit_amount_cents,
            currency=body.currency,
            interval=body.interval,
            lookup_key=lookup_key,
        )
    except CappeStripeError as exc:
        # Drop the reservation so it cannot accumulate as an unusable orphan.
        async with get_connection() as conn:
            await conn.execute("DELETE FROM cappe_billing_prices WHERE id = $1", pending_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Stripe: {exc}"
        ) from exc

    async with get_connection() as conn:
        async with conn.transaction():
            superseded = await conn.fetch(
                """
                UPDATE cappe_billing_prices
                   SET is_current = false, active = false, archived_at = NOW()
                 WHERE product_code = $1 AND role = $2 AND interval = $3
                   AND currency = $4 AND is_current
                RETURNING id, stripe_price_id
                """,
                code, body.role, body.interval, body.currency.upper(),
            )
            row = await conn.fetchrow(
                """
                UPDATE cappe_billing_prices
                   SET stripe_price_id = $2, lookup_key = $3, is_current = true, active = true
                 WHERE id = $1
                RETURNING *
                """,
                pending_id, stripe_price_id, lookup_key,
            )
            await _audit(conn, admin, "price.create", code, {
                "lookup_key": lookup_key,
                "unit_amount_cents": body.unit_amount_cents,
                "superseded": [str(s["id"]) for s in superseded],
            })

    # Best effort — an orphaned active Price charges nobody, so a failure here
    # must not fail the admin's edit.
    for s in superseded:
        if s["stripe_price_id"]:
            try:
                await cs.archive_price(s["stripe_price_id"])
            except CappeStripeError as exc:
                logger.warning("cappe: could not archive price %s: %s", s["stripe_price_id"], exc)

    invalidate_catalog_cache()
    return dict(row)


# ── Accounts + subscriptions ──────────────────────────────────────────────

@router.get("/admin/billing/accounts", response_model=list[CappeAdminAccount])
async def list_accounts(
    plan: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    _admin: CappeAccount = Depends(require_cappe_platform_admin),
):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT a.id, a.email, a.name, a.plan, a.account_type, a.status,
                   a.is_platform_admin, a.created_at,
                   s.status AS subscription_status, s.source AS subscription_source,
                   s.comped_until
              FROM cappe_accounts a
              LEFT JOIN cappe_subscriptions s
                     ON s.account_id = a.id
                    AND s.status IN ('trialing','active','past_due','incomplete','unpaid','paused')
             WHERE ($1::text IS NULL OR a.plan = $1)
               AND ($2::text IS NULL OR a.email ILIKE '%' || $2 || '%'
                                     OR a.name  ILIKE '%' || $2 || '%')
             ORDER BY a.created_at DESC
             LIMIT $3
            """,
            plan, q, limit,
        )
    return [CappeAdminAccount(**dict(r)) for r in rows]


@router.get("/admin/billing/subscriptions")
async def list_subscriptions(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    _admin: CappeAccount = Depends(require_cappe_platform_admin),
):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT s.*, a.email, p.name AS plan_name
              FROM cappe_subscriptions s
              JOIN cappe_accounts a ON a.id = s.account_id
              LEFT JOIN cappe_billing_products p ON p.code = s.plan_code
             WHERE ($1::text IS NULL OR s.status = $1)
             ORDER BY s.created_at DESC
             LIMIT $2
            """,
            status_filter, limit,
        )
    return [dict(r) for r in rows]


@router.post("/admin/billing/accounts/{account_id}/comp")
async def comp_account(
    account_id: UUID,
    body: CappeCompRequest,
    admin: CappeAccount = Depends(require_cappe_platform_admin),
):
    """Grant a plan at no charge.

    Recorded as a real subscription row with `source='comp'` rather than by
    poking `cappe_accounts.plan`, so comps stay visible, expirable and
    revocable instead of looking exactly like paying customers in every report.
    """
    async with get_connection() as conn:
        plan = await conn.fetchrow(
            "SELECT code FROM cappe_billing_products WHERE code = $1 AND kind = 'plan'",
            body.plan_code,
        )
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown plan")
        account = await conn.fetchval("SELECT 1 FROM cappe_accounts WHERE id = $1", account_id)
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown account")

        try:
            async with conn.transaction():
                await billing_svc.grant_comp(
                    conn, account_id=account_id, plan_code=body.plan_code,
                    until=body.until, reason=body.reason,
                )
                await _audit(conn, admin, "account.comp", str(account_id),
                             body.model_dump(mode="json"))
        except billing_svc.LiveSubscriptionExists as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"status": "ok", "plan_code": body.plan_code}


@router.post("/admin/billing/accounts/{account_id}/platform-admin")
async def set_platform_admin(
    account_id: UUID,
    body: CappePlatformAdminRequest,
    admin: CappeAccount = Depends(require_cappe_platform_admin),
):
    async with get_connection() as conn:
        if not body.is_platform_admin:
            # Refuse to remove the last admin — otherwise the admin surface
            # becomes permanently unreachable and only a SQL console gets it back.
            remaining = await conn.fetchval(
                "SELECT COUNT(*) FROM cappe_accounts "
                "WHERE is_platform_admin AND status = 'active' AND id <> $1",
                account_id,
            )
            if not remaining:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot remove the last platform administrator.",
                )
        updated = await conn.fetchval(
            "UPDATE cappe_accounts SET is_platform_admin = $1, updated_at = NOW() "
            "WHERE id = $2 RETURNING id",
            body.is_platform_admin, account_id,
        )
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown account")
        await _audit(conn, admin, "account.platform_admin", str(account_id),
                     {"is_platform_admin": body.is_platform_admin})
    return {"status": "ok"}


@router.get("/admin/billing/events")
async def list_billing_events(
    limit: int = Query(default=50, ge=1, le=200),
    _admin: CappeAccount = Depends(require_cappe_platform_admin),
):
    """Recent Stripe events claimed by Cappe's consumers — for debugging a
    webhook that appears not to have landed."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT event_id, event_type, consumer, received_at FROM stripe_webhook_events "
            "WHERE consumer LIKE 'cappe%' ORDER BY received_at DESC LIMIT $1",
            limit,
        )
    return [dict(r) for r in rows]
