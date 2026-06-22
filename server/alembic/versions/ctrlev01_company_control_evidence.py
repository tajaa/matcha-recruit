"""Controls-evidence verification overrides (universal proof-of-controls)

Revision ID: ctrlev01
Revises: payequity01
Create Date: 2026-06-21

Universal controls-evidence register (WTW p.85 "mitigation-evidence systems of
record … package for underwriters buys down rate"). The register auto-computes
each control from existing HR/safety data; this table stores ONLY the per-control
verification override + note a company/broker adds on top. Gated by the
`controls_evidence` feature.
"""

from alembic import op


revision = "ctrlev01"
down_revision = "payequity01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_control_evidence (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id   UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            control_key  VARCHAR(50) NOT NULL,
            status       VARCHAR(20)
                           CHECK (status IN ('strong','partial','gap','na')),
            note         TEXT,
            verified_at  TIMESTAMPTZ,
            updated_by   UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_company_control_evidence UNIQUE (company_id, control_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_company_control_evidence_company "
        "ON company_control_evidence(company_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS company_control_evidence")
