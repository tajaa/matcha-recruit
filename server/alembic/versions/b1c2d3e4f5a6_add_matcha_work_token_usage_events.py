"""add matcha work token usage events

Revision ID: b1c2d3e4f5a6
Revises: a2b3c4d5e6f8
Create Date: 2026-02-25
"""

from alembic import op


revision = "b1c2d3e4f5a6"
down_revision = "a2b3c4d5e6f8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_token_usage_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
            model VARCHAR(120) NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            estimated BOOLEAN NOT NULL DEFAULT false,
            operation VARCHAR(40) NOT NULL DEFAULT 'send_message',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_token_usage_events_company_user_model_created
        ON mw_token_usage_events(company_id, user_id, model, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_token_usage_events_thread_id
        ON mw_token_usage_events(thread_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_token_usage_events_user_created
        ON mw_token_usage_events(user_id, created_at)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_mw_token_usage_events_user_created")
    op.execute("DROP INDEX IF EXISTS idx_mw_token_usage_events_thread_id")
    op.execute("DROP INDEX IF EXISTS idx_mw_token_usage_events_company_user_model_created")
    op.execute("DROP TABLE IF EXISTS mw_token_usage_events")
