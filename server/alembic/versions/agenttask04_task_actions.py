"""Espresso Tasks: doing something with a finding (buy it, book it, write about it).

Revision ID: agenttask04
Revises: mwjobs02

A playbook declares the actions its findings take (`agent_tasks/actions/`).
Each one is proposed first: the server freezes exactly what it will do and
shows it; the person confirms; only then is it carried out, once. This table
is that record: the proposal (`frozen`, `preview`), its status, and what came
of it (`result`, a receipt or a link).

`status` moves proposed -> running -> done | failed, or proposed -> cancelled
| expired. Confirming claims the row (`status = 'proposed'`), so a second
confirm can't run it again. A new table only, so the upgrade is instant; the
downgrade drops it.
"""
from alembic import op

revision = "agenttask04"
down_revision = "mwjobs02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_agent_task_actions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            task_id UUID NOT NULL REFERENCES mw_agent_tasks(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES mw_agent_task_items(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            action TEXT NOT NULL CHECK (action ~ '^[a-z][a-z0-9_]{0,39}$'),
            status TEXT NOT NULL DEFAULT 'proposed'
                CHECK (status IN ('proposed', 'running', 'done', 'failed', 'cancelled', 'expired')),
            params JSONB NOT NULL DEFAULT '{}'::jsonb,
            frozen JSONB NOT NULL DEFAULT '{}'::jsonb,
            preview JSONB NOT NULL DEFAULT '{}'::jsonb,
            result JSONB,
            error TEXT,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            decided_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_agent_task_actions_item
            ON mw_agent_task_actions(item_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_agent_task_actions_user
            ON mw_agent_task_actions(user_id, action, created_at)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS mw_agent_task_actions")
