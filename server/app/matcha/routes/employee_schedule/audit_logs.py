"""Tenant-scoped query and CSV export for published-shift edit history."""

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client

from ._shared import require_company_id


router = APIRouter()

_QUERY_LIMIT = 200
_EXPORT_LIMIT = 10_000
_PUBLISHED_EDIT_FILTER = """
(
    (sal.action IN ('shift.update', 'shift.delete')
     AND sal.details->>'was_published' = 'true')
    OR
    (sal.action IN ('assignment.create', 'assignment.delete')
     AND sal.details->>'shift_status' = 'published'
     AND COALESCE(sal.details->>'request_type', '') NOT IN ('swap', 'pickup')
     AND NOT EXISTS (
         SELECT 1
         FROM schedule_requests sr
         WHERE sr.company_id = sal.company_id
           AND sr.id::text = sal.details->>'request_id'
           AND sr.request_type IN ('swap', 'pickup')
     ))
)
"""


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _details(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _csv_cell(value: Any) -> Any:
    """Keep user-controlled labels inert when the CSV opens in a spreadsheet."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _audit_filters(
    company_id: UUID,
    *,
    start: datetime | None,
    end: datetime | None,
    shift_id: UUID | None,
    actor_user_id: UUID | None,
    employee_id: UUID | None,
) -> tuple[str, list[Any]]:
    params: list[Any] = [company_id]
    where = ["sal.company_id = $1", _PUBLISHED_EDIT_FILTER]
    for value, expression in (
        (start, "sal.created_at >= ${}"),
        (end, "sal.created_at < ${}"),
        (shift_id, "sal.entity_id = ${}"),
        (actor_user_id, "sal.actor_user_id = ${}"),
    ):
        if value is not None:
            params.append(value)
            where.append(expression.format(len(params)))
    if employee_id is not None:
        params.append(str(employee_id))
        position = len(params)
        where.append(
            f"(sal.details->>'employee_id' = ${position} OR "
            f"sal.details->'assigned_employee_ids' ? ${position})"
        )
    return " AND ".join(where), params


async def _fetch_audit_rows(
    conn,
    company_id: UUID,
    *,
    start: datetime | None,
    end: datetime | None,
    shift_id: UUID | None,
    actor_user_id: UUID | None,
    employee_id: UUID | None,
    limit: int,
    offset: int = 0,
):
    where, params = _audit_filters(
        company_id,
        start=start,
        end=end,
        shift_id=shift_id,
        actor_user_id=actor_user_id,
        employee_id=employee_id,
    )
    params.extend((limit, offset))
    return await conn.fetch(
        f"""
        SELECT sal.id, sal.entity_id AS shift_id, sal.actor_user_id, sal.action,
               sal.details, sal.created_at, u.email AS actor_email,
               COALESCE(c.name, a.name, u.email) AS actor_name
        FROM schedule_audit_log sal
        LEFT JOIN users u ON u.id = sal.actor_user_id
        LEFT JOIN clients c ON c.user_id = sal.actor_user_id
        LEFT JOIN admins a ON a.user_id = sal.actor_user_id
        WHERE {where}
        ORDER BY sal.created_at DESC, sal.id DESC
        LIMIT ${len(params) - 1} OFFSET ${len(params)}
        """,
        *params,
    )


async def _count_audit_rows(
    conn,
    company_id: UUID,
    *,
    start: datetime | None,
    end: datetime | None,
    shift_id: UUID | None,
    actor_user_id: UUID | None,
    employee_id: UUID | None,
) -> int:
    where, params = _audit_filters(
        company_id,
        start=start,
        end=end,
        shift_id=shift_id,
        actor_user_id=actor_user_id,
        employee_id=employee_id,
    )
    return int(await conn.fetchval(
        f"SELECT COUNT(*) FROM schedule_audit_log sal WHERE {where}",
        *params,
    ))


async def _serialize_rows(conn, company_id: UUID, rows) -> list[dict]:
    parsed = [(row, _details(row["details"])) for row in rows]
    employee_ids: set[UUID] = set()
    for _, details in parsed:
        raw_ids = [details.get("employee_id"), *details.get("assigned_employee_ids", [])]
        for value in raw_ids:
            if value:
                try:
                    employee_ids.add(UUID(str(value)))
                except ValueError:
                    continue

    employees = {}
    if employee_ids:
        employee_rows = await conn.fetch(
            """
            SELECT id, first_name, last_name
            FROM employees
            WHERE org_id = $1 AND id = ANY($2::uuid[])
            """,
            company_id,
            list(employee_ids),
        )
        employees = {
            str(row["id"]): {
                "id": str(row["id"]),
                "name": " ".join(filter(None, (row["first_name"], row["last_name"]))).strip(),
            }
            for row in employee_rows
        }

    result = []
    for row, details in parsed:
        raw_ids = [details.get("employee_id"), *details.get("assigned_employee_ids", [])]
        assigned = []
        seen = set()
        for value in raw_ids:
            key = str(value) if value else None
            if key and key not in seen:
                seen.add(key)
                assigned.append(employees.get(key, {"id": key, "name": None}))
        fields = details.get("fields", [])
        before = details.get("before")
        after = details.get("after")
        if row["action"] in ("assignment.create", "assignment.delete"):
            assignment = {
                "employee_id": details.get("employee_id"),
                "shift_starts_at": details.get("shift_starts_at"),
                "shift_ends_at": details.get("shift_ends_at"),
                "shift_status": details.get("shift_status"),
                "location_id": details.get("location_id"),
            }
            fields = ["assignment"]
            before = assignment if row["action"] == "assignment.delete" else None
            after = assignment if row["action"] == "assignment.create" else None
        elif row["action"] == "shift.delete":
            fields = ["deleted"]
        result.append({
            "id": str(row["id"]),
            "timestamp": row["created_at"].isoformat(),
            "shift_id": str(row["shift_id"]) if row["shift_id"] else None,
            "action": row["action"],
            "modifying_user": {
                "id": str(row["actor_user_id"]) if row["actor_user_id"] else None,
                "name": row["actor_name"],
                "email": row["actor_email"],
            },
            "assigned_employees": assigned,
            "fields": fields,
            "before": before,
            "after": after,
            "details": details,
        })
    return result


def _validate_window(start: datetime | None, end: datetime | None) -> tuple[datetime | None, datetime | None]:
    start = _utc(start)
    end = _utc(end)
    if start is not None and end is not None and end <= start:
        raise HTTPException(status_code=422, detail="end must be after start")
    return start, end


@router.get("/audit-logs")
async def list_published_shift_audit_logs(
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    shift_id: UUID | None = Query(None),
    actor_user_id: UUID | None = Query(None),
    employee_id: UUID | None = Query(None),
    limit: int = Query(_QUERY_LIMIT, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user=Depends(require_admin_or_client),
):
    """List manager/admin changes to shifts that were already published."""
    company_id = await require_company_id(current_user)
    start, end = _validate_window(start, end)
    async with get_connection() as conn:
        rows = await _fetch_audit_rows(
            conn,
            company_id,
            start=start,
            end=end,
            shift_id=shift_id,
            actor_user_id=actor_user_id,
            employee_id=employee_id,
            limit=limit,
            offset=offset,
        )
        total = await _count_audit_rows(
            conn,
            company_id,
            start=start,
            end=end,
            shift_id=shift_id,
            actor_user_id=actor_user_id,
            employee_id=employee_id,
        )
        logs = await _serialize_rows(conn, company_id, rows)
    return {"logs": logs, "total": total}


@router.get("/audit-logs/export")
async def export_published_shift_audit_logs(
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    shift_id: UUID | None = Query(None),
    actor_user_id: UUID | None = Query(None),
    employee_id: UUID | None = Query(None),
    current_user=Depends(require_admin_or_client),
):
    """Export the same filtered published-shift audit view as UTF-8 CSV."""
    company_id = await require_company_id(current_user)
    start, end = _validate_window(start, end)
    async with get_connection() as conn:
        rows = await _fetch_audit_rows(
            conn,
            company_id,
            start=start,
            end=end,
            shift_id=shift_id,
            actor_user_id=actor_user_id,
            employee_id=employee_id,
            limit=_EXPORT_LIMIT + 1,
        )
        if len(rows) > _EXPORT_LIMIT:
            raise HTTPException(
                status_code=413,
                detail="Export exceeds 10,000 rows; narrow the date or employee filters",
            )
        logs = await _serialize_rows(conn, company_id, rows)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "timestamp", "shift_id", "action", "modifying_user_id",
        "modifying_user", "modifying_user_email", "assigned_employees",
        "fields", "before", "after", "details",
    ])
    for log in logs:
        actor = log["modifying_user"]
        writer.writerow([
            log["timestamp"],
            log["shift_id"],
            log["action"],
            actor["id"],
            _csv_cell(actor["name"]),
            _csv_cell(actor["email"]),
            _csv_cell("; ".join(employee["name"] or employee["id"] for employee in log["assigned_employees"])),
            ", ".join(log["fields"]),
            json.dumps(log["before"], sort_keys=True) if log["before"] is not None else "",
            json.dumps(log["after"], sort_keys=True) if log["after"] is not None else "",
            json.dumps(log["details"], sort_keys=True),
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="published-shift-audit-log.csv"'},
    )
