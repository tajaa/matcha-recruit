"""Add companies.report_poster_branding (Magic-Link QR poster color scheme).

Per-company ``{"primary", "secondary"}`` hex palette for the anonymous-reporting
QR poster PDF. NULL = the Matcha default green/orange. Matcha branding on the
poster is not configurable; only the primary background + secondary accent are.

Revision ID: posterbrand01
Revises: irinforesp01
Create Date: 2026-07-03
"""
from alembic import op


revision = "posterbrand01"
down_revision = "irinforesp01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS report_poster_branding JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS report_poster_branding")
