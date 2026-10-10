"""Mark the waiting schedule requests as already told to store managers.

Store managers (employees flagged is_manager/is_supervisor) now get the
manager-ready bell row and push, and the recovery sweep chases any store
manager without a delivered in-app row. Without this floor, the first sweep
after the deploy would push every request already waiting to every store
manager at once. Same precedent as empsched25's backlog floor.

Set-based: one INSERT ... SELECT over the requests already waiting. The
recipient rule mirrors `schedule_manager_scope.store_manager_recipients_sql`
(every store the request touches is the manager's; never the requester or the
coworker). No schema change.

Run this BEFORE deploying the code that reads it. Requests created between the
two are genuinely new and are notified normally.

Revision ID: empsched29
Revises: empsched28
"""

from alembic import op


revision = "empsched29"
down_revision = "empsched28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO schedule_request_notification_deliveries
            (company_id, request_id, recipient_user_id, event_type, sent_at)
        SELECT DISTINCT r.company_id, r.id, mgr.user_id, 'manager_ready_in_app', NOW()
          FROM schedule_requests r
          JOIN employees e ON e.id = r.employee_id
          LEFT JOIN employees te ON te.id = r.target_employee_id
          LEFT JOIN schedule_shifts s ON s.id = r.shift_id
          LEFT JOIN schedule_shifts cs ON cs.id = r.counter_shift_id
          JOIN LATERAL (
                SELECT m.user_id, array_agg(m.work_location_id) AS locs
                  FROM employees m
                  JOIN users mu ON mu.id = m.user_id
                 WHERE m.org_id = r.company_id
                   AND mu.role = 'employee' AND mu.is_active
                   AND COALESCE(m.employment_status, 'active') = 'active'
                   AND (COALESCE(m.is_manager, false) OR COALESCE(m.is_supervisor, false))
                   AND m.work_location_id IS NOT NULL
                 GROUP BY m.user_id
          ) mgr ON (e.work_location_id = ANY(mgr.locs)
                    AND (r.shift_id IS NULL OR s.location_id = ANY(mgr.locs))
                    AND (r.counter_shift_id IS NULL OR cs.location_id = ANY(mgr.locs))
                    AND (r.target_employee_id IS NULL OR te.work_location_id = ANY(mgr.locs)))
         WHERE r.status = 'awaiting_manager'
           AND mgr.user_id IS DISTINCT FROM e.user_id
           AND mgr.user_id IS DISTINCT FROM te.user_id
        ON CONFLICT (request_id, recipient_user_id, event_type) DO NOTHING
    """)


def downgrade() -> None:
    """No-op. The rows are ordinary delivery receipts; removing them would make
    the sweep re-notify the backlog."""
