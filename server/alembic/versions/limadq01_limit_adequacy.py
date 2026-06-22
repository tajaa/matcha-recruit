"""Limit-adequacy + contract review (carried coverage + contract requirements)

Revision ID: limadq01
Revises: venuesev01
Create Date: 2026-06-21

Contract & limit-adequacy review (gap-analysis #6/#28, WTW "benchmarking +
contractual-limit review = essential tool"). Two new tables:

- ``company_coverage_lines`` — the limits a company actually carries, per line,
  plus the endorsement booleans (additional-insured / waiver-of-subrogation /
  primary-&-noncontributory) so we can diff against contract requirements.
- ``company_contracts`` — uploaded/entered customer/vendor/lease contracts with
  the insurance requirements Gemini extracted (or the company keyed) as JSONB.
  The PDF itself is parsed and discarded; only the structured requirements are
  stored.

Gated by the ``limit_adequacy`` feature.
"""

from alembic import op


revision = "limadq01"
down_revision = "venuesev01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_coverage_lines (
            id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id               UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            line                     VARCHAR(40) NOT NULL,
            carrier                  VARCHAR(255),
            per_occurrence           NUMERIC(14,2),
            aggregate                NUMERIC(14,2),
            retention                NUMERIC(14,2),
            additional_insured       BOOLEAN NOT NULL DEFAULT FALSE,
            waiver_of_subrogation    BOOLEAN NOT NULL DEFAULT FALSE,
            primary_noncontributory  BOOLEAN NOT NULL DEFAULT FALSE,
            effective_date           DATE,
            expiry_date              DATE,
            note                     TEXT,
            updated_by               UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_company_coverage_line UNIQUE (company_id, line)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_company_coverage_lines_company "
        "ON company_coverage_lines(company_id)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_contracts (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name             VARCHAR(255) NOT NULL,
            counterparty     VARCHAR(255),
            status           VARCHAR(20) NOT NULL DEFAULT 'parsed',
            requirements     JSONB NOT NULL DEFAULT '[]'::jsonb,
            ai_available     BOOLEAN NOT NULL DEFAULT FALSE,
            source_filename  VARCHAR(255),
            uploaded_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_company_contracts_company "
        "ON company_contracts(company_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS company_contracts")
    op.execute("DROP TABLE IF EXISTS company_coverage_lines")
