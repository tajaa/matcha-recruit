"""Add risk_assessment_snapshots.recommendations_at

The Gemini recommendations pass (report + recommendations) was debounced off
`computed_at` — but pass 1 (dimensions) rewrites `computed_at` on every
refresh, so a company edited more often than every 10 minutes never
regenerated its recommendations. Gate that pass on its own timestamp
instead. Backfilled from `computed_at` so existing snapshots don't all
trigger a Gemini burst on the next refresh.

Revision ID: riskrec01
Revises: oploc01
Create Date: 2026-08-03
"""

from alembic import op


revision = "riskrec01"
down_revision = "oploc01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE risk_assessment_snapshots
        ADD COLUMN IF NOT EXISTS recommendations_at TIMESTAMPTZ
    """)
    op.execute("""
        UPDATE risk_assessment_snapshots
        SET recommendations_at = computed_at
        WHERE recommendations_at IS NULL
    """)


def downgrade():
    op.execute("ALTER TABLE risk_assessment_snapshots DROP COLUMN IF EXISTS recommendations_at")
