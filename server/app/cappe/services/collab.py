"""Cappe collab domain logic — fee resolution, offer state machine, materializers.

Single choke point: every offer status change goes through transition helpers
here (mirrors matcha discipline's transition_status pattern). Routes never
UPDATE cappe_collab_offers.status directly.

Creator-first stance: cancel asymmetry (brand owes for approved work), auto-
approve on brand silence, and a deterministic Deal Check are all here — see
CAPPE_CREATOR_MARKETPLACE_PLAN.md Part 3 + the protections addendum folded
into it.
"""
import json
import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException, status

from ..models.collab import CollabTerms, DealCheckItem
from ...config import get_settings
from .email import dashboard_url, send_cappe_collab_completed_email, send_cappe_collab_payment_due_email, send_cappe_deliverable_decision_email

logger = logging.getLogger("cappe.collab")

async def resolve_contact(conn, offer_row, side: str) -> tuple[str, Optional[str]]:
    if side == "brand":
        row = await conn.fetchrow("SELECT ca.email, ca.name FROM cappe_creator_profiles p JOIN cappe_accounts ca ON ca.id = p.account_id WHERE p.id = $1", offer_row["creator_profile_id"])
        return row["email"], row["name"]
    row = await conn.fetchrow("SELECT email, name FROM cappe_accounts WHERE id = $1", offer_row["brand_account_id"])
    return row["email"], row["name"] or offer_row["brand_name"]

async def notify_auto_approve(conn, offer_id: UUID, offer_row, result: dict) -> None:
    if not result["deliverables"] and not result["fired_payments"]:
        return
    creator_email, creator_name = await resolve_contact(conn, offer_row, "brand")
    brand_email, brand_name = await resolve_contact(conn, offer_row, "creator")
    for d in result["deliverables"]:
        await send_cappe_deliverable_decision_email(creator_email, creator_name, offer_row["title"], d["label"], True, None, dashboard_url(f"/creator/deals/{offer_id}"))
    for p in result["fired_payments"]:
        await send_cappe_collab_payment_due_email(brand_email, brand_name, offer_row["title"], p["label"], p["amount_cents"], dashboard_url(f"/collabs/{offer_id}"))
    if result["completed"]:
        await send_cappe_collab_completed_email(brand_email, brand_name, offer_row["title"], dashboard_url(f"/collabs/{offer_id}"))
        await send_cappe_collab_completed_email(creator_email, creator_name, offer_row["title"], dashboard_url(f"/creator/deals/{offer_id}"))

TERMINAL_STATUSES = {"completed", "declined", "withdrawn", "cancelled"}
PRE_ACCEPT_STATUSES = {"sent", "negotiating"}


# ── Marketplace settings knobs ───────────────────────────────────────────────

async def resolve_marketplace_int(conn, key: str, subkey: str, fallback: int) -> int:
    """Read an int knob from cappe_marketplace_settings; fall back on missing/garbage."""
    raw = await conn.fetchval("SELECT value FROM cappe_marketplace_settings WHERE key = $1", key)
    if raw is None:
        return fallback
    try:
        val = json.loads(raw) if isinstance(raw, str) else raw
        return int(val[subkey])
    except (KeyError, TypeError, ValueError):
        logger.warning("cappe collab: bad settings row %s=%r, using fallback", key, raw)
        return fallback


async def resolve_collab_fee_bps(conn) -> int:
    return await resolve_marketplace_int(
        conn, "collab_fee_bps", "bps", get_settings().cappe_platform_fee_bps
    )


async def resolve_min_offer_cents(conn) -> int:
    return await resolve_marketplace_int(conn, "min_offer_cents", "cents", 5000)


async def resolve_auto_approve_days(conn) -> int:
    return await resolve_marketplace_int(conn, "auto_approve_days", "days", 14)


# ── Materializers ─────────────────────────────────────────────────────────────

def expand_deliverables(terms: CollabTerms) -> list[dict]:
    """Quantity-expanded deliverable rows (a `quantity: 3` line -> 3 rows),
    idx 0-based across the whole list."""
    rows, idx = [], 0
    for d in terms.deliverables:
        for _ in range(d.quantity):
            rows.append({"idx": idx, "type": d.type, "platform": d.platform,
                         "spec": d.spec, "due_date": d.due_date})
            idx += 1
    return rows


