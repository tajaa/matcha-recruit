"""PTO request approve/deny — the shared decision core.

Moved from routes/employees/_shared.py (refactor round 2, stage 3).
"""
from typing import Optional
from uuid import UUID


async def decide_pto_request_core(
    conn,
    *,
    company_id: UUID,
    request_id: UUID,
    decision: str,
    actor_user_id: Optional[UUID],
    note: Optional[str] = None,
) -> dict:
    """Approve or deny a PENDING PTO request. Caller owns the transaction.

    Lifted out of `pto_admin.handle_pto_request` so non-HTTP callers (Huume's
    `pto_decision` staged action) reach the same logic. The transaction is the
    caller's on purpose: an approval writes BOTH `pto_requests.status` AND
    `pto_balances.used_hours`, which the route did as two bare executes that
    could diverge if the second failed.

    Returns a verdict dict rather than raising, so a chat surface can relay it:
      {"status": "ok"|"not_found"|"invalid_status"|"reason_required",
       "message": str, "decision"?: "approved"|"denied", "employee_id"?: UUID,
       "hours"?: Any}
    """
    decision = (decision or "").strip().lower()
    if decision not in ("approve", "deny"):
        return {"status": "invalid_status", "message": "Invalid action. Must be 'approve' or 'deny'"}

    pto_request = await conn.fetchrow(
        """
        SELECT pr.*, e.org_id FROM pto_requests pr
        JOIN employees e ON pr.employee_id = e.id
        WHERE pr.id = $1 AND e.org_id = $2
        """,
        request_id, company_id,
    )
    if not pto_request:
        return {"status": "not_found", "message": "PTO request not found"}
    if pto_request["status"] != "pending":
        return {"status": "invalid_status", "message": "Can only approve/deny pending requests"}

    # The acting user's own employee row, when they have one — `approved_by`
    # references employees, not users, so an admin without a row stays NULL.
    admin_employee = await conn.fetchrow(
        "SELECT id FROM employees WHERE user_id = $1", actor_user_id,
    ) if actor_user_id else None
    approved_by = admin_employee["id"] if admin_employee else None

    if decision == "approve":
        await conn.execute(
            """
            UPDATE pto_requests
            SET status = 'approved', approved_by = $1, approved_at = NOW(), updated_at = NOW()
            WHERE id = $2
            """,
            approved_by, request_id,
        )
        await conn.execute(
            """
            UPDATE pto_balances
            SET used_hours = used_hours + $1, updated_at = NOW()
            WHERE employee_id = $2 AND year = EXTRACT(YEAR FROM CURRENT_DATE)
            """,
            pto_request["hours"], pto_request["employee_id"],
        )
        return {"status": "ok", "message": "PTO request approved", "decision": "approved",
                "employee_id": pto_request["employee_id"], "hours": pto_request["hours"]}

    if not (note or "").strip():
        return {"status": "reason_required", "message": "Denial reason is required"}
    await conn.execute(
        """
        UPDATE pto_requests
        SET status = 'denied', denial_reason = $1, approved_by = $2, approved_at = NOW(), updated_at = NOW()
        WHERE id = $3
        """,
        note.strip(), approved_by, request_id,
    )
    return {"status": "ok", "message": "PTO request denied", "decision": "denied",
            "employee_id": pto_request["employee_id"], "hours": pto_request["hours"]}
