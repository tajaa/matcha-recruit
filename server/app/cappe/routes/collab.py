"""Cappe collabs — brand<->creator offers: negotiation (immutable terms revisions),
chat, deliverables, installment payments via Stripe Connect direct charges.
State machine + money logic live in services/collab.py; routes stay thin."""

import json
import logging
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount
from ..models.collab import (
    BrandStats,
    Campaign,
    CampaignPatch,
    CampaignUpsert,
    DeliverableOut,
    DeliverableRevision,
    DeliverableSubmit,
    OfferCancel,
    OfferCounter,
    OfferCreate,
    OfferDecline,
    OfferDetail,
    OfferListItem,
    OfferMessageCreate,
    OfferMessageOut,
    OfferPage,
    OfferRevisionOut,
    PaymentOut,
)
from ..services import collab as svc
from ..services.common import loads
from ..services.email import (
    dashboard_url,
    send_cappe_collab_completed_email,
    send_cappe_collab_message_email,
    send_cappe_collab_payment_due_email,
    send_cappe_collab_payment_nudge_email,
    send_cappe_deliverable_decision_email,
    send_cappe_deliverable_submitted_email,
    send_cappe_offer_accepted_email,
    send_cappe_offer_closed_email,
    send_cappe_offer_counter_email,
    send_cappe_offer_received_email,
)
from ..services.stripe_connect import CappeStripeError, get_cappe_stripe

logger = logging.getLogger("cappe.collab.routes")

router = APIRouter()


async def _write_rate_limit(account_id: UUID) -> None:
    await check_rate_limit(str(account_id), "cappe_collab_write", 60, 3600)


async def _recipient_send_ok(email: str) -> bool:
    try:
        await check_rate_limit(email.lower(), "cappe_collab_msg_to", 20, 3600)
        return True
    except HTTPException:
        return False


async def _brand_stats(conn, brand_account_id: UUID) -> BrandStats:
    row = await conn.fetchrow(
        """SELECT
             COUNT(DISTINCT o.id) FILTER (WHERE o.status = 'completed') AS completed_collabs,
             COUNT(DISTINCT o.id) FILTER (WHERE o.status = 'cancelled' AND o.cancelled_by = 'brand') AS brand_cancelled,
             COUNT(DISTINCT o.id) FILTER (WHERE o.status = 'active') AS in_progress,
             AVG(EXTRACT(EPOCH FROM (p.paid_at - p.due_at)) / 3600.0)
                 FILTER (WHERE p.paid_at IS NOT NULL AND p.due_at IS NOT NULL) AS avg_hours_to_pay
           FROM cappe_collab_offers o
           LEFT JOIN cappe_collab_payments p ON p.offer_id = o.id
          WHERE o.brand_account_id = $1""",
        brand_account_id,
    )
    return BrandStats(
        completed_collabs=row["completed_collabs"] or 0,
        brand_cancelled=row["brand_cancelled"] or 0,
        in_progress=row["in_progress"] or 0,
        avg_hours_to_pay=float(row["avg_hours_to_pay"])
        if row["avg_hours_to_pay"] is not None
        else None,
    )


async def _notify_auto_approve(conn, offer_id: UUID, offer_row, result: dict) -> None:
    await svc.notify_auto_approve(conn, offer_id, offer_row, result)


async def _notify_auto_approve_bg(offer_row: dict, result: dict) -> None:
    """BackgroundTasks entrypoint for _notify_auto_approve — opens its own
    connection since the request-scoped one is already released back to the
    pool by the time background tasks run (list_offers can auto-approve
    across several offers per request)."""
    offer_id = offer_row["id"]
    async with get_connection() as conn:
        await _notify_auto_approve(conn, offer_id, offer_row, result)


