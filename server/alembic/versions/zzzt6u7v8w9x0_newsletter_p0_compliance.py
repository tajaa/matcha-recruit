"""newsletter P0 — soft-bounce counter, scheduled_send claim, per-send bounce trace, preheader

P0 of the newsletter improvement plan. Adds the columns the application code
needs to (a) cap soft bounces at 3 before suppressing a subscriber,
(b) claim a scheduled newsletter atomically so two beats can't double-send,
(c) record per-send bounce kind, and (d) carry a preheader through to the
email template.

Revision ID: zzzt6u7v8w9x0
Revises: zzzs5t6u7v8w9
Create Date: 2026-05-03
"""

from alembic import op


revision = "zzzt6u7v8w9x0"
down_revision = "zzzs5t6u7v8w9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE newsletter_subscribers
            ADD COLUMN IF NOT EXISTS soft_bounce_count INT NOT NULL DEFAULT 0
    """)
    op.execute("""
        ALTER TABLE newsletters
            ADD COLUMN IF NOT EXISTS preheader VARCHAR(255),
            ADD COLUMN IF NOT EXISTS scheduled_send_started_at TIMESTAMPTZ
    """)
    op.execute("""
        ALTER TABLE newsletter_sends
            ADD COLUMN IF NOT EXISTS bounced_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS bounce_kind VARCHAR(20)
    """)
    # Partial index — beats only scan the small set of newsletters waiting
    # to be picked up.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_newsletters_scheduled
            ON newsletters(status, scheduled_at)
            WHERE status = 'scheduled' AND scheduled_at IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_newsletters_scheduled")
    op.execute("ALTER TABLE newsletter_sends DROP COLUMN IF EXISTS bounce_kind")
    op.execute("ALTER TABLE newsletter_sends DROP COLUMN IF EXISTS bounced_at")
    op.execute("ALTER TABLE newsletters DROP COLUMN IF EXISTS scheduled_send_started_at")
    op.execute("ALTER TABLE newsletters DROP COLUMN IF EXISTS preheader")
    op.execute("ALTER TABLE newsletter_subscribers DROP COLUMN IF EXISTS soft_bounce_count")
