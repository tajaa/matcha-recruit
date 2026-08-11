"""Company-scoped Matcha Work permissions.

Explicit grants supplement the existing client/employee defaults. The
resource owner company is always supplied by the caller before authorization
is resolved, preventing a collaborator's home-company role from widening
access to another tenant.

Revision ID: mwperm01
Revises: huumecode01
"""

from alembic import op


revision = "mwperm01"
down_revision = "huumecode01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_work_permissions (
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            level VARCHAR(20) NOT NULL
                CHECK (level IN ('member', 'reviewer', 'operator', 'admin')),
            granted_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (company_id, user_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_work_permissions_user
            ON mw_work_permissions(user_id)
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS mw_work_permissions")
