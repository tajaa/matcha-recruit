"""Case read-only views: audit log, retaliation risk, investigation interviews, linked incidents, claims-readiness PDF."""
import json
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Response, Query

from ....database import get_connection
from ...dependencies import require_admin_or_client, get_client_company_id
from ....core.models.auth import CurrentUser
from ...services import claims_readiness
from ...models.er_case import (
    AuditLogEntry,
    AuditLogResponse,
)

from ._shared import (
    logger,
    _verify_case_company,
)

router = APIRouter()


@router.get("/{case_id}/audit-log", response_model=AuditLogResponse)
async def get_audit_log(
    case_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get audit log for a case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")
        rows = await conn.fetch(
            """
            SELECT id, case_id, user_id, action, entity_type, entity_id, details, ip_address, created_at
            FROM er_audit_log
            WHERE case_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            case_id,
            limit,
            offset,
        )

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM er_audit_log WHERE case_id = $1",
            case_id,
        )

        entries = [
            AuditLogEntry(
                id=row["id"],
                case_id=row["case_id"],
                user_id=row["user_id"],
                action=row["action"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                details=row["details"],
                ip_address=row["ip_address"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return AuditLogResponse(entries=entries, total=total or 0)


# ===========================================
# Retaliation Risk
# ===========================================

@router.get("/{case_id}/retaliation-risk")
async def get_retaliation_risk(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: UUID = Depends(get_client_company_id),
):
    """Check for retaliation risk: adverse actions against involved employees after case creation."""
    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")

        # Get the case details
        case_row = await conn.fetchrow(
            "SELECT id, created_at, involved_employees FROM er_cases WHERE id = $1",
            case_id,
        )
        if not case_row:
            raise HTTPException(status_code=404, detail="Case not found")

        case_created = case_row["created_at"]
        if case_created and case_created.tzinfo is None:
            case_created = case_created.replace(tzinfo=timezone.utc)

        # Parse involved employees
        involved = case_row["involved_employees"]
        if isinstance(involved, str):
            try:
                involved = json.loads(involved)
            except (json.JSONDecodeError, TypeError):
                involved = []
        if not isinstance(involved, list):
            involved = []

        events: list[dict[str, Any]] = []
        at_risk = False

        for entry in involved:
            if not isinstance(entry, dict):
                continue
            emp_id_str = entry.get("employee_id")
            if not emp_id_str:
                continue

            try:
                emp_id = UUID(str(emp_id_str))
            except (ValueError, TypeError):
                continue

            # Get employee name
            emp_row = await conn.fetchrow(
                "SELECT first_name, last_name FROM employees WHERE id = $1",
                emp_id,
            )
            emp_name = "Unknown"
            if emp_row:
                first = emp_row["first_name"] or ""
                last = emp_row["last_name"] or ""
                emp_name = f"{first} {last}".strip() or "Unknown"

            # Check progressive_discipline after case creation
            try:
                disc_rows = await conn.fetch(
                    """
                    SELECT id, discipline_type, issued_date
                    FROM progressive_discipline
                    WHERE employee_id = $1 AND company_id = $2
                      AND issued_date >= $3
                    ORDER BY issued_date ASC
                    """,
                    emp_id, company_id, case_created,
                )
                for row in disc_rows:
                    issued = row["issued_date"]
                    if issued:
                        if isinstance(issued, date) and not isinstance(issued, datetime):
                            issued_dt = datetime.combine(issued, datetime.min.time(), tzinfo=timezone.utc)
                        elif issued.tzinfo is None:
                            issued_dt = issued.replace(tzinfo=timezone.utc)
                        else:
                            issued_dt = issued
                        days_since = (issued_dt - case_created).days
                        events.append({
                            "employee_id": str(emp_id),
                            "employee_name": emp_name,
                            "event_type": f"discipline:{row['discipline_type']}",
                            "event_date": issued.isoformat() if hasattr(issued, 'isoformat') else str(issued),
                            "days_since_case": days_since,
                        })
                        at_risk = True
            except Exception:
                logger.warning("progressive_discipline query failed for retaliation risk check")

            # Check involuntary offboarding after case creation
            try:
                offb_rows = await conn.fetch(
                    """
                    SELECT id, started_at
                    FROM offboarding_cases
                    WHERE employee_id = $1 AND is_voluntary = false
                      AND started_at >= $2
                    ORDER BY started_at ASC
                    """,
                    emp_id, case_created,
                )
                for row in offb_rows:
                    started = row["started_at"]
                    if started:
                        if started.tzinfo is None:
                            started = started.replace(tzinfo=timezone.utc)
                        days_since = (started - case_created).days
                        events.append({
                            "employee_id": str(emp_id),
                            "employee_name": emp_name,
                            "event_type": "involuntary_termination",
                            "event_date": started.isoformat(),
                            "days_since_case": days_since,
                        })
                        at_risk = True
            except Exception:
                logger.warning("offboarding_cases query failed for retaliation risk check")

        # Sort events by days_since_case ascending
        events.sort(key=lambda x: x["days_since_case"])

        return {"at_risk": at_risk, "events": events}


# ===========================================
# Investigation Interview Linked Data (Phase 2)
# ===========================================

@router.get("/{case_id}/investigation-interviews")
async def get_case_investigation_interviews(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List investigation interviews linked to this ER case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")

        rows = await conn.fetch(
            """
            SELECT irii.id, irii.incident_id, irii.interview_id, irii.interviewee_role,
                   irii.interviewee_name, irii.interviewee_email, irii.status,
                   irii.created_at, irii.completed_at,
                   i.transcript IS NOT NULL as has_transcript,
                   i.investigation_analysis
            FROM ir_investigation_interviews irii
            JOIN interviews i ON irii.interview_id = i.id
            WHERE irii.er_case_id = $1
            ORDER BY irii.created_at DESC
            """,
            case_id,
        )

        results = []
        for row in rows:
            analysis = row["investigation_analysis"]
            if isinstance(analysis, str):
                analysis = json.loads(analysis)
            results.append({
                "id": str(row["id"]),
                "incident_id": str(row["incident_id"]),
                "interview_id": str(row["interview_id"]),
                "interviewee_role": row["interviewee_role"],
                "interviewee_name": row["interviewee_name"],
                "interviewee_email": row["interviewee_email"],
                "status": row["status"],
                "has_transcript": row["has_transcript"],
                "investigation_analysis": analysis,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
            })
        return results


@router.get("/{case_id}/linked-incidents")
async def get_case_linked_incidents(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return IR incidents linked to this ER case via er_case_id."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_connection() as conn:
        await _verify_case_company(conn, case_id, company_id, current_user.role == "admin")

        rows = await conn.fetch(
            """
            SELECT id, incident_number, title, incident_type, severity, status,
                   occurred_at, location, reported_by_name, created_at
            FROM ir_incidents
            WHERE er_case_id = $1
            ORDER BY occurred_at DESC
            """,
            case_id,
        )

        return [
            {
                "id": str(row["id"]),
                "incident_number": row["incident_number"],
                "title": row["title"],
                "incident_type": row["incident_type"],
                "severity": row["severity"],
                "status": row["status"],
                "occurred_at": row["occurred_at"].isoformat() if row["occurred_at"] else None,
                "location": row["location"],
                "reported_by_name": row["reported_by_name"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]


@router.get("/{case_id}/claims-readiness.pdf")
async def er_case_claims_readiness_pdf(
    case_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Claims-readiness / defense packet (PDF) for an ER case."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Case not found")
    async with get_connection() as conn:
        data = await claims_readiness.build_er_packet(conn, case_id, company_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Case not found")
    pdf = await claims_readiness.render_er_packet_pdf(data)
    num = str(data["case"].get("case_number") or case_id).replace("/", "-").replace('"', "")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="claims-readiness-{num}.pdf"'},
    )
