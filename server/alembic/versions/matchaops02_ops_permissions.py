"""Add company-scoped Matcha Ops permission overrides."""

from alembic import op


revision = "matchaops02"
down_revision = "matchaops01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops_permissions (
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
        CREATE TABLE IF NOT EXISTS ops_permission_audit_log (
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
        """
        INSERT INTO ops_permissions (company_id, user_id, level, granted_by, created_at, updated_at)
        SELECT company_id, user_id, level, granted_by, created_at, updated_at
          FROM mw_work_permissions
        ON CONFLICT (company_id, user_id) DO NOTHING
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ops_permissions_user ON ops_permissions(user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ops_permission_audit_log")
    op.execute("DROP TABLE IF EXISTS ops_permissions")
