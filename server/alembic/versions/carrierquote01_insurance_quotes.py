"""Carrier quote/bind — Coterie integration.

Revision ID: carrierquote01
Revises: empsched02
Create Date: 2026-07-17

Adds `insurance_quotes` (a company's quote requests + carrier responses across the
draft→quoted→bound lifecycle) and two columns on `company_certificates` so a bound
policy lands in the existing certificate store with its premium + provenance.

Additive only. No `integration_connections` change — Coterie auth is a platform
partner API key (env), not a per-company OAuth token, so there is no per-company
connection row to track.
"""

from alembic import op


revision = "carrierquote01"
down_revision = "empsched02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS insurance_quotes (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            carrier         VARCHAR(40) NOT NULL DEFAULT 'coterie',
            line            VARCHAR(40) NOT NULL,
            quote_ref       VARCHAR(120),
            status          VARCHAR(20) NOT NULL DEFAULT 'draft'
                              CHECK (status IN ('draft','quoted','bound','expired','error')),
            premium_cents   BIGINT,
            request_payload JSONB NOT NULL DEFAULT '{}',
            quote_payload   JSONB NOT NULL DEFAULT '{}',
            error_message   TEXT,
            expires_at      TIMESTAMPTZ,
            certificate_id  UUID REFERENCES company_certificates(id) ON DELETE SET NULL,
            created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_insurance_quotes_company "
        "ON insurance_quotes(company_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_insurance_quotes_status "
        "ON insurance_quotes(company_id, status)"
    )
    # A bound carrier policy lands in the existing COI store — record its premium
    # and that it came from a carrier bind (vs. an uploaded PDF), so the two are
    # distinguishable and the certificate list can show premium.
    op.execute("ALTER TABLE company_certificates ADD COLUMN IF NOT EXISTS source VARCHAR(40)")
    op.execute("ALTER TABLE company_certificates ADD COLUMN IF NOT EXISTS premium_cents BIGINT")


def downgrade():
    op.execute("DROP TABLE IF EXISTS insurance_quotes")
    op.execute("ALTER TABLE company_certificates DROP COLUMN IF EXISTS premium_cents")
    op.execute("ALTER TABLE company_certificates DROP COLUMN IF EXISTS source")
