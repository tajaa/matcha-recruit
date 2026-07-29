"""Global (non-project) manual task board + auto-populated deadline feed.

Moved here from routes/matcha_work/workspace.py (2026-07-28) — the data is
core HR-ops deadlines (credentials, incidents, training, compliance), not a
matcha-work concern, and it was previously stranded behind the matcha_work
feature gate. `_UPCOMING_SOURCES` etc. come straight from `.upcoming` now
instead of the lazy cross-package import workspace.py used to need.

Route order: /tasks/dismiss is registered before /tasks/{task_id} — the
opposite order (as it was in workspace.py) means Starlette matches
DELETE /tasks/dismiss against /tasks/{task_id} first and 422s on UUID
coercion, since task_id used a plain (non-UUID) path param. Fixed here.
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.routes.dashboard.upcoming import _UPCOMING_SOURCES, _apply_company_filter, _severity_from_days

router = APIRouter()


@router.post("/tasks/dismiss")
async def dismiss_auto_task(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Dismiss an auto-populated task item."""
    cat = body.get("source_category", "")
    sid = body.get("source_id", "")
    if not cat or not sid:
        raise HTTPException(status_code=400, detail="source_category and source_id required")
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO mw_task_dismissals (user_id, source_category, source_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, source_category, source_id) DO NOTHING
            """,
            current_user.id, cat, sid,
        )
    return {"status": "dismissed"}


@router.delete("/tasks/dismiss")
async def undismiss_auto_task(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Un-dismiss a previously dismissed auto-populated task."""
    cat = body.get("source_category", "")
    sid = body.get("source_id", "")
    if not cat or not sid:
        raise HTTPException(status_code=400, detail="source_category and source_id required")
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM mw_task_dismissals WHERE user_id = $1 AND source_category = $2 AND source_id = $3",
            current_user.id, cat, sid,
        )
    return {"status": "restored"}


@router.get("/tasks")
async def list_tasks(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Combined task board: auto-populated items + manual tasks + dismissals."""
    from datetime import date as _date, timedelta as _td

    company_id = await get_client_company_id(current_user)
    today = _date.today()
    lookahead = today + _td(days=90)

    # 1. Auto-populated items from upcoming sources
    auto_items = []
    async with get_connection() as conn:
        import asyncpg as _asyncpg
        for source in _UPCOMING_SOURCES:
            try:
                sql = _apply_company_filter(source["sql"], company_id)
                uses_p1 = "$1" in sql
                uses_p2 = "$2" in sql
                if uses_p1 and uses_p2:
                    rows = await conn.fetch(sql, company_id, lookahead)
                elif uses_p1:
                    rows = await conn.fetch(sql, company_id)
                elif uses_p2:
                    rows = await conn.fetch(sql, lookahead)
                else:
                    rows = await conn.fetch(sql)
            except (_asyncpg.UndefinedTableError, _asyncpg.UndefinedColumnError):
                continue
            except Exception:
                continue
            for row in rows:
                deadline = row["deadline"]
                if deadline is None:
                    continue
                days_until = (deadline - today).days
                link = source["link"]
                row_id = row.get("id")
                if row_id and "{id}" in link:
                    link = link.replace("{id}", row_id)
                auto_items.append({
                    "category": source["category"],
                    "source_id": row.get("id") or "",
                    "title": row["title"] or source["category"].title(),
                    "subtitle": row.get("subtitle"),
                    "date": str(deadline),
                    "days_until": days_until,
                    "severity": _severity_from_days(days_until),
                    "link": link,
                })

    auto_items.sort(key=lambda x: x["days_until"])

    # 2. Manual tasks
    manual_items = []
    async with get_connection() as conn:
        try:
            rows = await conn.fetch(
                """
                SELECT id, title, description, due_date, horizon, priority, status,
                       completed_at, link, category, created_at, updated_at
                FROM mw_tasks
                WHERE company_id = $1 AND status != 'cancelled' AND project_id IS NULL
                ORDER BY
                    CASE WHEN status = 'completed' THEN 1 ELSE 0 END,
                    due_date ASC NULLS LAST,
                    created_at DESC
                """,
                company_id,
            )
            for r in rows:
                d = dict(r)
                d["id"] = str(d["id"])
                d["source"] = "manual"
                if d["due_date"]:
                    d["days_until"] = (d["due_date"] - today).days
                    d["date"] = str(d["due_date"])
                else:
                    d["days_until"] = None
                    d["date"] = None
                manual_items.append(d)
        except Exception:
            pass  # table may not exist yet

    # 3. Dismissed IDs
    dismissed_ids = []
    async with get_connection() as conn:
        try:
            rows = await conn.fetch(
                "SELECT source_category, source_id FROM mw_task_dismissals WHERE user_id = $1",
                current_user.id,
            )
            dismissed_ids = [f"{r['source_category']}:{r['source_id']}" for r in rows]
        except Exception:
            pass

    return {
        "auto_items": auto_items,
        "manual_items": manual_items,
        "dismissed_ids": dismissed_ids,
        "total": len(auto_items) + len(manual_items),
    }


@router.post("/tasks", status_code=201)
async def create_task(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a manual task."""
    from datetime import date as _date

    company_id = await get_client_company_id(current_user)
    if not company_id:
        raise HTTPException(status_code=400, detail="No company associated")

    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    due_date = body.get("due_date")
    if due_date and isinstance(due_date, str):
        due_date = _date.fromisoformat(due_date)

    horizon = body.get("horizon")
    priority = body.get("priority", "medium")
    if priority not in ("critical", "high", "medium", "low"):
        priority = "medium"

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_tasks (company_id, created_by, title, description, due_date, horizon, priority, link)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            company_id, current_user.id, title,
            body.get("description"), due_date, horizon, priority, body.get("link"),
        )
    d = dict(row)
    d["id"] = str(d["id"])
    d["company_id"] = str(d["company_id"])
    d["created_by"] = str(d["created_by"])
    d["source"] = "manual"
    if d.get("due_date"):
        d["days_until"] = (d["due_date"] - _date.today()).days
        d["date"] = str(d["due_date"])
    else:
        d["days_until"] = None
        d["date"] = None
    return d


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update a manual task."""
    company_id = await get_client_company_id(current_user)

    allowed = {"title", "description", "due_date", "horizon", "priority", "status", "link"}
    sets = []
    vals = []
    idx = 1
    for k, v in body.items():
        if k in allowed:
            if k == "due_date" and isinstance(v, str):
                from datetime import date as _date
                v = _date.fromisoformat(v)
            sets.append(f"{k} = ${idx}")
            vals.append(v)
            idx += 1

    if not sets:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    # Auto-fill completed_at
    if body.get("status") == "completed":
        sets.append(f"completed_at = ${idx}")
        vals.append(datetime.now(timezone.utc))
        idx += 1
    elif body.get("status") == "pending":
        sets.append(f"completed_at = ${idx}")
        vals.append(None)
        idx += 1

    sets.append(f"updated_at = NOW()")
    vals.extend([task_id, company_id])

    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"UPDATE mw_tasks SET {', '.join(sets)} WHERE id = ${idx} AND company_id = ${idx + 1} RETURNING *",
            *vals,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    d = dict(row)
    d["id"] = str(d["id"])
    d["source"] = "manual"
    return d


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Cancel a manual task."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE mw_tasks SET status = 'cancelled', updated_at = NOW() WHERE id = $1 AND company_id = $2",
            task_id, company_id,
        )
    return {"status": "cancelled"}