def build_payment_rows(terms: CollabTerms, deliverable_count: int) -> list[dict]:
    """Installment plan for the accepted terms. amount sums exactly to
    compensation_cents; remainders land on the LAST row."""
    total = terms.compensation_cents
    if terms.payment_schedule == "upfront":
        return [{"idx": 0, "label": "Full payment", "trigger": "on_accept",
                 "amount_cents": total, "deliverable_idx": None}]
    if terms.payment_schedule == "split_50_50":
        first = total // 2
        return [
            {"idx": 0, "label": "50% on acceptance", "trigger": "on_accept",
             "amount_cents": first, "deliverable_idx": None},
            {"idx": 1, "label": "50% on completion", "trigger": "on_all_approved",
             "amount_cents": total - first, "deliverable_idx": None},
        ]
    # per_deliverable
    n = max(1, deliverable_count)
    base = total // n
    rows = []
    for i in range(n):
        amount = base if i < n - 1 else total - base * (n - 1)
        rows.append({"idx": i, "label": f"Deliverable {i + 1} of {n}",
                     "trigger": "on_deliverable", "amount_cents": amount,
                     "deliverable_idx": i})
    return rows
    # Zero-compensation offers (compensation_cents == 0, gifting-only) skip
    # payment rows entirely at accept — this function is not called when
    # total is 0 (the payments CHECK requires amount_cents > 0).


# ── Offer lookup ───────────────────────────────────────────────────────────────

