"""Restore the schedule-digest activation lost by schemasync01.

schemasync01 replayed huumesched01 after empsched13 was already stamped. On a
database missing the scheduler_settings row, that recreated huumesched01's
original disabled value, but empsched13's later ``enabled=true`` update could
not run again. Reassert the final state intended by empsched13.

Revision ID: schedrepair01
Revises: schemasync01
"""
from alembic import op


revision = "schedrepair01"
down_revision = "schemasync01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO scheduler_settings(task_key, display_name, description, enabled, max_per_cycle)
        VALUES ('schedule_daily_digest', 'Daily schedule digest',
                'Break requirements and visible schedule notes for location managers and employees.',
                true, 500)
        ON CONFLICT (task_key) DO UPDATE SET enabled = true
        """
    )


def downgrade() -> None:
    # No-op: empsched13 remains applied on its separate migration head and owns
    # the activation. Disabling or deleting the row here would undo its intended
    # state rather than reverse anything introduced by this repair.
    pass
