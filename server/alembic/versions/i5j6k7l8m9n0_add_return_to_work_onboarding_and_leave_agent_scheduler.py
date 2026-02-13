"""add_return_to_work_onboarding_and_leave_agent_scheduler

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "i5j6k7l8m9n0"
down_revision: Union[str, Sequence[str]] = "h4i5j6k7l8m9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Extend onboarding for return-to-work workflows and seed orchestrator scheduler."""
    op.execute(
        """
        ALTER TABLE onboarding_tasks
            DROP CONSTRAINT IF EXISTS check_category,
            ADD CONSTRAINT check_category CHECK (
                category IN ('documents', 'equipment', 'training', 'admin', 'return_to_work')
            )
        """
    )

    op.execute(
        """
        ALTER TABLE employee_onboarding_tasks
            DROP CONSTRAINT IF EXISTS check_onboarding_category,
            ADD CONSTRAINT check_onboarding_category CHECK (
                category IN ('documents', 'equipment', 'training', 'admin', 'return_to_work')
            )
        """
    )

    op.execute(
        """
        ALTER TABLE employee_onboarding_tasks
            ADD COLUMN IF NOT EXISTS leave_request_id UUID
            REFERENCES leave_requests(id) ON DELETE SET NULL
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_onboarding_tasks_leave_request_id
            ON employee_onboarding_tasks(leave_request_id)
        """
    )

    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'leave_agent_orchestration',
            'Leave Agent Orchestration',
            'Runs return-to-work and accommodation lifecycle orchestration checks.',
            false,
            20
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade() -> None:
    """Remove return-to-work onboarding extensions and orchestrator scheduler seed."""
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'leave_agent_orchestration'")

    op.execute(
        """
        UPDATE onboarding_tasks
        SET category = 'admin'
        WHERE category = 'return_to_work'
        """
    )

    op.execute(
        """
        UPDATE employee_onboarding_tasks
        SET category = 'admin'
        WHERE category = 'return_to_work'
        """
    )

    op.execute(
        """
        ALTER TABLE onboarding_tasks
            DROP CONSTRAINT IF EXISTS check_category,
            ADD CONSTRAINT check_category CHECK (
                category IN ('documents', 'equipment', 'training', 'admin')
            )
        """
    )

    op.execute(
        """
        ALTER TABLE employee_onboarding_tasks
            DROP CONSTRAINT IF EXISTS check_onboarding_category,
            ADD CONSTRAINT check_onboarding_category CHECK (
                category IN ('documents', 'equipment', 'training', 'admin')
            )
        """
    )

    op.execute("DROP INDEX IF EXISTS idx_employee_onboarding_tasks_leave_request_id")
    op.execute("ALTER TABLE employee_onboarding_tasks DROP COLUMN IF EXISTS leave_request_id")
