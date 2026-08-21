"""Manager decisions for expired schedule-blocking requirements."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_connection
from ...dependencies import require_admin_or_client
from ...models.scheduling.employee_schedule import EligibilityCaseDecision
from ._shared import log_audit, require_company_id

router = APIRouter()


@router.get("/eligibility-cases")
async def list_eligibility_cases(current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT c.*, e.first_name, e.last_name FROM schedule_eligibility_cases c
               JOIN employees e ON e.id=c.employee_id WHERE c.company_id=$1
               ORDER BY c.detected_at DESC LIMIT 200""", company_id)
    return {"cases": [{**dict(row), "id": str(row["id"]), "employee_id": str(row["employee_id"])} for row in rows]}


@router.post("/eligibility-cases/{case_id}/decision")
async def decide_eligibility_case(case_id: UUID, body: EligibilityCaseDecision,
                                  current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            case = await conn.fetchrow("SELECT * FROM schedule_eligibility_cases WHERE id=$1 AND company_id=$2 FOR UPDATE", case_id, company_id)
            if not case:
                raise HTTPException(status_code=404, detail="Eligibility case not found")
            if case["status"] not in ("removal_requested", "warning_open"):
                raise HTTPException(status_code=409, detail="Eligibility case already decided")
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
