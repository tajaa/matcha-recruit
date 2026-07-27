"""IR Corrective Actions (CAPA) endpoints — structured, accountable follow-through.

The free-text ir_incidents.corrective_actions column stays as a notes layer (the
IR Copilot + AI recommendation cards write it). This module owns the accountable
layer: ir_corrective_actions rows, each with its own owner, due date, status
lifecycle, and post-completion effectiveness verification.

All routes are 2+ segments (or nested under /{incident_id}) so none collide with
crud's /{incident_id} catch-all. They inherit the parent mount's
require_feature("incidents") gate. Tenant isolation goes through
_get_incident_with_company_check (per-incident routes) or an explicit
company_id filter (the company-wide list + by-id routes).
"""
import logging
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.feature_flags import get_company_features
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client, require_feature
from app.matcha.models.ir.capa import (
    CorrectiveAction,
    CorrectiveActionCreate,
    CorrectiveActionListResponse,
    CorrectiveActionUpdate,
    OpenCorrectiveAction,
    OpenCorrectiveActionsResponse,
)

from ._shared import _get_incident_with_company_check, log_audit

logger = logging.getLogger(__name__)

router = APIRouter()

# Columns selected for a corrective-action row + its hydrated owner name.
_CA_SELECT = """
    ca.id, ca.incident_id, ca.description, ca.action_type, ca.priority,
    ca.assigned_to, ca.assignee_name, ca.due_date, ca.status,
    ca.completed_at, ca.verified_by, ca.verified_at, ca.effectiveness,
    ca.training_requirement_id,
    ca.created_by, ca.created_at, ca.updated_at,
    COALESCE(cl.name, u.email) AS assigned_to_name
"""

_CA_FROM = """
    FROM ir_corrective_actions ca
    LEFT JOIN users u ON u.id = ca.assigned_to
    LEFT JOIN clients cl ON cl.user_id = ca.assigned_to AND cl.company_id = ca.company_id
"""

# status values that count as "not yet done" for the overdue derivation.
_OPEN_STATUSES = ("open", "in_progress")