async def _offer_detail(conn, offer_id: UUID, account_id: UUID) -> OfferDetail:
    offer_row, side = await svc.get_offer_side(conn, offer_id, account_id)

    if offer_row["status"] == "active":
        result = await svc.auto_approve_overdue(conn, offer_id)
        await _notify_auto_approve(conn, offer_id, offer_row, result)
        offer_row, side = await svc.get_offer_side(conn, offer_id, account_id)

    revision_rows = await conn.fetch(
        "SELECT * FROM cappe_collab_offer_revisions WHERE offer_id = $1 ORDER BY revision_no",
        offer_id,
    )
    message_rows = await conn.fetch(
        "SELECT * FROM cappe_collab_messages WHERE offer_id = $1 ORDER BY created_at",
        offer_id,
    )
    deliverable_rows = await conn.fetch(
        "SELECT * FROM cappe_collab_deliverables WHERE offer_id = $1 ORDER BY idx",
        offer_id,
    )
    payment_rows = await conn.fetch(
        "SELECT * FROM cappe_collab_payments WHERE offer_id = $1 ORDER BY idx", offer_id
    )

    revisions = [
        OfferRevisionOut(
            id=r["id"],
            revision_no=r["revision_no"],
            proposed_by=r["proposed_by"],
            terms=loads(r["terms"]),
            message=r["message"],
            created_at=r["created_at"],
        )
        for r in revision_rows
    ]

    deal_check = None
    brand_stats = None
    if side == "creator" and revisions:
        # Once accepted, the terms in force are the accepted revision, not
        # necessarily revisions[-1] — see svc.accepted_revision.
        relevant = (
            next(
                (r for r in revisions if r.id == offer_row["accepted_revision_id"]),
                None,
            )
            if offer_row["accepted_revision_id"]
            else None
        )
        if relevant is None:
            relevant = revisions[-1]
        rate_rows = await conn.fetch(
            "SELECT deliverable_type, platform, price_cents FROM cappe_creator_rate_cards WHERE profile_id = $1",
            offer_row["creator_profile_id"],
        )
        b_stats = await _brand_stats(conn, offer_row["brand_account_id"])
        deal_check = svc.analyze_terms_for_creator(
            relevant.terms,
            [dict(r) for r in rate_rows],
            {"completed_collabs": b_stats.completed_collabs},
            datetime.now(timezone.utc),
        )
        brand_stats = b_stats

    auto_approve_days = await svc.resolve_auto_approve_days(conn)

    return OfferDetail(
        id=offer_row["id"],
        title=offer_row["title"],
        status=offer_row["status"],
        payment_schedule=offer_row["payment_schedule"],
        total_cents=offer_row["total_cents"],
        currency=offer_row["currency"],
        campaign_id=offer_row["campaign_id"],
        brand_name=offer_row["brand_name"],
        creator_handle=offer_row["creator_handle"],
        creator_display_name=offer_row["creator_display_name"],
        creator_avatar_url=offer_row["creator_avatar_url"],
        last_action_at=offer_row["last_action_at"],
        created_at=offer_row["created_at"],
        side=side,
        accepted_revision_id=offer_row["accepted_revision_id"],
        declined_reason=offer_row["declined_reason"],
        cancelled_by=offer_row["cancelled_by"],
        cancel_reason=offer_row["cancel_reason"],
        revisions=revisions,
        messages=[OfferMessageOut(**dict(m)) for m in message_rows],
        deliverables=[DeliverableOut(**dict(d)) for d in deliverable_rows],
        payments=[PaymentOut(**dict(p)) for p in payment_rows],
        creator_payouts_ready=bool(
            offer_row["creator_stripe_account_id"]
            and offer_row["creator_charges_enabled"]
        ),
        deal_check=deal_check,
        brand_stats=brand_stats,
        auto_approve_days=auto_approve_days,
    )


# ── Campaigns (brand-only) ────────────────────────────────────────────────────


def _require_business(account: CappeAccount) -> None:
    if account.account_type != "business":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Business account required"
        )


@router.get("/collab/campaigns", response_model=list[Campaign])
async def list_campaigns(account: CappeAccount = Depends(require_cappe_account)):
    _require_business(account)
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT c.*, (SELECT COUNT(*) FROM cappe_collab_offers o WHERE o.campaign_id = c.id) AS offer_count "
            "FROM cappe_collab_campaigns c WHERE brand_account_id = $1 ORDER BY created_at DESC",
            account.id,
        )
        return [Campaign(**dict(r)) for r in rows]


