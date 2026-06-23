"""Legal Defense builder — matters, chat transcript, packets, audit log

Revision ID: legaldef01
Revises: propd01
Create Date: 2026-06-23

Backs the full-platform "Legal Defense" feature: an admin opens a legal matter
(subpoena / class action / EEOC / etc.), converses with a grounded AI that pulls
the company's own records, and exports an attorney-facing evidence packet (memo
PDF + ZIP bundle). All tables are company-scoped; the audit log records every
matter mutation, chat turn, packet generation, and download (legal-grade trail).
Gated by the `legal_defense` feature.

NOTE: the alembic history on this branch has multiple leaves; `down_revision`
is set to the property tip (`propd01`). Confirm the correct head for your
environment before `alembic upgrade`.
"""

from alembic import op


revision = "legaldef01"
down_revision = "propd01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_matters (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            title           VARCHAR(300) NOT NULL,
            matter_type     VARCHAR(30)
                              CHECK (matter_type IN ('subpoena','class_action',
                                     'eeoc_charge','single_plaintiff','audit','other')),
            allegation      TEXT,
            defense_theory  TEXT,
            status          VARCHAR(20) NOT NULL DEFAULT 'draft'
                              CHECK (status IN ('draft','active','closed')),
            evidence_start  DATE,
            evidence_end    DATE,
            -- Optional "prepared at the direction of counsel" work-product posture.
            counsel_directed BOOLEAN NOT NULL DEFAULT FALSE,
            counsel_name    VARCHAR(200),
            counsel_email   VARCHAR(320),
            created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at       TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_legal_matters_company "
        "ON legal_matters(company_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_matter_messages (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            matter_id   UUID NOT NULL REFERENCES legal_matters(id) ON DELETE CASCADE,
            role        VARCHAR(16) NOT NULL
                          CHECK (role IN ('user','assistant','system')),
            content     TEXT NOT NULL,
            metadata    JSONB,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_legal_matter_messages_matter "
        "ON legal_matter_messages(matter_id, created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_matter_packets (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            matter_id     UUID NOT NULL REFERENCES legal_matters(id) ON DELETE CASCADE,
            company_id    UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            kind          VARCHAR(8) NOT NULL CHECK (kind IN ('pdf','zip')),
            storage_path  TEXT NOT NULL,
            filename      VARCHAR(300) NOT NULL,
            citations     JSONB,
            file_size     BIGINT,
            generated_by  UUID REFERENCES users(id) ON DELETE SET NULL,
            generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_legal_matter_packets_matter "
        "ON legal_matter_packets(matter_id, generated_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_matter_audit_log (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            matter_id   UUID REFERENCES legal_matters(id) ON DELETE CASCADE,
            user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
            action      VARCHAR(50) NOT NULL,
            details     JSONB,
            ip_address  VARCHAR(64),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_legal_matter_audit_matter "
        "ON legal_matter_audit_log(matter_id, created_at)"
    )

    # Token-gated delivery of a generated packet to outside counsel (mirrors
    # er_case_export_links): the realistic SMB flow is owner → forwards to lawyer.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_matter_share_links (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            matter_id           UUID NOT NULL REFERENCES legal_matters(id) ON DELETE CASCADE,
            company_id          UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            packet_id           UUID NOT NULL REFERENCES legal_matter_packets(id) ON DELETE CASCADE,
            token               VARCHAR(64) NOT NULL UNIQUE,
            recipient_email     VARCHAR(320),
            expires_at          TIMESTAMPTZ,
            revoked             BOOLEAN NOT NULL DEFAULT FALSE,
            download_count      INTEGER NOT NULL DEFAULT 0,
            last_downloaded_at  TIMESTAMPTZ,
            created_by          UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_legal_matter_share_matter "
        "ON legal_matter_share_links(matter_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS legal_matter_share_links")
    op.execute("DROP TABLE IF EXISTS legal_matter_audit_log")
    op.execute("DROP TABLE IF EXISTS legal_matter_packets")
    op.execute("DROP TABLE IF EXISTS legal_matter_messages")
    op.execute("DROP TABLE IF EXISTS legal_matters")
