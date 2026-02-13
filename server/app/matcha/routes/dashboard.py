"""Dashboard stats endpoint — returns company-scoped metrics."""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ...core.models.auth import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()


class PendingIncident(BaseModel):
    id: UUID
    incident_number: str
    title: str
    severity: str


class ActivityItem(BaseModel):
    action: str
    timestamp: datetime
    type: str  # 'success' | 'warning' | 'neutral'


class IncidentSummary(BaseModel):
    total_open: int
    critical: int
    high: int
    medium: int
    low: int
    recent_7_days: int


class DashboardStats(BaseModel):
    active_policies: int
    pending_signatures: int
    total_employees: int
    compliance_rate: float
    pending_incidents: List[PendingIncident]
    recent_activity: List[ActivityItem]
    incident_summary: Optional[IncidentSummary] = None


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get dashboard stats scoped to the user's company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return DashboardStats(
            active_policies=0,
            pending_signatures=0,
            total_employees=0,
            compliance_rate=0.0,
            pending_incidents=[],
            recent_activity=[],
        )

    async with get_connection() as conn:
        # Active policies
        active_policies = await conn.fetchval(
            "SELECT COUNT(*) FROM policies WHERE company_id = $1 AND status = 'active'",
            company_id,
        ) or 0

        # Pending signatures
        pending_signatures = await conn.fetchval(
            """SELECT COUNT(*) FROM policy_signatures ps
               JOIN policies p ON ps.policy_id = p.id
               WHERE p.company_id = $1 AND ps.status = 'pending'""",
            company_id,
        ) or 0

        # Total employees (active only)
        total_employees = await conn.fetchval(
            "SELECT COUNT(*) FROM employees WHERE org_id = $1 AND termination_date IS NULL",
            company_id,
        ) or 0

        # Compliance rate: signed / total signatures for active policies
        sig_stats = await conn.fetchrow(
            """SELECT
                 COUNT(*) FILTER (WHERE ps.status = 'signed') AS signed_count,
                 COUNT(*) AS total_count
               FROM policy_signatures ps
               JOIN policies p ON ps.policy_id = p.id
               WHERE p.company_id = $1 AND p.status = 'active'""",
            company_id,
        )
        if sig_stats and sig_stats["total_count"] > 0:
            compliance_rate = round(
                (sig_stats["signed_count"] / sig_stats["total_count"]) * 100, 1
            )
        else:
            compliance_rate = 0.0

        # Pending incidents (reported, investigating, or action_required)
        incident_rows = await conn.fetch(
            """SELECT id, incident_number, title, severity
               FROM ir_incidents
               WHERE company_id = $1 AND status IN ('reported', 'investigating', 'action_required')
               ORDER BY occurred_at DESC
               LIMIT 5""",
            company_id,
        )
        pending_incidents = [
            PendingIncident(
                id=row["id"],
                incident_number=row["incident_number"],
                title=row["title"],
                severity=row["severity"] or "medium",
            )
            for row in incident_rows
        ]

        # Incident summary (open incidents by severity + recent 7 days)
        ir_severity_rows = await conn.fetch(
            """SELECT severity, COUNT(*) AS cnt
               FROM ir_incidents
               WHERE company_id = $1 AND status IN ('reported', 'investigating', 'action_required')
               GROUP BY severity""",
            company_id,
        )
        severity_map = {row["severity"]: row["cnt"] for row in ir_severity_rows}
        total_open = sum(severity_map.values())

        recent_7_days = await conn.fetchval(
            """SELECT COUNT(*) FROM ir_incidents
               WHERE company_id = $1 AND created_at >= NOW() - INTERVAL '7 days'""",
            company_id,
        ) or 0

        incident_summary = IncidentSummary(
            total_open=total_open,
            critical=severity_map.get("critical", 0),
            high=severity_map.get("high", 0),
            medium=severity_map.get("medium", 0),
            low=severity_map.get("low", 0),
            recent_7_days=recent_7_days,
        )

        # Recent activity from audit log
        activity_rows = await conn.fetch(
            """SELECT al.action, al.created_at, al.details
               FROM ir_audit_log al
               JOIN ir_incidents i ON al.incident_id = i.id
               WHERE i.company_id = $1
               ORDER BY al.created_at DESC
               LIMIT 10""",
            company_id,
        )
        recent_activity = []
        for row in activity_rows:
            action_type = "neutral"
            action_str = row["action"]
            if "resolved" in action_str or "closed" in action_str:
                action_type = "success"
            elif "created" in action_str or "flagged" in action_str:
                action_type = "warning"
            recent_activity.append(
                ActivityItem(
                    action=_format_action(action_str, row["details"]),
                    timestamp=row["created_at"],
                    type=action_type,
                )
            )

    return DashboardStats(
        active_policies=active_policies,
        pending_signatures=pending_signatures,
        total_employees=total_employees,
        compliance_rate=compliance_rate,
        pending_incidents=pending_incidents,
        recent_activity=recent_activity,
        incident_summary=incident_summary,
    )


def _format_action(action: str, details: dict | None) -> str:
    """Format an audit log action into a human-readable string."""
    labels = {
        "incident_created": "New incident report created",
        "incident_updated": "Incident report updated",
        "status_changed": "Incident status changed",
        "note_added": "Note added to incident",
        "document_uploaded": "Document uploaded to incident",
        "analysis_generated": "AI analysis generated for incident",
    }
    base = labels.get(action, action.replace("_", " ").title())
    if details and isinstance(details, dict):
        title = details.get("title") or details.get("incident_number")
        if title:
            base = f"{base}: {title}"
    return base
