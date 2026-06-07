"""Fractional HR admin tooling.

Internal master-admin vertical for running HR fractionally on behalf of client
companies. Admin-only (mounted under ``require_admin``). Surfaces:

  * an aggregate book-of-business view across all engagements, and
  * per-client management of scope, hours (retainer burn), and tasks.

The client companies may or may not be existing platform tenants — ``company_id``
on ``fractional_clients`` is nullable so a net-new client can be tracked without
standing up a login.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...core.dependencies import require_admin
from ...core.models.auth import CurrentUser
from ...database import get_connection
from ..models.fractional_hr import (
    SERVICE_CATEGORIES,
    AssignmentCreateRequest,
    ClientCreateRequest,
    ClientUpdateRequest,
    ScopeItemCreateRequest,
    ScopeItemUpdateRequest,
    TaskCreateRequest,
    TaskUpdateRequest,
    TimeEntryCreateRequest,
)

router = APIRouter()

_PERIOD_BUCKET = {"weekly": "wk_hours", "monthly": "mo_hours", "quarterly": "qtr_hours"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _f(value) -> Optional[float]:
    """asyncpg returns Decimal for NUMERIC; normalize to float for JSON."""
    return float(value) if value is not None else None


def _client_out(row) -> dict:
    """Serialize a fractional_clients row. The pool has no JSONB codec, so
    ``jurisdictions`` comes back as a JSON string — parse it to a list."""
    d = dict(row)
    j = d.get("jurisdictions")
    if isinstance(j, str):
        try:
            parsed = json.loads(j)
            d["jurisdictions"] = parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            d["jurisdictions"] = []
    return d


async def _log_audit(conn, client_id, actor_id, action: str, detail: dict | None = None) -> None:
    await conn.execute(
        """
        INSERT INTO fractional_audit_log (client_id, actor_id, action, detail)
        VALUES ($1, $2, $3, $4::jsonb)
        """,
        client_id,
        actor_id,
        action,
        json.dumps(detail or {}),
    )


def _hours_summary(client: dict, period_logged: float, total_logged: float) -> dict:
    """Compute the billing-model-aware hours/utilization picture for a client."""
    model = client["billing_model"]
    budget = _f(client.get("retainer_hours"))
    summary = {
        "billing_model": model,
        "retainer_period": client.get("retainer_period"),
        "total_logged": round(total_logged, 2),
        "budget": budget,
        "used": None,
        "remaining": None,
        "utilization_pct": None,
        "basis": None,
    }
    if model == "monthly_retainer":
        used = period_logged
        summary.update(basis="period", used=round(used, 2))
        if budget:
            summary["remaining"] = round(budget - used, 2)
            summary["utilization_pct"] = round(used / budget * 100, 1)
    elif model == "hours_block":
        used = total_logged
        summary.update(basis="block", used=round(used, 2))
        if budget:
            summary["remaining"] = round(budget - used, 2)
            summary["utilization_pct"] = round(used / budget * 100, 1)
    elif model == "project_fixed":
        summary.update(basis="project", used=round(total_logged, 2), project_fee=_f(client.get("project_fee")))
    else:  # hourly
        rate = _f(client.get("billing_rate"))
        summary.update(basis="hourly", used=round(total_logged, 2), billing_rate=rate)
        if rate is not None:
            summary["billable_amount"] = round(total_logged * rate, 2)
    return summary


async def _get_client_or_404(conn, client_id: str) -> dict:
    try:
        cid = UUID(client_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Client not found")
    row = await conn.fetchrow("SELECT * FROM fractional_clients WHERE id = $1", cid)
    if not row:
        raise HTTPException(status_code=404, detail="Client not found")
    return _client_out(row)


def _uuid_or_none(value: Optional[str]) -> Optional[UUID]:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid id: {value}")


# --------------------------------------------------------------------------- #
# Metadata / pickers
# --------------------------------------------------------------------------- #
@router.get("/meta")
async def get_meta(_admin: CurrentUser = Depends(require_admin)):
    return {
        "service_categories": SERVICE_CATEGORIES,
        "billing_models": ["monthly_retainer", "hours_block", "project_fixed", "hourly"],
        "client_statuses": ["prospect", "active", "paused", "offboarded"],
        "task_statuses": ["todo", "in_progress", "blocked", "review", "done"],
        "scope_statuses": ["planned", "active", "on_hold", "done"],
        "priorities": ["low", "medium", "high"],
        "assignment_roles": ["lead", "consultant", "jr"],
    }


@router.get("/pros")
async def list_pros(_admin: CurrentUser = Depends(require_admin)):
    """Admin users who can be assigned to engagements."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT id, email, role FROM users WHERE role = 'admin' AND is_active = true ORDER BY email"
        )
    return {"pros": [dict(r) for r in rows]}


