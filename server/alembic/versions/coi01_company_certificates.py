"""Certificate-of-insurance tracking.

Revision ID: coi01
Revises: tcor01
Create Date: 2026-07-11

Inbound certificates with extracted carried limits (JSONB), expiry, verify
status, and an optional link to the contract that required them.
"""

from alembic import op


revision = "coi01"
down_revision = "tcor01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_certificates (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id         UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            holder_name        VARCHAR(255),
            carrier            VARCHAR(255),
            certificate_number VARCHAR(100),
            lines              JSONB NOT NULL DEFAULT '[]',
            expiry_date        DATE,
            status             VARCHAR(20) NOT NULL DEFAULT 'unknown'
                                 CHECK (status IN ('active','expiring','expired','unknown')),
            contract_id        UUID REFERENCES company_contracts(id) ON DELETE SET NULL,
            verification       JSONB,
            source_filename    VARCHAR(255),
            storage_path       TEXT,
            ai_available       BOOLEAN NOT NULL DEFAULT FALSE,
            uploaded_by        UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_company_certificates_company "
        "ON company_certificates(company_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_company_certificates_expiry "
        "ON company_certificates(expiry_date)"
    )
    # Seed the scheduler row (disabled) so an admin can turn the expiry sweep on.
    op.execute(
        """
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES ('coi_expiry', 'COI Expiry Sweep',
                'Alert company admins about certificates of insurance expiring within 30 days.', false, 50)
        ON CONFLICT (task_key) DO NOTHING
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS company_certificates")
