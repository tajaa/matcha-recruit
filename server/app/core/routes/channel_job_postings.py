"""Channel job posting routes — create, manage, and apply to job postings within paid channels."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import get_current_user
from ..models.auth import CurrentUser
from ..services.channel_job_posting_service import (
    create_job_posting_product_and_price,
    create_job_posting_checkout,
    cancel_job_posting_subscription,
    send_invitations,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

_USER_NAME_EXPR = "COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email)"


class CreateJobPostingRequest(BaseModel):
    title: str
    description: Optional[str] = None
    requirements: Optional[str] = None
    compensation_summary: Optional[str] = None
    location: Optional[str] = None


class UpdateJobPostingRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    compensation_summary: Optional[str] = None
    location: Optional[str] = None


class InviteToPostingRequest(BaseModel):
    user_ids: list[UUID]


class SubmitApplicationRequest(BaseModel):
    cover_letter: Optional[str] = None


class UpdateApplicationRequest(BaseModel):
    status: str  # reviewed, shortlisted, rejected
    reviewer_notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_member_role(conn, channel_id: UUID, user_id: UUID) -> Optional[str]:
    """Return the user's role in the channel, or None if not a member."""
    return await conn.fetchval(
        "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
        channel_id, user_id,
    )


# ---------------------------------------------------------------------------
# 1. POST /{channel_id}/job-postings — create a new job posting
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/job-postings", status_code=status.HTTP_201_CREATED)
async def create_job_posting(
    channel_id: UUID,
    body: CreateJobPostingRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new job posting in a channel (owner/mod only)."""
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role not in ("owner", "moderator"):
            raise HTTPException(status_code=403, detail="Only channel owners and moderators can create job postings")

        # Validate channel exists and check feature flag
        ch = await conn.fetchrow("SELECT company_id, name FROM channels WHERE id = $1", channel_id)
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")
        company_id = ch["company_id"]

        features = await conn.fetchval("SELECT enabled_features FROM companies WHERE id = $1", company_id)
        from ..feature_flags import merge_company_features
        merged = merge_company_features(features)
        if not merged.get("channel_job_postings") and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Job postings feature is not enabled for this company")

        # Create Stripe product and price for this posting
        product_id, price_id = await create_job_posting_product_and_price(
            channel_id=channel_id,
            channel_name=ch["name"],
            posting_title=body.title,
        )

        row = await conn.fetchrow(
            """
            INSERT INTO channel_job_postings
                (channel_id, posted_by, title, description, requirements,
                 compensation_summary, location, status,
                 stripe_product_id, stripe_price_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'draft', $8, $9)
            RETURNING id, channel_id, posted_by, title, description, requirements,
                      compensation_summary, location, status,
                      stripe_product_id, stripe_price_id,
                      created_at, updated_at
            """,
            channel_id, current_user.id, body.title, body.description,
            body.requirements, body.compensation_summary, body.location,
            product_id, price_id,
        )

    return dict(row)


# ---------------------------------------------------------------------------
# 2. GET /{channel_id}/job-postings — list job postings
# ---------------------------------------------------------------------------

@router.get("/{channel_id}/job-postings")
async def list_job_postings(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List job postings in a channel. Owners/mods see all; members see active + invited."""
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role is None:
            raise HTTPException(status_code=403, detail="You are not a member of this channel")

        if role in ("owner", "moderator"):
            rows = await conn.fetch(
                """
                SELECT jp.id, jp.title, jp.status, jp.location, jp.created_at, jp.updated_at,
                       (SELECT COUNT(*) FROM channel_job_applications a WHERE a.posting_id = jp.id) AS applicant_count,
                       (SELECT COUNT(*) FROM channel_job_invitations i WHERE i.posting_id = jp.id) AS invited_count
                FROM channel_job_postings jp
                WHERE jp.channel_id = $1
                ORDER BY jp.created_at DESC
                """,
                channel_id,
            )
        else:
            # Members only see active postings where they have an invitation
            rows = await conn.fetch(
                """
                SELECT jp.id, jp.title, jp.status, jp.location, jp.created_at, jp.updated_at,
                       (SELECT COUNT(*) FROM channel_job_applications a WHERE a.posting_id = jp.id) AS applicant_count,
                       (SELECT COUNT(*) FROM channel_job_invitations i WHERE i.posting_id = jp.id) AS invited_count
                FROM channel_job_postings jp
                WHERE jp.channel_id = $1 AND jp.status = 'active'
                  AND EXISTS (
                      SELECT 1 FROM channel_job_invitations inv
                      WHERE inv.posting_id = jp.id AND inv.user_id = $2
                  )
                ORDER BY jp.created_at DESC
                """,
                channel_id, current_user.id,
            )

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 3. GET /{channel_id}/job-postings/{posting_id} — posting detail
# ---------------------------------------------------------------------------

@router.get("/{channel_id}/job-postings/{posting_id}")
async def get_job_posting(
    channel_id: UUID,
    posting_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get full detail for a job posting. Invited member or owner/mod."""
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role is None:
            raise HTTPException(status_code=403, detail="You are not a member of this channel")

        posting = await conn.fetchrow(
            """
            SELECT jp.*, u.email AS posted_by_email
            FROM channel_job_postings jp
            JOIN users u ON u.id = jp.posted_by
            WHERE jp.id = $1 AND jp.channel_id = $2
            """,
            posting_id, channel_id,
        )
        if not posting:
            raise HTTPException(status_code=404, detail="Job posting not found")

        is_owner_mod = role in ("owner", "moderator")

        # Check invitation for non-owner/mod
        invitation = await conn.fetchrow(
            "SELECT * FROM channel_job_invitations WHERE posting_id = $1 AND user_id = $2",
            posting_id, current_user.id,
        )
        if not is_owner_mod and not invitation:
            raise HTTPException(status_code=403, detail="You do not have access to this posting")

        # Mark invitation as viewed
        if invitation and invitation["viewed_at"] is None:
            await conn.execute(
                "UPDATE channel_job_invitations SET viewed_at = NOW() WHERE id = $1",
                invitation["id"],
            )

        # Get current user's application
        application = await conn.fetchrow(
            "SELECT * FROM channel_job_applications WHERE posting_id = $1 AND applicant_id = $2",
            posting_id, current_user.id,
        )

        result = dict(posting)
        result["my_invitation"] = dict(invitation) if invitation else None
        result["my_application"] = dict(application) if application else None

    return result


# ---------------------------------------------------------------------------
# 4. PATCH /{channel_id}/job-postings/{posting_id} — update posting
# ---------------------------------------------------------------------------

@router.patch("/{channel_id}/job-postings/{posting_id}")
async def update_job_posting(
    channel_id: UUID,
    posting_id: UUID,
    body: UpdateJobPostingRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a job posting (owner/mod only). Cannot update closed postings."""
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role not in ("owner", "moderator"):
            raise HTTPException(status_code=403, detail="Only channel owners and moderators can update job postings")

        posting = await conn.fetchrow(
            "SELECT id, status FROM channel_job_postings WHERE id = $1 AND channel_id = $2",
            posting_id, channel_id,
        )
        if not posting:
            raise HTTPException(status_code=404, detail="Job posting not found")
        if posting["status"] == "closed":
            raise HTTPException(status_code=400, detail="Cannot update a closed job posting")

        updates = {}
        for field in ("title", "description", "requirements", "compensation_summary", "location"):
            val = getattr(body, field)
            if val is not None:
                updates[field] = val

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        set_clauses = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates))
        values = list(updates.values())

        row = await conn.fetchrow(
            f"""
            UPDATE channel_job_postings
            SET {set_clauses}, updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            posting_id, *values,
        )

    return dict(row)


# ---------------------------------------------------------------------------
# 5. POST /{channel_id}/job-postings/{posting_id}/checkout — start checkout
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/job-postings/{posting_id}/checkout")
async def checkout_job_posting(
    channel_id: UUID,
    posting_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a Stripe checkout session for a job posting subscription (owner/mod only)."""
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role not in ("owner", "moderator"):
            raise HTTPException(status_code=403, detail="Only channel owners and moderators can manage billing")

        posting = await conn.fetchrow(
            "SELECT id, stripe_price_id FROM channel_job_postings WHERE id = $1 AND channel_id = $2",
            posting_id, channel_id,
        )
        if not posting:
            raise HTTPException(status_code=404, detail="Job posting not found")

    url = await create_job_posting_checkout(
        posting_id=posting_id,
        channel_id=channel_id,
        user_id=current_user.id,
        stripe_price_id=posting["stripe_price_id"],
    )

    return {"checkout_url": url}


# ---------------------------------------------------------------------------
# 6. POST /{channel_id}/job-postings/{posting_id}/cancel — cancel subscription
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/job-postings/{posting_id}/cancel")
async def cancel_job_posting(
    channel_id: UUID,
    posting_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Cancel the Stripe subscription for a job posting (owner/mod only)."""
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role not in ("owner", "moderator"):
            raise HTTPException(status_code=403, detail="Only channel owners and moderators can manage billing")

        posting = await conn.fetchrow(
            "SELECT id, stripe_subscription_id FROM channel_job_postings WHERE id = $1 AND channel_id = $2",
            posting_id, channel_id,
        )
        if not posting:
            raise HTTPException(status_code=404, detail="Job posting not found")
        if not posting["stripe_subscription_id"]:
            raise HTTPException(status_code=400, detail="No active subscription for this posting")

    paid_through = await cancel_job_posting_subscription(posting["stripe_subscription_id"])

    return {"paid_through": paid_through}


# ---------------------------------------------------------------------------
# 7. POST /{channel_id}/job-postings/{posting_id}/close — close posting
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/job-postings/{posting_id}/close")
async def close_job_posting(
    channel_id: UUID,
    posting_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Close a job posting (owner/mod only). Does NOT cancel Stripe subscription."""
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role not in ("owner", "moderator"):
            raise HTTPException(status_code=403, detail="Only channel owners and moderators can close job postings")

        posting = await conn.fetchrow(
            "SELECT id, status FROM channel_job_postings WHERE id = $1 AND channel_id = $2",
            posting_id, channel_id,
        )
        if not posting:
            raise HTTPException(status_code=404, detail="Job posting not found")

        row = await conn.fetchrow(
            """
            UPDATE channel_job_postings
            SET status = 'closed', closed_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            posting_id,
        )

    return dict(row)


# ---------------------------------------------------------------------------
# 8. POST /{channel_id}/job-postings/{posting_id}/invite — invite members
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/job-postings/{posting_id}/invite")
async def invite_to_posting(
    channel_id: UUID,
    posting_id: UUID,
    body: InviteToPostingRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Invite channel members to a job posting (owner/mod only)."""
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role not in ("owner", "moderator"):
            raise HTTPException(status_code=403, detail="Only channel owners and moderators can send invitations")

        posting = await conn.fetchrow(
            "SELECT id, title FROM channel_job_postings WHERE id = $1 AND channel_id = $2",
            posting_id, channel_id,
        )
        if not posting:
            raise HTTPException(status_code=404, detail="Job posting not found")

        # Validate all user_ids are channel members
        member_check = await conn.fetch(
            "SELECT user_id FROM channel_members WHERE channel_id = $1 AND user_id = ANY($2::uuid[])",
            channel_id, body.user_ids,
        )
        member_ids = {r["user_id"] for r in member_check}
        non_members = [uid for uid in body.user_ids if uid not in member_ids]
        if non_members:
            raise HTTPException(
                status_code=400,
                detail=f"{len(non_members)} user(s) are not members of this channel",
            )

        company_id = await conn.fetchval("SELECT company_id FROM channels WHERE id = $1", channel_id)
        inviter_name = await conn.fetchval(
            f"SELECT {_USER_NAME_EXPR} FROM users u "
            "LEFT JOIN clients c ON c.user_id = u.id "
            "LEFT JOIN employees e ON e.user_id = u.id "
            "LEFT JOIN admins a ON a.user_id = u.id "
            "WHERE u.id = $1",
            current_user.id,
        )

    await send_invitations(
        posting_id=posting_id,
        channel_id=channel_id,
        company_id=company_id,
        user_ids=body.user_ids,
        inviter_name=inviter_name or current_user.email,
        posting_title=posting["title"],
    )

    return {"invited": len(body.user_ids)}


# ---------------------------------------------------------------------------
# 9. GET /{channel_id}/job-postings/{posting_id}/applicants — list applicants
# ---------------------------------------------------------------------------

@router.get("/{channel_id}/job-postings/{posting_id}/applicants")
async def list_applicants(
    channel_id: UUID,
    posting_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List applications for a job posting (owner/mod only)."""
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role not in ("owner", "moderator"):
            raise HTTPException(status_code=403, detail="Only channel owners and moderators can view applicants")

        posting = await conn.fetchrow(
            "SELECT id FROM channel_job_postings WHERE id = $1 AND channel_id = $2",
            posting_id, channel_id,
        )
        if not posting:
            raise HTTPException(status_code=404, detail="Job posting not found")

        rows = await conn.fetch(
            f"""
            SELECT app.id, app.applicant_id, app.status, app.cover_letter,
                   app.reviewer_notes, app.submitted_at, app.reviewed_at,
                   u.email AS applicant_email,
                   {_USER_NAME_EXPR} AS applicant_name
            FROM channel_job_applications app
            JOIN users u ON u.id = app.applicant_id
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE app.posting_id = $1
            ORDER BY app.created_at DESC
            """,
            posting_id,
        )

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 10. POST /{channel_id}/job-postings/{posting_id}/apply — submit application
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/job-postings/{posting_id}/apply", status_code=status.HTTP_201_CREATED)
async def apply_to_posting(
    channel_id: UUID,
    posting_id: UUID,
    body: SubmitApplicationRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Apply to a job posting. Must have an invitation and posting must be active."""
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role is None:
            raise HTTPException(status_code=403, detail="You are not a member of this channel")

        posting = await conn.fetchrow(
            "SELECT id, status, posted_by, title FROM channel_job_postings WHERE id = $1 AND channel_id = $2",
            posting_id, channel_id,
        )
        if not posting:
            raise HTTPException(status_code=404, detail="Job posting not found")
        if posting["status"] != "active":
            raise HTTPException(status_code=400, detail="This job posting is not currently accepting applications")

        # Verify invitation exists
        invitation = await conn.fetchval(
            "SELECT id FROM channel_job_invitations WHERE posting_id = $1 AND user_id = $2",
            posting_id, current_user.id,
        )
        if not invitation:
            raise HTTPException(status_code=403, detail="You have not been invited to this posting")

        # Check for existing application
        existing = await conn.fetchval(
            "SELECT id FROM channel_job_applications WHERE posting_id = $1 AND applicant_id = $2",
            posting_id, current_user.id,
        )
        if existing:
            raise HTTPException(status_code=409, detail="You have already applied to this posting")

        row = await conn.fetchrow(
            """
            INSERT INTO channel_job_applications (posting_id, applicant_id, cover_letter, status)
            VALUES ($1, $2, $3, 'submitted')
            RETURNING *
            """,
            posting_id, current_user.id, body.cover_letter,
        )

        # Send notification to the posting creator
        try:
            from ...matcha.services import notification_service as notif_svc
            company_id = await conn.fetchval("SELECT company_id FROM channels WHERE id = $1", channel_id)
            applicant_name = await conn.fetchval(
                f"SELECT {_USER_NAME_EXPR} FROM users u "
                "LEFT JOIN clients c ON c.user_id = u.id "
                "LEFT JOIN employees e ON e.user_id = u.id "
                "LEFT JOIN admins a ON a.user_id = u.id "
                "WHERE u.id = $1",
                current_user.id,
            )
            if company_id:
                await notif_svc.create_notification(
                    user_id=posting["posted_by"],
                    company_id=company_id,
                    type="job_application_received",
                    title=f"New application for {posting['title']}",
                    body=f"{applicant_name} applied to your job posting",
                    link=f"/work/channels/{channel_id}/job-postings/{posting_id}/applicants",
                )
        except Exception:
            pass

    return dict(row)


# ---------------------------------------------------------------------------
# 11. POST /{channel_id}/job-postings/{posting_id}/withdraw — withdraw application
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/job-postings/{posting_id}/withdraw")
async def withdraw_application(
    channel_id: UUID,
    posting_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Withdraw your application from a job posting."""
    async with get_connection() as conn:
        application = await conn.fetchrow(
            """
            SELECT app.id, app.status
            FROM channel_job_applications app
            JOIN channel_job_postings jp ON jp.id = app.posting_id
            WHERE app.posting_id = $1 AND app.applicant_id = $2 AND jp.channel_id = $3
            """,
            posting_id, current_user.id, channel_id,
        )
        if not application:
            raise HTTPException(status_code=404, detail="Application not found")

        await conn.execute(
            "UPDATE channel_job_applications SET status = 'withdrawn' WHERE id = $1",
            application["id"],
        )

    return {"ok": True, "status": "withdrawn"}


# ---------------------------------------------------------------------------
# 12. PATCH /{channel_id}/job-postings/{posting_id}/applicants/{application_id}
# ---------------------------------------------------------------------------

@router.patch("/{channel_id}/job-postings/{posting_id}/applicants/{application_id}")
async def update_application(
    channel_id: UUID,
    posting_id: UUID,
    application_id: UUID,
    body: UpdateApplicationRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an application's status and reviewer notes (owner/mod only)."""
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role not in ("owner", "moderator"):
            raise HTTPException(status_code=403, detail="Only channel owners and moderators can review applications")

        application = await conn.fetchrow(
            """
            SELECT app.id, app.applicant_id
            FROM channel_job_applications app
            JOIN channel_job_postings jp ON jp.id = app.posting_id
            WHERE app.id = $1 AND app.posting_id = $2 AND jp.channel_id = $3
            """,
            application_id, posting_id, channel_id,
        )
        if not application:
            raise HTTPException(status_code=404, detail="Application not found")

        if body.status not in ("reviewed", "shortlisted", "rejected"):
            raise HTTPException(status_code=400, detail="Status must be one of: reviewed, shortlisted, rejected")

        row = await conn.fetchrow(
            """
            UPDATE channel_job_applications
            SET status = $2, reviewer_notes = $3, reviewed_by = $4, reviewed_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            application_id, body.status, body.reviewer_notes, current_user.id,
        )

        # Notify the applicant
        try:
            from ...matcha.services import notification_service as notif_svc
            company_id = await conn.fetchval("SELECT company_id FROM channels WHERE id = $1", channel_id)
            posting_title = await conn.fetchval(
                "SELECT title FROM channel_job_postings WHERE id = $1", posting_id,
            )
            status_label = body.status.replace("_", " ").title()
            if company_id:
                await notif_svc.create_notification(
                    user_id=application["applicant_id"],
                    company_id=company_id,
                    type="job_application_status_changed",
                    title=f"Application update: {posting_title}",
                    body=f"Your application status changed to {status_label}",
                    link=f"/work/channels/{channel_id}/job-postings/{posting_id}",
                )
        except Exception:
            pass

    return dict(row)


# ---------------------------------------------------------------------------
# 13. GET /job-postings/my-invitations — pending invitations for current user
# ---------------------------------------------------------------------------

@router.get("/job-postings/my-invitations")
async def my_invitations(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get all pending job posting invitations for the current user across all channels."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT inv.id, inv.posting_id, inv.invited_at, inv.viewed_at,
                   jp.title AS posting_title, jp.status AS posting_status,
                   jp.location, jp.compensation_summary,
                   ch.id AS channel_id, ch.name AS channel_name
            FROM channel_job_invitations inv
            JOIN channel_job_postings jp ON jp.id = inv.posting_id
            JOIN channels ch ON ch.id = jp.channel_id
            WHERE inv.user_id = $1
              AND jp.status = 'active'
              AND NOT EXISTS (
                  SELECT 1 FROM channel_job_applications app
                  WHERE app.posting_id = inv.posting_id AND app.applicant_id = inv.user_id
              )
            ORDER BY inv.invited_at DESC
            """,
            current_user.id,
        )

    return [dict(r) for r in rows]
