"""Broker Pilot — starter template ("mode") on sessions

Revision ID: brokerpilot02
Revises: brokerpilot01
Create Date: 2026-07-12

Adds `broker_pilot_sessions.template_key` — the starter mode a broker chose when
opening the session (contract_review / mid_year / renewal_90 / new_business /
loss_run / quote_comparison). NULL means an open-ended session (legacy rows +
"Open analysis"). The catalog itself lives in code
(`services/broker_pilot.py:PILOT_TEMPLATES`); this column only persists which one
a session is in, so the analyst prompt can stay "in mode" on every turn.

NOTE: the alembic history on this branch has multiple leaves; `down_revision` is
set to `brokerpilot01` (the migration that created these tables). Confirm the
correct head for your environment before `alembic upgrade`. The change is a
single idempotent ADD COLUMN, so it composes cleanly wherever it lands in the
chain.
"""

from alembic import op


revision = "brokerpilot02"
down_revision = "brokerpilot01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE broker_pilot_sessions "
        "ADD COLUMN IF NOT EXISTS template_key VARCHAR(40)"
    )


def downgrade():
    op.execute("ALTER TABLE broker_pilot_sessions DROP COLUMN IF EXISTS template_key")
