"""Add mw_project_elements table and element_id to mw_project_tasks.

Revision ID: zzzzah1b2c3d4
Revises: zzzz9h0i1j2k3
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa

revision = "zzzzah1b2c3d4"
down_revision = "zzzz9h0i1j2k3"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_project_elements (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            project_id UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            kind TEXT,
            description TEXT,
            assigned_to TEXT,
            "order" INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_project_elements_project ON mw_project_elements(project_id)")
    op.execute("""
        ALTER TABLE mw_tasks
        ADD COLUMN IF NOT EXISTS element_id TEXT REFERENCES mw_project_elements(id) ON DELETE SET NULL
    """)


def downgrade():
    op.execute("ALTER TABLE mw_tasks DROP COLUMN IF EXISTS element_id")
    op.execute("DROP TABLE IF EXISTS mw_project_elements")