@router.post(
    "/collab/campaigns", status_code=status.HTTP_201_CREATED, response_model=Campaign
)
async def create_campaign(
    body: CampaignUpsert, account: CappeAccount = Depends(require_cappe_account)
):
    _require_business(account)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "INSERT INTO cappe_collab_campaigns (brand_account_id, title, description, budget_min_cents, "
            "budget_max_cents, deliverable_notes) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *, 0 AS offer_count",
            account.id,
            body.title,
            body.description,
            body.budget_min_cents,
            body.budget_max_cents,
            body.deliverable_notes,
        )
        return Campaign(**dict(row))


@router.patch("/collab/campaigns/{campaign_id}", response_model=Campaign)
async def update_campaign(
    campaign_id: UUID,
    body: CampaignPatch,
    account: CappeAccount = Depends(require_cappe_account),
):
    _require_business(account)
    fields = body.model_fields_set
    sets, args = [], []
    for col in (
        "title",
        "description",
        "budget_min_cents",
        "budget_max_cents",
        "deliverable_notes",
        "status",
    ):
        if col in fields:
            args.append(getattr(body, col))
            sets.append(f"{col} = ${len(args)}")
    if not sets:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields to update",
        )
    sets.append("updated_at = NOW()")
    args.extend([campaign_id, account.id])
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"UPDATE cappe_collab_campaigns SET {', '.join(sets)} "
            f"WHERE id = ${len(args) - 1} AND brand_account_id = ${len(args)} "
            f"RETURNING *, (SELECT COUNT(*) FROM cappe_collab_offers o WHERE o.campaign_id = cappe_collab_campaigns.id) AS offer_count",
            *args,
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found"
            )
        return Campaign(**dict(row))


# ── Offers ───────────────────────────────────────────────────────────────────


@router.post(
    "/collab/offers", status_code=status.HTTP_201_CREATED, response_model=OfferDetail
)
async def create_offer(
    body: OfferCreate,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    _require_business(account)
    await _write_rate_limit(account.id)
    async with get_connection() as conn:
        target = await conn.fetchrow(
            "SELECT id, status, open_to_offers, account_id FROM cappe_creator_profiles WHERE id = $1",
            body.creator_profile_id,
        )
        if (
            target is None
            or target["status"] != "published"
            or not target["open_to_offers"]
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This creator is not accepting offers",
            )
        if target["account_id"] == account.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="You can't send an offer to yourself",
            )
        if body.campaign_id is not None:
            owns = await conn.fetchval(
                "SELECT 1 FROM cappe_collab_campaigns WHERE id = $1 AND brand_account_id = $2",
                body.campaign_id,
                account.id,
            )
            if not owns:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found"
                )

        min_cents = await svc.resolve_min_offer_cents(conn)
        if 0 < body.terms.compensation_cents < min_cents:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Minimum offer is ${min_cents / 100:.0f}",
            )

        async with conn.transaction():
            offer_id = await conn.fetchval(
                "INSERT INTO cappe_collab_offers (campaign_id, brand_account_id, creator_profile_id, title) "
                "VALUES ($1,$2,$3,$4) RETURNING id",
                body.campaign_id,
                account.id,
                body.creator_profile_id,
                body.title,
            )
            await conn.execute(
                "INSERT INTO cappe_collab_offer_revisions (offer_id, revision_no, proposed_by, terms, message) "
                "VALUES ($1, 1, 'brand', $2::jsonb, $3)",
                offer_id,
                json.dumps(body.terms.model_dump(mode="json")),
                body.message,
            )
            if body.message:
                await conn.execute(
                    "INSERT INTO cappe_collab_messages (offer_id, sender, sender_account_id, body) "
                    "VALUES ($1, 'brand', $2, $3)",
                    offer_id,
                    account.id,
                    body.message,
                )

        creator_contact = await conn.fetchrow(
            "SELECT ca.email, ca.name FROM cappe_creator_profiles p JOIN cappe_accounts ca ON ca.id = p.account_id "
            "WHERE p.id = $1",
            body.creator_profile_id,
        )
        background.add_task(
            send_cappe_offer_received_email,
            creator_contact["email"],
            creator_contact["name"],
            account.name or account.email,
            body.title,
            dashboard_url(f"/creator/deals/{offer_id}"),
        )
        return await _offer_detail(conn, offer_id, account.id)


