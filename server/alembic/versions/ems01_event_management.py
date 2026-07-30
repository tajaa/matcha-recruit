"""EMS: event management system — "@huume" channel intake + IR promotion

Backs the `ems` feature flag (server/app/core/feature_flags.py). A member
typing "@huume <what happened>" in any werk channel gets the message
classified into a structured `ems_events` row by a one-shot Gemini call
(services/ems/event_intake.py — NOT the Huume agent loop, which hard-requires
an mw_threads row via store._locked_state_update). Huume then confirms in the
channel via a persisted system message, which needs two changes to
`channel_messages`:

- `sender_id` becomes nullable — a system message has no human sender, and
  fabricating a bot `users` row was rejected as roster noise.
- `message_type` distinguishes it from a normal user message so edit/delete/
  react routes can 403 on it and the client can render it distinctly.

The partial unique index `uniq_channel_messages_sender_cmid` on
`(sender_id, client_message_id) WHERE client_message_id IS NOT NULL` is
unaffected by the nullability change: a system message inserts with BOTH
columns NULL, so it never matches the index's WHERE clause and is never a
candidate for ON CONFLICT inference.

`ems_events.message_id` carries its own partial unique index so an
ON CONFLICT ... DO NOTHING at the app layer makes a WS cmid-retry replay of
the triggering message a no-op rather than a duplicate event.

NOTE: the alembic history on this branch has multiple leaves; `down_revision`
is set to `handbookpilot02`, a verified head at authoring time. Confirm the
correct head for your environment before `alembic upgrade`.

Revision ID: ems01
Revises: handbookpilot02
Create Date: 2026-07-30
"""

from alembic import op


revision = "ems01"
down_revision = "handbookpilot02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE channel_messages ALTER COLUMN sender_id DROP NOT NULL")
    op.execute(
        "ALTER TABLE channel_messages ADD COLUMN IF NOT EXISTS "
        "message_type VARCHAR(20) NOT NULL DEFAULT 'user'"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ems_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
            message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
            reporter_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            title VARCHAR(300),
            category VARCHAR(50) NOT NULL DEFAULT 'uncategorized',
            severity_hint VARCHAR(20),
            doc JSONB NOT NULL DEFAULT '{}'::jsonb,
            narrative TEXT NOT NULL,
            incident_recommendation BOOLEAN NOT NULL DEFAULT false,
            incident_reasoning TEXT,
            suggested_incident_type VARCHAR(50),
            suggested_severity VARCHAR(20),
            status VARCHAR(20) NOT NULL DEFAULT 'logged'
                CHECK (status IN ('logged', 'promoted', 'dismissed')),
            incident_id UUID REFERENCES ir_incidents(id) ON DELETE SET NULL,
            promoted_by UUID REFERENCES users(id),
            promoted_at TIMESTAMPTZ,
            dismissed_by UUID REFERENCES users(id),
            dismissed_at TIMESTAMPTZ,
            token_usage JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ems_events_company "
        "ON ems_events(company_id, created_at DESC)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uniq_ems_events_message "
        "ON ems_events(message_id) WHERE message_id IS NOT NULL"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ems_event_audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id UUID NOT NULL REFERENCES ems_events(id) ON DELETE CASCADE,
            user_id UUID REFERENCES users(id),
            action VARCHAR(50) NOT NULL,
            details JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ems_event_audit_log_event "
        "ON ems_event_audit_log(event_id, created_at DESC)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS ems_event_audit_log")
    op.execute("DROP TABLE IF EXISTS ems_events")
    op.execute("ALTER TABLE channel_messages DROP COLUMN IF EXISTS message_type")
    # Restoring NOT NULL requires no NULL rows to exist. Any system message
    # rows written while this migration was applied must be deleted first —
    # this repo has no bot user to backfill sender_id onto.
    op.execute("DELETE FROM channel_messages WHERE sender_id IS NULL")
    op.execute("ALTER TABLE channel_messages ALTER COLUMN sender_id SET NOT NULL")
