"""Add mw_projects table and project_id to mw_threads.

Revision ID: zx2y3z4a5b6c
Revises: zw1x2y3z4a5b
Create Date: 2026-03-30
"""
from alembic import op

revision = "zx2y3z4a5b6c"
down_revision = "zw1x2y3z4a5b"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_projects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            created_by UUID NOT NULL REFERENCES users(id),
            title VARCHAR(255) NOT NULL DEFAULT 'Untitled Project',
            sections JSONB DEFAULT '[]'::jsonb,
            status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            is_pinned BOOLEAN DEFAULT false,
            version INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_mw_projects_company_id ON mw_projects(company_id);

        ALTER TABLE mw_threads ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES mw_projects(id) ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS idx_mw_threads_project_id ON mw_threads(project_id);
    """)


def downgrade():
    op.execute("""
        ALTER TABLE mw_threads DROP COLUMN IF EXISTS project_id;
        DROP TABLE IF EXISTS mw_projects;
    """)
