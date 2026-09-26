"""Durable employee schedule notification deliveries.

Revision ID: empsched26
Revises: empsched25
"""

from alembic import op


revision = "empsched26"
down_revision = "empsched25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE schedule_employee_notification_deliveries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            recipient_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            event_type VARCHAR(40) NOT NULL,
            dedupe_key TEXT NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sent_at TIMESTAMPTZ,
            attempts INTEGER NOT NULL DEFAULT 0,
            failed_at TIMESTAMPTZ,
            UNIQUE (recipient_user_id, event_type, dedupe_key)
        )
    """)
    op.execute("""
        CREATE INDEX ix_schedule_employee_notifications_pending
        ON schedule_employee_notification_deliveries(created_at)
        WHERE sent_at IS NULL AND failed_at IS NULL
    """)
    op.execute("""
        INSERT INTO scheduler_settings(task_key, display_name, description, enabled, max_per_cycle)
        VALUES ('schedule_employee_notifications', 'Employee schedule notifications',
                'Recover employee schedule bell and push deliveries.', true, 500)
        ON CONFLICT (task_key) DO UPDATE SET enabled=true
    """)


def downgrade() -> None:
    op.execute("DELETE FROM scheduler_settings WHERE task_key='schedule_employee_notifications'")
    op.execute("DROP INDEX ix_schedule_employee_notifications_pending")
    op.execute("DROP TABLE schedule_employee_notification_deliveries")
