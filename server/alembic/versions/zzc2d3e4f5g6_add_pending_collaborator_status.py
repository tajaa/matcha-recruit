"""Add 'pending' to mw_project_collaborators status check constraint.

Revision ID: zzc2d3e4f5g6
Revises: zzb1c2d3e4f5
Create Date: 2026-04-03
"""
from alembic import op

revision = "zzc2d3e4f5g6"
down_revision = "zzb1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE mw_project_collaborators DROP CONSTRAINT IF EXISTS mw_project_collaborators_status_check")
    op.execute("ALTER TABLE mw_project_collaborators ADD CONSTRAINT mw_project_collaborators_status_check CHECK (status IN ('active', 'pending', 'removed'))")


def downgrade() -> None:
    op.execute("ALTER TABLE mw_project_collaborators DROP CONSTRAINT IF EXISTS mw_project_collaborators_status_check")
    op.execute("ALTER TABLE mw_project_collaborators ADD CONSTRAINT mw_project_collaborators_status_check CHECK (status IN ('active', 'removed'))")
