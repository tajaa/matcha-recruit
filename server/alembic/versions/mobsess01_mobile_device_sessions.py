"""Add independently revocable Matcha Schedule device sessions.

Revision ID: mobsess01
Revises: invitefix01
"""

from alembic import op


revision = "mobsess01"
down_revision = "invitefix01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE auth_device_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            client VARCHAR(32) NOT NULL,
            device_name TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            revoked_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX idx_auth_device_sessions_active_user
        ON auth_device_sessions(user_id) WHERE revoked_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE auth_device_sessions")
