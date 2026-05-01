"""add stripe_webhook_events for top-level event ID dedupe

Revision ID: zzzr4s5t6u7v8
Revises: zzzq3r4s5t6u7
Create Date: 2026-05-01
"""

from alembic import op

revision = "zzzr4s5t6u7v8"
down_revision = "zzzq3r4s5t6u7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS stripe_webhook_events (
            event_id   VARCHAR(128) PRIMARY KEY,
            event_type VARCHAR(100) NOT NULL,
            received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_stripe_webhook_events_received_at
            ON stripe_webhook_events (received_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stripe_webhook_events")
