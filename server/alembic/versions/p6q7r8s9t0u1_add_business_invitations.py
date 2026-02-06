"""add business_invitations table

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-02-06
"""
from alembic import op
import sqlalchemy as sa

revision = "p6q7r8s9t0u1"
down_revision = "o5p6q7r8s9t0"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS business_invitations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            token VARCHAR(64) NOT NULL UNIQUE,
            created_by UUID NOT NULL REFERENCES users(id),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            used_by_company_id UUID REFERENCES companies(id),
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP,
            note TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_business_invitations_token
        ON business_invitations(token)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS business_invitations")
