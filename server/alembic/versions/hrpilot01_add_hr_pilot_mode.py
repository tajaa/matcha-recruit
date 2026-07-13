"""add hr_pilot_mode column to mw_threads

New Matcha Work thread grounding mode (see
app/matcha/services/matcha_work_modes.py THREAD_MODES registry).

Revision ID: hrpilot01
Revises: mwmodes01
Create Date: 2026-07-13
"""

from alembic import op


revision = "hrpilot01"
down_revision = "mwmodes01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE mw_threads
        ADD COLUMN IF NOT EXISTS hr_pilot_mode BOOLEAN NOT NULL DEFAULT false
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE mw_threads
        DROP COLUMN IF EXISTS hr_pilot_mode
        """
    )
