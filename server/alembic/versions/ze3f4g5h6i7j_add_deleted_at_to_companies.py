"""add deleted_at to companies

Revision ID: ze3f4g5h6i7j
Revises: zd2e3f4g5h6i
Create Date: 2026-03-12
"""
from alembic import op

revision = "ze3f4g5h6i7j"
down_revision = "zd2e3f4g5h6i"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP")


def downgrade() -> None:
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS deleted_at")
