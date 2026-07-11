"""add osha_ita_submissions + osha_ita_credentials — direct ITA electronic filing

Turns the ITA path from "export a CSV and upload it yourself" into a one-click
API submission. Two tables:

  - osha_ita_credentials: the company's OSHA ITA API token, encrypted at rest
    (enc:v1: Fernet, via app.core.services.secret_crypto). One row per company.
  - osha_ita_submissions: an auditable filing history per (company, location,
    year) — status, the ITA-returned submission id, the raw response, and any
    error. Gives idempotency (don't double-file a year) + a record of what was
    filed when.

Prod is Stripe-test / pre-customer; this ships behind the existing reviewer
attestation gate and is never auto-invoked. Live credential testing against the
ITA sandbox is a user step before any real filing.

Revision ID: ita01
Revises: irdl01
Create Date: 2026-07-11
"""

from alembic import op


revision = "ita01"
down_revision = "irdl01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS osha_ita_credentials (
            company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            api_token TEXT NOT NULL,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS osha_ita_submissions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID,
            year INTEGER NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'submitted', 'accepted', 'rejected', 'error')),
            ita_submission_id TEXT,
            establishment_count INTEGER NOT NULL DEFAULT 0,
            response_payload JSONB,
            error_detail TEXT,
            submitted_by UUID,
            submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_osha_ita_submissions_company_year "
        "ON osha_ita_submissions(company_id, year DESC);"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS osha_ita_submissions")
    op.execute("DROP TABLE IF EXISTS osha_ita_credentials")
