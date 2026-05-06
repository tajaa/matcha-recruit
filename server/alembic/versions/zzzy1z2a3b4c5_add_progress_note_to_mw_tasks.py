"""Add progress_note column to mw_tasks for per-task 'where we are at' status.

Revision ID: zzzy1z2a3b4c5
Revises: zzzx0y1z2a3b4
Create Date: 2026-05-06
"""
from alembic import op


revision = "zzzy1z2a3b4c5"
down_revision = "zzzx0y1z2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE mw_tasks ADD COLUMN IF NOT EXISTS progress_note TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE mw_tasks DROP COLUMN IF EXISTS progress_note")
