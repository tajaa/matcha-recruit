"""add er_case_export_links table

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-03-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b5c6d7e8f9a0'
down_revision: Union[str, Sequence[str], None] = 'a4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS er_case_export_links (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id UUID NOT NULL REFERENCES er_cases(id) ON DELETE CASCADE,
            org_id UUID NOT NULL,
            token VARCHAR(64) NOT NULL UNIQUE,
            password_hash VARCHAR(256) NOT NULL,
            storage_path TEXT NOT NULL,
            filename VARCHAR(256) NOT NULL,
            created_by UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            download_count INT NOT NULL DEFAULT 0,
            last_downloaded_at TIMESTAMPTZ,
            failed_attempts INT NOT NULL DEFAULT 0
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_er_export_links_token ON er_case_export_links(token)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_er_export_links_case_id ON er_case_export_links(case_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS er_case_export_links")