@router.get("/collab/offers", response_model=OfferPage)
async def list_offers(
    side: Literal["brand", "creator"] = Query(...),
    status_csv: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=2000),
    account: CappeAccount = Depends(require_cappe_account),
):
    statuses = [s.strip() for s in status_csv.split(",")] if status_csv else None
    async with get_connection() as conn:
        if side == "brand":
            _require_business(account)
            rows = await conn.fetch(
                """SELECT o.id, o.title, o.status, o.payment_schedule, o.total_cents, o.currency,
                          o.campaign_id, ba.name AS brand_name, p.handle AS creator_handle,
                          p.display_name AS creator_display_name, p.avatar_url AS creator_avatar_url,
                          o.last_action_at, o.created_at, COUNT(*) OVER() AS total
                     FROM cappe_collab_offers o
                     JOIN cappe_creator_profiles p ON p.id = o.creator_profile_id
                     JOIN cappe_accounts ba ON ba.id = o.brand_account_id
                    WHERE o.brand_account_id = $1
                      AND ($2::text[] IS NULL OR o.status = ANY($2))
                    ORDER BY o.last_action_at DESC LIMIT $3 OFFSET $4""",
                account.id,
                statuses,
                limit,
                offset,
            )
        else:
            if account.account_type != "creator":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Creator account required",
                )
            rows = await conn.fetch(
                """SELECT o.id, o.title, o.status, o.payment_schedule, o.total_cents, o.currency,
                          o.campaign_id, ba.name AS brand_name, p.handle AS creator_handle,
                          p.display_name AS creator_display_name, p.avatar_url AS creator_avatar_url,
                          o.last_action_at, o.created_at, COUNT(*) OVER() AS total
                     FROM cappe_collab_offers o
                     JOIN cappe_creator_profiles p ON p.id = o.creator_profile_id
                     JOIN cappe_accounts ba ON ba.id = o.brand_account_id
                    WHERE p.account_id = $1
                      AND ($2::text[] IS NULL OR o.status = ANY($2))
                    ORDER BY o.last_action_at DESC LIMIT $3 OFFSET $4""",
                account.id,
                statuses,
                limit,
                offset,
            )

        total = rows[0]["total"] if rows else 0
        row_dicts = [dict(r) for r in rows]

        items = []
        for d in row_dicts:
            d.pop("total", None)
            items.append(OfferListItem(**d))
        return OfferPage(offers=items, total=total)


