"""Manager decisions for expired schedule-blocking requirements."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from ...dependencies import require_company_member
from ...models.scheduling.employee_schedule import EligibilityCaseDecision
from ._shared import log_audit, require_company_id
from ...services.scheduling.schedule_eligibility_authorization import (
    eligibility_case_decision_error,
    require_eligibility_case_access,
    resolve_eligibility_manager_scope,
)

router = APIRouter()


@router.get("/eligibility-cases")
async def list_eligibility_cases(
    location_id: UUID | None = Query(None),
    current_user=Depends(require_company_member),
):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        scope = await resolve_eligibility_manager_scope(
            conn, company_id=company_id, actor_user_id=current_user.id, actor_role=current_user.role,
        )
        if location_id is not None and not scope.permits(location_id):
            raise HTTPException(status_code=404, detail="Location not found")
        if not scope.is_company_operations and not scope.managed_location_ids:
            return {"cases": []}
        rows = await conn.fetch(
            """SELECT c.*, e.first_name, e.last_name, ct.label AS credential_label,
                      bl.name AS location_name,
                      COUNT(a.shift_id) AS affected_assignment_count,
                      COUNT(a.shift_id) FILTER (WHERE a.action_status='removed') AS removed_assignment_count
                 FROM schedule_eligibility_cases c
                 JOIN employees e ON e.id=c.employee_id
                 LEFT JOIN employee_credential_requirements ecr ON ecr.id=c.requirement_id
                 LEFT JOIN scoped_credential_types ct ON ct.id=ecr.credential_type_id
                 LEFT JOIN business_locations bl ON bl.id=c.location_id
                 LEFT JOIN schedule_eligibility_case_assignments a ON a.case_id=c.id
              WHERE c.company_id=$1
                 AND ($2::uuid IS NULL OR c.location_id=$2)
                 AND ($3::boolean OR c.location_id=ANY($4::uuid[]))
              GROUP BY c.id, e.first_name, e.last_name, ct.label, bl.name
              ORDER BY c.detected_at DESC LIMIT 200""",
            company_id, location_id, scope.is_company_operations, list(scope.managed_location_ids))
    cases = []
    for row in rows:
        item = dict(row)
        for key in ("id", "employee_id", "location_id", "requirement_id", "manager_decision_by", "manager_acknowledged_by"):
            if item.get(key) is not None:
                item[key] = str(item[key])
        item["automatic_enforcement"] = str(item.get("blocking_reason_code") or "").endswith("_auto_unassigned")
        cases.append(item)
    return {"cases": cases}


@router.post("/eligibility-cases/{case_id}/decision")
async def decide_eligibility_case(case_id: UUID, body: EligibilityCaseDecision,
                                  current_user=Depends(require_company_member)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            case, _scope = await require_eligibility_case_access(
                conn, company_id=company_id, case_id=case_id, actor_user_id=current_user.id,
                actor_role=current_user.role, lock=True,
            )
            decision_error = eligibility_case_decision_error(case)
            if decision_error:
                raise HTTPException(status_code=409, detail=decision_error)
            if body.decision == "keep" and (not body.acknowledgement_confirmed or not body.acknowledgement_note):
                raise HTTPException(status_code=422, detail={
                    "code": "eligibility_acknowledgement_required",
                    "message": "Confirm and explain the decision to retain this employee despite the cited requirement.",
                    "legal_basis": case["legal_basis"],
                })
            if body.decision == "keep":
                await conn.execute("""UPDATE schedule_eligibility_cases SET status='keep_acknowledged', manager_decision_by=$1,
                    manager_decision_at=NOW(), manager_acknowledged_by=$1, manager_acknowledged_at=NOW(), acknowledgement_note=$2, updated_at=NOW() WHERE id=$3""",
                    current_user.id, body.acknowledgement_note.strip(), case_id)
                await conn.execute("UPDATE schedule_eligibility_case_assignments SET action_status='retained', acted_at=NOW() WHERE case_id=$1 AND action_status='pending'", case_id)
                await log_audit(conn, company_id, "eligibility_case", case_id, current_user.id, "eligibility_case.keep_acknowledged", {"legal_basis": case["legal_basis"], "note": body.acknowledgement_note})
            else:
                assignments = await conn.fetch("SELECT shift_id, employee_id FROM schedule_eligibility_case_assignments WHERE case_id=$1 AND action_status='pending' FOR UPDATE", case_id)
                for assignment in assignments:
                    deleted = await conn.fetchval("""DELETE FROM schedule_shift_assignments a USING schedule_shifts s
                        WHERE a.shift_id=$1 AND a.employee_id=$2 AND a.shift_id=s.id AND s.company_id=$3 RETURNING a.shift_id""",
                        assignment["shift_id"], assignment["employee_id"], company_id)
                    action = "removed" if deleted else "no_longer_assigned"
                    await conn.execute("UPDATE schedule_eligibility_case_assignments SET action_status=$1, acted_at=NOW() WHERE case_id=$2 AND shift_id=$3 AND employee_id=$4", action, case_id, assignment["shift_id"], assignment["employee_id"])
                    if deleted:
                        await log_audit(conn, company_id, "assignment", assignment["shift_id"], current_user.id, "assignment.delete", {"source": "schedule_eligibility_case", "case_id": str(case_id), "employee_id": str(assignment["employee_id"])})
                await conn.execute("UPDATE schedule_eligibility_cases SET status='removal_completed', manager_decision_by=$1, manager_decision_at=NOW(), resolved_at=NOW(), updated_at=NOW() WHERE id=$2", current_user.id, case_id)
        return {"id": str(case_id), "decision": body.decision}
