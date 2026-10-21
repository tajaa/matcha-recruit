"""A magazine's paid readers, free subscriptions and earnings — owner side
(cappemag05).

  * `GET /sites/{id}/magazine/readers` — who pays (magazine subscriptions
    that got past checkout) and who has a comp.
  * `POST /sites/{id}/magazine/comps` — give a reader a free subscription,
    for some months or until revoked. The reader is a shopper row on the site
    (made if new) and is emailed; 50 a day per account.
    `DELETE /sites/{id}/magazine/comps/{comp_id}` revokes one.
  * `GET /sites/{id}/magazine/earnings` — the payments ledger
    (`cappe_magazine_payments`): what readers paid, Gummfit's share as Stripe
    took it, refunds, and the writer's Stripe balance. Stripe's processing
    fee comes out of that balance and isn't in the ledger.

Readers cancel from their account page; the owner can cancel one through the
store's subscription routes (`routes/shopper_subscriptions.py`), which take
both kinds.
"""
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeMagazineCompCreate
from ..services.common import site_public_origin
from ..services.entitlements import resolve_entitlements
from ..services.magazine.billing import fee_bps
from ..services.magazine.pages import front_path
from ..services.stripe_connect import CappeStripeError, get_cappe_stripe
from ._shared import get_owned_site

logger = logging.getLogger(__name__)

router = APIRouter()

COMPS_PER_DAY = 50
_ABANDONED = ("preparing", "incomplete", "cancel_requested", "incomplete_expired")


@router.get("/sites/{site_id}/magazine/readers")
async def list_readers(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        subs = await conn.fetch(
            """SELECT sub.id, sub.status, sub.total_cents, sub.currency, sub.current_period_end,
                      sub.cancel_at_period_end, sub.created_at, sh.email, sh.name
                 FROM cappe_shopper_subscriptions sub LEFT JOIN cappe_shoppers sh ON sh.id = sub.shopper_id
                WHERE sub.site_id = $1 AND sub.kind = 'magazine' AND sub.status <> ALL($2::text[])
                ORDER BY sub.created_at DESC LIMIT 500""",
            site_id, list(_ABANDONED),
        )
        comps = await conn.fetch(
            """SELECT c.id, c.note, c.expires_at, c.created_at, sh.email, sh.name
                 FROM cappe_magazine_comps c JOIN cappe_shoppers sh ON sh.id = c.shopper_id
                WHERE c.site_id = $1 AND c.revoked_at IS NULL
                ORDER BY c.created_at DESC LIMIT 500""",
            site_id,
        )
    return {"subscriptions": [dict(r) for r in subs], "comps": [dict(r) for r in comps]}


@router.post("/sites/{site_id}/magazine/comps", status_code=status.HTTP_201_CREATED)
async def give_comp(site_id: UUID, body: CappeMagazineCompCreate, background: BackgroundTasks,
                    account: CappeAccount = Depends(require_cappe_account)):
    """A free subscription. Giving one to a reader who already has one sets
    its end to the new one's."""
    email = str(body.email).strip().lower()
    expires = datetime.now(timezone.utc) + timedelta(days=30 * body.months) if body.months else None
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        if not (await resolve_entitlements(account.plan, conn=conn)).has("magazine_paid"):
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED,
                                detail="Free subscriptions come with paid subscriptions, on the Writer plan or above.")
        mag = await conn.fetchrow("SELECT name, front_at_root FROM cappe_magazines WHERE site_id = $1", site_id)
        if not mag:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Set up the magazine first.")
    await check_rate_limit(str(account.id), "cappe_mag_comp", COMPS_PER_DAY, 86_400)
    async with get_connection() as conn, conn.transaction():
        shopper = await conn.fetchrow(
            "INSERT INTO cappe_shoppers (site_id, email) VALUES ($1, $2) "
            "ON CONFLICT (site_id, email) DO UPDATE SET updated_at = NOW() RETURNING id, deleting",
            site_id, email,
        )
        if shopper["deleting"]:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That reader is deleting their account.")
        comp = await conn.fetchrow(
            """INSERT INTO cappe_magazine_comps (site_id, shopper_id, note, expires_at) VALUES ($1, $2, $3, $4)
               ON CONFLICT (site_id, shopper_id) WHERE revoked_at IS NULL
               DO UPDATE SET expires_at = EXCLUDED.expires_at,
                             note = COALESCE(EXCLUDED.note, cappe_magazine_comps.note)
               RETURNING id, note, expires_at, created_at""",
            site_id, shopper["id"], (body.note or "").strip() or None, expires,
        )
    from ..services.email import send_cappe_magazine_comp_email, store_reply_to

    origin = site_public_origin(site)
    background.add_task(
        send_cappe_magazine_comp_email, email, mag["name"] or site["name"], expires,
        f"{origin}{front_path(mag)}" if origin else None,
        reply_to=store_reply_to(site.get("meta_config"), account.email),
    )
    return {**dict(comp), "email": email}


@router.delete("/sites/{site_id}/magazine/comps/{comp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_comp(site_id: UUID, comp_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        revoked = await conn.fetchval(
            "UPDATE cappe_magazine_comps SET revoked_at = NOW() WHERE id = $1 AND site_id = $2 "
            "AND revoked_at IS NULL RETURNING id",
            comp_id, site_id,
        )
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Free subscription not found")


_TOTALS = ("SELECT currency, COUNT(*) AS payments, COALESCE(SUM(amount_cents), 0) AS gross_cents, "
           "COALESCE(SUM(fee_cents), 0) AS fee_cents, COALESCE(SUM(refunded_cents), 0) AS refunded_cents "
           "FROM cappe_magazine_payments WHERE site_id = $1{since} GROUP BY currency ORDER BY currency")


def _totals(rows) -> list[dict]:
    return [{**dict(r), "net_cents": r["gross_cents"] - r["fee_cents"] - r["refunded_cents"]} for r in rows]


@router.get("/sites/{site_id}/magazine/earnings")
async def earnings(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        all_time = await conn.fetch(_TOTALS.format(since=""), site_id)
        last_30 = await conn.fetch(_TOTALS.format(since=" AND paid_at > NOW() - interval '30 days'"), site_id)
        recent = await conn.fetch(
            """SELECT p.id, p.amount_cents, p.fee_cents, p.refunded_cents, p.currency, p.billing_reason, p.paid_at,
                      sh.email
                 FROM cappe_magazine_payments p LEFT JOIN cappe_shoppers sh ON sh.id = p.shopper_id
                WHERE p.site_id = $1 ORDER BY p.paid_at DESC LIMIT 25""",
            site_id,
        )
        paying = await conn.fetchval(
            "SELECT COUNT(*) FROM cappe_shopper_subscriptions WHERE site_id = $1 AND kind = 'magazine' "
            "AND status IN ('active', 'trialing', 'past_due')",
            site_id,
        )
        bps = await fee_bps(conn)
        stripe_account = await conn.fetchval("SELECT stripe_account_id FROM cappe_accounts WHERE id = $1", account.id)
    balance = None
    if stripe_account:
        try:
            balance = await get_cappe_stripe().connected_balance(stripe_account)
        except CappeStripeError:
            logger.info("magazine earnings: Stripe balance unavailable for %s", account.id)
    return {
        "fee_bps": bps, "paying_readers": int(paying or 0),
        "all_time": _totals(all_time), "last_30_days": _totals(last_30),
        "payments": [dict(r) for r in recent], "balance": balance,
    }