@router.get("/collab/offers/{offer_id}", response_model=OfferDetail)
async def get_offer(
    offer_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        return await _offer_detail(conn, offer_id, account.id)


@router.post("/collab/offers/{offer_id}/counter", response_model=OfferDetail)
async def counter_offer(
    offer_id: UUID,
    body: OfferCounter,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    await _write_rate_limit(account.id)
    async with get_connection() as conn:
        offer_row, side = await svc.get_offer_side(conn, offer_id, account.id)
        if offer_row["status"] not in svc.PRE_ACCEPT_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Offer is no longer negotiable",
            )

        min_cents = await svc.resolve_min_offer_cents(conn)
        if 0 < body.terms.compensation_cents < min_cents:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Minimum offer is ${min_cents / 100:.0f}",
            )

        async with conn.transaction():
            # Lock + recheck under the transaction — the pre-read above can't
            # see a concurrent accept_offer that grabs FOR UPDATE first; that
            # accept commits, our lock acquires next, and the recheck stops
            # us inserting a revision the accept already closed the door on.
            locked = await conn.fetchrow(
                "SELECT status FROM cappe_collab_offers WHERE id=$1 FOR UPDATE",
                offer_id,
            )
            if locked is None or locked["status"] not in svc.PRE_ACCEPT_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Offer is no longer negotiable",
                )
            rev_no = await conn.fetchval(
                "SELECT COALESCE(MAX(revision_no), 0) + 1 FROM cappe_collab_offer_revisions WHERE offer_id = $1",
                offer_id,
            )
            rev_id = await conn.fetchval(
                "INSERT INTO cappe_collab_offer_revisions (offer_id, revision_no, proposed_by, terms, message) "
                "VALUES ($1,$2,$3,$4::jsonb,$5) RETURNING id",
                offer_id,
                rev_no,
                side,
                json.dumps(body.terms.model_dump(mode="json")),
                body.message,
            )
            await conn.execute(
                "UPDATE cappe_collab_offers SET status='negotiating', last_action_at=NOW(), updated_at=NOW() "
                "WHERE id=$1",
                offer_id,
            )
            if body.message:
                await conn.execute(
                    "INSERT INTO cappe_collab_messages (offer_id, sender, sender_account_id, body, revision_id) "
                    "VALUES ($1,$2,$3,$4,$5)",
                    offer_id,
                    side,
                    account.id,
                    body.message,
                    rev_id,
                )

        counterpart_email, counterpart_name = await _resolve_contact(
            conn, offer_row, side
        )
        background.add_task(
            send_cappe_offer_counter_email,
            counterpart_email,
            counterpart_name,
            account.name or account.email,
            offer_row["title"],
            dashboard_url(
                f"/{'creator/deals' if side == 'brand' else 'collabs'}/{offer_id}"
            ),
        )
        return await _offer_detail(conn, offer_id, account.id)


async def _resolve_contact(conn, offer_row, side: str) -> tuple[str, Optional[str]]:
    return await svc.resolve_contact(conn, offer_row, side)


@router.post("/collab/offers/{offer_id}/accept", response_model=OfferDetail)
async def accept_offer_route(
    offer_id: UUID,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        offer_row, side = await svc.get_offer_side(conn, offer_id, account.id)
        async with conn.transaction():
            await svc.accept_offer(conn, offer_row, side)

        detail = await _offer_detail(conn, offer_id, account.id)
        funding_due = any(
            p.trigger == "on_accept" and p.status == "due" for p in detail.payments
        )

        brand_email, brand_name = await _resolve_contact(conn, offer_row, "creator")
        creator_email, creator_name = await _resolve_contact(conn, offer_row, "brand")
        background.add_task(
            send_cappe_offer_accepted_email,
            brand_email,
            brand_name,
            offer_row["title"],
            dashboard_url(f"/collabs/{offer_id}"),
            funding_due=funding_due,
        )
        background.add_task(
            send_cappe_offer_accepted_email,
            creator_email,
            creator_name,
            offer_row["title"],
            dashboard_url(f"/creator/deals/{offer_id}"),
            funding_due=False,
        )
        return detail


@router.post("/collab/offers/{offer_id}/decline", response_model=OfferDetail)
async def decline_offer(
    offer_id: UUID,
    body: OfferDecline,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        offer_row, side = await svc.get_offer_side(conn, offer_id, account.id)
        if side != "creator":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the creator can decline",
            )
        if offer_row["status"] not in svc.PRE_ACCEPT_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Offer can no longer be declined",
            )
        updated = await conn.fetchval(
            "UPDATE cappe_collab_offers SET status='declined', declined_at=NOW(), declined_reason=$2, "
            "last_action_at=NOW(), updated_at=NOW() WHERE id=$1 AND status = ANY($3) RETURNING id",
            offer_id,
            body.reason,
            list(svc.PRE_ACCEPT_STATUSES),
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Offer can no longer be declined",
            )
        email, name = await _resolve_contact(conn, offer_row, "creator")
        background.add_task(
            send_cappe_offer_closed_email,
            email,
            name,
            offer_row["title"],
            "declined",
            body.reason,
            dashboard_url(f"/collabs/{offer_id}"),
        )
        return await _offer_detail(conn, offer_id, account.id)


