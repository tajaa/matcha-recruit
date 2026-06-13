"""Cappe booking self-serve + reminders.

Bookings get an unguessable `access_token` (same pattern as cappe_orders) so a
customer can view / cancel / reschedule from an emailed link without an account,
and a `reminder_sent_at` stamp so the reminder job sends exactly once. Also
seeds the (disabled) scheduler_settings row that gates the reminder Celery task.

Revision ID: zzzzcappe09
Revises: zzzzcappe08
"""
from alembic import op

revision = "zzzzcappe09"
down_revision = "zzzzcappe08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Unguessable customer access token (DEFAULT covers new inserts).
    op.execute("""
        ALTER TABLE cappe_bookings
            ADD COLUMN IF NOT EXISTS access_token VARCHAR(64)
                DEFAULT replace(gen_random_uuid()::text, '-', ''),
            ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMPTZ
    """)
    # Backfill existing rows (DEFAULT only applies to new inserts).
    op.execute(
        "UPDATE cappe_bookings SET access_token = replace(gen_random_uuid()::text, '-', '') "
        "WHERE access_token IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_bookings_access_token "
        "ON cappe_bookings(access_token)"
    )
    # Cheap scan for the reminder job: confirmed, not-yet-reminded, by start time.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_bookings_reminder "
        "ON cappe_bookings(starts_at) "
        "WHERE status = 'confirmed' AND reminder_sent_at IS NULL"
    )
    # Disabled-by-default scheduler row gating the reminder task.
    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES (
            'cappe_booking_reminders',
            'Cappe Booking Reminders',
            'Emails Cappe customers a reminder ~24h before a confirmed booking.',
            false,
            200
        )
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'cappe_booking_reminders'")
    op.execute("DROP INDEX IF EXISTS idx_cappe_bookings_reminder")
    op.execute("DROP INDEX IF EXISTS idx_cappe_bookings_access_token")
    op.execute("ALTER TABLE cappe_bookings DROP COLUMN IF EXISTS reminder_sent_at")
    op.execute("ALTER TABLE cappe_bookings DROP COLUMN IF EXISTS access_token")
