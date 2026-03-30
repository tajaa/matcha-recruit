"""Add project_type and project_data columns to mw_projects.

Revision ID: zy3z4a5b6c7d
Revises: zx2y3z4a5b6c
Create Date: 2026-03-30
"""
from alembic import op

revision = "zy3z4a5b6c7d"
down_revision = "zx2y3z4a5b6c"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE mw_projects ADD COLUMN IF NOT EXISTS project_type VARCHAR(30) DEFAULT 'general'")
    op.execute("ALTER TABLE mw_projects ADD COLUMN IF NOT EXISTS project_data JSONB DEFAULT '{}'::jsonb")


def downgrade():
    op.execute("ALTER TABLE mw_projects DROP COLUMN IF EXISTS project_data")
    op.execute("ALTER TABLE mw_projects DROP COLUMN IF EXISTS project_type")
