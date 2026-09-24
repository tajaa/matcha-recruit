"""Allow employees to claim published open schedule seats.

Revision ID: empsched25
Revises: devicetok02
"""

from alembic import op


revision = "empsched25"
down_revision = "devicetok02"
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


def downgrade() -> None:
    op.execute("DROP INDEX uq_schedule_requests_open_claim")
    op.execute("DELETE FROM schedule_requests WHERE request_type = 'claim'")
    op.execute("ALTER TABLE schedule_requests DROP CONSTRAINT schedule_requests_request_type_check")
    op.execute(
        "ALTER TABLE schedule_requests ADD CONSTRAINT schedule_requests_request_type_check "
        "CHECK (request_type IN ('swap', 'drop', 'pickup', 'unavailable', 'availability'))"
    )
