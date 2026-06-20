"""Grievance workflow routes — the core of the Labor Relations package.

This module's ``router`` is re-exported as the package router (see
``__init__.py``); CBA/clause routes are composed onto it. Lifecycle:
draft → file (activate step 1) → respond/advance through the contractual steps
→ resolve/withdraw. Each step carries computed contractual deadlines.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.database import get_connection
from app.core.models.auth import CurrentUser
from app.core.services.storage import get_storage
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.labor_relations import (
    AdvanceRequest,
    AttachClausesRequest,
    GrievanceCreateRequest,
    GrievanceUpdateRequest,
    ResolveRequest,
    StepRespondRequest,
    WithdrawRequest,
)
from app.matcha.routes.labor_relations._shared import (
    _require_company,
    _serialize,
    _serialize_list,
    compute_step_deadlines,
    get_grievance_or_404,
    next_grievance_number,
    resolve_step_config,
    seed_grievance_steps,
    write_audit,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Resolution → terminal grievance status.
_RESOLUTION_STATUS = {
    "granted": "resolved",
    "partially_granted": "resolved",
    "arbitrated_win": "resolved",
    "denied": "denied",
    "arbitrated_loss": "denied",
    "settled": "settled",
    "withdrawn": "withdrawn",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _validate_grievance_fks(conn, company_id: UUID, fields: dict) -> None:
    """Reject any foreign-key body field that doesn't belong to the caller's
    company. Without this, a client could reference another tenant's
    employee/CBA/discipline/ER id and leak it back via the detail view.
    Employees are scoped on `org_id` (== company_id); all others on `company_id`.
    """
    for key in ("grievant_employee_id", "steward_employee_id"):
        val = fields.get(key)
        if val and not await conn.fetchval(
            "SELECT 1 FROM employees WHERE id = $1 AND org_id = $2", val, company_id,
        ):
            raise HTTPException(status_code=400, detail="Employee not found")
    if fields.get("cba_id") and not await conn.fetchval(
        "SELECT 1 FROM lr_cbas WHERE id = $1 AND company_id = $2", fields["cba_id"], company_id,
    ):
        raise HTTPException(status_code=400, detail="CBA not found")
    if fields.get("linked_discipline_id") and not await conn.fetchval(
        "SELECT 1 FROM progressive_discipline WHERE id = $1 AND company_id = $2",
        fields["linked_discipline_id"], company_id,
    ):
        raise HTTPException(status_code=400, detail="Discipline record not found")
    if fields.get("linked_er_case_id") and not await conn.fetchval(
        "SELECT 1 FROM er_cases WHERE id = $1 AND company_id = $2",
        fields["linked_er_case_id"], company_id,
    ):
        raise HTTPException(status_code=400, detail="ER case not found")
    if fields.get("assigned_to") and not await conn.fetchval(
        "SELECT 1 FROM clients WHERE user_id = $1 AND company_id = $2",
        fields["assigned_to"], company_id,
    ):
        raise HTTPException(status_code=400, detail="Assignee is not a member of this company")


async def _load_step_config(conn, grievance: dict) -> tuple[list[dict], bool]:
    """Resolve the grievance procedure (CBA config or fallback) for a grievance."""
    cba = None
    if grievance.get("cba_id"):
        cba = await conn.fetchrow(
            "SELECT grievance_step_config FROM lr_cbas WHERE id = $1 AND company_id = $2",
            grievance["cba_id"], grievance["company_id"],
        )
        cba = dict(cba) if cba else None
    return resolve_step_config(cba)


async def _grievance_detail(conn, grievance: dict) -> dict:
    """Build the full grievance detail payload."""
    gid = grievance["id"]
    steps = await conn.fetch(
        "SELECT * FROM lr_grievance_steps WHERE grievance_id = $1 ORDER BY step_number", gid,
    )
    clauses = await conn.fetch(
        """
        SELECT c.* FROM lr_cba_clauses c
        JOIN lr_grievance_violated_clauses v ON v.clause_id = c.id
        WHERE v.grievance_id = $1
        ORDER BY c.sort_order, c.created_at
        """,
        gid,
    )
    # Tenant-scope the FK reads (defense-in-depth behind write validation):
    # never expose another company's employee/CBA even if a stale id is stored.
    grievant = None
    if grievance.get("grievant_employee_id"):
        grievant = await conn.fetchrow(
            "SELECT id, first_name, last_name, job_title, department "
            "FROM employees WHERE id = $1 AND org_id = $2",
            grievance["grievant_employee_id"], grievance["company_id"],
        )
    cba = None
    if grievance.get("cba_id"):
        cba = await conn.fetchrow(
            "SELECT id, union_name, union_local, status, grievance_steps_confirmed "
            "FROM lr_cbas WHERE id = $1 AND company_id = $2",
            grievance["cba_id"], grievance["company_id"],
        )
    _, used_fallback = await _load_step_config(conn, grievance)
    out = _serialize(grievance)
    out["steps"] = _serialize_list(steps)
    out["violated_clauses"] = _serialize_list(clauses)
    out["grievant"] = _serialize(grievant)
    out["cba"] = _serialize(cba)
    out["used_fallback_steps"] = used_fallback
    return out


# ── Dashboard (registered BEFORE /{grievance_id} so it isn't shadowed) ───────

@router.get("/grievances/dashboard")
async def grievance_dashboard(
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        status_rows = await conn.fetch(
            "SELECT status, COUNT(*) AS n FROM lr_grievances WHERE company_id = $1 GROUP BY status",
            company_id,
        )
        step_rows = await conn.fetch(
            """
            SELECT current_step, COUNT(*) AS n FROM lr_grievances
            WHERE company_id = $1 AND status NOT IN ('resolved','withdrawn','denied','settled')
            GROUP BY current_step
            """,
            company_id,
        )
        overdue = await conn.fetch(
            """
            SELECT g.id, g.grievance_number, g.title, g.current_step,
                   s.step_number, s.step_name, s.deadline_to_respond
            FROM lr_grievance_steps s
            JOIN lr_grievances g ON g.id = s.grievance_id
            WHERE s.company_id = $1 AND s.status = 'active'
              AND s.deadline_to_respond IS NOT NULL
              AND s.deadline_to_respond < (NOW() AT TIME ZONE 'UTC')::date
            ORDER BY s.deadline_to_respond ASC
            """,
            company_id,
        )
        expiring = await conn.fetch(
            """
            SELECT id, union_name, expiration_date FROM lr_cbas
            WHERE company_id = $1 AND status = 'active' AND expiration_date IS NOT NULL
              AND expiration_date <= (NOW() AT TIME ZONE 'UTC')::date + (renewal_alert_days || ' days')::interval
            ORDER BY expiration_date ASC
            """,
            company_id,
        )
    return {
        "by_status": {r["status"]: r["n"] for r in status_rows},
        "by_step": {str(r["current_step"]): r["n"] for r in step_rows},
        "overdue": _serialize_list(overdue),
        "expiring_cbas": _serialize_list(expiring),
    }


# ── Grievance collection ─────────────────────────────────────────────────────

@router.get("/grievances")
async def list_grievances(
    status: Optional[str] = None,
    grievance_type: Optional[str] = None,
    employee_id: Optional[UUID] = None,
    cba_id: Optional[UUID] = None,
    overdue: bool = False,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    clauses = ["g.company_id = $1"]
    vals: list = [company_id]
    idx = 2
    if status:
        clauses.append(f"g.status = ${idx}"); vals.append(status); idx += 1
    if grievance_type:
        clauses.append(f"g.grievance_type = ${idx}"); vals.append(grievance_type); idx += 1
    if employee_id:
        clauses.append(f"g.grievant_employee_id = ${idx}"); vals.append(employee_id); idx += 1
    if cba_id:
        clauses.append(f"g.cba_id = ${idx}"); vals.append(cba_id); idx += 1
    if overdue:
        clauses.append(
            "EXISTS (SELECT 1 FROM lr_grievance_steps s WHERE s.grievance_id = g.id "
            "AND s.status = 'active' AND s.deadline_to_respond IS NOT NULL "
            "AND s.deadline_to_respond < (NOW() AT TIME ZONE 'UTC')::date)"
        )
    where = " AND ".join(clauses)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT g.*, e.first_name AS grievant_first_name, e.last_name AS grievant_last_name
            FROM lr_grievances g
            LEFT JOIN employees e ON e.id = g.grievant_employee_id AND e.org_id = g.company_id
            WHERE {where}
            ORDER BY g.created_at DESC
            """,
            *vals,
        )
    return {"grievances": _serialize_list(rows)}


