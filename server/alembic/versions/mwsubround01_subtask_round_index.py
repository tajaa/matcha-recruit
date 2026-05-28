"""Add mw_subtasks.round_index — per-round checklist scoping on kanban tickets.

Each kanban ticket runs in review-cycle "rounds" (round 1 = initial work; every
"Start Next Round" opens the next). Until now subtasks were a single flat list
shared across all rounds. `round_index` scopes a checklist item to the round it
belongs to: starting a new round rolls every *uncompleted* item forward into the
new round and leaves *completed* items stamped on the round they were finished
in (so they archive out of the live checklist and only surface in that round's
"Fixed in Round N" history rollup).

Existing rows default to round 1 — correct for any ticket that never started a
second round. Idempotent (ADD COLUMN IF NOT EXISTS).

Revision ID: mwsubround01
Revises: cmpreqbf02
Create Date: 2026-05-28
"""
from alembic import op


revision = "mwsubround01"
down_revision = "cmpreqbf02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE mw_subtasks "
        "ADD COLUMN IF NOT EXISTS round_index INTEGER NOT NULL DEFAULT 1"
    )


def downgrade():
    op.execute("ALTER TABLE mw_subtasks DROP COLUMN IF EXISTS round_index")