@router.post("/collab/offers/{offer_id}/withdraw", response_model=OfferDetail)
async def withdraw_offer(
    offer_id: UUID,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        offer_row, side = await svc.get_offer_side(conn, offer_id, account.id)
        if side != "brand":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the brand can withdraw",
            )
        if offer_row["status"] not in svc.PRE_ACCEPT_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Offer can no longer be withdrawn",
            )
        updated = await conn.fetchval(
            "UPDATE cappe_collab_offers SET status='withdrawn', last_action_at=NOW(), updated_at=NOW() "
            "WHERE id=$1 AND status = ANY($2) RETURNING id",
            offer_id,
            list(svc.PRE_ACCEPT_STATUSES),
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Offer can no longer be withdrawn",
            )
        email, name = await _resolve_contact(conn, offer_row, "brand")
        background.add_task(
            send_cappe_offer_closed_email,
            email,
            name,
            offer_row["title"],
            "withdrawn",
            None,
            dashboard_url(f"/creator/deals/{offer_id}"),
        )
        return await _offer_detail(conn, offer_id, account.id)


@router.post("/collab/offers/{offer_id}/cancel", response_model=OfferDetail)
async def cancel_offer_route(
    offer_id: UUID,
    body: OfferCancel,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        offer_row, side = await svc.get_offer_side(conn, offer_id, account.id)
        async with conn.transaction():
            await svc.cancel_offer(conn, offer_row, side, body.reason)
        email, name = await _resolve_contact(conn, offer_row, side)
        link = dashboard_url(
            f"/{'creator/deals' if side == 'brand' else 'collabs'}/{offer_id}"
        )
        background.add_task(
            send_cappe_offer_closed_email,
            email,
            name,
            offer_row["title"],
            "cancelled",
            body.reason,
            link,
        )
        return await _offer_detail(conn, offer_id, account.id)


@router.post(
    "/collab/offers/{offer_id}/messages",
    status_code=status.HTTP_201_CREATED,
    response_model=OfferMessageOut,
)
async def send_message(
    offer_id: UUID,
    body: OfferMessageCreate,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    await _write_rate_limit(account.id)
    async with get_connection() as conn:
        offer_row, side = await svc.get_offer_side(conn, offer_id, account.id)
        if offer_row["status"] in svc.TERMINAL_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Conversation is closed"
            )
        row = await conn.fetchrow(
            "INSERT INTO cappe_collab_messages (offer_id, sender, sender_account_id, body) "
            "VALUES ($1,$2,$3,$4) RETURNING *",
            offer_id,
            side,
            account.id,
            body.body,
        )
        await svc.touch(conn, offer_id)

        email, name = await _resolve_contact(conn, offer_row, side)
        if await _recipient_send_ok(email):
            link = dashboard_url(
                f"/{'creator/deals' if side == 'brand' else 'collabs'}/{offer_id}"
            )
            background.add_task(
                send_cappe_collab_message_email,
                email,
                name,
                account.name or account.email,
                offer_row["title"],
                body.body,
                link,
            )
        return OfferMessageOut(**dict(row))


# ── Deliverables ─────────────────────────────────────────────────────────────


@router.post(
    "/collab/offers/{offer_id}/deliverables/{deliverable_id}/submit",
    response_model=DeliverableOut,
)
async def submit_deliverable(
    offer_id: UUID,
    deliverable_id: UUID,
    body: DeliverableSubmit,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        offer_row, side = await svc.get_offer_side(conn, offer_id, account.id)
        if side != "creator":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the creator can submit deliverables",
            )
        if offer_row["status"] != "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Offer is not active"
            )
        row = await conn.fetchrow(
            "UPDATE cappe_collab_deliverables SET status='submitted', submission_url=$2, submission_note=$3, "
            "proof_media_url=$4, submitted_at=NOW(), updated_at=NOW() "
            "WHERE id=$1 AND offer_id=$5 AND status IN ('pending','revision_requested') RETURNING *",
            deliverable_id,
            body.submission_url,
            body.submission_note,
            body.proof_media_url,
            offer_id,
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already submitted or approved",
            )
        await svc.touch(conn, offer_id)
        email, name = await _resolve_contact(conn, offer_row, "creator")
        background.add_task(
            send_cappe_deliverable_submitted_email,
            email,
            name,
            offer_row["title"],
            f"{row['type']} #{row['idx'] + 1}",
            dashboard_url(f"/collabs/{offer_id}"),
        )
        return DeliverableOut(**dict(row))


