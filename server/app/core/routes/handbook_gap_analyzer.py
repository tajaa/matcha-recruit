"""Free-tier Handbook Gap Analyzer endpoints.

Surface:
    POST /resources/handbook-gap-analyzer/analyze
        Authed business user (any tier — surfaced as a Free-plan tool).
        Multipart upload (PDF + states + industry). Stores PDF, inserts a
        handbook_audit_reports row keyed to the user, kicks the Celery worker.

    GET /resources/handbook-gap-analyzer/report/{report_id}
        Authed business user. Owner = user_id match (or email fallback for
        legacy rows). Non-owners receive 403.

Gating to authed callers prevents anonymous abuse — running an audit always
requires a Free-tier signup at minimum.
"""

import json
import logging
import re
from datetime import timedelta
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from ...database import get_connection
from ..models.auth import CurrentUser
from ..services.redis_cache import check_rate_limit, client_ip
from ..services.storage import get_storage
from ...matcha.dependencies import require_client

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MiB
MAX_STATES_PER_REPORT = 6
MAX_AUDITS_PER_ACCOUNT_PER_MONTH = 2  # hard cap; resets at the start of each calendar month
IP_RATE_LIMIT_KEY = "handbook_gap_analyzer:ip"
IP_RATE_LIMIT_PER_DAY = 12  # belt-and-suspenders against one IP fanning out via many accounts
STATE_CODE_RE = re.compile(r"^[A-Z]{2}$")
SAMPLE_GAPS_LIMIT = 2


def _parse_states(raw: str) -> list[str]:
    if not raw:
        return []
    parts = [p.strip().upper() for p in raw.replace(";", ",").split(",")]
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if not p or p in seen:
            continue
        if not STATE_CODE_RE.match(p):
            raise HTTPException(status_code=400, detail=f"Invalid state code: {p}")
        seen.add(p)
        out.append(p)
    return out


def _summarize_gaps(report: dict[str, Any]) -> dict[str, Any]:
    counts = report.get("gap_counts") or {}
    if isinstance(counts, str):
        try:
            counts = json.loads(counts)
        except json.JSONDecodeError:
            counts = {}

    sample = counts.pop("sample_gaps", []) if isinstance(counts, dict) else []
    return {
        "status": report.get("status"),
        "states": report.get("states") or [],
        "industry": report.get("industry"),
        "gap_counts": {
            "critical": int(counts.get("critical", 0)),
            "important": int(counts.get("important", 0)),
            "recommended": int(counts.get("recommended", 0)),
            "total_gaps": int(counts.get("total_gaps", 0)),
            "total_states": int(counts.get("total_states", len(report.get("states") or []))),
            "by_state": counts.get("by_state") or {},
        },
        "sample_gaps": sample[:SAMPLE_GAPS_LIMIT],
        "created_at": report["created_at"].isoformat() if report.get("created_at") else None,
        "completed_at": report["completed_at"].isoformat() if report.get("completed_at") else None,
    }


