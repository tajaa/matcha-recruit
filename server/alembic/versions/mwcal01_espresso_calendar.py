"""Espresso calendar: the person's own events, and the timezone they live in.

- `mw_calendar_events`: one row per event on a person's Espresso calendar.
  User-scoped like the productivity boards (`company_id` is stored when there
  is one, never required). A timed event has `starts_at`/`ends_at`; an all-day
  event has `start_date`/`end_date` (end inclusive) and no times. The CHECK
  keeps exactly one of the two shapes. `source_*` says where it came from: the
  person, the assistant, an email (`source_ref` = Gmail message id) or a
  journal.
- `mw_calendar_prefs`: the IANA timezone the person's Espresso app reports,
  so the assistant can say "Friday at 3" in their time instead of UTC.

Additive; nothing reads these tables outside the calendar routes and the
assistant's calendar ability.

Revision ID: mwcal01
Revises: symchat01
Create Date: 2026-10-10
"""
from alembic import op


revision = "mwcal01"
down_revision = "symchat01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_calendar_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
            title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 300),
            notes TEXT,
            location TEXT,
            all_day BOOLEAN NOT NULL DEFAULT FALSE,
            starts_at TIMESTAMPTZ,
            ends_at TIMESTAMPTZ,
            start_date DATE,
            end_date DATE,
            source_kind VARCHAR(16) NOT NULL DEFAULT 'manual'
                CHECK (source_kind IN ('manual', 'assistant', 'email', 'journal')),
            source_ref TEXT,
            source_label TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT mw_calendar_events_when CHECK (
                (all_day AND start_date IS NOT NULL AND end_date IS NOT NULL
                    AND end_date >= start_date AND starts_at IS NULL AND ends_at IS NULL)
                OR (NOT all_day AND starts_at IS NOT NULL AND ends_at IS NOT NULL
                    AND ends_at >= starts_at AND start_date IS NULL AND end_date IS NULL)
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_calendar_events_user_start "
        "ON mw_calendar_events(user_id, starts_at) WHERE NOT all_day"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_calendar_events_user_date "
        "ON mw_calendar_events(user_id, start_date) WHERE all_day"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_calendar_events_source "
        "ON mw_calendar_events(user_id, source_kind, source_ref) WHERE source_ref IS NOT NULL"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_calendar_prefs (
            user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            timezone TEXT NOT NULL CHECK (char_length(timezone) BETWEEN 1 AND 64),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mw_calendar_prefs")
    op.execute("DROP TABLE IF EXISTS mw_calendar_events")