@router.get("/linkable-companies")
async def linkable_companies(
    q: Optional[str] = Query(default=None, max_length=255),
    _admin: CurrentUser = Depends(require_admin),
):
    """Existing tenants a fractional client can be linked to (for jump-into-tooling)."""
    async with get_connection() as conn:
        if q:
            rows = await conn.fetch(
                """
                SELECT id, name, industry, status FROM companies
                WHERE deleted_at IS NULL AND name ILIKE $1
                ORDER BY name LIMIT 50
                """,
                f"%{q}%",
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, name, industry, status FROM companies
                WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 50
                """
            )
    return {"companies": [dict(r) for r in rows]}


# --------------------------------------------------------------------------- #
# Aggregate overview (book of business)
# --------------------------------------------------------------------------- #
@router.get("/overview")
async def overview(_admin: CurrentUser = Depends(require_admin)):
    async with get_connection() as conn:
        status_counts = await conn.fetch(
            "SELECT status, COUNT(*) AS n FROM fractional_clients GROUP BY status"
        )
        committed = await conn.fetchval(
            """
            SELECT COALESCE(SUM(retainer_hours), 0) FROM fractional_clients
            WHERE status = 'active' AND billing_model = 'monthly_retainer'
            """
        )
        logged_month = await conn.fetchval(
            """
            SELECT COALESCE(SUM(hours), 0) FROM fractional_time_entries
            WHERE entry_date >= date_trunc('month', CURRENT_DATE)
            """
        )
        task_stats = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE status <> 'done') AS open_tasks,
                COUNT(*) FILTER (WHERE status <> 'done' AND due_date < CURRENT_DATE) AS overdue_tasks,
                COUNT(*) FILTER (WHERE status = 'done'
                    AND completed_at >= date_trunc('month', CURRENT_DATE)) AS completed_this_month
            FROM fractional_tasks
            """
        )
        by_category = await conn.fetch(
            """
            SELECT service_category, COUNT(*) AS n FROM fractional_tasks
            WHERE status <> 'done' GROUP BY service_category ORDER BY n DESC
            """
        )
        # Per-pro load: clients led + open tasks assigned + hours logged this month.
        pro_load = await conn.fetch(
            """
            SELECT u.id, u.email,
                (SELECT COUNT(*) FROM fractional_clients c
                    WHERE c.lead_pro_id = u.id AND c.status = 'active') AS clients_led,
                (SELECT COUNT(*) FROM fractional_tasks t
                    WHERE t.assignee_pro_id = u.id AND t.status <> 'done') AS open_tasks,
                (SELECT COALESCE(SUM(te.hours), 0) FROM fractional_time_entries te
                    WHERE te.pro_id = u.id
                    AND te.entry_date >= date_trunc('month', CURRENT_DATE)) AS hours_month
            FROM users u
            WHERE u.role = 'admin' AND u.is_active = true
            AND (
                EXISTS (SELECT 1 FROM fractional_clients c WHERE c.lead_pro_id = u.id)
                OR EXISTS (SELECT 1 FROM fractional_assignments a WHERE a.pro_user_id = u.id)
                OR EXISTS (SELECT 1 FROM fractional_time_entries te WHERE te.pro_id = u.id)
            )
            ORDER BY hours_month DESC
            """
        )
        # At-risk: monthly retainer over budget this month, or has overdue tasks.
        at_risk = await conn.fetch(
            """
            SELECT c.id, c.name, c.status, c.billing_model, c.retainer_hours,
                COALESCE(mo.hours, 0) AS month_hours,
                COALESCE(t.overdue, 0) AS overdue_tasks
            FROM fractional_clients c
            LEFT JOIN (
                SELECT client_id, SUM(hours) AS hours FROM fractional_time_entries
                WHERE entry_date >= date_trunc('month', CURRENT_DATE)
                GROUP BY client_id
            ) mo ON mo.client_id = c.id
            LEFT JOIN (
                SELECT client_id, COUNT(*) AS overdue FROM fractional_tasks
                WHERE status <> 'done' AND due_date < CURRENT_DATE
                GROUP BY client_id
            ) t ON t.client_id = c.id
            WHERE c.status IN ('active', 'paused')
            AND (
                COALESCE(t.overdue, 0) > 0
                OR (c.billing_model = 'monthly_retainer' AND c.retainer_hours IS NOT NULL
                    AND COALESCE(mo.hours, 0) > c.retainer_hours)
            )
            ORDER BY overdue_tasks DESC, month_hours DESC
            """
        )

    return {
        "status_counts": {r["status"]: r["n"] for r in status_counts},
        "committed_retainer_hours": _f(committed),
        "hours_logged_this_month": _f(logged_month),
        "open_tasks": task_stats["open_tasks"] if task_stats else 0,
        "overdue_tasks": task_stats["overdue_tasks"] if task_stats else 0,
        "tasks_completed_this_month": task_stats["completed_this_month"] if task_stats else 0,
        "work_by_category": [{"service_category": r["service_category"], "count": r["n"]} for r in by_category],
        "pro_load": [
            {
                "id": r["id"],
                "email": r["email"],
                "clients_led": r["clients_led"],
                "open_tasks": r["open_tasks"],
                "hours_month": _f(r["hours_month"]),
            }
            for r in pro_load
        ],
        "at_risk": [
            {
                "id": r["id"],
                "name": r["name"],
                "status": r["status"],
                "billing_model": r["billing_model"],
                "retainer_hours": _f(r["retainer_hours"]),
                "month_hours": _f(r["month_hours"]),
                "overdue_tasks": r["overdue_tasks"],
            }
            for r in at_risk
        ],
    }