@router.get("/quota")
async def get_audit_quota(
    current_user: CurrentUser = Depends(require_client),
):
    """Returns how many audits the caller has run this calendar month and the
    remaining allowance. Lets the UI render a quota chip before upload."""
    from datetime import datetime, timezone

    async with get_connection() as conn:
        used = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM handbook_audit_reports
            WHERE user_id = $1
              AND created_at >= date_trunc('month', NOW())
            """,
            current_user.id,
        )
    used = int(used or 0)
    now = datetime.now(timezone.utc)
    next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    return {
        "used": used,
        "limit": MAX_AUDITS_PER_ACCOUNT_PER_MONTH,
        "remaining": max(0, MAX_AUDITS_PER_ACCOUNT_PER_MONTH - used),
        "resets_at": next_month.isoformat(),
    }


@router.post("/analyze")
async def submit_handbook_for_analysis(
    request: Request,
    pdf: UploadFile = File(...),
    states: str = Form(...),
    industry: Optional[str] = Form(None),
    current_user: CurrentUser = Depends(require_client),
):
    """Authed handbook upload. Returns a report_id the client polls."""
    state_list = _parse_states(states)
    if not state_list:
        raise HTTPException(status_code=400, detail="At least one state is required")
    if len(state_list) > MAX_STATES_PER_REPORT:
        raise HTTPException(
            status_code=400,
            detail=f"Pick at most {MAX_STATES_PER_REPORT} states for a single audit",
        )

    content_type = (pdf.content_type or "").lower()
    filename = (pdf.filename or "").lower()
    if "pdf" not in content_type and not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Upload must be a PDF")

    pdf_bytes = await pdf.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="PDF is empty")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF must be 10MB or smaller")

    # Hard per-account cap: 2 audits per calendar month. Counts every attempt
    # (success or failure) so a user gets exactly one retry if the first run
    # errored. Resets at the first of the next month.
    async with get_connection() as conn:
        used_this_month = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM handbook_audit_reports
            WHERE user_id = $1
              AND created_at >= date_trunc('month', NOW())
            """,
            current_user.id,
        )
    used_this_month = int(used_this_month or 0)
    if used_this_month >= MAX_AUDITS_PER_ACCOUNT_PER_MONTH:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
        raise HTTPException(
            status_code=429,
            detail=(
                f"You've used your {MAX_AUDITS_PER_ACCOUNT_PER_MONTH} handbook audits "
                f"for this month. Quota resets {next_month.strftime('%B %-d, %Y')}."
            ),
        )

    # Belt-and-suspenders IP guard against one network spinning up many accounts.
    ip = client_ip(request) or "unknown"
    try:
        await check_rate_limit(
            ip,
            IP_RATE_LIMIT_KEY,
            IP_RATE_LIMIT_PER_DAY,
            24 * 60 * 60,
        )
    except HTTPException:
        raise
    except Exception:
        pass

    try:
        storage_path = await get_storage().upload_private_file(
            pdf_bytes,
            filename or "handbook.pdf",
            prefix="handbook-audits",
            content_type="application/pdf",
        )
    except Exception as exc:
        logger.exception("Handbook PDF upload failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not store the uploaded PDF")

    industry_clean = (industry or "").strip().lower()[:64] or None
    user_email = (current_user.email or "").strip().lower() or None

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO handbook_audit_reports
                (email, user_id, states, industry, pdf_storage_path, status)
            VALUES ($1, $2, $3::text[], $4, $5, 'processing')
            RETURNING id
            """,
            user_email,
            current_user.id,
            state_list,
            industry_clean,
            storage_path,
        )
    report_id = str(row["id"])

    try:
        from app.workers.tasks.handbook_audit import analyze_handbook_audit
        analyze_handbook_audit.delay(report_id)
    except Exception as exc:
        logger.exception("Could not enqueue handbook audit task: %s", exc)
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE handbook_audit_reports SET status='failed', error_text=$2 WHERE id=$1",
                report_id,
                f"Worker enqueue failed: {exc}"[:1000],
            )
        raise HTTPException(
            status_code=503,
            detail="The audit worker is unavailable. Try again in a few minutes.",
        )

    return {"report_id": report_id, "status": "processing"}


@router.get("/report/{report_id}")
async def get_handbook_audit_report(
    report_id: UUID,
    current_user: CurrentUser = Depends(require_client),
):
    """Polling endpoint. Returns the full report when the caller owns it."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, email, user_id, states, industry, status,
                   gap_counts, gaps_jsonb, error_text,
                   created_at, completed_at
            FROM handbook_audit_reports
            WHERE id = $1
            """,
            report_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    report = dict(row)

    user_email = (current_user.email or "").lower() or None
    is_owner = bool(
        (report.get("user_id") and str(report["user_id"]) == str(current_user.id))
        or (user_email and report.get("email") and user_email == report["email"].lower())
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="This report belongs to another account")

    if isinstance(report.get("gap_counts"), str):
        try:
            report["gap_counts"] = json.loads(report["gap_counts"])
        except json.JSONDecodeError:
            report["gap_counts"] = {}

    summary = _summarize_gaps(report)
    summary["report_id"] = str(report["id"])
    summary["is_owner"] = True
    if report["status"] == "failed":
        summary["error"] = (report.get("error_text") or "Audit failed")[:400]

    # Backfill user_id on legacy/email-matched rows so future GETs are fast.
    if not report.get("user_id"):
        try:
            async with get_connection() as conn:
                await conn.execute(
                    "UPDATE handbook_audit_reports SET user_id = $2 WHERE id = $1",
                    report["id"],
                    current_user.id,
                )
        except Exception as exc:
            logger.warning("Could not backfill user_id on report %s: %s", report["id"], exc)

    gaps_raw = report.get("gaps_jsonb")
    if isinstance(gaps_raw, str):
        try:
            gaps_raw = json.loads(gaps_raw)
        except json.JSONDecodeError:
            gaps_raw = []
    summary["gaps"] = gaps_raw or []
    return summary
