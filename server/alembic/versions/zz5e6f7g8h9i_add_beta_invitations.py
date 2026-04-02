"""Add beta_invitations table.

Revision ID: zz5e6f7g8h9i
Revises: zz4d5e6f7g8h
Create Date: 2026-04-02
"""
from alembic import op

revision = "zz5e6f7g8h9i"
down_revision = "zz4d5e6f7g8h"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS beta_invitations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) NOT NULL,
            token VARCHAR(64) NOT NULL UNIQUE,
            status VARCHAR(20) DEFAULT 'pending',
            invited_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            registered_at TIMESTAMPTZ,
            user_id UUID REFERENCES users(id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_beta_invitations_token ON beta_invitations(token)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_beta_invitations_email ON beta_invitations(email)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS beta_invitations")