# --------------------------------------------------------------------------- #
# Clients (engagements)
# --------------------------------------------------------------------------- #
@router.get("/clients")
async def list_clients(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None, max_length=255),
    _admin: CurrentUser = Depends(require_admin),
):
    async with get_connection() as conn:
        conditions = []
        params: list = []
        if status_filter:
            params.append(status_filter)
            conditions.append(f"c.status = ${len(params)}")
        if q:
            params.append(f"%{q}%")
            conditions.append(f"c.name ILIKE ${len(params)}")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        clients = await conn.fetch(
            f"""
            SELECT c.*, comp.name AS company_name, u.email AS lead_pro_email
            FROM fractional_clients c
            LEFT JOIN companies comp ON comp.id = c.company_id
            LEFT JOIN users u ON u.id = c.lead_pro_id
            {where}
            ORDER BY c.created_at DESC
            """,
            *params,
        )
        hours = await conn.fetch(
            """
            SELECT client_id,
                COALESCE(SUM(hours), 0) AS total,
                COALESCE(SUM(hours) FILTER (WHERE entry_date >= date_trunc('week', CURRENT_DATE)), 0) AS wk_hours,
                COALESCE(SUM(hours) FILTER (WHERE entry_date >= date_trunc('month', CURRENT_DATE)), 0) AS mo_hours,
                COALESCE(SUM(hours) FILTER (WHERE entry_date >= date_trunc('quarter', CURRENT_DATE)), 0) AS qtr_hours
            FROM fractional_time_entries GROUP BY client_id
            """
        )
        tasks = await conn.fetch(
            """
            SELECT client_id,
                COUNT(*) FILTER (WHERE status <> 'done') AS open_tasks,
                COUNT(*) FILTER (WHERE status <> 'done' AND due_date < CURRENT_DATE) AS overdue_tasks
            FROM fractional_tasks GROUP BY client_id
            """
        )

    hours_by = {r["client_id"]: r for r in hours}
    tasks_by = {r["client_id"]: r for r in tasks}
    result = []
    for row in clients:
        c = _client_out(row)
        h = hours_by.get(c["id"])
        period_bucket = _PERIOD_BUCKET.get(c["retainer_period"], "mo_hours")
        period_logged = _f(h[period_bucket]) if h else 0.0
        total_logged = _f(h["total"]) if h else 0.0
        t = tasks_by.get(c["id"])
        c["hours_summary"] = _hours_summary(c, period_logged or 0.0, total_logged or 0.0)
        c["open_tasks"] = t["open_tasks"] if t else 0
        c["overdue_tasks"] = t["overdue_tasks"] if t else 0
        result.append(c)
    return {"clients": result}


