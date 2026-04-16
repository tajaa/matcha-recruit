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
    open_to_all: bool = False


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


class RejectPostingRequest(BaseModel):
    reason: Optional[str] = None


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

        # Owner posts skip approval and go straight to draft (then checkout).
        # Mod posts in someone else's channel land in pending_approval so the
        # channel owner can vet them before they hit the feed.
        initial_status = "draft" if role == "owner" else "pending_approval"

        # Stripe product/price are created up-front for both paths so the
        # recruiter can complete checkout as soon as the posting is approved.
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
                 stripe_product_id, stripe_price_id, open_to_all,
                 approved_by, approved_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                    CASE WHEN $8 = 'draft' THEN $2 END,
                    CASE WHEN $8 = 'draft' THEN NOW() END)
            RETURNING id, channel_id, posted_by, title, description, requirements,
                      compensation_summary, location, status,
                      stripe_product_id, stripe_price_id, open_to_all,
                      approved_by, approved_at,
                      created_at, updated_at
            """,
            channel_id, current_user.id, body.title, body.description,
            body.requirements, body.compensation_summary, body.location,
            initial_status, product_id, price_id, body.open_to_all,
        )

        # Notify the channel owner when a mod post needs approval.
        if initial_status == "pending_approval":
            try:
                from ...matcha.services import notification_service as notif_svc
                owner_id = await conn.fetchval(
                    "SELECT user_id FROM channel_members WHERE channel_id = $1 AND role = 'owner' LIMIT 1",
                    channel_id,
                )
                if owner_id and owner_id != current_user.id:
                    await notif_svc.create_notification(
                        user_id=owner_id,
                        company_id=company_id,
                        type="channel_job_posting_pending",
                        title=f"Job posting needs approval: {body.title}",
                        body=f"{ch['name']} moderator created a new posting awaiting your approval",
                        link=f"/work/channels/{channel_id}/job-postings/{row['id']}",
                    )
            except Exception:
                pass

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

        if role == "owner":
            # Owner sees everything including mod posts awaiting their approval.
            rows = await conn.fetch(
                """
                SELECT jp.id, jp.title, jp.status, jp.location, jp.open_to_all,
                       jp.posted_by, jp.approved_by, jp.approved_at,
                       jp.created_at, jp.updated_at,
                       (SELECT COUNT(*) FROM channel_job_applications a WHERE a.posting_id = jp.id) AS applicant_count,
                       (SELECT COUNT(*) FROM channel_job_invitations i WHERE i.posting_id = jp.id) AS invited_count
                FROM channel_job_postings jp
                WHERE jp.channel_id = $1
                ORDER BY jp.created_at DESC
                """,
                channel_id,
            )
        elif role == "moderator":
            # Mods see everything EXCEPT other mods' pending_approval posts.
            # They still see their own pending posts so they can track status.
            rows = await conn.fetch(
                """
                SELECT jp.id, jp.title, jp.status, jp.location, jp.open_to_all,
                       jp.posted_by, jp.approved_by, jp.approved_at,
                       jp.created_at, jp.updated_at,
                       (SELECT COUNT(*) FROM channel_job_applications a WHERE a.posting_id = jp.id) AS applicant_count,
                       (SELECT COUNT(*) FROM channel_job_invitations i WHERE i.posting_id = jp.id) AS invited_count
                FROM channel_job_postings jp
                WHERE jp.channel_id = $1
                  AND (jp.status != 'pending_approval' OR jp.posted_by = $2)
                ORDER BY jp.created_at DESC
                """,
                channel_id, current_user.id,
            )
        else:
            # Members see active postings that are either open-to-all or
            # where they have an explicit invitation.
            rows = await conn.fetch(
                """
                SELECT jp.id, jp.title, jp.status, jp.location, jp.open_to_all,
                       jp.created_at, jp.updated_at,
                       (SELECT COUNT(*) FROM channel_job_applications a WHERE a.posting_id = jp.id) AS applicant_count,
                       (SELECT COUNT(*) FROM channel_job_invitations i WHERE i.posting_id = jp.id) AS invited_count
                FROM channel_job_postings jp
                WHERE jp.channel_id = $1 AND jp.status = 'active'
                  AND (
                      jp.open_to_all = true
                      OR EXISTS (
                          SELECT 1 FROM channel_job_invitations inv
                          WHERE inv.posting_id = jp.id AND inv.user_id = $2
                      )
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
        is_open_to_all = bool(posting["open_to_all"])
        is_poster = posting["posted_by"] == current_user.id

        # Mods who didn't post a pending_approval posting can't see it — the
        # owner needs to gate approval without another mod front-running them.
        if (
            posting["status"] == "pending_approval"
            and role != "owner"
            and not is_poster
        ):
            raise HTTPException(status_code=404, detail="Job posting not found")

        # Check invitation for non-owner/mod
        invitation = await conn.fetchrow(
            "SELECT * FROM channel_job_invitations WHERE posting_id = $1 AND user_id = $2",
            posting_id, current_user.id,
        )
        if not is_owner_mod and not invitation and not is_open_to_all:
            raise HTTPException(status_code=403, detail="You do not have access to this posting")

        # Mark invitation as viewed (only applies to explicit targeted invites)
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
        result["i_can_apply"] = bool(
            posting["status"] == "active"
            and not is_owner_mod
            and (invitation is not None or is_open_to_all)
            and application is None
        )

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
            "SELECT id, status, posted_by, stripe_price_id FROM channel_job_postings WHERE id = $1 AND channel_id = $2",
            posting_id, channel_id,
        )
        if not posting:
            raise HTTPException(status_code=404, detail="Job posting not found")
        # Only the recruiter who created the posting can run checkout, and
        # only once the post has been approved (status moved past
        # pending_approval / rejected into draft).
        if posting["posted_by"] != current_user.id and role != "owner":
            raise HTTPException(status_code=403, detail="Only the recruiter who created the posting can pay for it")
        if posting["status"] == "pending_approval":
            raise HTTPException(
                status_code=400,
                detail="This posting is awaiting owner approval — you can't pay for it yet",
            )
        if posting["status"] == "rejected":
            raise HTTPException(status_code=400, detail="This posting was rejected")

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
                   app.resume_snapshot,
                   u.email AS applicant_email,
                   {_USER_NAME_EXPR} AS applicant_name
            FROM channel_job_applications app
            JOIN users u ON u.id = app.applicant_id
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE app.posting_id = $1
            ORDER BY app.submitted_at DESC
            """,
            posting_id,
        )

        # Gate parsed resume payload behind the Matcha Recruiter tier.
        # Non-recruiter owners/mods still see that applications exist +
        # the cover letter, but the parsed resume is stripped.
        is_recruiter_tier = bool(
            await conn.fetchval(
                "SELECT recruiter_until > NOW() FROM users WHERE id = $1",
                current_user.id,
            )
        )

    out = []
    for r in rows:
        d = dict(r)
        snap = d.get("resume_snapshot")
        if not is_recruiter_tier:
            # Drop the parsed payload — keep a flag so the client knows
            # a snapshot exists and can prompt the upgrade.
            d["resume_snapshot"] = None
            d["resume_locked"] = snap is not None
        else:
            d["resume_locked"] = False
            if isinstance(snap, str):
                try:
                    d["resume_snapshot"] = json.loads(snap)
                except json.JSONDecodeError:
                    d["resume_snapshot"] = None
        out.append(d)
    return out


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
    """Apply to a job posting. Allowed if explicitly invited OR the posting
    is open to all members. The applicant must have a profile resume —
    we snapshot it into channel_job_applications.resume_snapshot.
    """
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role is None:
            raise HTTPException(status_code=403, detail="You are not a member of this channel")

        posting = await conn.fetchrow(
            "SELECT id, status, posted_by, title, open_to_all FROM channel_job_postings WHERE id = $1 AND channel_id = $2",
            posting_id, channel_id,
        )
        if not posting:
            raise HTTPException(status_code=404, detail="Job posting not found")
        if posting["status"] != "active":
            raise HTTPException(status_code=400, detail="This job posting is not currently accepting applications")

        # Verify invitation exists OR posting is open to all
        invitation = await conn.fetchval(
            "SELECT id FROM channel_job_invitations WHERE posting_id = $1 AND user_id = $2",
            posting_id, current_user.id,
        )
        if not invitation and not posting["open_to_all"]:
            raise HTTPException(status_code=403, detail="You have not been invited to this posting")

        # Check for existing application
        existing = await conn.fetchval(
            "SELECT id FROM channel_job_applications WHERE posting_id = $1 AND applicant_id = $2",
            posting_id, current_user.id,
        )
        if existing:
            raise HTTPException(status_code=409, detail="You have already applied to this posting")

        # Pull the applicant's profile resume — this is required to apply.
        resume_row = await conn.fetchrow(
            "SELECT parsed_data FROM user_resumes WHERE user_id = $1",
            current_user.id,
        )
        if not resume_row:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "no_resume",
                    "message": "Upload your resume to your profile to apply.",
                },
            )
        snapshot = resume_row["parsed_data"]
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except json.JSONDecodeError:
                snapshot = {}

        row = await conn.fetchrow(
            """
            INSERT INTO channel_job_applications
                (posting_id, applicant_id, cover_letter, status, resume_snapshot)
            VALUES ($1, $2, $3, 'submitted', $4::jsonb)
            RETURNING *
            """,
            posting_id, current_user.id, body.cover_letter, json.dumps(snapshot),
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
# NEW: POST /{channel_id}/job-postings/{posting_id}/approve — owner approves
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/job-postings/{posting_id}/approve")
async def approve_job_posting(
    channel_id: UUID,
    posting_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Channel owner approves a mod-created pending posting. Transitions
    status pending_approval → draft so the recruiter can run checkout."""
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role != "owner":
            raise HTTPException(status_code=403, detail="Only the channel owner can approve job postings")

        posting = await conn.fetchrow(
            "SELECT id, status, posted_by, title FROM channel_job_postings WHERE id = $1 AND channel_id = $2",
            posting_id, channel_id,
        )
        if not posting:
            raise HTTPException(status_code=404, detail="Job posting not found")
        if posting["status"] != "pending_approval":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot approve a posting in status '{posting['status']}'",
            )

        row = await conn.fetchrow(
            """
            UPDATE channel_job_postings
            SET status = 'draft', approved_by = $2, approved_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            posting_id, current_user.id,
        )

        # Tell the recruiter their post is approved and ready for checkout.
        try:
            from ...matcha.services import notification_service as notif_svc
            company_id = await conn.fetchval("SELECT company_id FROM channels WHERE id = $1", channel_id)
            if company_id:
                await notif_svc.create_notification(
                    user_id=posting["posted_by"],
                    company_id=company_id,
                    type="channel_job_posting_approved",
                    title=f"Job posting approved: {posting['title']}",
                    body="The channel owner approved your posting. Complete checkout to activate it.",
                    link=f"/work/channels/{channel_id}/job-postings/{posting_id}",
                )
        except Exception:
            pass

    return dict(row)


# ---------------------------------------------------------------------------
# NEW: POST /{channel_id}/job-postings/{posting_id}/reject — owner rejects
# ---------------------------------------------------------------------------

@router.post("/{channel_id}/job-postings/{posting_id}/reject")
async def reject_job_posting(
    channel_id: UUID,
    posting_id: UUID,
    body: RejectPostingRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Channel owner rejects a pending posting. Status becomes 'rejected'
    and the posting is hidden from the feed."""
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role != "owner":
            raise HTTPException(status_code=403, detail="Only the channel owner can reject job postings")

        posting = await conn.fetchrow(
            "SELECT id, status, posted_by, title FROM channel_job_postings WHERE id = $1 AND channel_id = $2",
            posting_id, channel_id,
        )
        if not posting:
            raise HTTPException(status_code=404, detail="Job posting not found")
        if posting["status"] != "pending_approval":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reject a posting in status '{posting['status']}'",
            )

        row = await conn.fetchrow(
            """
            UPDATE channel_job_postings
            SET status = 'rejected', rejected_reason = $2, updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            posting_id, body.reason,
        )

        try:
            from ...matcha.services import notification_service as notif_svc
            company_id = await conn.fetchval("SELECT company_id FROM channels WHERE id = $1", channel_id)
            if company_id:
                await notif_svc.create_notification(
                    user_id=posting["posted_by"],
                    company_id=company_id,
                    type="channel_job_posting_rejected",
                    title=f"Job posting rejected: {posting['title']}",
                    body=body.reason or "The channel owner rejected your posting.",
                    link=f"/work/channels/{channel_id}/job-postings/{posting_id}",
                )
        except Exception:
            pass

    return dict(row)


# ---------------------------------------------------------------------------
# NEW: GET /job-postings/my-pending-approvals — owner's approval queue
# ---------------------------------------------------------------------------

@router.get("/job-postings/my-pending-approvals")
async def my_pending_approvals(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return all pending_approval postings across channels the current
    user owns, so a creator can review the queue in one place."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT jp.id, jp.title, jp.description, jp.location,
                   jp.compensation_summary, jp.created_at,
                   ch.id AS channel_id, ch.name AS channel_name,
                   jp.posted_by,
                   {_USER_NAME_EXPR} AS posted_by_name
            FROM channel_job_postings jp
            JOIN channels ch ON ch.id = jp.channel_id
            JOIN channel_members cm ON cm.channel_id = ch.id
            JOIN users u ON u.id = jp.posted_by
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE jp.status = 'pending_approval'
              AND cm.user_id = $1 AND cm.role = 'owner'
            ORDER BY jp.created_at DESC
            """,
            current_user.id,
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# NEW: GET /{channel_id}/open-postings — channel-wide postings for banner
# ---------------------------------------------------------------------------

@router.get("/{channel_id}/open-postings")
async def list_open_postings(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return active postings in this channel that are open to all members.

    Used by the channel view to render a 'open role' banner without needing
    a URL parameter. Only members of the channel see anything.
    """
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role is None:
            raise HTTPException(status_code=403, detail="You are not a member of this channel")

        rows = await conn.fetch(
            """
            SELECT jp.id, jp.title, jp.location, jp.compensation_summary,
                   jp.created_at,
                   EXISTS(
                       SELECT 1 FROM channel_job_applications app
                       WHERE app.posting_id = jp.id AND app.applicant_id = $2
                   ) AS already_applied
            FROM channel_job_postings jp
            WHERE jp.channel_id = $1
              AND jp.status = 'active'
              AND jp.open_to_all = true
              AND (jp.paid_through IS NULL OR jp.paid_through > NOW())
            ORDER BY jp.created_at DESC
            """,
            channel_id, current_user.id,
        )

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# NEW: GET /{channel_id}/job-posting-fee — channel-owned posting fee
# ---------------------------------------------------------------------------

@router.get("/{channel_id}/job-posting-fee")
async def get_job_posting_fee(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return the channel's job posting fee so the create modal can show
    recruiters what a new posting will cost. NULL means the platform
    default is used.
    """
    async with get_connection() as conn:
        role = await _get_member_role(conn, channel_id, current_user.id)
        if role not in ("owner", "moderator"):
            raise HTTPException(status_code=403, detail="Only channel owners and moderators can view the job posting fee")

        fee_cents = await conn.fetchval(
            "SELECT job_posting_fee_cents FROM channels WHERE id = $1",
            channel_id,
        )

    return {
        "fee_cents": fee_cents,
        "default_used": fee_cents is None,
    }


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
