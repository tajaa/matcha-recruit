"""Cappe newsletter — subscribers + campaigns (owner side).

Public signup/unsubscribe live in public.py. Sending is STUBBED: send marks the
campaign 'sent' and records how many deliverable (subscribed, non-reserved-
domain) recipients it *would* have reached — no email actually goes out.
"""
import asyncpg
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...core.services.email._shared import _is_reserved_test_domain
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeCampaign,
    CappeCampaignCreate,
    CappeCampaignUpdate,
    CappeSubscriber,
    CappeSubscriberCreate,
)
from ._shared import get_owned_site

router = APIRouter()

_SUB_COLS = "id, site_id, email, name, status, source, created_at, unsubscribed_at"
_CAMPAIGN_COLS = (
    "id, site_id, subject, body_html, from_name, status, scheduled_at, "
    "sent_at, recipient_count, created_at, updated_at"
)


# --- Subscribers ------------------------------------------------------------

@router.get("/sites/{site_id}/subscribers", response_model=list[CappeSubscriber])
async def list_subscribers(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_SUB_COLS} FROM cappe_subscribers WHERE site_id = $1 ORDER BY created_at DESC",
            site_id,
        )
    return [dict(r) for r in rows]


@router.post("/sites/{site_id}/subscribers", response_model=CappeSubscriber, status_code=status.HTTP_201_CREATED)
async def add_subscriber(
    site_id: UUID, body: CappeSubscriberCreate, account: CappeAccount = Depends(require_cappe_account)
):
    """Owner-side manual add. Reserved test domains are rejected (bounce guard)."""
    email = str(body.email).strip().lower()
    if _is_reserved_test_domain(email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reserved/test email domains are not allowed")
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        try:
            row = await conn.fetchrow(
                f"""INSERT INTO cappe_subscribers (site_id, email, name, source, status)
                    VALUES ($1, $2, $3, $4, 'subscribed')
                    RETURNING {_SUB_COLS}""",
                site_id, email, body.name, body.source,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already subscribed")
    return dict(row)


@router.delete("/sites/{site_id}/subscribers/{subscriber_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscriber(
    site_id: UUID, subscriber_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        result = await conn.execute(
            "DELETE FROM cappe_subscribers WHERE id = $1 AND site_id = $2", subscriber_id, site_id
        )
    if result.endswith(" 0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")


# --- Campaigns --------------------------------------------------------------

@router.get("/sites/{site_id}/campaigns", response_model=list[CappeCampaign])
async def list_campaigns(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_CAMPAIGN_COLS} FROM cappe_campaigns WHERE site_id = $1 ORDER BY created_at DESC",
            site_id,
        )
    return [dict(r) for r in rows]


@router.post("/sites/{site_id}/campaigns", response_model=CappeCampaign, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    site_id: UUID, body: CappeCampaignCreate, account: CappeAccount = Depends(require_cappe_account)
):
    initial_status = "scheduled" if body.scheduled_at else "draft"
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"""INSERT INTO cappe_campaigns (site_id, subject, body_html, from_name, scheduled_at, status)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING {_CAMPAIGN_COLS}""",
            site_id, body.subject, body.body_html, body.from_name, body.scheduled_at, initial_status,
        )
    return dict(row)


@router.get("/sites/{site_id}/campaigns/{campaign_id}", response_model=CappeCampaign)
async def get_campaign(
    site_id: UUID, campaign_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"SELECT {_CAMPAIGN_COLS} FROM cappe_campaigns WHERE id = $1 AND site_id = $2",
            campaign_id, site_id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return dict(row)


@router.put("/sites/{site_id}/campaigns/{campaign_id}", response_model=CappeCampaign)
async def update_campaign(
    site_id: UUID, campaign_id: UUID, body: CappeCampaignUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        current = await conn.fetchrow(
            "SELECT status FROM cappe_campaigns WHERE id = $1 AND site_id = $2", campaign_id, site_id
        )
        if current is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        if current["status"] in ("sent", "sending"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A sent campaign can't be edited")

        sets, args = [], []
        for col in ("subject", "body_html", "from_name", "scheduled_at", "status"):
            val = getattr(body, col)
            if val is not None:
                args.append(val)
                sets.append(f"{col} = ${len(args)}")
        if not sets:
            row = await conn.fetchrow(
                f"SELECT {_CAMPAIGN_COLS} FROM cappe_campaigns WHERE id = $1", campaign_id
            )
            return dict(row)
        sets.append("updated_at = NOW()")
        args.extend([campaign_id, site_id])
        row = await conn.fetchrow(
            f"UPDATE cappe_campaigns SET {', '.join(sets)} "
            f"WHERE id = ${len(args) - 1} AND site_id = ${len(args)} RETURNING {_CAMPAIGN_COLS}",
            *args,
        )
    return dict(row)


@router.delete("/sites/{site_id}/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    site_id: UUID, campaign_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        result = await conn.execute(
            "DELETE FROM cappe_campaigns WHERE id = $1 AND site_id = $2", campaign_id, site_id
        )
    if result.endswith(" 0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")


@router.post("/sites/{site_id}/campaigns/{campaign_id}/send", response_model=CappeCampaign)
async def send_campaign(
    site_id: UUID, campaign_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    """Stage the campaign for sending and dispatch the background blast. The
    Celery task (cappe_campaign_send) does the throttled per-recipient send and
    flips status 'sending' → 'sent' with the real recipient count."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        campaign = await conn.fetchrow(
            "SELECT status FROM cappe_campaigns WHERE id = $1 AND site_id = $2", campaign_id, site_id
        )
        if campaign is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        if campaign["status"] in ("sent", "sending"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Campaign already sent")

        row = await conn.fetchrow(
            f"""UPDATE cappe_campaigns SET status = 'sending', updated_at = NOW()
                WHERE id = $1 AND site_id = $2 RETURNING {_CAMPAIGN_COLS}""",
            campaign_id, site_id,
        )

    # Hand off to the worker; revert to draft so the creator can retry if the
    # broker is unreachable.
    try:
        from app.workers.tasks.cappe_campaign_send import run_cappe_campaign_send
        run_cappe_campaign_send.delay(str(campaign_id))
    except Exception:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                f"""UPDATE cappe_campaigns SET status = 'draft', updated_at = NOW()
                    WHERE id = $1 AND site_id = $2 RETURNING {_CAMPAIGN_COLS}""",
                campaign_id, site_id,
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sending is temporarily unavailable — please try again shortly.",
        )
    return dict(row)
