"""Audit Matcha Work permission changes.

Revision ID: mwperm02
Revises: ems03
"""

from alembic import op


revision = "mwperm02"
down_revision = "ems03"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_work_permission_audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            action VARCHAR(20) NOT NULL CHECK (action IN ('granted', 'updated', 'revoked')),
            old_level VARCHAR(20),
            new_level VARCHAR(20),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_work_permission_audit_company "
        "ON mw_work_permission_audit_log(company_id, created_at DESC)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS mw_work_permission_audit_log")
