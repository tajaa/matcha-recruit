"""User-authorized Apple Calendar bridge; no provider credentials are stored.

Revision ID: mwcal02
Revises: mwcal01
"""
from alembic import op
revision = "mwcal02"
down_revision = "mwcal01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE mw_apple_calendar_connections (
            user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            connection_id UUID NOT NULL,
            calendars JSONB NOT NULL DEFAULT '[]'::jsonb,
            destination TEXT NOT NULL,
            snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
            window_start TIMESTAMPTZ,
            window_end TIMESTAMPTZ,
            complete BOOLEAN NOT NULL DEFAULT TRUE,
            synced_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE TABLE mw_apple_calendar_actions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            connection_id UUID NOT NULL,
            operation TEXT NOT NULL CHECK (operation IN ('create', 'update', 'delete')),
            payload JSONB NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'claimed', 'done', 'failed', 'unknown', 'cancelled')),
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            claimed_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX idx_mw_apple_actions_user ON mw_apple_calendar_actions(user_id, created_at DESC)")
    op.execute("CREATE INDEX idx_mw_apple_actions_pending ON mw_apple_calendar_actions(user_id) WHERE status = 'pending'")


def downgrade():
    op.execute("DROP TABLE mw_apple_calendar_actions")
    op.execute("DROP TABLE mw_apple_calendar_connections")
