"""Productivity card due_date — ties cards to the calendar view.

A card with a `due_date` shows on the calendar on that day; the kanban shows it
by column regardless. Nullable, so board-only cards stay off the calendar.

Revision ID: prodcal01
Revises: prodkanban01
Create Date: 2026-06-10
"""
from alembic import op


revision = "prodcal01"
down_revision = "prodkanban01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE mw_productivity_cards ADD COLUMN IF NOT EXISTS due_date DATE")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_prod_cards_due ON mw_productivity_cards(board_id, due_date)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_mw_prod_cards_due")
    op.execute("ALTER TABLE mw_productivity_cards DROP COLUMN IF EXISTS due_date")
