"""Add source to company_wc_mods (manual vs parsed worksheet)

Revision ID: wcmodsrc01
Revises: wcrate3dp01
Create Date: 2026-06-22

The experience-mod trajectory is being automated (gap-analysis: "automate Experience
Mod trajectory tracking"). A recorded mod can now arrive three ways; this column
distinguishes the two PERSISTED real-mod sources:
  - 'manual'    — broker keyed it (the original flow)
  - 'worksheet' — auto-extracted from the bureau experience-rating worksheet PDF

The directional 'proxy' (actual incurred ÷ expected losses) is computed live from
loss-runs + class payroll and is never stored, so it needs no enum value here.
Default 'manual' keeps every existing row valid with no backfill.
"""

from alembic import op


revision = "wcmodsrc01"
down_revision = "wcrate3dp01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE company_wc_mods
            ADD COLUMN IF NOT EXISTS source VARCHAR(16) NOT NULL DEFAULT 'manual'
                CHECK (source IN ('manual', 'worksheet'))
        """
    )


def downgrade():
    op.execute("ALTER TABLE company_wc_mods DROP COLUMN IF EXISTS source")
