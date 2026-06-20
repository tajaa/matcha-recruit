"""EPL readiness: broker-recorded attestations for non-derivable underwriting asks

Revision ID: epldeep01
Revises: wcdeep01
Create Date: 2026-06-20

Backs the EPL-readiness lens (services/epl_readiness.py). Five of the report's
EPL underwriting asks have no Matcha data source — pay transparency, biometric/
BIPA controls, pay equity, AI hiring-tool audits, DEI posture. The broker records
these during a consultative review; one row per (company, item_key).

The derived factors (policy/training/discipline/ER/wage-hour) need no schema —
they read existing tables.
"""

from alembic import op


revision = "epldeep01"
down_revision = "wcdeep01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_epl_attestations (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            broker_id   UUID REFERENCES brokers(id) ON DELETE SET NULL,
            item_key    VARCHAR(40) NOT NULL,
            status      VARCHAR(16) NOT NULL DEFAULT 'unknown'
                          CHECK (status IN ('in_place', 'partial', 'gap', 'unknown')),
            note        TEXT,
            updated_by  UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_company_epl_attestation UNIQUE (company_id, item_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_company_epl_attestations_company "
        "ON company_epl_attestations(company_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS company_epl_attestations")
