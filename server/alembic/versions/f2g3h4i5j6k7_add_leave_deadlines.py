"""add_leave_deadlines

Revision ID: f2g3h4i5j6k7
Revises: e1f2a3b4c5d6
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2g3h4i5j6k7'
down_revision: Union[str, Sequence[str]] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create leave_deadlines table and seed scheduler_settings."""

    op.execute("""
        CREATE TABLE IF NOT EXISTS leave_deadlines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            leave_request_id UUID REFERENCES leave_requests(id) ON DELETE CASCADE,
            org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            deadline_type VARCHAR(50) NOT NULL,
            due_date DATE NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            escalation_level INTEGER DEFAULT 0,
            completed_at TIMESTAMP,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_leave_deadlines_due_date
            ON leave_deadlines(due_date)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_leave_deadlines_status
            ON leave_deadlines(status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_leave_deadlines_leave_request_id
            ON leave_deadlines(leave_request_id)
    """)

    # Seed scheduler_settings for the leave deadline checks task
    op.execute("""
        INSERT INTO scheduler_settings (task_key, task_label, description, enabled, max_per_cycle)
        VALUES ('leave_deadline_checks', 'Leave Deadline Checks',
                'Checks leave compliance deadlines and escalates overdue items.',
                false, 0)
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade() -> None:
    """Drop leave_deadlines table and remove scheduler setting."""
    op.execute("DROP TABLE IF EXISTS leave_deadlines")
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'leave_deadline_checks'")
