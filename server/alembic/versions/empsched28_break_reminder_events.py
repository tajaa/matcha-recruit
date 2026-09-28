"""Append-only record of break-reminder deliveries (email + push).

Wage-and-hour reviews (California meal/rest periods above all) ask what the
employer told each employee about their breaks and when. Until now the only
trace of a break reminder was the daily digest's dedupe claim, which is pruned
after 90 days, and worker logs, which die with every blue/green deploy.

``schedule_break_reminder_events`` keeps one row per delivery ATTEMPT on either
channel, with its outcome as reported at send time:

* ``employee_id`` / ``location_id`` carry no foreign key on purpose, and their
  names are snapshotted: the history has to outlive a roster row or a closed
  store, and an FK ``ON DELETE SET NULL`` would itself be an UPDATE.
* A ``BEFORE UPDATE`` trigger refuses every update, so a recorded outcome cannot
  be rewritten. DELETE is left alone so a deleted company still cascades.
* ``event_date`` is the location's calendar day, stored at write time, so the
  inclusive date filter never re-derives it from a timezone string at query
  time.
* ``dedupe_key`` (unique when present) is the break-start push's one-attempt
  guard; email attempts leave it NULL because a released digest claim is
  retried and each retry is its own attempt.

Also seeds the ``schedule_break_reminders`` scheduler row DISABLED: turning it
on starts pushing every published planned break to employees' phones.

Revision ID: empsched28
Revises: empsched27
"""

from alembic import op

revision = "empsched28"
down_revision = "empsched27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE schedule_break_reminder_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            event_date DATE NOT NULL,
            channel VARCHAR(10) NOT NULL CHECK (channel IN ('email', 'push')),
            reminder_type VARCHAR(20) NOT NULL
                CHECK (reminder_type IN ('daily_digest', 'break_start')),
            recipient_type VARCHAR(20) NOT NULL
                CHECK (recipient_type IN ('employee', 'manager')),
            recipient TEXT,
            recipient_user_id UUID,
            employee_id UUID,
            employee_name TEXT,
            covered_employee_ids UUID[] NOT NULL DEFAULT '{}',
            location_id UUID,
            location_name TEXT,
            location_timezone TEXT,
            shift_id UUID,
            assignment_id UUID,
            break_kind VARCHAR(10) CHECK (break_kind IN ('meal', 'rest')),
            break_start_local TIMESTAMP,
            break_duration_minutes INTEGER,
            context JSONB NOT NULL DEFAULT '{}'::jsonb,
            outcome VARCHAR(20) NOT NULL
                CHECK (outcome IN ('accepted', 'failed', 'unavailable')),
            outcome_detail TEXT,
            dedupe_key TEXT
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_schedule_break_reminder_events_dedupe
        ON schedule_break_reminder_events(dedupe_key)
        WHERE dedupe_key IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX ix_schedule_break_reminder_events_company_date
        ON schedule_break_reminder_events(company_id, event_date DESC, occurred_at DESC)
    """)
    op.execute("""
        CREATE INDEX ix_schedule_break_reminder_events_location
        ON schedule_break_reminder_events(company_id, location_id, event_date DESC)
    """)
    op.execute("""
        CREATE INDEX ix_schedule_break_reminder_events_covered
        ON schedule_break_reminder_events USING GIN (covered_employee_ids)
    """)
    op.execute("""
        CREATE FUNCTION schedule_break_reminder_events_append_only()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'schedule_break_reminder_events is append-only';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_schedule_break_reminder_events_append_only
        BEFORE UPDATE ON schedule_break_reminder_events
        FOR EACH ROW EXECUTE FUNCTION schedule_break_reminder_events_append_only()
    """)
    op.execute("""
        INSERT INTO scheduler_settings(task_key, display_name, description, enabled, max_per_cycle)
        VALUES ('schedule_break_reminders', 'Break-start push reminders',
                'Push each published planned meal/rest break to the employee''s Matcha Schedule app as it starts, and record every attempt.',
                false, 500)
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM scheduler_settings WHERE task_key='schedule_break_reminders'")
    op.execute("DROP TABLE schedule_break_reminder_events")
    op.execute("DROP FUNCTION schedule_break_reminder_events_append_only()")
