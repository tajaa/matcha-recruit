"""Add mw_project_files table for project file attachments.

Revision ID: zzb1c2d3e4f5
Revises: zza0b1c2d3e4
Create Date: 2026-04-03
"""
from alembic import op

revision = "zzb1c2d3e4f5"
down_revision = "zza0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_project_files (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            uploaded_by UUID NOT NULL REFERENCES users(id),
            filename VARCHAR(500) NOT NULL,
            storage_url TEXT NOT NULL,
            content_type VARCHAR(100),
            file_size BIGINT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_project_files_project_id ON mw_project_files(project_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mw_project_files")
