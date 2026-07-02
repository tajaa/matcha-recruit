"""Tell-Us — add event_key to the points ledger.

Cooldown + daily-cap were scoped by `reason`, but multiple earning rules share
one reason ('earn_feedback' covers first_feedback, useful_feedback, and
feedback_with_media). Inside a single submission the earlier award tripped the
later rule's cooldown, so the media bonus never paid out. Scoping by the rule's
`event_key` needs the ledger to record it.

Revision ID: tellus_app_02
Revises: tellus_app_01
Create Date: 2026-07-01
"""
from alembic import op


revision = "tellus_app_02"
down_revision = "tellus_app_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tellus_points_ledger ADD COLUMN IF NOT EXISTS event_key TEXT")
    # Serves the cooldown ("latest award for this event") and daily-cap
    # ("today's total for this event") lookups.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_ledger_event "
        "ON tellus_points_ledger (account_id, event_key, created_at DESC) "
        "WHERE event_key IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tellus_ledger_event")
    op.execute("ALTER TABLE tellus_points_ledger DROP COLUMN IF EXISTS event_key")