@router.post(
    "/collab/offers/{offer_id}/deliverables/{deliverable_id}/approve",
    response_model=OfferDetail,
)
async def approve_deliverable(
    offer_id: UUID,
    deliverable_id: UUID,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        offer_row, side = await svc.get_offer_side(conn, offer_id, account.id)
        if side != "brand":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the brand can approve deliverables",
            )

        async with conn.transaction():
            row = await conn.fetchrow(
                "UPDATE cappe_collab_deliverables SET status='approved', approved_at=NOW(), updated_at=NOW() "
                "WHERE id=$1 AND offer_id=$2 AND status='submitted' RETURNING *",
                deliverable_id,
                offer_id,
            )
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Deliverable is not submitted",
                )
            fired = await svc.fire_deliverable_payment(conn, offer_id, deliverable_id)
            all_fired = await svc.fire_all_approved_payments(conn, offer_id)
            completed = await svc.check_completion(conn, offer_id)

        creator_email, creator_name = await _resolve_contact(conn, offer_row, "brand")
        brand_email, brand_name = await _resolve_contact(conn, offer_row, "creator")
        label = f"{row['type']} #{row['idx'] + 1}"
        background.add_task(
            send_cappe_deliverable_decision_email,
            creator_email,
            creator_name,
            offer_row["title"],
            label,
            True,
            None,
            dashboard_url(f"/creator/deals/{offer_id}"),
        )

        due_ids = [i for i in [fired] if i] + all_fired
        if due_ids:
            pay_rows = await conn.fetch(
                "SELECT id, label, amount_cents FROM cappe_collab_payments WHERE id = ANY($1)",
                due_ids,
            )
            for p in pay_rows:
                background.add_task(
                    send_cappe_collab_payment_due_email,
                    brand_email,
                    brand_name,
                    offer_row["title"],
                    p["label"],
                    p["amount_cents"],
                    dashboard_url(f"/collabs/{offer_id}"),
                )
        if completed:
            background.add_task(
                send_cappe_collab_completed_email,
                brand_email,
                brand_name,
                offer_row["title"],
                dashboard_url(f"/collabs/{offer_id}"),
            )
            background.add_task(
                send_cappe_collab_completed_email,
                creator_email,
                creator_name,
                offer_row["title"],
                dashboard_url(f"/creator/deals/{offer_id}"),
            )
        return await _offer_detail(conn, offer_id, account.id)


@router.post(
    "/collab/offers/{offer_id}/deliverables/{deliverable_id}/request-revision",
    response_model=DeliverableOut,
)
async def request_deliverable_revision(
    offer_id: UUID,
    deliverable_id: UUID,
    body: DeliverableRevision,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        offer_row, side = await svc.get_offer_side(conn, offer_id, account.id)
        if side != "brand":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the brand can request revisions",
            )

        async with conn.transaction():
            deliverable = await conn.fetchrow(
                "SELECT * FROM cappe_collab_deliverables WHERE id=$1 AND offer_id=$2 FOR UPDATE",
                deliverable_id, offer_id)
            if deliverable is None or deliverable["status"] != "submitted":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deliverable is not submitted")
            rev = await svc.accepted_revision(conn, offer_row)
            terms = svc.CollabTerms.model_validate(loads(rev["terms"])) if rev else None
            revision_rounds = terms.revision_rounds if terms else 1
            if deliverable["revision_count"] >= revision_rounds:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    detail=f"Revision limit reached ({revision_rounds}) — approve or cancel")
            row = await conn.fetchrow(
                "UPDATE cappe_collab_deliverables SET status='revision_requested', review_note=$2, revision_count=revision_count+1, updated_at=NOW() "
                "WHERE id=$1 AND offer_id=$3 AND status='submitted' RETURNING *",
                deliverable_id, body.review_note, offer_id)
            if row is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deliverable is not submitted")
        email, name = await _resolve_contact(conn, offer_row, "brand")
        background.add_task(
            send_cappe_deliverable_decision_email,
            email,
            name,
            offer_row["title"],
            f"{row['type']} #{row['idx'] + 1}",
            False,
            body.review_note,
            dashboard_url(f"/creator/deals/{offer_id}"),
        )
        return DeliverableOut(**dict(row))


