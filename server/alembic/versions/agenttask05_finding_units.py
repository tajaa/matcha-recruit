"""Espresso Tasks: an apartment building's homes for rent, one by one, and page screenshots.

Revision ID: agenttask05
Revises: agenttask04

A building found by an apartments task has many homes. Where its leasing
system publishes them (`research/units.py`: SightMap, Avalon), each one is
kept in `units`: unit number, floor, beds, baths, square feet, rent, move-in
date, any special and its floor plan. The person's limits are checked per
home, so a building fits only when one real home meets all of them.

`screenshots` keeps a finding's page as the browser drew it, apart from its
photos: it never counts against the photo caps or stands in for a photo.

Columns with a constant default, so the upgrade changes no rows and is
instant; the downgrade drops them.
"""
from alembic import op

revision = "agenttask05"
down_revision = "agenttask04"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE mw_agent_task_items
            ADD COLUMN IF NOT EXISTS units JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS screenshots JSONB NOT NULL DEFAULT '[]'::jsonb
    """)


def downgrade():
    op.execute("""
        ALTER TABLE mw_agent_task_items
            DROP COLUMN IF EXISTS screenshots,
            DROP COLUMN IF EXISTS units
    """)