@router.post("/clients", status_code=status.HTTP_201_CREATED)
async def create_client(body: ClientCreateRequest, admin: CurrentUser = Depends(require_admin)):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO fractional_clients (
                name, company_id, status, billing_model, retainer_hours, retainer_period,
                rollover_unused, billing_rate, project_fee, currency, industry, headcount,
                jurisdictions, contact_name, contact_email, contact_phone, lead_pro_id,
                start_date, notes, created_by
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb,
                $14, $15, $16, $17, $18, $19, $20
            ) RETURNING *
            """,
            body.name,
            _uuid_or_none(body.company_id),
            body.status,
            body.billing_model,
            body.retainer_hours,
            body.retainer_period,
            body.rollover_unused,
            body.billing_rate,
            body.project_fee,
            body.currency,
            body.industry,
            body.headcount,
            json.dumps(body.jurisdictions),
            body.contact_name,
            body.contact_email,
            body.contact_phone,
            _uuid_or_none(body.lead_pro_id),
            body.start_date,
            body.notes,
            admin.id,
        )
        await _log_audit(conn, row["id"], admin.id, "client.create", {"name": body.name})
    return _client_out(row)


@router.get("/clients/{client_id}")
async def get_client(client_id: str, _admin: CurrentUser = Depends(require_admin)):
    async with get_connection() as conn:
        client = await _get_client_or_404(conn, client_id)
        cid = client["id"]
        company = None
        if client["company_id"]:
            company = await conn.fetchrow(
                "SELECT id, name, industry, status FROM companies WHERE id = $1", client["company_id"]
            )
        lead = None
        if client["lead_pro_id"]:
            lead = await conn.fetchrow("SELECT id, email FROM users WHERE id = $1", client["lead_pro_id"])
        assignments = await conn.fetch(
            """
            SELECT a.id, a.role, a.pro_user_id, u.email
            FROM fractional_assignments a JOIN users u ON u.id = a.pro_user_id
            WHERE a.client_id = $1 ORDER BY a.role, u.email
            """,
            cid,
        )
        hrow = await conn.fetchrow(
            """
            SELECT
                COALESCE(SUM(hours), 0) AS total,
                COALESCE(SUM(hours) FILTER (WHERE entry_date >= date_trunc('week', CURRENT_DATE)), 0) AS wk_hours,
                COALESCE(SUM(hours) FILTER (WHERE entry_date >= date_trunc('month', CURRENT_DATE)), 0) AS mo_hours,
                COALESCE(SUM(hours) FILTER (WHERE entry_date >= date_trunc('quarter', CURRENT_DATE)), 0) AS qtr_hours
            FROM fractional_time_entries WHERE client_id = $1
            """,
            cid,
        )
        trow = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE status <> 'done') AS open_tasks,
                COUNT(*) FILTER (WHERE status <> 'done' AND due_date < CURRENT_DATE) AS overdue_tasks,
                COUNT(*) AS total_tasks
            FROM fractional_tasks WHERE client_id = $1
            """,
            cid,
        )

    period_bucket = _PERIOD_BUCKET.get(client["retainer_period"], "mo_hours")
    summary = _hours_summary(client, _f(hrow[period_bucket]) or 0.0, _f(hrow["total"]) or 0.0)
    return {
        "client": client,
        "company": dict(company) if company else None,
        "lead_pro": dict(lead) if lead else None,
        "assignments": [dict(a) for a in assignments],
        "hours_summary": summary,
        "task_counts": dict(trow),
    }


