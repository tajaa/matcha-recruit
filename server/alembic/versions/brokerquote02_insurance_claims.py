"""Insurance claims bridge — FNOL + loss-run import records.

Revision ID: brokerquote02
Revises: brokerquote01
Create Date: 2026-07-18

Adds `insurance_claims`, the record for the broker Claims Bridge:
- a First Notice of Loss (`kind='fnol'`) filed to the carrier from a logged
  IR incident (`incident_id`), and
- a loss-run import event (`kind='loss_run_import'`) noting a pull from the
  carrier (the loss *data* itself rides the existing loss-development inputs;
  this row is the provenance/audit of the pull).

Subject is exactly one of a tenant `company_id` or an off-platform
`external_client_id` (same shape as `insurance_quotes`). Carrier calls are
capability-gated in the service layer; this table just persists what happened.

Additive. Reversible.
"""

from alembic import op


revision = "brokerquote02"
down_revision = "brokerquote01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS insurance_claims (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id         UUID REFERENCES companies(id) ON DELETE CASCADE,
            external_client_id UUID REFERENCES broker_external_clients(id) ON DELETE CASCADE,
            broker_id          UUID REFERENCES brokers(id) ON DELETE SET NULL,
            quote_id           UUID REFERENCES insurance_quotes(id) ON DELETE SET NULL,
            incident_id        UUID,
            carrier            VARCHAR(40) NOT NULL DEFAULT 'coterie',
            kind               VARCHAR(20) NOT NULL
                                 CHECK (kind IN ('fnol', 'loss_run_import')),
            claim_ref          VARCHAR(120),
            status             VARCHAR(20) NOT NULL DEFAULT 'open',
            amount_cents       BIGINT,
            payload            JSONB NOT NULL DEFAULT '{}',
            created_by         UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_insurance_claims_subject
                CHECK ((company_id IS NOT NULL) <> (external_client_id IS NOT NULL))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_insurance_claims_company ON insurance_claims(company_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_insurance_claims_external "
        "ON insurance_claims(external_client_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_insurance_claims_incident ON insurance_claims(incident_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS insurance_claims")
