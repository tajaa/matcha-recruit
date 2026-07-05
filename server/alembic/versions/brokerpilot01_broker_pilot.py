"""Broker Pilot — grounded per-client analysis chat (sessions, docs, packets, audit)

Revision ID: brokerpilot01
Revises: adminupd01
Create Date: 2026-07-05

Backs the Broker Pro "Broker Pilot" feature: a broker opens a per-client analysis
session (on-platform company or off-platform external client), uploads ad-hoc P&C
documents (loss runs, dec pages, quotes, carrier letters), and converses with an
AI grounded in both the uploads and the platform data on file. Sessions persist
the transcript; uploaded documents persist to the private S3 bucket with their
AI extraction; memo PDFs persist as packets. Every mutation/generation/download
is audit-logged.

`subject_id` is deliberately un-FK'd — it points at `companies` or
`broker_external_clients` depending on `subject_kind` (same polymorphism as
`wc_loss_runs.subject_kind/subject_id`).

NOTE: the alembic history on this branch has had multiple leaves in the past;
`down_revision` is set to `adminupd01` (verified single head at authoring time).
Confirm the correct head for your environment before `alembic upgrade`.
"""

from alembic import op


revision = "brokerpilot01"
down_revision = "adminupd01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_pilot_sessions (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id    UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            subject_kind VARCHAR(10) NOT NULL
                           CHECK (subject_kind IN ('company','external')),
            subject_id   UUID NOT NULL,
            title        VARCHAR(300) NOT NULL,
            status       VARCHAR(20) NOT NULL DEFAULT 'active'
                           CHECK (status IN ('active','closed')),
            created_by   UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at    TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_broker_pilot_sessions_broker "
        "ON broker_pilot_sessions(broker_id, updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_broker_pilot_sessions_subject "
        "ON broker_pilot_sessions(broker_id, subject_kind, subject_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_pilot_messages (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES broker_pilot_sessions(id) ON DELETE CASCADE,
            role       VARCHAR(16) NOT NULL
                         CHECK (role IN ('user','assistant','system')),
            content    TEXT NOT NULL,
            metadata   JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_broker_pilot_messages_session "
        "ON broker_pilot_messages(session_id, created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_pilot_documents (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id     UUID NOT NULL REFERENCES broker_pilot_sessions(id) ON DELETE CASCADE,
            -- Denormalized from the session so ownership checks and cross-session
            -- doc queries never need the join.
            broker_id      UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            filename       VARCHAR(300) NOT NULL,
            storage_path   TEXT NOT NULL,
            content_type   VARCHAR(100),
            file_size      BIGINT,
            page_count     INTEGER,
            doc_type       VARCHAR(30)
                             CHECK (doc_type IN ('loss_run','dec_page','quote',
                                    'carrier_letter','bordereau','policy_form',
                                    'financials','other')),
            status         VARCHAR(16) NOT NULL DEFAULT 'processing'
                             CHECK (status IN ('processing','ready','text_only','failed')),
            extraction     JSONB,
            extracted_text TEXT,
            error          TEXT,
            uploaded_by    UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_broker_pilot_documents_session "
        "ON broker_pilot_documents(session_id, created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_pilot_packets (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id   UUID NOT NULL REFERENCES broker_pilot_sessions(id) ON DELETE CASCADE,
            broker_id    UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            storage_path TEXT NOT NULL,
            filename     VARCHAR(300) NOT NULL,
            citations    JSONB,
            file_size    BIGINT,
            generated_by UUID REFERENCES users(id) ON DELETE SET NULL,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_broker_pilot_packets_session "
        "ON broker_pilot_packets(session_id, generated_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_pilot_audit_log (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID REFERENCES broker_pilot_sessions(id) ON DELETE CASCADE,
            user_id    UUID REFERENCES users(id) ON DELETE SET NULL,
            action     VARCHAR(50) NOT NULL,
            details    JSONB,
            ip_address VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_broker_pilot_audit_session "
        "ON broker_pilot_audit_log(session_id, created_at)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS broker_pilot_audit_log")
    op.execute("DROP TABLE IF EXISTS broker_pilot_packets")
    op.execute("DROP TABLE IF EXISTS broker_pilot_documents")
    op.execute("DROP TABLE IF EXISTS broker_pilot_messages")
    op.execute("DROP TABLE IF EXISTS broker_pilot_sessions")