@router.patch("/clients/{client_id}")
async def update_client(client_id: str, body: ClientUpdateRequest, admin: CurrentUser = Depends(require_admin)):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    async with get_connection() as conn:
        await _get_client_or_404(conn, client_id)
        sets: list[str] = []
        params: list = []
        for key, value in fields.items():
            if key in ("company_id", "lead_pro_id"):
                value = _uuid_or_none(value)
            elif key == "jurisdictions":
                params.append(json.dumps(value))
                sets.append(f"{key} = ${len(params)}::jsonb")
                continue
            params.append(value)
            sets.append(f"{key} = ${len(params)}")
        params.append(UUID(client_id))
        row = await conn.fetchrow(
            f"UPDATE fractional_clients SET {', '.join(sets)}, updated_at = NOW() WHERE id = ${len(params)} RETURNING *",
            *params,
        )
        await _log_audit(conn, row["id"], admin.id, "client.update", {"fields": list(fields.keys())})
    return _client_out(row)


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(client_id: str, admin: CurrentUser = Depends(require_admin)):
    async with get_connection() as conn:
        client = await _get_client_or_404(conn, client_id)
        await _log_audit(conn, None, admin.id, "client.delete", {"id": str(client["id"]), "name": client["name"]})
        await conn.execute("DELETE FROM fractional_clients WHERE id = $1", client["id"])
    return None


