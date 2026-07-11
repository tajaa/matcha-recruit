"""TCOR premium/fee/retention inputs per line + policy year.

Revision ID: tcor01
Revises: riskext00
Create Date: 2026-07-11

Stored inputs for the Total Cost of Risk view (premiums + fees + mitigation +
current retention). Modeled retained losses come from the risk snapshot's
Monte-Carlo — not stored here. NULLS NOT DISTINCT so the null-policy-year row
upserts cleanly (PG15).
"""

from alembic import op


revision = "tcor01"
down_revision = "riskext00"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_tcor_inputs (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id            UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            line                  VARCHAR(40) NOT NULL,
            annual_premium        NUMERIC(14,2),
            fees                  NUMERIC(14,2),
            risk_mitigation_spend NUMERIC(14,2),
            current_retention     NUMERIC(14,2),
            policy_year           INTEGER,
            updated_by            UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_company_tcor_inputs
                UNIQUE NULLS NOT DISTINCT (company_id, line, policy_year)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_company_tcor_inputs_company "
        "ON company_tcor_inputs(company_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS company_tcor_inputs")
