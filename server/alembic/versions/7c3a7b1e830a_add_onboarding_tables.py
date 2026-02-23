"""add_onboarding_tables

Revision ID: 7c3a7b1e830a
Revises: 7c2a6a0d729f
Create Date: 2026-01-19 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision = '7c3a7b1e830a'
down_revision = '7c2a6a0d729f'
branch_labels = None
depends_on = None
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c3a7b1e830a'
down_revision: Union[str, Sequence[str], None] = '7c2a6a0d729f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create onboarding_tasks table (template tasks)
    op.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_tasks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            title VARCHAR(500) NOT NULL,
            description TEXT,
            category VARCHAR(50) NOT NULL DEFAULT 'admin',
            is_employee_task BOOLEAN NOT NULL DEFAULT false,
            due_days INTEGER DEFAULT 7,
            is_active BOOLEAN NOT NULL DEFAULT true,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT check_category CHECK (
                category IN ('documents', 'equipment', 'training', 'admin')
            )
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_onboarding_tasks_org_id ON onboarding_tasks(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_onboarding_tasks_category ON onboarding_tasks(category)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_onboarding_tasks_is_active ON onboarding_tasks(is_active)")

    # Create employee_onboarding_tasks table (assigned tasks)
    op.execute("""
        CREATE TABLE IF NOT EXISTS employee_onboarding_tasks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            task_id UUID REFERENCES onboarding_tasks(id) ON DELETE SET NULL,
            title VARCHAR(500) NOT NULL,
            description TEXT,
            category VARCHAR(50) NOT NULL DEFAULT 'admin',
            is_employee_task BOOLEAN NOT NULL DEFAULT false,
            due_date DATE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            completed_at TIMESTAMP,
            completed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT check_onboarding_category CHECK (
                category IN ('documents', 'equipment', 'training', 'admin')
            ),
            CONSTRAINT check_onboarding_status CHECK (
                status IN ('pending', 'completed', 'skipped')
            )
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_employee_onboarding_tasks_employee_id ON employee_onboarding_tasks(employee_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_employee_onboarding_tasks_status ON employee_onboarding_tasks(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_employee_onboarding_tasks_task_id ON employee_onboarding_tasks(task_id)")

    # Add denial_reason column to pto_requests if not exists
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'pto_requests' AND column_name = 'denial_reason'
            ) THEN
                ALTER TABLE pto_requests ADD COLUMN denial_reason TEXT;
            END IF;
        END $$;
    """)

    # Add carryover_hours column to pto_balances if not exists
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'pto_balances' AND column_name = 'carryover_hours'
            ) THEN
                ALTER TABLE pto_balances ADD COLUMN carryover_hours DECIMAL(6,2) DEFAULT 0;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS employee_onboarding_tasks CASCADE")
    op.execute("DROP TABLE IF EXISTS onboarding_tasks CASCADE")
