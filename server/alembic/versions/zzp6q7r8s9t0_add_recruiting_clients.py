"""Add recruiting_clients table and hiring_client_id on mw_projects.

Gives freelance recruiters a way to organize projects by the external hiring
client they're recruiting for. Business users can also opt in.

Revision ID: zzp6q7r8s9t0
Revises: zzo5p6q7r8s9
Create Date: 2026-04-13
"""
from alembic import op

revision = "zzp6q7r8s9t0"
down_revision = "zzo5p6q7r8s9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS recruiting_clients (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            website TEXT,
            logo_url TEXT,
            notes TEXT,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            archived_at TIMESTAMPTZ
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_recruiting_clients_company "
        "ON recruiting_clients(company_id) WHERE archived_at IS NULL"
    )
    op.execute(
        "ALTER TABLE mw_projects ADD COLUMN IF NOT EXISTS hiring_client_id "
        "UUID REFERENCES recruiting_clients(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_projects_hiring_client "
        "ON mw_projects(hiring_client_id) WHERE hiring_client_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_mw_projects_hiring_client")
    op.execute("ALTER TABLE mw_projects DROP COLUMN IF EXISTS hiring_client_id")
    op.execute("DROP INDEX IF EXISTS idx_recruiting_clients_company")
    op.execute("DROP TABLE IF EXISTS recruiting_clients")
