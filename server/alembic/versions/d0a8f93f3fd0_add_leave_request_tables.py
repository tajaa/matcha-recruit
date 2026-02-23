"""add_leave_request_tables

Revision ID: d0a8f93f3fd0
Revises: r8s9t0u1v2w3
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op

revision = 'd0a8f93f3fd0'
down_revision = 'r8s9t0u1v2w3'
branch_labels = None
depends_on = None
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0a8f93f3fd0'
down_revision: Union[str, Sequence[str]] = 'r8s9t0u1v2w3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create leave_requests and employee_hours_log tables."""

    op.execute("""
        CREATE TABLE IF NOT EXISTS leave_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            leave_type VARCHAR(30) NOT NULL,
            reason TEXT,
            start_date DATE NOT NULL,
            end_date DATE,
            expected_return_date DATE,
            actual_return_date DATE,
            status VARCHAR(30) NOT NULL DEFAULT 'requested',
            intermittent BOOLEAN DEFAULT false,
            intermittent_schedule TEXT,
            hours_approved DECIMAL(8,2),
            hours_used DECIMAL(8,2) DEFAULT 0,
            denial_reason TEXT,
            reviewed_by UUID REFERENCES users(id),
            reviewed_at TIMESTAMP,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT check_leave_type CHECK (
                leave_type IN ('fmla', 'state_pfml', 'parental', 'bereavement',
                               'jury_duty', 'medical', 'military', 'unpaid_loa')
            ),
            CONSTRAINT check_leave_status CHECK (
                status IN ('requested', 'approved', 'denied',
                           'active', 'completed', 'cancelled')
            )
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_leave_requests_employee_id
            ON leave_requests(employee_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_leave_requests_org_id
            ON leave_requests(org_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_leave_requests_status
            ON leave_requests(status)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS employee_hours_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            hours_worked DECIMAL(8,2) NOT NULL,
            source VARCHAR(30) DEFAULT 'manual',
            created_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT check_hours_source CHECK (
                source IN ('manual', 'payroll_import', 'time_clock')
            ),
            CONSTRAINT uq_hours_log_employee_period
                UNIQUE(employee_id, period_start, period_end)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_employee_hours_log_employee_id
            ON employee_hours_log(employee_id)
    """)


def downgrade() -> None:
    """Drop leave_requests and employee_hours_log tables."""
    op.execute("DROP TABLE IF EXISTS employee_hours_log")
    op.execute("DROP TABLE IF EXISTS leave_requests")
