"""Add workbook_type to handbooks

Revision ID: zr6s7t8u9v0w
Revises: zq5r6s7t8u9v
Create Date: 2026-03-18
"""

from alembic import op

revision = "zr6s7t8u9v0w"
down_revision = "zq5r6s7t8u9v"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE handbooks ADD COLUMN IF NOT EXISTS workbook_type VARCHAR(60)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_handbooks_workbook_type ON handbooks(workbook_type)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_handbooks_workbook_type")
    op.execute("ALTER TABLE handbooks DROP COLUMN IF EXISTS workbook_type")
