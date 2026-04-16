"""Profile-level resume routes.

Stores a single parsed resume per user in the `user_resumes` table. The
parsed payload matches the ResumeCandidate schema used by matcha-work
recruiting projects, so it can be snapshotted into job applications or
displayed in UI without any transformation.

Also exposes the Matcha Recruiter tier endpoints — a per-user paid
upgrade that unlocks parsed resume reads on channel job applications.
"""

import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from ...database import get_connection
from ...matcha.services.resume_parser import (
    RESUME_UPLOAD_EXTENSIONS,
    RESUME_UPLOAD_MAX_BYTES,
    ResumeParseError,
    parse_resume_file,
)
from ..dependencies import get_current_user
from ..models.auth import CurrentUser
from ..services.storage import get_storage
from ..services.stripe_service import StripeService

logger = logging.getLogger(__name__)

router = APIRouter()


class ProfileResumeResponse(BaseModel):
    filename: str
    resume_url: str
    parsed_data: dict
    updated_at: str


def _row_to_response(row) -> ProfileResumeResponse:
    parsed = row["parsed_data"]
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError:
            parsed = {}
    return ProfileResumeResponse(
        filename=row["filename"],
        resume_url=row["resume_url"],
        parsed_data=parsed or {},
        updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
    )


@router.post("/me/resume", response_model=ProfileResumeResponse)
async def upload_my_resume(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Upload a resume PDF/DOC/DOCX/TXT, parse it, and upsert into the
    caller's profile. Replaces any existing resume.
    """
    filename = file.filename or "resume"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in RESUME_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(RESUME_UPLOAD_EXTENSIONS))}",
        )

    raw = await file.read()
    if len(raw) > RESUME_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit")
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")

    content_type = file.content_type or "application/octet-stream"

    try:
        parsed_data, raw_text = await parse_resume_file(raw, filename, content_type)
    except ResumeParseError as e:
        logger.warning("Profile resume parse failed for user %s: %s", current_user.id, e)
        raise HTTPException(
            status_code=422,
            detail="Could not parse resume. Please try a different file or format.",
        )

    # Upload raw file to storage (best-effort). Failing the upload is not
    # fatal — we still persist the parsed data so the user gets value.
    try:
        resume_url = await get_storage().upload_file(
            raw,
            filename,
            prefix=f"profile_resumes/{current_user.id}",
            content_type=content_type,
        )
    except Exception as e:
        logger.warning("Profile resume S3 upload failed for user %s: %s", current_user.id, e)
        resume_url = ""

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO user_resumes (user_id, filename, resume_url, raw_text, parsed_data, updated_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, NOW())
            ON CONFLICT (user_id) DO UPDATE
              SET filename = EXCLUDED.filename,
                  resume_url = EXCLUDED.resume_url,
                  raw_text = EXCLUDED.raw_text,
                  parsed_data = EXCLUDED.parsed_data,
                  updated_at = NOW()
            RETURNING filename, resume_url, parsed_data, updated_at
            """,
            current_user.id,
            filename,
            resume_url,
            raw_text,
            json.dumps(parsed_data),
        )

    return _row_to_response(row)


@router.get("/me/resume", response_model=Optional[ProfileResumeResponse])
async def get_my_resume(current_user: CurrentUser = Depends(get_current_user)):
    """Return the caller's parsed resume, or null if none uploaded."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT filename, resume_url, parsed_data, updated_at FROM user_resumes WHERE user_id = $1",
            current_user.id,
        )
    if not row:
        return None
    return _row_to_response(row)


@router.delete("/me/resume", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_resume(current_user: CurrentUser = Depends(get_current_user)):
    """Delete the caller's profile resume."""
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM user_resumes WHERE user_id = $1",
            current_user.id,
        )
    return None


class TierInfoResponse(BaseModel):
    is_recruiter: bool
    recruiter_until: Optional[str]


class CheckoutUrlResponse(BaseModel):
    checkout_url: str


class RecruiterCheckoutRequest(BaseModel):
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


@router.get("/me/tier", response_model=TierInfoResponse)
async def get_my_tier(current_user: CurrentUser = Depends(get_current_user)):
    """Return the caller's subscription tier info — mainly whether the
    Matcha Recruiter upgrade is currently active.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT recruiter_until,
                   (recruiter_until IS NOT NULL AND recruiter_until > NOW()) AS is_recruiter
            FROM users WHERE id = $1
            """,
            current_user.id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return TierInfoResponse(
        is_recruiter=bool(row["is_recruiter"]),
        recruiter_until=row["recruiter_until"].isoformat() if row["recruiter_until"] else None,
    )


@router.post("/me/recruiter-checkout", response_model=CheckoutUrlResponse)
async def start_recruiter_checkout(
    body: RecruiterCheckoutRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Start a Stripe checkout session for the Matcha Recruiter monthly
    subscription. The webhook flips users.recruiter_until on success.
    """
    stripe_service = StripeService()
    try:
        session = await stripe_service.create_recruiter_tier_checkout(
            user_id=current_user.id,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
    except Exception as e:
        logger.error("Recruiter checkout failed for user %s: %s", current_user.id, e)
        raise HTTPException(status_code=500, detail="Could not start recruiter checkout")

    url = getattr(session, "url", None)
    if not url:
        raise HTTPException(status_code=500, detail="Stripe returned no checkout URL")
    return CheckoutUrlResponse(checkout_url=url)


async def _is_recruiter(conn, user_id) -> bool:
    """Check if the given user currently has an active recruiter tier."""
    return bool(
        await conn.fetchval(
            "SELECT recruiter_until > NOW() FROM users WHERE id = $1",
            user_id,
        )
    )


@router.get("/{user_id}/resume", response_model=Optional[ProfileResumeResponse])
async def get_user_resume_as_recruiter(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Fetch another user's live profile resume — only allowed if the caller
    has posted a channel job posting that user applied to. Used so recruiters
    can see an applicant's current profile alongside the submit-time snapshot.
    """
    async with get_connection() as conn:
        # Authorization: caller must be the recruiter on a posting that
        # the target user has applied to.
        allowed = await conn.fetchval(
            """
            SELECT 1
            FROM channel_job_applications app
            JOIN channel_job_postings jp ON jp.id = app.posting_id
            WHERE app.applicant_id = $1 AND jp.posted_by = $2
            LIMIT 1
            """,
            user_id,
            current_user.id,
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Not authorized to view this resume")
        # Gate: only Matcha Recruiter tier users can read parsed resumes.
        if not await _is_recruiter(conn, current_user.id):
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "recruiter_tier_required",
                    "message": "Upgrade to Matcha Recruiter to view parsed applicant resumes.",
                },
            )

        row = await conn.fetchrow(
            "SELECT filename, resume_url, parsed_data, updated_at FROM user_resumes WHERE user_id = $1",
            user_id,
        )
    if not row:
        return None
    return _row_to_response(row)
