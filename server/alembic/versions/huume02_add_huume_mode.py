"""huume: add huume_mode column to mw_threads

New Matcha Work thread grounding mode — the agentic onboarding harness
(see app/matcha/services/matcha_work/matcha_work_modes.py THREAD_MODES
registry). Mirrors hrpilot01_add_hr_pilot_mode.py's shape.

Revision ID: huume02
Revises: huume01
Create Date: 2026-07-26
"""

from alembic import op


revision = "huume02"
down_revision = "huume01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE mw_threads
        ADD COLUMN IF NOT EXISTS huume_mode BOOLEAN NOT NULL DEFAULT false
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE mw_threads
        DROP COLUMN IF EXISTS huume_mode
        """
    )
