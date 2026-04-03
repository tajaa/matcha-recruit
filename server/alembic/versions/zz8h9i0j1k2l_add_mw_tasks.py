"""Add mw_tasks and mw_task_dismissals tables.

Revision ID: zz8h9i0j1k2l
Revises: zz7g8h9i0j1k
Create Date: 2026-04-02
"""
from alembic import op

revision = "zz8h9i0j1k2l"
down_revision = "zz7g8h9i0j1k"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_tasks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            created_by UUID NOT NULL REFERENCES users(id),
            title VARCHAR(500) NOT NULL,
            description TEXT,
            due_date DATE,
            horizon VARCHAR(20) CHECK (horizon IN ('today','this_week','this_month','this_quarter')),
            priority VARCHAR(20) NOT NULL DEFAULT 'medium'
                CHECK (priority IN ('critical','high','medium','low')),
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','completed','cancelled')),
            completed_at TIMESTAMPTZ,
            link VARCHAR(500),
            category VARCHAR(40) DEFAULT 'manual',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_tasks_company_status ON mw_tasks(company_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_tasks_due_date ON mw_tasks(company_id, due_date) WHERE status = 'pending'")

    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_task_dismissals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            source_category VARCHAR(40) NOT NULL,
            source_id TEXT NOT NULL,
            dismissed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, source_category, source_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_task_dismissals_user ON mw_task_dismissals(user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mw_task_dismissals")
    op.execute("DROP TABLE IF EXISTS mw_tasks")
