"""Add matcha_lite_invite_tokens table for admin-generated signup links.

Revision ID: zzzzdi4e5f6g7
Revises: zzzzci3d4e5f6
Create Date: 2026-05-23
"""
from alembic import op

revision = "zzzzdi4e5f6g7"
down_revision = "zzzzci3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS matcha_lite_invite_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            token VARCHAR(64) UNIQUE NOT NULL,
            created_by UUID REFERENCES users(id),
            note TEXT,
            used_at TIMESTAMPTZ,
            used_by_company_id UUID REFERENCES companies(id),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS matcha_lite_invite_tokens")
