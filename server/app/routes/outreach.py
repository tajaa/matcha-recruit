"""API routes for project outreach and candidate screening."""
import secrets
import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from ..database import get_connection
from ..config import get_settings
from ..services.email import get_email_service
from ..models.outreach import (
    OutreachSendRequest,
    OutreachSendResult,
    OutreachResponse,
    OutreachPublicInfo,
    OutreachInterestResponse,
    InterviewStartResponse,
    OutreachStatus,
)

router = APIRouter()


def generate_token() -> str:
    """Generate a unique token for outreach links."""
    return secrets.token_urlsafe(32)


def format_salary_range(salary_min: Optional[int], salary_max: Optional[int]) -> Optional[str]:
    """Format salary range for display."""
    if not salary_min and not salary_max:
        return None
    fmt = lambda n: f"${n:,}"
    if salary_min and salary_max:
        return f"{fmt(salary_min)} - {fmt(salary_max)}"
    if salary_min:
        return f"{fmt(salary_min)}+"
    return f"Up to {fmt(salary_max)}"


# ============================================================================
# Admin endpoints (require auth - handled by router prefix)
# ============================================================================

@router.post("/projects/{project_id}/outreach", response_model=OutreachSendResult)
async def send_outreach(project_id: UUID, request: OutreachSendRequest):
    """Send outreach emails to selected candidates in a project."""
    email_service = get_email_service()
    settings = get_settings()

    async with get_connection() as conn:
        # Get project details
        project = await conn.fetchrow(
            """
            SELECT company_name, name, position_title, location, salary_min, salary_max, requirements, benefits
            FROM projects WHERE id = $1
            """,
            project_id,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        salary_range = format_salary_range(project["salary_min"], project["salary_max"])

        sent_count = 0
        failed_count = 0
        skipped_count = 0
        errors = []

        for candidate_id in request.candidate_ids:
            # Get candidate details
            candidate = await conn.fetchrow(
                "SELECT id, name, email FROM candidates WHERE id = $1",
                candidate_id,
            )
            if not candidate:
                errors.append({"candidate_id": str(candidate_id), "error": "Candidate not found"})
                failed_count += 1
                continue

            if not candidate["email"]:
                errors.append({"candidate_id": str(candidate_id), "error": "No email address"})
                skipped_count += 1
                continue

            # Check if outreach already exists
            existing = await conn.fetchval(
                "SELECT id FROM project_outreach WHERE project_id = $1 AND candidate_id = $2",
                project_id,
                candidate_id,
            )
            if existing:
                skipped_count += 1
                continue

            # Generate token and create outreach record
            token = generate_token()

            await conn.execute(
                """
                INSERT INTO project_outreach (project_id, candidate_id, token, status, email_sent_at)
                VALUES ($1, $2, $3, $4, NOW())
                """,
                project_id,
                candidate_id,
                token,
                OutreachStatus.SENT.value,
            )

            # Send email
            success = await email_service.send_outreach_email(
                to_email=candidate["email"],
                to_name=candidate["name"],
                company_name=project["company_name"],
                position_title=project["position_title"] or project["name"],
                location=project["location"],
                salary_range=salary_range,
                outreach_token=token,
                custom_message=request.custom_message,
            )

            if success:
                sent_count += 1
            else:
                # Email failed but record created - mark as failed
                await conn.execute(
                    "UPDATE project_outreach SET status = 'email_failed' WHERE token = $1",
                    token,
                )
                errors.append({"candidate_id": str(candidate_id), "error": "Email send failed"})
                failed_count += 1

        return OutreachSendResult(
            sent_count=sent_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            errors=errors,
        )


@router.get("/projects/{project_id}/outreach", response_model=list[OutreachResponse])
async def list_project_outreach(project_id: UUID, status: Optional[str] = None):
    """List all outreach records for a project."""
    async with get_connection() as conn:
        # Verify project exists
        project = await conn.fetchval("SELECT id FROM projects WHERE id = $1", project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if status:
            rows = await conn.fetch(
                """
                SELECT o.*, c.name as candidate_name, c.email as candidate_email
                FROM project_outreach o
                JOIN candidates c ON o.candidate_id = c.id
                WHERE o.project_id = $1 AND o.status = $2
                ORDER BY o.created_at DESC
                """,
                project_id,
                status,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT o.*, c.name as candidate_name, c.email as candidate_email
                FROM project_outreach o
                JOIN candidates c ON o.candidate_id = c.id
                WHERE o.project_id = $1
                ORDER BY o.created_at DESC
                """,
                project_id,
            )

        return [
            OutreachResponse(
                id=row["id"],
                project_id=row["project_id"],
                candidate_id=row["candidate_id"],
                candidate_name=row["candidate_name"],
                candidate_email=row["candidate_email"],
                token=row["token"],
                status=row["status"],
                email_sent_at=row["email_sent_at"],
                interest_response_at=row["interest_response_at"],
                interview_id=row["interview_id"],
                screening_score=row["screening_score"],
                screening_recommendation=row["screening_recommendation"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


# ============================================================================
# Public endpoints (no auth - token-based access)
# ============================================================================

@router.get("/outreach/{token}", response_model=OutreachPublicInfo)
async def get_outreach_info(token: str):
    """Get public info for an outreach link (candidate landing page)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT o.*, p.company_name, p.name as project_name, p.position_title,
                   p.location, p.salary_min, p.salary_max, p.requirements, p.benefits,
                   c.name as candidate_name
            FROM project_outreach o
            JOIN projects p ON o.project_id = p.id
            JOIN candidates c ON o.candidate_id = c.id
            WHERE o.token = $1
            """,
            token,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Invalid or expired link")

        # Mark as opened if still in sent status
        if row["status"] == OutreachStatus.SENT.value:
            await conn.execute(
                "UPDATE project_outreach SET status = $1 WHERE token = $2",
                OutreachStatus.OPENED.value,
                token,
            )

        return OutreachPublicInfo(
            company_name=row["company_name"],
            position_title=row["position_title"] or row["project_name"],
            location=row["location"],
            salary_range=format_salary_range(row["salary_min"], row["salary_max"]),
            requirements=row["requirements"],
            benefits=row["benefits"],
            status=row["status"],
            candidate_name=row["candidate_name"],
        )


@router.post("/outreach/{token}/respond", response_model=OutreachInterestResponse)
async def respond_to_outreach(token: str, interested: bool = True):
    """Record candidate's interest response."""
    settings = get_settings()

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, status, project_id, candidate_id FROM project_outreach WHERE token = $1",
            token,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Invalid or expired link")

        # Check if already responded
        if row["status"] in (
            OutreachStatus.INTERESTED.value,
            OutreachStatus.DECLINED.value,
            OutreachStatus.SCREENING_STARTED.value,
            OutreachStatus.SCREENING_COMPLETE.value,
        ):
            if row["status"] == OutreachStatus.DECLINED.value:
                return OutreachInterestResponse(
                    status="declined",
                    message="You've already declined this opportunity.",
                )
            return OutreachInterestResponse(
                status=row["status"],
                message="You've already responded to this opportunity.",
                interview_url=f"{settings.app_base_url}/outreach/{token}/screening" if row["status"] != OutreachStatus.DECLINED.value else None,
            )

        if interested:
            await conn.execute(
                """
                UPDATE project_outreach
                SET status = $1, interest_response_at = NOW()
                WHERE token = $2
                """,
                OutreachStatus.INTERESTED.value,
                token,
            )
            return OutreachInterestResponse(
                status="interested",
                message="Great! You can now proceed to the screening interview.",
                interview_url=f"{settings.app_base_url}/outreach/{token}/screening",
            )
        else:
            await conn.execute(
                """
                UPDATE project_outreach
                SET status = $1, interest_response_at = NOW()
                WHERE token = $2
                """,
                OutreachStatus.DECLINED.value,
                token,
            )

            # Also update candidate stage in project to rejected
            await conn.execute(
                """
                UPDATE project_candidates
                SET stage = 'rejected', notes = COALESCE(notes, '') || E'\\nDeclined outreach.', updated_at = NOW()
                WHERE project_id = $1 AND candidate_id = $2
                """,
                row["project_id"],
                row["candidate_id"],
            )

            return OutreachInterestResponse(
                status="declined",
                message="Thank you for letting us know. We'll keep you in mind for future opportunities.",
            )


@router.post("/outreach/{token}/start-interview", response_model=InterviewStartResponse)
async def start_screening_interview(token: str):
    """Start a screening interview for the outreach candidate."""
    settings = get_settings()

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT o.id, o.status, o.project_id, o.candidate_id, o.interview_id,
                   p.company_name, c.name as candidate_name
            FROM project_outreach o
            JOIN projects p ON o.project_id = p.id
            JOIN candidates c ON o.candidate_id = c.id
            WHERE o.token = $1
            """,
            token,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Invalid or expired link")

        # Must have expressed interest first
        if row["status"] not in (
            OutreachStatus.INTERESTED.value,
            OutreachStatus.SCREENING_STARTED.value,
        ):
            raise HTTPException(
                status_code=400,
                detail="Please express interest first before starting the interview.",
            )

        # If interview already exists, return it
        if row["interview_id"]:
            return InterviewStartResponse(
                interview_id=row["interview_id"],
                websocket_url=f"/api/ws/interview/{row['interview_id']}",
            )

        # Get or create a company for this project (use existing or create temporary)
        # For now, we'll create the interview without a company_id or with a dummy one
        # since screening interviews don't strictly need company culture context

        # Create the screening interview
        interview_row = await conn.fetchrow(
            """
            INSERT INTO interviews (interviewer_name, interview_type, status)
            VALUES ($1, 'screening', 'pending')
            RETURNING id
            """,
            row["candidate_name"] or "Candidate",
        )

        interview_id = interview_row["id"]

        # Update outreach with interview reference
        await conn.execute(
            """
            UPDATE project_outreach
            SET interview_id = $1, status = $2
            WHERE token = $3
            """,
            interview_id,
            OutreachStatus.SCREENING_STARTED.value,
            token,
        )

        return InterviewStartResponse(
            interview_id=interview_id,
            websocket_url=f"/api/ws/interview/{interview_id}",
        )


@router.post("/outreach/screening-complete/{interview_id}")
async def handle_screening_complete(interview_id: UUID):
    """
    Called when a screening interview completes.
    Updates outreach status and candidate stage based on results.
    """
    async with get_connection() as conn:
        # Get the outreach record for this interview
        outreach = await conn.fetchrow(
            """
            SELECT o.id, o.project_id, o.candidate_id, o.token
            FROM project_outreach o
            WHERE o.interview_id = $1
            """,
            interview_id,
        )

        if not outreach:
            # Not an outreach interview, skip
            return {"status": "skipped", "message": "Not an outreach interview"}

        # Get the screening analysis from the interview
        interview = await conn.fetchrow(
            "SELECT screening_analysis FROM interviews WHERE id = $1",
            interview_id,
        )

        if not interview or not interview["screening_analysis"]:
            return {"status": "pending", "message": "Analysis not yet available"}

        analysis = json.loads(interview["screening_analysis"]) if isinstance(interview["screening_analysis"], str) else interview["screening_analysis"]

        overall_score = analysis.get("overall_score", 0)
        recommendation = analysis.get("recommendation", "fail")

        # Update outreach record
        await conn.execute(
            """
            UPDATE project_outreach
            SET status = $1, screening_score = $2, screening_recommendation = $3
            WHERE id = $4
            """,
            OutreachStatus.SCREENING_COMPLETE.value,
            overall_score,
            recommendation,
            outreach["id"],
        )

        # Update candidate stage in project based on recommendation
        new_stage = "initial"  # Default
        notes_addition = f"Screening score: {overall_score:.0f}% - {recommendation}"

        if recommendation == "strong_pass":
            new_stage = "interview"
            notes_addition += " - Advanced to interview round"
        elif recommendation == "pass":
            new_stage = "screening"
            notes_addition += " - Passed initial screening"
        elif recommendation == "borderline":
            new_stage = "initial"
            notes_addition += " - Needs review"
        else:  # fail
            new_stage = "rejected"
            notes_addition += " - Did not pass screening"

        await conn.execute(
            """
            UPDATE project_candidates
            SET stage = $1, notes = COALESCE(notes, '') || E'\\n' || $2, updated_at = NOW()
            WHERE project_id = $3 AND candidate_id = $4
            """,
            new_stage,
            notes_addition,
            outreach["project_id"],
            outreach["candidate_id"],
        )

        return {
            "status": "updated",
            "recommendation": recommendation,
            "score": overall_score,
            "new_stage": new_stage,
        }