@router.post("/grievances", status_code=201)
async def create_grievance(
    body: GrievanceCreateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    fields = body.model_dump(exclude_unset=True)
    async with get_connection() as conn:
        await _validate_grievance_fks(conn, company_id, fields)
        # Resolve the grievance procedure from the (ownership-checked) CBA.
        cba = None
        if body.cba_id:
            cba = await conn.fetchrow(
                "SELECT id, grievance_step_config FROM lr_cbas WHERE id = $1 AND company_id = $2",
                body.cba_id, company_id,
            )
            cba = dict(cba) if cba else None
        step_config, used_fallback = resolve_step_config(cba)

        # Retry the per-company number allocation on a concurrent collision —
        # uq_lr_grievance_number is the backstop; each attempt re-numbers in a
        # fresh transaction.
        last_exc: Optional[Exception] = None
        for _attempt in range(4):
            try:
                async with conn.transaction():
                    number = await next_grievance_number(conn, company_id)
                    row = await conn.fetchrow(
                        """
                        INSERT INTO lr_grievances
                            (company_id, grievance_number, cba_id, grievant_employee_id, is_class_grievance,
                             steward_employee_id, steward_name_external, title, description, grievance_type,
                             incident_date, assigned_to, linked_discipline_id, linked_er_case_id,
                             status, current_step, created_by)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, 'draft', 1, $15)
                        RETURNING *
                        """,
                        company_id, number, body.cba_id, body.grievant_employee_id, body.is_class_grievance,
                        body.steward_employee_id, body.steward_name_external, body.title, body.description,
                        body.grievance_type, body.incident_date, body.assigned_to, body.linked_discipline_id,
                        body.linked_er_case_id, current_user.id,
                    )
                    gid = row["id"]
                    await seed_grievance_steps(conn, gid, company_id, step_config)
                    if body.violated_clause_ids:
                        await _replace_violated_clauses(conn, gid, company_id, body.violated_clause_ids)
                    await write_audit(conn, company_id, "grievance", gid, current_user.id, "created",
                                      {"number": number, "used_fallback_steps": used_fallback})
                    return await _grievance_detail(conn, dict(row))
            except asyncpg.UniqueViolationError as exc:
                last_exc = exc
                continue
        raise HTTPException(status_code=409, detail="Could not allocate a grievance number; please retry") from last_exc


@router.get("/grievances/{grievance_id}")
async def get_grievance(
    grievance_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        grievance = await get_grievance_or_404(conn, grievance_id, company_id)
        return await _grievance_detail(conn, grievance)


@router.patch("/grievances/{grievance_id}")
async def update_grievance(
    grievance_id: UUID,
    body: GrievanceUpdateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    sets: list[str] = []
    vals: list = []
    idx = 1
    for key, value in fields.items():
        sets.append(f"{key} = ${idx}"); vals.append(value); idx += 1
    sets.append("updated_at = NOW()")
    async with get_connection() as conn:
        async with conn.transaction():
            grievance = await get_grievance_or_404(conn, grievance_id, company_id)
            await _validate_grievance_fks(conn, company_id, fields)
            cba_changed = "cba_id" in fields and fields["cba_id"] != grievance["cba_id"]
            if cba_changed and grievance["status"] != "draft":
                raise HTTPException(status_code=409, detail="Cannot change the CBA after the grievance is filed")
            vals.extend([grievance_id, company_id])
            row = await conn.fetchrow(
                f"UPDATE lr_grievances SET {', '.join(sets)} "
                f"WHERE id = ${idx} AND company_id = ${idx + 1} RETURNING *",
                *vals,
            )
            if cba_changed:
                # Re-seed the step timeline from the new CBA's procedure so the
                # steps + computed deadlines match the attached contract (draft only).
                await conn.execute("DELETE FROM lr_grievance_steps WHERE grievance_id = $1", grievance_id)
                new_cba = None
                if fields["cba_id"]:
                    new_cba = await conn.fetchrow(
                        "SELECT grievance_step_config FROM lr_cbas WHERE id = $1 AND company_id = $2",
                        fields["cba_id"], company_id,
                    )
                    new_cba = dict(new_cba) if new_cba else None
                step_config, _ = resolve_step_config(new_cba)
                await seed_grievance_steps(conn, grievance_id, company_id, step_config)
            await write_audit(conn, company_id, "grievance", grievance_id, current_user.id, "updated",
                              {"fields": list(fields.keys())})
            return await _grievance_detail(conn, dict(row))


# ── Lifecycle transitions ────────────────────────────────────────────────────

@router.post("/grievances/{grievance_id}/file")
async def file_grievance(
    grievance_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        async with conn.transaction():
            grievance = await get_grievance_or_404(conn, grievance_id, company_id)
            if grievance["status"] != "draft":
                raise HTTPException(status_code=409, detail="Grievance already filed")
            step_config, _ = await _load_step_config(conn, grievance)
            today = _utcnow().date()
            deadlines = compute_step_deadlines(step_config, 1, today)
            await conn.execute(
                """
                UPDATE lr_grievance_steps
                SET status = 'active', filed_at = NOW(),
                    deadline_to_respond = $2, deadline_to_advance = $3, updated_at = NOW()
                WHERE grievance_id = $1 AND step_number = 1
                """,
                grievance_id, deadlines["deadline_to_respond"], deadlines["deadline_to_advance"],
            )
            row = await conn.fetchrow(
                """
                UPDATE lr_grievances
                SET status = 'filed', filed_date = $2, current_step = 1, updated_at = NOW()
                WHERE id = $1 RETURNING *
                """,
                grievance_id, today,
            )
            await write_audit(conn, company_id, "grievance", grievance_id, current_user.id, "filed",
                              {"deadline_to_respond": str(deadlines["deadline_to_respond"])})
            return await _grievance_detail(conn, dict(row))


@router.post("/grievances/{grievance_id}/steps/{step_number}/respond")
async def respond_step(
    grievance_id: UUID,
    step_number: int,
    body: StepRespondRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        async with conn.transaction():
            grievance = await get_grievance_or_404(conn, grievance_id, company_id)
            step = await conn.fetchrow(
                "SELECT * FROM lr_grievance_steps WHERE grievance_id = $1 AND step_number = $2",
                grievance_id, step_number,
            )
            if not step:
                raise HTTPException(status_code=404, detail="Step not found")
            if step["status"] != "active":
                raise HTTPException(status_code=409, detail="Only the active step can receive a response")

            step_config, _ = await _load_step_config(conn, grievance)
            response_date = body.response_date or _utcnow().date()
            # The union's window to advance opens off the actual response date.
            advance_deadline = compute_step_deadlines(step_config, step_number, response_date)["deadline_to_advance"]

            await conn.execute(
                """
                UPDATE lr_grievance_steps
                SET status = 'responded', management_response = $3, union_position = $4,
                    outcome = $5, response_received_at = NOW(), deadline_to_advance = $6,
                    heard_by_user_id = $7, updated_at = NOW()
                WHERE grievance_id = $1 AND step_number = $2
                """,
                grievance_id, step_number, body.management_response, body.union_position,
                body.outcome, advance_deadline, current_user.id,
            )
            if grievance["status"] in ("filed", "advanced"):
                await conn.execute(
                    "UPDATE lr_grievances SET status = 'in_progress', updated_at = NOW() WHERE id = $1",
                    grievance_id,
                )
            await write_audit(conn, company_id, "grievance_step", grievance_id, current_user.id,
                              "step_responded", {"step": step_number, "outcome": body.outcome})
            grievance = await get_grievance_or_404(conn, grievance_id, company_id)
            return await _grievance_detail(conn, grievance)


@router.post("/grievances/{grievance_id}/advance")
async def advance_grievance(
    grievance_id: UUID,
    body: AdvanceRequest = AdvanceRequest(),
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        async with conn.transaction():
            grievance = await get_grievance_or_404(conn, grievance_id, company_id)
            if grievance["status"] in ("resolved", "withdrawn", "denied", "settled"):
                raise HTTPException(status_code=409, detail="Grievance is closed")
            current_step = grievance["current_step"]
            next_step_number = current_step + 1
            next_step = await conn.fetchrow(
                "SELECT * FROM lr_grievance_steps WHERE grievance_id = $1 AND step_number = $2",
                grievance_id, next_step_number,
            )
            if not next_step:
                raise HTTPException(status_code=409, detail="No further steps; resolve or move to arbitration")

            step_config, _ = await _load_step_config(conn, grievance)
            today = _utcnow().date()
            deadlines = compute_step_deadlines(step_config, next_step_number, today)
            # Mark the current step advanced (if not already terminal).
            await conn.execute(
                "UPDATE lr_grievance_steps SET status = 'advanced', updated_at = NOW() "
                "WHERE grievance_id = $1 AND step_number = $2 AND status NOT IN ('resolved','skipped')",
                grievance_id, current_step,
            )
            await conn.execute(
                """
                UPDATE lr_grievance_steps
                SET status = 'active', filed_at = NOW(),
                    deadline_to_respond = $3, deadline_to_advance = $4, updated_at = NOW()
                WHERE grievance_id = $1 AND step_number = $2
                """,
                grievance_id, next_step_number, deadlines["deadline_to_respond"], deadlines["deadline_to_advance"],
            )
            # Last step named for arbitration flips the grievance to 'arbitration'.
            new_status = "arbitration" if "arbitration" in (next_step["step_name"] or "").lower() else "advanced"
            row = await conn.fetchrow(
                "UPDATE lr_grievances SET status = $2, current_step = $3, updated_at = NOW() "
                "WHERE id = $1 RETURNING *",
                grievance_id, new_status, next_step_number,
            )
            await write_audit(conn, company_id, "grievance", grievance_id, current_user.id, "advanced",
                              {"to_step": next_step_number, "note": body.note})
            return await _grievance_detail(conn, dict(row))


@router.post("/grievances/{grievance_id}/resolve")
async def resolve_grievance(
    grievance_id: UUID,
    body: ResolveRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    new_status = _RESOLUTION_STATUS.get(body.resolution, "resolved")
    async with get_connection() as conn:
        async with conn.transaction():
            await get_grievance_or_404(conn, grievance_id, company_id)
            row = await conn.fetchrow(
                """
                UPDATE lr_grievances
                SET status = $2, resolution = $3, resolution_summary = $4,
                    resolved_at = NOW(), updated_at = NOW()
                WHERE id = $1 RETURNING *
                """,
                grievance_id, new_status, body.resolution, body.resolution_summary,
            )
            # Close out any still-open steps.
            await conn.execute(
                "UPDATE lr_grievance_steps SET status = 'resolved', updated_at = NOW() "
                "WHERE grievance_id = $1 AND status IN ('pending','active','responded')",
                grievance_id,
            )
            await write_audit(conn, company_id, "grievance", grievance_id, current_user.id, "resolved",
                              {"resolution": body.resolution})
            return await _grievance_detail(conn, dict(row))


@router.post("/grievances/{grievance_id}/withdraw")
async def withdraw_grievance(
    grievance_id: UUID,
    body: WithdrawRequest = WithdrawRequest(),
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        async with conn.transaction():
            await get_grievance_or_404(conn, grievance_id, company_id)
            row = await conn.fetchrow(
                """
                UPDATE lr_grievances
                SET status = 'withdrawn', resolution = 'withdrawn',
                    resolution_summary = $2, resolved_at = NOW(), updated_at = NOW()
                WHERE id = $1 RETURNING *
                """,
                grievance_id, body.reason,
            )
            await conn.execute(
                "UPDATE lr_grievance_steps SET status = 'skipped', updated_at = NOW() "
                "WHERE grievance_id = $1 AND status IN ('pending','active')",
                grievance_id,
            )
            await write_audit(conn, company_id, "grievance", grievance_id, current_user.id, "withdrawn",
                              {"reason": body.reason})
            return await _grievance_detail(conn, dict(row))


# ── Violated clauses (M:N) ───────────────────────────────────────────────────

async def _replace_violated_clauses(conn, grievance_id: UUID, company_id: UUID, clause_ids: list[UUID]) -> None:
    """Replace the grievance's violated-clause set. Validates clause ownership."""
    await conn.execute("DELETE FROM lr_grievance_violated_clauses WHERE grievance_id = $1", grievance_id)
    for cid in clause_ids:
        owned = await conn.fetchval(
            "SELECT 1 FROM lr_cba_clauses WHERE id = $1 AND company_id = $2", cid, company_id,
        )
        if not owned:
            raise HTTPException(status_code=400, detail=f"Clause {cid} not found")
        await conn.execute(
            "INSERT INTO lr_grievance_violated_clauses (grievance_id, clause_id) VALUES ($1, $2) "
            "ON CONFLICT DO NOTHING",
            grievance_id, cid,
        )


@router.post("/grievances/{grievance_id}/clauses")
async def set_violated_clauses(
    grievance_id: UUID,
    body: AttachClausesRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        async with conn.transaction():
            grievance = await get_grievance_or_404(conn, grievance_id, company_id)
            await _replace_violated_clauses(conn, grievance_id, company_id, body.clause_ids)
            await write_audit(conn, company_id, "grievance", grievance_id, current_user.id,
                              "clauses_set", {"count": len(body.clause_ids)})
            return await _grievance_detail(conn, grievance)


# ── Documents ────────────────────────────────────────────────────────────────

@router.post("/grievances/{grievance_id}/documents")
async def upload_grievance_document(
    grievance_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    """Upload a grievance evidence file to private storage and attach it.

    The storage path is generated server-side (never accepted from the client),
    so a caller cannot point a grievance at an arbitrary bucket/object.
    """
    company_id = _require_company(company_id)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")
    storage = get_storage()
    try:
        path = await storage.upload_private_file(
            file_bytes, file.filename or "evidence",
            prefix="grievance-documents", content_type=file.content_type,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Grievance document upload failed for %s: %s", grievance_id, exc)
        raise HTTPException(status_code=502, detail="Document upload failed") from exc
    doc = {
        "id": str(uuid4()),
        "storage_path": path,
        "filename": file.filename,
        "content_type": file.content_type,
        "added_at": _utcnow().isoformat(),
        "added_by": str(current_user.id),
    }
    async with get_connection() as conn:
        async with conn.transaction():
            await get_grievance_or_404(conn, grievance_id, company_id)
            row = await conn.fetchrow(
                """
                UPDATE lr_grievances
                SET documents = COALESCE(documents, '[]'::jsonb) || $2::jsonb, updated_at = NOW()
                WHERE id = $1 RETURNING *
                """,
                grievance_id, json.dumps([doc]),
            )
            await write_audit(conn, company_id, "grievance", grievance_id, current_user.id,
                              "document_added", {"filename": file.filename})
            return await _grievance_detail(conn, dict(row))


@router.get("/grievances/{grievance_id}/documents/{doc_id}/url")
async def get_grievance_document_url(
    grievance_id: UUID,
    doc_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    """Presigned download URL for an attached grievance document. The path is
    read from the owned grievance's own JSONB — never a client-supplied path."""
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        grievance = await get_grievance_or_404(conn, grievance_id, company_id)
    docs = grievance.get("documents") or []
    if isinstance(docs, str):
        try:
            docs = json.loads(docs)
        except (json.JSONDecodeError, TypeError):
            docs = []
    match = next((d for d in docs if isinstance(d, dict) and d.get("id") == doc_id), None)
    if not match or not match.get("storage_path"):
        raise HTTPException(status_code=404, detail="Document not found")
    url = get_storage().get_presigned_download_url(match["storage_path"], expires_in=900)
    if not url:
        raise HTTPException(status_code=502, detail="Could not generate download link")
    return {"url": url, "filename": match.get("filename")}


# ── Audit ────────────────────────────────────────────────────────────────────

@router.get("/grievances/{grievance_id}/audit-log")
async def grievance_audit_log(
    grievance_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        await get_grievance_or_404(conn, grievance_id, company_id)
        rows = await conn.fetch(
            """
            SELECT a.*, COALESCE(c.name, u.email) AS actor_name
            FROM lr_audit_log a
            LEFT JOIN users u ON u.id = a.actor_user_id
            LEFT JOIN clients c ON c.user_id = u.id
            WHERE a.company_id = $1
              AND ((a.entity_type = 'grievance' AND a.entity_id = $2)
                   OR (a.entity_type = 'grievance_step' AND a.entity_id = $2))
            ORDER BY a.created_at DESC
            """,
            company_id, grievance_id,
        )
    return {"audit_log": _serialize_list(rows)}


# ── AI merit assessment (SSE) ────────────────────────────────────────────────

@router.post("/grievances/{grievance_id}/assess-merit")
async def assess_merit(
    grievance_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
    company_id: Optional[UUID] = Depends(get_client_company_id),
):
    """Stream a Gemini merit assessment grading grievance facts vs cited clauses."""
    company_id = _require_company(company_id)
    async with get_connection() as conn:
        grievance = await get_grievance_or_404(conn, grievance_id, company_id)
        detail = await _grievance_detail(conn, grievance)

    async def event_stream():
        try:
            from app.matcha.services.labor_relations_ai import assess_grievance_merit
            async for chunk in assess_grievance_merit(detail):
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.error("Grievance merit assessment failed for %s: %s", grievance_id, exc)
            yield f"data: {json.dumps({'error': 'assessment_failed'})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
