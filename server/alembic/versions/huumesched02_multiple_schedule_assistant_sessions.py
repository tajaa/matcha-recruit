"""Allow a manager more than one schedule-assistant chat per location/week.

The editor opened the same durable thread forever, so every question a manager
ever asked about a store's week lived in one unbounded conversation.  The
surface now opens a fresh thread each time and lets the manager go back to an
earlier one, which means the ``(company, user, location, week_start)`` unique
constraint has to go.  The auth boundary is unchanged: a session is still
resolved by that tuple, it just no longer has to be the only one.

Revision ID: huumesched02
Revises: schedloc02
"""

from alembic import op


revision = "huumesched02"
down_revision = "schedloc02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The constraint name is server-generated (and truncated at 63 chars on
    # some databases), so find it by its column set rather than by name.
    op.execute(
        """
        DO $$
        DECLARE constraint_name text;
        BEGIN
            SELECT c.conname INTO constraint_name
            FROM pg_constraint c
            WHERE c.conrelid = 'schedule_assistant_sessions'::regclass
              AND c.contype = 'u'
              AND (
                  SELECT array_agg(a.attname ORDER BY a.attname)
                  FROM pg_attribute a
                  WHERE a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
              ) = ARRAY['company_id', 'location_id', 'user_id', 'week_start']
            ORDER BY c.conname
            LIMIT 1;
            IF constraint_name IS NOT NULL THEN
                EXECUTE format(
                    'ALTER TABLE schedule_assistant_sessions DROP CONSTRAINT %I',
                    constraint_name
                );
            END IF;
        END $$
        """
    )
    # The panel lists a manager's own prior chats for one location/week.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_schedule_assistant_sessions_owner_week
        ON schedule_assistant_sessions(
            company_id, user_id, location_id, week_start, created_at DESC
        )
        """
    )


def downgrade() -> None:
    """Re-collapse to one session per tuple.

    Restoring the constraint means the extra conversations cannot be kept.
    The newest session per tuple survives; the older rows (and the threads
    they point at) are dropped, so this direction loses chat history.
    """
    op.execute(
        """
        DELETE FROM mw_threads t
        USING (
            SELECT s.thread_id
            FROM (
                SELECT thread_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY company_id, user_id, location_id, week_start
                           ORDER BY created_at DESC, id DESC
                       ) AS rank
                FROM schedule_assistant_sessions
            ) s
            WHERE s.rank > 1
        ) stale
        WHERE t.id = stale.thread_id
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_schedule_assistant_sessions_owner_week")
    op.execute(
        """
        ALTER TABLE schedule_assistant_sessions
        ADD CONSTRAINT schedule_assistant_sessions_company_user_location_week_key
        UNIQUE (company_id, user_id, location_id, week_start)
        """
    )
