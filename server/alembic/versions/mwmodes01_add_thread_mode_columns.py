"""add benefits/legal/risk/training mode columns to mw_threads

New Matcha Work thread grounding modes (see
app/matcha/services/matcha_work_modes.py THREAD_MODES registry).

Revision ID: mwmodes01
Revises: zzzzbi2c3d4e5
Create Date: 2026-07-11
"""

from alembic import op


revision = "mwmodes01"
down_revision = "zzzzbi2c3d4e5"
branch_labels = None
depends_on = None

_COLUMNS = ("benefits_mode", "legal_mode", "risk_mode", "training_mode")


def upgrade():
    for col in _COLUMNS:
        op.execute(
            f"""
            ALTER TABLE mw_threads
            ADD COLUMN IF NOT EXISTS {col} BOOLEAN NOT NULL DEFAULT false
            """
        )


def downgrade():
    for col in _COLUMNS:
        op.execute(
            f"""
            ALTER TABLE mw_threads
            DROP COLUMN IF EXISTS {col}
            """
        )