async def get_offer_side(conn, offer_id: UUID, account_id: UUID):
    """Load the offer + resolve which side the caller is. 404 on missing or
    non-participant (existence not leaked)."""
    row = await conn.fetchrow(
        """SELECT o.*, p.account_id AS creator_account_id, p.handle AS creator_handle,
                  p.display_name AS creator_display_name, p.avatar_url AS creator_avatar_url,
                  ba.name AS brand_name, ca.stripe_account_id AS creator_stripe_account_id,
                  ca.stripe_charges_enabled AS creator_charges_enabled
             FROM cappe_collab_offers o
             JOIN cappe_creator_profiles p ON p.id = o.creator_profile_id
             JOIN cappe_accounts ba ON ba.id = o.brand_account_id
             JOIN cappe_accounts ca ON ca.id = p.account_id
            WHERE o.id = $1""",
        offer_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    if row["brand_account_id"] == account_id:
        return row, "brand"
    if row["creator_account_id"] == account_id:
        return row, "creator"
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")


async def latest_revision(conn, offer_id: UUID):
    return await conn.fetchrow(
        "SELECT * FROM cappe_collab_offer_revisions WHERE offer_id = $1 "
        "ORDER BY revision_no DESC LIMIT 1",
        offer_id,
    )


async def accepted_revision(conn, offer_row):
    """The revision terms actually in force. Once an offer has an
    accepted_revision_id, that row is the source of truth — NOT
    revisions[-1] — because a race between accept and a concurrent counter
    (closed by accept_offer's FOR UPDATE lock going forward, but old rows
    can still predate that fix) can leave a later revision in the table
    that was never agreed to. Falls back to the latest revision while still
    pre-accept, when there is no accepted_revision_id yet."""
    if offer_row["accepted_revision_id"]:
        rev = await conn.fetchrow(
            "SELECT * FROM cappe_collab_offer_revisions WHERE id = $1", offer_row["accepted_revision_id"]
        )
        if rev is not None:
            return rev
    return await latest_revision(conn, offer_row["id"])


# ── Accept ───────────────────────────────────────────────────────────────────

async def accept_offer(conn, offer_row, side: str) -> None:
    """Call inside `async with conn.transaction():`. Locks the offer row
    (SELECT ... FOR UPDATE) before reading the latest revision, same pattern
    as cancel_offer — otherwise a counter-offer can insert a new revision
    between this function's read and its guarded UPDATE, and the accept
    proceeds against terms that were superseded before it landed."""
    locked = await conn.fetchrow(
        "SELECT status FROM cappe_collab_offers WHERE id=$1 FOR UPDATE", offer_row["id"]
    )
    if locked is None or locked["status"] not in PRE_ACCEPT_STATUSES:
        raise HTTPException(status_code=409, detail="Offer is not open for acceptance")

    rev = await latest_revision(conn, offer_row["id"])
    if rev is None or rev["proposed_by"] == side:
        raise HTTPException(
            status_code=409, detail="You proposed the latest terms — the other side must accept"
        )

    terms_raw = rev["terms"]
    terms = CollabTerms.model_validate(json.loads(terms_raw) if isinstance(terms_raw, str) else terms_raw)

    if terms.compensation_cents > 0:
        if not offer_row["creator_stripe_account_id"] or not offer_row["creator_charges_enabled"]:
            raise HTTPException(
                status_code=409,
                detail={"code": "payouts_not_ready",
                        "message": "Creator must finish Stripe payout setup before accepting"},
            )

    updated = await conn.fetchrow(
        """UPDATE cappe_collab_offers
              SET status='accepted', accepted_revision_id=$2, payment_schedule=$3,
                  total_cents=$4, accepted_at=NOW(), last_action_at=NOW(), updated_at=NOW()
            WHERE id=$1 AND status = ANY($5)
        RETURNING id""",
        offer_row["id"], rev["id"], terms.payment_schedule, terms.compensation_cents,
        list(PRE_ACCEPT_STATUSES),
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="Offer is not open for acceptance")

    deliverable_rows = expand_deliverables(terms)
    deliverable_ids: dict[int, UUID] = {}
    for d in deliverable_rows:
        did = await conn.fetchval(
            """INSERT INTO cappe_collab_deliverables (offer_id, idx, type, platform, spec, due_date)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
            offer_row["id"], d["idx"], d["type"], d["platform"], d["spec"], d["due_date"],
        )
        deliverable_ids[d["idx"]] = did

    has_on_accept_due = False
    if terms.compensation_cents > 0:
        payment_rows = build_payment_rows(terms, len(deliverable_rows))
        for p in payment_rows:
            deliverable_id = deliverable_ids.get(p["deliverable_idx"]) if p["deliverable_idx"] is not None else None
            is_due_now = p["trigger"] == "on_accept"
            has_on_accept_due = has_on_accept_due or is_due_now
            await conn.execute(
                """INSERT INTO cappe_collab_payments
                       (offer_id, idx, label, amount_cents, trigger, deliverable_id, status, due_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                offer_row["id"], p["idx"], p["label"], p["amount_cents"], p["trigger"],
                deliverable_id, "due" if is_due_now else "scheduled",
                datetime.utcnow() if is_due_now else None,
            )

    if not has_on_accept_due:
        # Gifting collab (no payment rows) or a per_deliverable schedule
        # (nothing due until the first approval): nothing blocks work
        # starting, so go straight to active ("underway") instead of
        # waiting on a webhook that will never fire an on_accept payment.
        await conn.execute(
            "UPDATE cappe_collab_offers SET status='active', updated_at=NOW() WHERE id=$1",
            offer_row["id"],
        )


# ── Payment firing ─────────────────────────────────────────────────────────────

async def fire_deliverable_payment(conn, offer_id: UUID, deliverable_id: UUID) -> Optional[UUID]:
    return await conn.fetchval(
        """UPDATE cappe_collab_payments SET status='due', due_at=NOW(), updated_at=NOW()
            WHERE offer_id=$1 AND deliverable_id=$2 AND trigger='on_deliverable' AND status='scheduled'
        RETURNING id""",
        offer_id, deliverable_id,
    )


async def fire_all_approved_payments(conn, offer_id: UUID) -> list[UUID]:
    all_approved = await conn.fetchval(
        "SELECT COUNT(*) FROM cappe_collab_deliverables WHERE offer_id = $1 AND status != 'approved'",
        offer_id,
    )
    if all_approved:
        return []
    rows = await conn.fetch(
        """UPDATE cappe_collab_payments SET status='due', due_at=NOW(), updated_at=NOW()
            WHERE offer_id=$1 AND trigger='on_all_approved' AND status='scheduled'
        RETURNING id""",
        offer_id,
    )
    return [r["id"] for r in rows]


async def check_completion(conn, offer_id: UUID) -> bool:
    row = await conn.fetchrow(
        """SELECT
             (SELECT COUNT(*) FROM cappe_collab_deliverables
               WHERE offer_id = $1 AND status != 'approved') = 0
             AND (SELECT COUNT(*) FROM cappe_collab_payments
               WHERE offer_id = $1 AND status NOT IN ('paid', 'cancelled')) = 0
             AS done""",
        offer_id,
    )
    if not row or not row["done"]:
        return False
    updated = await conn.fetchval(
        """UPDATE cappe_collab_offers
              SET status='completed', completed_at=NOW(), last_action_at=NOW(), updated_at=NOW()
            WHERE id=$1 AND status='active'
        RETURNING id""",
        offer_id,
    )
    return updated is not None


# ── Auto-approve on brand silence (creator-first protection C) ──────────────────

async def auto_approve_overdue(conn, offer_id: UUID) -> dict:
    """For an active offer, auto-approve any deliverable submitted more than
    N days ago and still awaiting brand review. Evaluated lazily at read time
    (top of _offer_detail / offer-list fetch) — no new worker infra; the
    creator opening their deal is the trigger. Fires the same payment +
    completion chain as a manual approve.

    Runs as one transaction so a failure between the deliverable UPDATE and
    firing its payment can't strand it in 'scheduled' forever — auto-approve
    only ever re-scans 'submitted' rows, so a half-applied approve is
    otherwise unrecoverable.

    Returns {"deliverables": [{id,label}], "fired_payments": [{id,label,amount_cents}],
    "completed": bool} so the caller can email the brand (payment due) and the
    creator (approved notice) — auto-approve must not fire payments silently."""
    offer = await conn.fetchrow("SELECT status FROM cappe_collab_offers WHERE id = $1", offer_id)
    if offer is None or offer["status"] != "active":
        return {"deliverables": [], "fired_payments": [], "completed": False}

    days = max(1, await resolve_auto_approve_days(conn))
    async with conn.transaction():
        rows = await conn.fetch(
            """UPDATE cappe_collab_deliverables
                  SET status='approved', approved_at=NOW(), updated_at=NOW(),
                      review_note=COALESCE(review_note || E'\n', '')
                          || 'Auto-approved after ' || $2::text || ' days without brand review'
                WHERE offer_id=$1 AND status='submitted'
                  AND submitted_at < NOW() - make_interval(days => $2)
            RETURNING id, type, idx""",
            offer_id, days,
        )
        approved = [{"id": r["id"], "label": f"{r['type']} #{r['idx'] + 1}"} for r in rows]

        fired_ids: list[UUID] = []
        for d in approved:
            fired = await fire_deliverable_payment(conn, offer_id, d["id"])
            if fired:
                fired_ids.append(fired)
        fired_ids.extend(await fire_all_approved_payments(conn, offer_id))

        fired_payments = []
        if fired_ids:
            pay_rows = await conn.fetch(
                "SELECT id, label, amount_cents FROM cappe_collab_payments WHERE id = ANY($1)", fired_ids
            )
            fired_payments = [{"id": p["id"], "label": p["label"], "amount_cents": p["amount_cents"]} for p in pay_rows]

        completed = await check_completion(conn, offer_id)

    return {"deliverables": approved, "fired_payments": fired_payments, "completed": completed}


# ── Cancel asymmetry (creator-first protection B) ────────────────────────────

async def cancel_offer(conn, offer_row, side: str, reason: str) -> None:
    """Brand owes for approved work; creator forfeits unearned installments.

    Call inside `async with conn.transaction():` — locks the offer row
    (SELECT ... FOR UPDATE) and branches on the status observed under that
    lock, not the caller's pre-read `offer_row`, so a webhook flipping
    accepted -> active between the caller's read and this call can't put a
    cancel through the wrong (more destructive) branch.

    - cancelled_by='creator': every unpaid payment (scheduled/due/processing)
      cancels — the creator is walking away, forfeits unearned installments.
    - cancelled_by='brand', offer was 'active' (work started): 'due'/
      'processing' rows SURVIVE — due-ness fires on approval events, so
      due == earned; only 'scheduled' rows cancel. Any deliverable already
      'submitted' (delivered, not yet reviewed) is also treated as earned —
      it's approved and its payment fired to 'due' before the scheduled rows
      are cancelled, so the creator isn't left uncompensated for work sitting
      in the brand's queue at cancel time regardless of the auto-approve
      window.
    - cancelled_by='brand', offer was 'accepted' (never funded, no work
      possible): everything unpaid cancels, same as a creator cancel.
    """
    locked = await conn.fetchrow(
        "SELECT status FROM cappe_collab_offers WHERE id=$1 FOR UPDATE", offer_row["id"]
    )
    if locked is None or locked["status"] not in ("accepted", "active"):
        raise HTTPException(status_code=409, detail="Offer cannot be cancelled from its current status")
    current_status = locked["status"]

    if side == "brand" and current_status == "active":
        submitted = await conn.fetch(
            "SELECT id FROM cappe_collab_deliverables WHERE offer_id=$1 AND status='submitted'",
            offer_row["id"],
        )
        for d in submitted:
            approved = await conn.fetchval(
                "UPDATE cappe_collab_deliverables SET status='approved', approved_at=NOW(), updated_at=NOW(), "
                "review_note=COALESCE(review_note || E'\n', '') || 'Approved at brand cancellation' "
                "WHERE id=$1 AND status='submitted' RETURNING id",
                d["id"],
            )
            if approved is not None:
                await fire_deliverable_payment(conn, offer_row["id"], d["id"])
        await fire_all_approved_payments(conn, offer_row["id"])

    updated = await conn.fetchval(
        """UPDATE cappe_collab_offers
              SET status='cancelled', cancelled_at=NOW(), cancelled_by=$2, cancel_reason=$3,
                  last_action_at=NOW(), updated_at=NOW()
            WHERE id=$1 AND status IN ('accepted', 'active')
        RETURNING id""",
        offer_row["id"], side, reason,
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="Offer cannot be cancelled from its current status")

    if side == "creator" or current_status == "accepted":
        cancel_statuses = ["scheduled", "due", "processing"]
    else:
        # brand cancel of an active (work-started) offer: due/processing survive
        cancel_statuses = ["scheduled"]

    await conn.execute(
        "UPDATE cappe_collab_payments SET status='cancelled', updated_at=NOW() "
        "WHERE offer_id=$1 AND status = ANY($2)",
        offer_row["id"], cancel_statuses,
    )
    # Paid installments stay 'paid' — milestone money is earned; refunds are
    # a manual admin action in Stripe, out of scope.


async def touch(conn, offer_id: UUID) -> None:
    await conn.execute(
        "UPDATE cappe_collab_offers SET last_action_at=NOW(), updated_at=NOW() WHERE id=$1",
        offer_id,
    )


# ── Deal Check — deterministic creator-side deal review (protection D) ───────
# No LLM: mirrors the discipline module's deterministic-gate philosophy.
# Computed server-side, surfaced ONLY on the creator's side of OfferDetail —
# a brand never receives the creator's private analysis of its own offer.

_EXCLUSIVITY_MIN_PER_MONTH_CENTS = 25_000  # $250/mo floor before "low pay" fires
_HEAVY_SCOPE_DELIVERABLE_COUNT = 5
_HEAVY_SCOPE_PER_DELIVERABLE_CENTS = 10_000  # $100/deliverable floor
_TIGHT_DEADLINE_DAYS = 7
_HIGH_REVISION_ROUNDS = 3


def analyze_terms_for_creator(
    terms: CollabTerms,
    rate_rows: list[dict],
    brand_stats: dict,
    now: datetime,
) -> list[DealCheckItem]:
    """Pure function — no I/O. `rate_rows` are the creator's own rate-card
    rows (deliverable_type, platform, price_cents); `brand_stats` has
    `completed_collabs` (int)."""
    items: list[DealCheckItem] = []

    # rate_below_card — sum the creator's card price for matching type+platform
    # deliverables and compare to what's offered.
    card_total = 0
    matched_all = True
    for d in terms.deliverables:
        match = next(
            (r for r in rate_rows if r["deliverable_type"] == d.type and r["platform"] == d.platform),
            None,
        )
        if match is None:
            matched_all = False
            continue
        card_total += match["price_cents"] * d.quantity
    if card_total > 0:
        if terms.compensation_cents < card_total:
            severity = "caution" if not matched_all else "warning"
            detail = (
                f"Your rate card puts this scope at ${card_total / 100:,.0f}"
                + ("" if matched_all else " (partial estimate — some deliverable types have no card rate)")
                + f", the offer is ${terms.compensation_cents / 100:,.0f}."
            )
            items.append(DealCheckItem(
                key="rate_below_card", severity=severity,
                title="Below your rate card", detail=detail,
            ))

    # paid_usage_long
    if terms.usage_rights.scope == "paid" and terms.usage_rights.duration_months:
        m = terms.usage_rights.duration_months
        if m > 12:
            items.append(DealCheckItem(
                key="paid_usage_long", severity="warning",
                title="Long paid usage term",
                detail=f"Brand keeps paid usage rights for {m} months.",
            ))
        elif m >= 6:
            items.append(DealCheckItem(
                key="paid_usage_long", severity="caution",
                title="Extended paid usage term",
                detail=f"Brand keeps paid usage rights for {m} months.",
            ))

    # whitelisting_unpriced
    if terms.usage_rights.whitelisting:
        items.append(DealCheckItem(
            key="whitelisting_unpriced", severity="caution",
            title="Whitelisting requested",
            detail="Running ads from your handle is typically priced 30-100% above the base rate — make sure that's reflected in compensation.",
        ))

    # exclusivity_low_pay
    if terms.exclusivity is not None:
        per_month = terms.compensation_cents / terms.exclusivity.duration_months
        if per_month < _EXCLUSIVITY_MIN_PER_MONTH_CENTS:
            items.append(DealCheckItem(
                key="exclusivity_low_pay", severity="warning",
                title="Exclusivity pay is thin",
                detail=f"${per_month / 100:,.0f}/mo for a {terms.exclusivity.duration_months}-month "
                       f"{terms.exclusivity.category} lockout.",
            ))

    # high_revision_rounds
    if terms.revision_rounds >= _HIGH_REVISION_ROUNDS:
        items.append(DealCheckItem(
            key="high_revision_rounds", severity="caution",
            title="High revision count",
            detail=f"Up to {terms.revision_rounds} revision rounds per deliverable.",
        ))

    # tight_deadlines
    tight = [d for d in terms.deliverables if d.due_date and (d.due_date - now.date()).days < _TIGHT_DEADLINE_DAYS]
    if tight:
        items.append(DealCheckItem(
            key="tight_deadlines", severity="caution",
            title="Tight deadline(s)",
            detail=f"{len(tight)} deliverable(s) due in under {_TIGHT_DEADLINE_DAYS} days.",
        ))

    # no_upfront_money
    if terms.payment_schedule == "per_deliverable":
        items.append(DealCheckItem(
            key="no_upfront_money", severity="caution",
            title="Nothing upfront",
            detail="Payment starts only after your first approval — consider countering 50/50 or upfront.",
        ))

    # heavy_scope_low_total
    if terms.deliverable_count >= _HEAVY_SCOPE_DELIVERABLE_COUNT:
        per_deliverable = terms.compensation_cents / terms.deliverable_count
        if per_deliverable < _HEAVY_SCOPE_PER_DELIVERABLE_CENTS:
            items.append(DealCheckItem(
                key="heavy_scope_low_total", severity="warning",
                title="Heavy scope, low total",
                detail=f"{terms.deliverable_count} deliverables at ${per_deliverable / 100:,.0f} each.",
            ))

    # new_brand
    if brand_stats.get("completed_collabs", 0) == 0:
        items.append(DealCheckItem(
            key="new_brand", severity="caution",
            title="New brand",
            detail="This brand has no completed collabs on Gummfit yet.",
        ))

    # payments_protected — always shown
    items.append(DealCheckItem(
        key="payments_protected", severity="good",
        title="Payments are protected",
        detail="All payments run through Gummfit checkout and terms lock the moment you accept.",
    ))

    return items
