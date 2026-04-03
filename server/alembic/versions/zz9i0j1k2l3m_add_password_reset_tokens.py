"""Add password_reset_tokens table.

Revision ID: zz9i0j1k2l3m
Revises: zz8h9i0j1k2l
Create Date: 2026-04-02
"""
from alembic import op

revision = "zz9i0j1k2l3m"
down_revision = "zz8h9i0j1k2l"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            token VARCHAR(128) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS password_reset_tokens")