async def _assert_assignable(conn, assigned_to, company_id) -> None:
    """Reject an assigned_to that isn't a user inside the caller's company.

    Without this, any admin could assign an action to an arbitrary user UUID:
    the read path's COALESCE(cl.name, u.email) would fall through to u.email for
    a foreign user (the clients join is company-scoped, the users join is not),
    turning the endpoint into an email-enumeration oracle, and the deadline
    worker would email that stranger the incident's number, title, and action
    text. An owner is either a business admin (clients) or an employee whose
    roster row is linked to a user account (employees.user_id).
    """
    if assigned_to is None:
        return
    ok = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM clients WHERE user_id = $1 AND company_id = $2
            UNION ALL
            SELECT 1 FROM employees WHERE user_id = $1 AND org_id = $2
        )
        """,
        str(assigned_to), str(company_id),
    )
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="assigned_to must be a user in your company",
        )


def _is_overdue(due_date, status: str) -> bool:
    if not due_date or status not in _OPEN_STATUSES:
        return False
    return due_date < date.today()


def _row_to_action(row) -> CorrectiveAction:
    return CorrectiveAction(
        id=row["id"],
        incident_id=row["incident_id"],
        description=row["description"],
        action_type=row["action_type"],
        priority=row["priority"],
        assigned_to=row["assigned_to"],
        assignee_name=row["assignee_name"],
        assigned_to_name=row["assigned_to_name"],
        due_date=row["due_date"],
        status=row["status"],
        completed_at=row["completed_at"],
        verified_by=row["verified_by"],
        verified_at=row["verified_at"],
        effectiveness=row["effectiveness"],
        training_requirement_id=row["training_requirement_id"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        overdue=_is_overdue(row["due_date"], row["status"]),
    )


@router.get("/{incident_id}/corrective-actions", response_model=CorrectiveActionListResponse)
async def list_corrective_actions(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """List the structured corrective actions for one incident."""
    async with get_connection() as conn:
        # Ownership check (raises 404 on cross-company access).
        await _get_incident_with_company_check(conn, incident_id, current_user, columns="id")
        rows = await conn.fetch(
            f"""
            SELECT {_CA_SELECT}
            {_CA_FROM}
            WHERE ca.incident_id = $1
            ORDER BY
                CASE ca.status WHEN 'open' THEN 0 WHEN 'in_progress' THEN 1
                    WHEN 'completed' THEN 2 WHEN 'verified' THEN 3 ELSE 4 END,
                ca.due_date ASC NULLS LAST, ca.created_at ASC
            """,
            str(incident_id),
        )
    actions = [_row_to_action(r) for r in rows]
    return CorrectiveActionListResponse(actions=actions, total=len(actions))


@router.post("/{incident_id}/corrective-actions", response_model=CorrectiveAction, status_code=201)
async def create_corrective_action(
    incident_id: UUID,
    payload: CorrectiveActionCreate,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Create a structured corrective/preventive action on an incident."""
    async with get_connection() as conn:
        incident = await _get_incident_with_company_check(
            conn, incident_id, current_user,
            columns="id, company_id, involved_employee_ids",
        )
        await _assert_assignable(conn, payload.assigned_to, incident["company_id"])

        training_requirement_id = None
        if payload.action_type == "training" and payload.training_requirement_id:
            features = await get_company_features(incident["company_id"], conn=conn)
            if not features.get("training"):
                raise HTTPException(status_code=403, detail="Training feature required for training corrective actions")
            requirement = await conn.fetchrow(
                "SELECT id, title, training_type, frequency_months "
                "FROM training_requirements WHERE id = $1 AND company_id = $2",
                str(payload.training_requirement_id), str(incident["company_id"]),
            )
            if not requirement:
                raise HTTPException(status_code=404, detail="Training requirement not found")
            training_requirement_id = requirement["id"]

        row = await conn.fetchrow(
            """
            INSERT INTO ir_corrective_actions
                (incident_id, company_id, description, action_type, priority,
                 assigned_to, assignee_name, due_date, created_by, training_requirement_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id
            """,
            str(incident_id),
            str(incident["company_id"]),
            payload.description.strip(),
            payload.action_type,
            payload.priority,
            str(payload.assigned_to) if payload.assigned_to else None,
            (payload.assignee_name or None),
            payload.due_date,
            str(current_user.id),
            training_requirement_id,
        )

        if training_requirement_id and incident["involved_employee_ids"]:
            try:
                from app.matcha.services.training.training_assignment import assign_training

                await assign_training(
                    conn,
                    incident["company_id"],
                    dict(requirement),
                    incident["involved_employee_ids"],
                    source_type="incident",
                    source_ref=incident_id,
                    due_date=payload.due_date,
                    assigned_by=current_user.id,
                    source_note=f"CAPA on incident {incident_id}",
                )
            except Exception:
                logger.exception(
                    "Failed to assign training from CAPA %s on incident %s",
                    row["id"], incident_id,
                )

        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "corrective_action_created",
            "corrective_action",
            str(row["id"]),
            {"description": payload.description[:200], "due_date": str(payload.due_date) if payload.due_date else None},
            request.client.host if request.client else None,
        )
        created = await conn.fetchrow(
            f"SELECT {_CA_SELECT} {_CA_FROM} WHERE ca.id = $1", row["id"]
        )
    return _row_to_action(created)


