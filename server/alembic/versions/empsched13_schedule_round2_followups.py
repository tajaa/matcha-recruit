"""Activate schedule digests and make manager-ready request email durable."""

from alembic import op


revision = "empsched13"
down_revision = "empsched12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The digest worker and idempotent delivery table shipped disabled. This
    # ticket makes the daily break/shift-note summary an active feature.
    op.execute("UPDATE scheduler_settings SET enabled=true WHERE task_key='schedule_daily_digest'")
    op.execute("""
        INSERT INTO scheduler_settings(task_key, display_name, description, enabled, max_per_cycle)
        VALUES ('schedule_request_notifications', 'Schedule request notifications',
                'Recovery delivery for manager-ready pickup and swap requests.', true, 500)
        ON CONFLICT (task_key) DO UPDATE SET enabled=true
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS schedule_request_notification_deliveries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            request_id UUID NOT NULL REFERENCES schedule_requests(id) ON DELETE CASCADE,
            recipient_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            event_type VARCHAR(40) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sent_at TIMESTAMPTZ,
            UNIQUE (request_id, recipient_user_id, event_type)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_schedule_request_notification_unsent
        ON schedule_request_notification_deliveries(company_id, created_at)
        WHERE sent_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_schedule_request_notification_unsent")
    op.execute("DROP TABLE IF EXISTS schedule_request_notification_deliveries")
    op.execute("DELETE FROM scheduler_settings WHERE task_key='schedule_request_notifications'")
    op.execute("UPDATE scheduler_settings SET enabled=false WHERE task_key='schedule_daily_digest'")
