"""Audit log endpoint for IR Incidents.

Reads the `ir_audit_log` table for a given incident. Writes happen via
`log_audit()` in `_legacy.py` (will move to `_shared.py` in step 10).
"""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.ir_incident import IRAuditLogEntry, IRAuditLogResponse


router = APIRouter()


@router.get("/{incident_id}/audit-log", response_model=IRAuditLogResponse)
async def get_audit_log(
    incident_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(require_admin_or_client),
):
    """Get the audit log for an incident."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    company_clause = "company_id = $2"

    async with get_connection() as conn:
        incident = await conn.fetchrow(
            f"SELECT id FROM ir_incidents WHERE id = $1 AND {company_clause}",
            str(incident_id),
            company_id,
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM ir_audit_log WHERE incident_id = $1",
            str(incident_id),
        )

        rows = await conn.fetch(
            """
            SELECT * FROM ir_audit_log
            WHERE incident_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            str(incident_id),
            limit,
            offset,
        )

        entries = [
            IRAuditLogEntry(
                id=row["id"],
                incident_id=row["incident_id"],
                user_id=row["user_id"],
                action=row["action"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                details=json.loads(row["details"]) if row["details"] else None,
                ip_address=row["ip_address"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return IRAuditLogResponse(entries=entries, total=total or 0)