async def _load_action_for_company(conn, action_id: UUID, company_id) -> dict:
    """Fetch an action scoped to the caller's company, or raise 404."""
    row = await conn.fetchrow(
        f"SELECT {_CA_SELECT} {_CA_FROM} WHERE ca.id = $1 AND ca.company_id = $2",
        str(action_id), str(company_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Corrective action not found")
    return row


@router.put("/corrective-actions/{action_id}", response_model=CorrectiveAction)
async def update_corrective_action(
    action_id: UUID,
    payload: CorrectiveActionUpdate,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """PATCH-style update. Only fields present in the request body are written.

    Status transitions stamp lifecycle timestamps server-side:
      -> completed  sets completed_at (and defaults effectiveness to 'pending')
      -> verified   sets verified_by + verified_at
    Moving back out of completed/verified clears the corresponding stamps so the
    row can't claim a completion it no longer has.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    fields = payload.model_fields_set
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    async with get_connection() as conn:
        existing = await _load_action_for_company(conn, action_id, company_id)

        sets = []
        params = []
        idx = 1

        def add(col, value):
            nonlocal idx
            sets.append(f"{col} = ${idx}")
            params.append(value)
            idx += 1

        if "description" in fields and payload.description is not None:
            add("description", payload.description.strip())
        if "action_type" in fields and payload.action_type is not None:
            add("action_type", payload.action_type)
        if "priority" in fields and payload.priority is not None:
            add("priority", payload.priority)
        if "assigned_to" in fields:
            await _assert_assignable(conn, payload.assigned_to, company_id)
            add("assigned_to", str(payload.assigned_to) if payload.assigned_to else None)
        if "assignee_name" in fields:
            add("assignee_name", payload.assignee_name or None)
        if "due_date" in fields:
            add("due_date", payload.due_date)
        if "effectiveness" in fields:
            add("effectiveness", payload.effectiveness)
        if "training_requirement_id" in fields:
            if payload.training_requirement_id:
                req_exists = await conn.fetchval(
                    "SELECT id FROM training_requirements WHERE id = $1 AND company_id = $2",
                    str(payload.training_requirement_id), str(company_id),
                )
                if not req_exists:
                    raise HTTPException(status_code=404, detail="Training requirement not found")
            add("training_requirement_id", str(payload.training_requirement_id) if payload.training_requirement_id else None)

        now = datetime.now(timezone.utc)
        if "status" in fields and payload.status is not None:
            new_status = payload.status
            add("status", new_status)
            if new_status == "completed":
                if existing["completed_at"] is None:
                    add("completed_at", now)
                if existing["effectiveness"] is None and "effectiveness" not in fields:
                    add("effectiveness", "pending")
            elif new_status == "verified":
                if existing["completed_at"] is None:
                    add("completed_at", now)
                add("verified_by", str(current_user.id))
                add("verified_at", now)
            else:
                # Reopened / in_progress / cancelled — drop stale completion stamps.
                add("completed_at", None)
                add("verified_by", None)
                add("verified_at", None)

        add("updated_at", now)

        params.append(str(action_id))
        params.append(str(company_id))
        await conn.execute(
            f"UPDATE ir_corrective_actions SET {', '.join(sets)} "
            f"WHERE id = ${idx} AND company_id = ${idx + 1}",
            *params,
        )

        await log_audit(
            conn,
            str(existing["incident_id"]),
            str(current_user.id),
            "corrective_action_updated",
            "corrective_action",
            str(action_id),
            {k: (str(getattr(payload, k)) if getattr(payload, k) is not None else None) for k in fields},
            request.client.host if request.client else None,
        )
        updated = await _load_action_for_company(conn, action_id, company_id)
    return _row_to_action(updated)


@router.delete("/corrective-actions/{action_id}", status_code=204)
async def delete_corrective_action(
    action_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Delete a corrective action."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Corrective action not found")
    async with get_connection() as conn:
        existing = await _load_action_for_company(conn, action_id, company_id)
        await conn.execute(
            "DELETE FROM ir_corrective_actions WHERE id = $1 AND company_id = $2",
            str(action_id), str(company_id),
        )
        await log_audit(
            conn,
            str(existing["incident_id"]),
            str(current_user.id),
            "corrective_action_deleted",
            "corrective_action",
            str(action_id),
            None,
            request.client.host if request.client else None,
        )
    return None


@router.get("/corrective-actions/open", response_model=OpenCorrectiveActionsResponse)
async def list_open_corrective_actions(
    current_user=Depends(require_admin_or_client),
):
    """Company-wide open + in-progress corrective actions (dashboard tile).

    Overdue rows (past due_date, still open) sort first. Carries incident
    number/title so the UI can link straight to the source incident.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return OpenCorrectiveActionsResponse(actions=[], total=0, overdue_count=0)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT {_CA_SELECT},
                   i.incident_number, i.title AS incident_title
            {_CA_FROM}
            JOIN ir_incidents i ON i.id = ca.incident_id
            WHERE ca.company_id = $1 AND ca.status IN ('open', 'in_progress')
            ORDER BY
                (ca.due_date IS NOT NULL AND ca.due_date < CURRENT_DATE) DESC,
                ca.due_date ASC NULLS LAST, ca.created_at ASC
            """,
            str(company_id),
        )
    actions = []
    overdue_count = 0
    for r in rows:
        overdue = _is_overdue(r["due_date"], r["status"])
        if overdue:
            overdue_count += 1
        base = _row_to_action(r)
        actions.append(
            OpenCorrectiveAction(
                **base.model_dump(),
                incident_number=r["incident_number"],
                incident_title=r["incident_title"],
            )
        )
    return OpenCorrectiveActionsResponse(
        actions=actions, total=len(actions), overdue_count=overdue_count
    )


# ---------------------------------------------------------------------------
# Assign training — the admin-triggered path (B2). Independent of CAPA: an
# admin can assign training straight from the incident without first creating
# a corrective action. When corrective_action_id is given, that CAPA is
# stamped action_type='training' + training_requirement_id so it shows the
# same linkage the CAPA-first path (create_corrective_action, above) produces.
# ---------------------------------------------------------------------------

class AssignTrainingRequest(BaseModel):
    requirement_id: UUID
    employee_ids: Optional[list[UUID]] = None
    due_date: Optional[date] = None
    note: Optional[str] = None
    corrective_action_id: Optional[UUID] = None


class AssignTrainingResponse(BaseModel):
    assigned_count: int
    accelerated_count: int
    already_open_count: int
    requirement_id: UUID


@router.post(
    "/{incident_id}/assign-training",
    response_model=AssignTrainingResponse,
    dependencies=[Depends(require_feature("training"))],
)
async def assign_training_from_incident(
    incident_id: UUID,
    payload: AssignTrainingRequest,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Assign a training requirement to this incident's involved employees
    (or an explicit subset). Defaults employee_ids to
    ir_incidents.involved_employee_ids — witnesses and no-roster ir_people
    aren't real `employees` rows and can't be targeted here.
    """
    async with get_connection() as conn:
        incident = await _get_incident_with_company_check(
            conn, incident_id, current_user,
            columns="id, company_id, involved_employee_ids",
        )
        company_id = incident["company_id"]

        requirement = await conn.fetchrow(
            "SELECT id, title, training_type, frequency_months "
            "FROM training_requirements WHERE id = $1 AND company_id = $2 AND is_active = true",
            str(payload.requirement_id), str(company_id),
        )
        if not requirement:
            raise HTTPException(status_code=404, detail="Training requirement not found")

        employee_ids = payload.employee_ids or list(incident["involved_employee_ids"] or [])
        if not employee_ids:
            raise HTTPException(
                status_code=400,
                detail="No employees to assign — pass employee_ids or add involved employees to the incident",
            )

        if payload.corrective_action_id:
            action_row = await conn.fetchrow(
                "SELECT id FROM ir_corrective_actions WHERE id = $1 AND incident_id = $2 AND company_id = $3",
                str(payload.corrective_action_id), str(incident_id), str(company_id),
            )
            if not action_row:
                raise HTTPException(status_code=404, detail="Corrective action not found")
            await conn.execute(
                "UPDATE ir_corrective_actions SET action_type = 'training', "
                "training_requirement_id = $1, updated_at = NOW() WHERE id = $2",
                str(requirement["id"]), str(payload.corrective_action_id),
            )

        from app.matcha.services.training.training_assignment import assign_training

        outcome = await assign_training(
            conn,
            company_id,
            dict(requirement),
            employee_ids,
            source_type="incident",
            source_ref=incident_id,
            source_note=payload.note or f"Assigned from incident {incident_id}",
            due_date=payload.due_date,
            assigned_by=current_user.id,
        )

        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "training_assigned",
            "training_record",
            str(requirement["id"]),
            {"assigned_count": outcome.assigned, "employee_count": len(employee_ids)},
            request.client.host if request.client else None,
        )

    return AssignTrainingResponse(
        assigned_count=outcome.assigned,
        accelerated_count=outcome.accelerated,
        already_open_count=outcome.already_open,
        requirement_id=requirement["id"],
    )


@router.get("/{incident_id}/trainings", dependencies=[Depends(require_feature("training"))])
async def list_incident_trainings(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Training records this incident triggered (source_type='incident')."""
    async with get_connection() as conn:
        incident = await _get_incident_with_company_check(
            conn, incident_id, current_user, columns="id, company_id"
        )
        rows = await conn.fetch(
            """
            SELECT r.id, r.employee_id, r.title, r.status, r.due_date,
                   r.completed_date, r.source_note,
                   e.first_name, e.last_name
            FROM training_records r
            JOIN employees e ON e.id = r.employee_id
            WHERE r.company_id = $1 AND r.source_type = 'incident' AND r.source_ref = $2
            ORDER BY r.created_at DESC
            """,
            str(incident["company_id"]), str(incident_id),
        )
        return [
            {
                "id": str(r["id"]),
                "employee_id": str(r["employee_id"]),
                "employee_name": f"{r['first_name'] or ''} {r['last_name'] or ''}".strip(),
                "title": r["title"],
                "status": r["status"],
                "due_date": r["due_date"].isoformat() if r["due_date"] else None,
                "completed_date": r["completed_date"].isoformat() if r["completed_date"] else None,
                "source_note": r["source_note"],
            }
            for r in rows
        ]
