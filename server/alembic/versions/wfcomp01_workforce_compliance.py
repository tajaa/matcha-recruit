"""Workforce compliance: AI-audit register, biometric/BIPA inventory, pay-transparency status

Revision ID: wfcomp01
Revises: wcstates01
Create Date: 2026-06-20

Business-first risk-input trackers (gated by the new `workforce_compliance`
feature). Each is a legal obligation the business must meet, and each flips its
EPL-readiness factor from broker-attested to derived:
- hiring_ai_audits        — AI hiring-tool bias-audit register (cadence/overdue).
- biometric_consent_points — biometric/BIPA collection + consent inventory.
- pay_transparency_status  — per-state pay-transparency posting compliance.
"""

from alembic import op


revision = "wfcomp01"
down_revision = "wcstates01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS hiring_ai_audits (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            tool_name       VARCHAR(255) NOT NULL,
            vendor          VARCHAR(255),
            purpose         VARCHAR(255),
            last_audit_date DATE,
            cadence_days    INTEGER NOT NULL DEFAULT 365,
            next_due_date   DATE,
            is_overdue      BOOLEAN NOT NULL DEFAULT FALSE,
            notes           TEXT,
            created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_hiring_ai_audit UNIQUE (company_id, tool_name)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_hiring_ai_audits_company ON hiring_ai_audits(company_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS biometric_consent_points (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id           UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id          UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            collection_type      VARCHAR(30) NOT NULL
                                   CHECK (collection_type IN ('fingerprint','face','iris','voice','hand_geometry','other')),
            purpose              VARCHAR(255),
            consent_obtained     BOOLEAN NOT NULL DEFAULT FALSE,
            consent_obtained_date DATE,
            consent_method       VARCHAR(20)
                                   CHECK (consent_method IN ('written','digital','verbal','other')),
            retention_policy     TEXT,
            is_active            BOOLEAN NOT NULL DEFAULT TRUE,
            notes                TEXT,
            created_by           UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_biometric_points_company ON biometric_consent_points(company_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pay_transparency_status (
            id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id             UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            state                  VARCHAR(2) NOT NULL,
            status                 VARCHAR(16) NOT NULL DEFAULT 'action_needed'
                                     CHECK (status IN ('compliant','action_needed','na')),
            postings_include_ranges BOOLEAN NOT NULL DEFAULT FALSE,
            note                   TEXT,
            updated_by             UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_at             TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_pay_transparency_state UNIQUE (company_id, state)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_pay_transparency_company ON pay_transparency_status(company_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS pay_transparency_status")
    op.execute("DROP TABLE IF EXISTS biometric_consent_points")
    op.execute("DROP TABLE IF EXISTS hiring_ai_audits")