# --------------------------------------------------------------------------- #
# Assignments (team)
# --------------------------------------------------------------------------- #
@router.post("/clients/{client_id}/assignments", status_code=status.HTTP_201_CREATED)
async def add_assignment(client_id: str, body: AssignmentCreateRequest, admin: CurrentUser = Depends(require_admin)):
    pro_id = _uuid_or_none(body.pro_user_id)
    async with get_connection() as conn:
        await _get_client_or_404(conn, client_id)
        exists = await conn.fetchval("SELECT 1 FROM users WHERE id = $1 AND role = 'admin'", pro_id)
        if not exists:
            raise HTTPException(status_code=400, detail="pro_user_id must be an admin user")
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO fractional_assignments (client_id, pro_user_id, role)
                VALUES ($1, $2, $3) RETURNING id, client_id, pro_user_id, role
                """,
                UUID(client_id),
                pro_id,
                body.role,
            )
        except asyncpg.exceptions.UniqueViolationError:
            raise HTTPException(status_code=409, detail="Pro already assigned to this client")
        await _log_audit(conn, UUID(client_id), admin.id, "assignment.add", {"pro_user_id": body.pro_user_id, "role": body.role})
    return dict(row)


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_assignment(assignment_id: str, admin: CurrentUser = Depends(require_admin)):
    aid = _uuid_or_none(assignment_id)
    async with get_connection() as conn:
        row = await conn.fetchrow("SELECT client_id FROM fractional_assignments WHERE id = $1", aid)
        if not row:
            raise HTTPException(status_code=404, detail="Assignment not found")
        await conn.execute("DELETE FROM fractional_assignments WHERE id = $1", aid)
        await _log_audit(conn, row["client_id"], admin.id, "assignment.remove", {"assignment_id": assignment_id})
    return None


# --------------------------------------------------------------------------- #
# Scope items
# --------------------------------------------------------------------------- #
@router.get("/clients/{client_id}/scope")
async def list_scope(client_id: str, _admin: CurrentUser = Depends(require_admin)):
    async with get_connection() as conn:
        await _get_client_or_404(conn, client_id)
        rows = await conn.fetch(
            "SELECT * FROM fractional_scope_items WHERE client_id = $1 ORDER BY created_at DESC",
            UUID(client_id),
        )
    return {"scope_items": [dict(r) for r in rows]}


@router.post("/clients/{client_id}/scope", status_code=status.HTTP_201_CREATED)
async def create_scope(client_id: str, body: ScopeItemCreateRequest, admin: CurrentUser = Depends(require_admin)):
    async with get_connection() as conn:
        await _get_client_or_404(conn, client_id)
        row = await conn.fetchrow(
            """
            INSERT INTO fractional_scope_items
                (client_id, service_category, title, description, status, priority, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *
            """,
            UUID(client_id),
            body.service_category,
            body.title,
            body.description,
            body.status,
            body.priority,
            admin.id,
        )
        await _log_audit(conn, UUID(client_id), admin.id, "scope.create", {"title": body.title})
    return dict(row)


@router.patch("/scope/{scope_id}")
async def update_scope(scope_id: str, body: ScopeItemUpdateRequest, admin: CurrentUser = Depends(require_admin)):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    sid = _uuid_or_none(scope_id)
    async with get_connection() as conn:
        existing = await conn.fetchrow("SELECT client_id FROM fractional_scope_items WHERE id = $1", sid)
        if not existing:
            raise HTTPException(status_code=404, detail="Scope item not found")
        sets = [f"{k} = ${i + 1}" for i, k in enumerate(fields.keys())]
        params = list(fields.values())
        params.append(sid)
        row = await conn.fetchrow(
            f"UPDATE fractional_scope_items SET {', '.join(sets)}, updated_at = NOW() WHERE id = ${len(params)} RETURNING *",
            *params,
        )
        await _log_audit(conn, existing["client_id"], admin.id, "scope.update", {"fields": list(fields.keys())})
    return dict(row)


@router.delete("/scope/{scope_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scope(scope_id: str, admin: CurrentUser = Depends(require_admin)):
    sid = _uuid_or_none(scope_id)
    async with get_connection() as conn:
        existing = await conn.fetchrow("SELECT client_id FROM fractional_scope_items WHERE id = $1", sid)
        if not existing:
            raise HTTPException(status_code=404, detail="Scope item not found")
        await conn.execute("DELETE FROM fractional_scope_items WHERE id = $1", sid)
        await _log_audit(conn, existing["client_id"], admin.id, "scope.delete", {"scope_id": scope_id})
    return None


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #
@router.get("/clients/{client_id}/tasks")
async def list_tasks(
    client_id: str,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    _admin: CurrentUser = Depends(require_admin),
):
    async with get_connection() as conn:
        await _get_client_or_404(conn, client_id)
        params: list = [UUID(client_id)]
        clause = ""
        if status_filter:
            params.append(status_filter)
            clause = f" AND t.status = ${len(params)}"
        rows = await conn.fetch(
            f"""
            SELECT t.*, u.email AS assignee_email, s.title AS scope_title
            FROM fractional_tasks t
            LEFT JOIN users u ON u.id = t.assignee_pro_id
            LEFT JOIN fractional_scope_items s ON s.id = t.scope_item_id
            WHERE t.client_id = $1{clause}
            ORDER BY (t.status = 'done'), t.due_date NULLS LAST, t.created_at DESC
            """,
            *params,
        )
    return {"tasks": [dict(r) for r in rows]}


@router.post("/clients/{client_id}/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(client_id: str, body: TaskCreateRequest, admin: CurrentUser = Depends(require_admin)):
    async with get_connection() as conn:
        await _get_client_or_404(conn, client_id)
        completed_at = datetime.utcnow() if body.status == "done" else None
        row = await conn.fetchrow(
            """
            INSERT INTO fractional_tasks (
                client_id, scope_item_id, title, description, service_category, status,
                priority, assignee_pro_id, due_date, estimated_hours, billable, created_by, completed_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13) RETURNING *
            """,
            UUID(client_id),
            _uuid_or_none(body.scope_item_id),
            body.title,
            body.description,
            body.service_category,
            body.status,
            body.priority,
            _uuid_or_none(body.assignee_pro_id),
            body.due_date,
            body.estimated_hours,
            body.billable,
            admin.id,
            completed_at,
        )
        await _log_audit(conn, UUID(client_id), admin.id, "task.create", {"title": body.title})
    return dict(row)


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, body: TaskUpdateRequest, admin: CurrentUser = Depends(require_admin)):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    tid = _uuid_or_none(task_id)
    async with get_connection() as conn:
        existing = await conn.fetchrow("SELECT client_id, status FROM fractional_tasks WHERE id = $1", tid)
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")
        sets: list[str] = []
        params: list = []
        for key, value in fields.items():
            if key in ("scope_item_id", "assignee_pro_id"):
                value = _uuid_or_none(value)
            params.append(value)
            sets.append(f"{key} = ${len(params)}")
        # Keep completed_at in sync with status transitions.
        if "status" in fields:
            if fields["status"] == "done" and existing["status"] != "done":
                sets.append("completed_at = NOW()")
            elif fields["status"] != "done":
                sets.append("completed_at = NULL")
        params.append(tid)
        row = await conn.fetchrow(
            f"UPDATE fractional_tasks SET {', '.join(sets)}, updated_at = NOW() WHERE id = ${len(params)} RETURNING *",
            *params,
        )
        await _log_audit(conn, existing["client_id"], admin.id, "task.update", {"fields": list(fields.keys())})
    return dict(row)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: str, admin: CurrentUser = Depends(require_admin)):
    tid = _uuid_or_none(task_id)
    async with get_connection() as conn:
        existing = await conn.fetchrow("SELECT client_id FROM fractional_tasks WHERE id = $1", tid)
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")
        await conn.execute("DELETE FROM fractional_tasks WHERE id = $1", tid)
        await _log_audit(conn, existing["client_id"], admin.id, "task.delete", {"task_id": task_id})
    return None


# --------------------------------------------------------------------------- #
# Time entries
# --------------------------------------------------------------------------- #
@router.get("/clients/{client_id}/time")
async def list_time(client_id: str, _admin: CurrentUser = Depends(require_admin)):
    async with get_connection() as conn:
        await _get_client_or_404(conn, client_id)
        rows = await conn.fetch(
            """
            SELECT te.*, u.email AS pro_email, t.title AS task_title
            FROM fractional_time_entries te
            LEFT JOIN users u ON u.id = te.pro_id
            LEFT JOIN fractional_tasks t ON t.id = te.task_id
            WHERE te.client_id = $1 ORDER BY te.entry_date DESC, te.created_at DESC
            """,
            UUID(client_id),
        )
    return {"time_entries": [dict(r) for r in rows]}


@router.post("/clients/{client_id}/time", status_code=status.HTTP_201_CREATED)
async def log_time(client_id: str, body: TimeEntryCreateRequest, admin: CurrentUser = Depends(require_admin)):
    pro_id = _uuid_or_none(body.pro_id) or admin.id
    async with get_connection() as conn:
        await _get_client_or_404(conn, client_id)
        row = await conn.fetchrow(
            """
            INSERT INTO fractional_time_entries
                (client_id, task_id, pro_id, hours, entry_date, note, billable, service_category)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *
            """,
            UUID(client_id),
            _uuid_or_none(body.task_id),
            pro_id,
            body.hours,
            body.entry_date or date.today(),
            body.note,
            body.billable,
            body.service_category,
        )
        await _log_audit(conn, UUID(client_id), admin.id, "time.log", {"hours": body.hours})
    return dict(row)


@router.delete("/time/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_time(entry_id: str, admin: CurrentUser = Depends(require_admin)):
    eid = _uuid_or_none(entry_id)
    async with get_connection() as conn:
        existing = await conn.fetchrow("SELECT client_id FROM fractional_time_entries WHERE id = $1", eid)
        if not existing:
            raise HTTPException(status_code=404, detail="Time entry not found")
        await conn.execute("DELETE FROM fractional_time_entries WHERE id = $1", eid)
        await _log_audit(conn, existing["client_id"], admin.id, "time.delete", {"entry_id": entry_id})
    return None