# ── Payments ─────────────────────────────────────────────────────────────────


@router.post("/collab/offers/{offer_id}/payments/{payment_id}/checkout")
async def checkout_payment(
    offer_id: UUID,
    payment_id: UUID,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        offer_row, side = await svc.get_offer_side(conn, offer_id, account.id)
        if side != "brand":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Only the brand can pay"
            )
        payment = await conn.fetchrow(
            "SELECT * FROM cappe_collab_payments WHERE id=$1 AND offer_id=$2",
            payment_id,
            offer_id,
        )
        if payment is None or payment["status"] not in ("due", "processing"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Payment is not due"
            )
        if (
            not offer_row["creator_stripe_account_id"]
            or not offer_row["creator_charges_enabled"]
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "payouts_not_ready",
                    "message": "Creator's payout setup isn't ready yet — try again once they finish",
                },
            )
        fee_bps = await svc.resolve_collab_fee_bps(conn)
        fee = max(0, payment["amount_cents"] * fee_bps // 10_000)

    try:
        session = await get_cappe_stripe().create_checkout_session(
            account_id=offer_row["creator_stripe_account_id"],
            currency=payment["currency"],
            line_items=[
                {
                    "price_data": {
                        "currency": payment["currency"],
                        "unit_amount": payment["amount_cents"],
                        "product_data": {
                            "name": f"{offer_row['title']} — {payment['label']}"
                        },
                    },
                    "quantity": 1,
                }
            ],
            application_fee_cents=fee,
            success_url=f"{dashboard_url(f'/collabs/{offer_id}')}?paid=1",
            cancel_url=dashboard_url(f"/collabs/{offer_id}"),
            metadata={
                "collab_payment_id": str(payment_id),
                "offer_id": str(offer_id),
                "platform_fee_cents": str(fee),
            },
            customer_email=account.email,
        )
    except CappeStripeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    async with get_connection() as conn:
        updated = await conn.fetchval(
            "UPDATE cappe_collab_payments SET status='processing', stripe_checkout_session_id=$2, "
            "fee_bps_snapshot=$3, fee_cents=$4, updated_at=NOW() "
            "WHERE id=$1 AND status IN ('due','processing') RETURNING id",
            payment_id,
            session.get("id"),
            fee_bps,
            fee,
        )
    if updated is None:
        logger.warning(
            "cappe collab checkout: payment %s settled during Stripe round-trip",
            payment_id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This payment was already settled",
        )
    return {"url": session.get("url")}


@router.post("/collab/offers/{offer_id}/payments/{payment_id}/nudge")
async def nudge_payment(
    offer_id: UUID,
    payment_id: UUID,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Creator-only reminder to the brand about an overdue installment.
    Rate-limited 1/day per payment — a chase, not a bell you can spam."""
    async with get_connection() as conn:
        offer_row, side = await svc.get_offer_side(conn, offer_id, account.id)
        if side != "creator":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the creator can nudge",
            )
        payment = await conn.fetchrow(
            "SELECT * FROM cappe_collab_payments WHERE id=$1 AND offer_id=$2",
            payment_id,
            offer_id,
        )
        if payment is None or payment["status"] not in ("due", "processing"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Payment is not due"
            )
        await check_rate_limit(f"nudge:{payment_id}", "cappe_collab_nudge", 1, 86400)
        email, name = await _resolve_contact(conn, offer_row, "creator")
        background.add_task(
            send_cappe_collab_payment_nudge_email,
            email,
            name,
            offer_row["title"],
            payment["label"],
            payment["amount_cents"],
            dashboard_url(f"/collabs/{offer_id}"),
        )
    return {"ok": True}
