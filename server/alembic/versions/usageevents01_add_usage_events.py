"""add usage_events — first-party product analytics

One append-only table behind every usage surface: SPA page views (authenticated
and public), server-side API calls (recorded by the `track_api_usage` middleware),
and the Werk desktop session/heartbeat beacons. `surface` + `event` discriminate.

Deliberately has no foreign keys on `user_id` / `company_id`: analytics rows
outlive the users and companies they describe, and the insert path is hot enough
that skipping the FK checks matters. `company_id` is resolved at flush time from
`clients.user_id` (the JWT carries no company), so it is NULL until then and
stays NULL for roles with no company (individual, candidate).

`path` only ever holds a normalized pattern — route templates like
`/api/ir/incidents/{incident_id}` server-side, and `:id` / `:token`-collapsed
segments client-side. Raw path tokens (e.g. `/report/<token>`) must never land
here: the beacon re-normalizes rather than trusting the client.

Revision ID: usageevents01
Revises: discipcomp01
"""
from alembic import op

revision = "usageevents01"
down_revision = "discipcomp01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_events (
            id          BIGSERIAL PRIMARY KEY,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            surface     TEXT NOT NULL,
            event       TEXT NOT NULL,
            path        TEXT NOT NULL,
            method      TEXT,
            status      SMALLINT,
            duration_ms INTEGER,
            user_id     UUID,
            company_id  UUID,
            role        TEXT,
            visitor_id  TEXT,
            meta        JSONB
        )
        """
    )
    # One statement per execute — the asyncpg dialect prepares each call and
    # can't take multiple commands in one prepared statement.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_events_occurred"
        " ON usage_events (occurred_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_events_company"
        " ON usage_events (company_id, occurred_at) WHERE company_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_events_user"
        " ON usage_events (user_id, occurred_at) WHERE user_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_events_event"
        " ON usage_events (event, occurred_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS usage_events")
