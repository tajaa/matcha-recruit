"""Analysis Pilot — bring-your-own-data risk analysis (sessions, datasets, comparisons, packets, audit)

Revision ID: analysispilot01
Revises: handbookpilot01
Create Date: 2026-07-07

Backs the company-facing "Analysis Pilot" feature: a company opens an analysis
session, uploads datasets (CSV / XLSX / financial-document PDF), a deterministic
engine computes risk/volatility metrics, and a grounded AI narrates + exports an
analyst report. Sessions persist the transcript; datasets persist to the private
S3 bucket with their parsed/normalized series + computed metrics; comparisons and
report PDFs persist. Every mutation/generation/download is audit-logged.

NOTE: the alembic history on this branch has multiple leaves. `down_revision` is
set to `handbookpilot01` — the tip of the Pilot chain (legaldef* → handbookpilot01)
at authoring time. Confirm the correct head for your environment before
`alembic upgrade` (the repo applies migrations via targeted scripts, not a single
`upgrade head`).
"""

from alembic import op


revision = "analysispilot01"
down_revision = "handbookpilot01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_pilot_sessions (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            title      VARCHAR(300) NOT NULL,
            domain     VARCHAR(30),
            goal       TEXT,
            status     VARCHAR(20) NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active','closed')),
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at  TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_pilot_sessions_company "
        "ON analysis_pilot_sessions(company_id, updated_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_pilot_datasets (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id   UUID NOT NULL REFERENCES analysis_pilot_sessions(id) ON DELETE CASCADE,
            company_id   UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            filename     VARCHAR(300) NOT NULL,
            storage_path TEXT NOT NULL,
            source_kind  VARCHAR(12) NOT NULL
                           CHECK (source_kind IN ('csv','xlsx','pdf')),
            content_type VARCHAR(100),
            file_size    BIGINT,
            row_count    INTEGER,
            column_count INTEGER,
            status       VARCHAR(16) NOT NULL DEFAULT 'processing'
                           CHECK (status IN ('processing','ready','needs_review','failed')),
            extraction   JSONB,   -- document path: raw Gemini figures + provenance
            normalized   JSONB,   -- unified model: series + periods + roles + kind
            mapping      JSONB,   -- user role overrides
            metrics      JSONB,   -- per-pack computed blocks (tiles/tables/charts/records)
            config       JSONB,   -- column_kinds / periods_per_year / risk_free
            error        TEXT,
            uploaded_by  UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_pilot_datasets_session "
        "ON analysis_pilot_datasets(session_id, created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_pilot_comparisons (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id  UUID NOT NULL REFERENCES analysis_pilot_sessions(id) ON DELETE CASCADE,
            company_id  UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            title       VARCHAR(300) NOT NULL,
            dataset_ids JSONB NOT NULL,
            spec        JSONB,
            result      JSONB,
            created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_pilot_comparisons_session "
        "ON analysis_pilot_comparisons(session_id, created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_pilot_messages (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES analysis_pilot_sessions(id) ON DELETE CASCADE,
            role       VARCHAR(16) NOT NULL CHECK (role IN ('user','assistant','system')),
            content    TEXT NOT NULL,
            metadata   JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_pilot_messages_session "
        "ON analysis_pilot_messages(session_id, created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_pilot_packets (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id   UUID NOT NULL REFERENCES analysis_pilot_sessions(id) ON DELETE CASCADE,
            company_id   UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            kind         VARCHAR(8) NOT NULL DEFAULT 'pdf',
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
        "CREATE INDEX IF NOT EXISTS idx_analysis_pilot_packets_session "
        "ON analysis_pilot_packets(session_id, generated_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_pilot_audit_log (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID REFERENCES analysis_pilot_sessions(id) ON DELETE CASCADE,
            user_id    UUID REFERENCES users(id) ON DELETE SET NULL,
            action     VARCHAR(50) NOT NULL,
            details    JSONB,
            ip_address VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_pilot_audit_session "
        "ON analysis_pilot_audit_log(session_id, created_at)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS analysis_pilot_audit_log")
    op.execute("DROP TABLE IF EXISTS analysis_pilot_packets")
    op.execute("DROP TABLE IF EXISTS analysis_pilot_messages")
    op.execute("DROP TABLE IF EXISTS analysis_pilot_comparisons")
    op.execute("DROP TABLE IF EXISTS analysis_pilot_datasets")
    op.execute("DROP TABLE IF EXISTS analysis_pilot_sessions")
