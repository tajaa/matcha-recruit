"""Persist location/week-scoped Huume sessions for the schedule editor.

The schedule editor must use the same durable ``mw_threads`` conversation and
Huume run/step audit trail as Matcha Work.  ``surface`` keeps these internal
assistant threads out of the regular workspace listing; the session mapping
prevents one manager, location, or week from inheriting another one's context.

Revision ID: huumesched01
Revises: empsched08
"""

from alembic import op


revision = "huumesched01"
down_revision = "empsched08"
branch_labels = None
# huume_mode is introduced on a separate migration branch; this migration
# writes that column when it creates a schedule thread, so make the ordering
# explicit for fresh databases applying all heads.
depends_on = "huume02"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE mw_threads
        ADD COLUMN IF NOT EXISTS surface VARCHAR(32) NOT NULL DEFAULT 'workspace'
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'mw_threads_surface_check'
            ) THEN
                ALTER TABLE mw_threads
                ADD CONSTRAINT mw_threads_surface_check
                CHECK (surface IN ('workspace', 'schedule_assistant'));
            END IF;
        END $$
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_threads_surface
        ON mw_threads(company_id, surface, updated_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_assistant_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
            week_start DATE NOT NULL,
            thread_id UUID NOT NULL UNIQUE REFERENCES mw_threads(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(company_id, user_id, location_id, week_start)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_schedule_assistant_sessions_location
        ON schedule_assistant_sessions(company_id, location_id, week_start)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_digest_deliveries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
            digest_date DATE NOT NULL,
            recipient_email VARCHAR(320) NOT NULL,
            recipient_type VARCHAR(20) NOT NULL CHECK (recipient_type IN ('manager', 'employee')),
            sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(location_id, digest_date, recipient_email, recipient_type)
        )
        """
    )
    op.execute(
        """
        INSERT INTO scheduler_settings(task_key, display_name, description, enabled, max_per_cycle)
        VALUES ('schedule_daily_digest', 'Daily schedule digest',
                'Break requirements and visible schedule notes for location managers and employees.',
                false, 500)
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM scheduler_settings WHERE task_key='schedule_daily_digest'")
    op.execute("DROP TABLE IF EXISTS schedule_digest_deliveries")
    op.execute("DROP TABLE IF EXISTS schedule_assistant_sessions")
    op.execute("DROP INDEX IF EXISTS idx_mw_threads_surface")
    op.execute("ALTER TABLE mw_threads DROP CONSTRAINT IF EXISTS mw_threads_surface_check")
    op.execute("ALTER TABLE mw_threads DROP COLUMN IF EXISTS surface")
