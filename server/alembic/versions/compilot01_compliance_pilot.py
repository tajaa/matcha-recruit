"""Compliance Pilot — chat-driven library building (sessions, messages, actions)

Revision ID: compilot01
Revises: jurfips01
Create Date: 2026-07-15

Backs the admin Compliance Studio "Pilot": an admin opens a chat session in a
mode (research / ask / check_sources / scope) and, from natural language, drives
the existing research → codify → commit pipeline over `jurisdiction_requirements`,
or asks the catalog (RAG). Sessions persist the transcript; ACTIONS persist the
research / approve / check_sources runs so they survive a tab close and the
transcript can re-render their cards.

No documents/packets/audit_log tables: the actions table is the audit of
pilot-initiated runs, and the writes that touch the catalog are already audited
by the jrver01 version trigger (labeled via `set_change_context`).

`admin_id` points at `users` (the admin running the session). Actions carry
`staged_ids` — a convenience snapshot of the pending rows a research run created;
the source of truth for "codifiable" stays `jurisdiction_requirements.status =
'pending'`, exactly as the Pipeline review treats it.
"""

from alembic import op


revision = "compilot01"
down_revision = "jurfips01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS compliance_pilot_sessions (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            admin_id   UUID REFERENCES users(id) ON DELETE SET NULL,
            title      VARCHAR(300) NOT NULL,
            mode       VARCHAR(40) NOT NULL DEFAULT 'research',
            status     VARCHAR(20) NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active','closed')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_compilot_sessions_updated "
        "ON compliance_pilot_sessions (updated_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS compliance_pilot_messages (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES compliance_pilot_sessions(id) ON DELETE CASCADE,
            role       VARCHAR(12) NOT NULL CHECK (role IN ('user','assistant','system')),
            content    TEXT NOT NULL DEFAULT '',
            metadata   JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_compilot_messages_session "
        "ON compliance_pilot_messages (session_id, created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS compliance_pilot_actions (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id  UUID NOT NULL REFERENCES compliance_pilot_sessions(id) ON DELETE CASCADE,
            kind        VARCHAR(20) NOT NULL
                          CHECK (kind IN ('research','approve','check_sources')),
            params      JSONB NOT NULL DEFAULT '{}'::jsonb,
            status      VARCHAR(12) NOT NULL DEFAULT 'running'
                          CHECK (status IN ('running','done','failed')),
            progress    JSONB,
            result      JSONB,
            staged_ids  UUID[],
            actor_id    UUID REFERENCES users(id) ON DELETE SET NULL,
            started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_compilot_actions_session "
        "ON compliance_pilot_actions (session_id, started_at DESC)"
    )
    # At most one running action per session — a double-confirm becomes a 409.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_compilot_action_running "
        "ON compliance_pilot_actions (session_id) WHERE status = 'running'"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS compliance_pilot_actions")
    op.execute("DROP TABLE IF EXISTS compliance_pilot_messages")
    op.execute("DROP TABLE IF EXISTS compliance_pilot_sessions")
