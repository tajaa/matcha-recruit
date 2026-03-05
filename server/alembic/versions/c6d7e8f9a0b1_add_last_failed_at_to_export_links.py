"""add last_failed_at to er_case_export_links

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-03-05
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c6d7e8f9a0b1'
down_revision: Union[str, Sequence[str], None] = 'b5c6d7e8f9a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE er_case_export_links
        ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMPTZ
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE er_case_export_links DROP COLUMN IF EXISTS last_failed_at")
