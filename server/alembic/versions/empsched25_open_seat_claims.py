"""Allow employees to claim published open schedule seats.

Also guards drop / time-off requests against repeat submission (each one
fans out to every manager), and marks every pre-existing unreviewed unilateral
request as already-notified so widening the recovery sweep to those types
does not replay the whole backlog on its first run.

Revision ID: empsched25
Revises: devicetok03
"""

from alembic import op


revision = "empsched25"
down_revision = "devicetok03"
branch_labels = None
depends_on = "empsched22"


def upgrade() -> None:
    op.execute("ALTER TABLE schedule_requests DROP CONSTRAINT schedule_requests_request_type_check")
    op.execute(
        "ALTER TABLE schedule_requests ADD CONSTRAINT schedule_requests_request_type_check "
        "CHECK (request_type IN ('swap', 'drop', 'pickup', 'unavailable', 'availability', 'claim'))"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_schedule_requests_open_claim "
        "ON schedule_requests(employee_id, shift_id) "
        "WHERE request_type = 'claim' AND status IN ('pending', 'awaiting_manager')"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_schedule_requests_open_drop "
        "ON schedule_requests(employee_id, shift_id) "
        "WHERE request_type = 'drop' AND status IN ('pending', 'awaiting_manager')"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_schedule_requests_open_unavailable "
        "ON schedule_requests(employee_id, unavailable_start, unavailable_end) "
        "WHERE request_type = 'unavailable' AND status IN ('pending', 'awaiting_manager')"
    )
    # Backlog floor for the widened recovery sweep: everything already waiting
    # counts as delivered on both channels for every current reviewer.
    op.execute("""
        INSERT INTO schedule_request_notification_deliveries
            (company_id, request_id, recipient_user_id, event_type, sent_at)
        SELECT r.company_id, r.id, u.id, e.event_type, NOW()
        FROM schedule_requests r
        JOIN clients c ON c.company_id = r.company_id
        JOIN users u ON u.id = c.user_id AND u.role = 'client'
        CROSS JOIN (VALUES ('manager_ready'), ('manager_ready_in_app')) AS e(event_type)
        WHERE r.status = 'awaiting_manager'
          AND r.request_type IN ('drop', 'unavailable', 'availability')
        ON CONFLICT (request_id, recipient_user_id, event_type) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP INDEX uq_schedule_requests_open_unavailable")
    op.execute("DROP INDEX uq_schedule_requests_open_drop")
    op.execute("DROP INDEX uq_schedule_requests_open_claim")
    op.execute("DELETE FROM schedule_requests WHERE request_type = 'claim'")
    op.execute("ALTER TABLE schedule_requests DROP CONSTRAINT schedule_requests_request_type_check")
    op.execute(
        "ALTER TABLE schedule_requests ADD CONSTRAINT schedule_requests_request_type_check "
        "CHECK (request_type IN ('swap', 'drop', 'pickup', 'unavailable', 'availability'))"
    )
