"""add employee_credentials table

Revision ID: zd2e3f4g5h6i
Revises: zc1d2e3f4g5h
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa


revision = "zd2e3f4g5h6i"
down_revision = "zc1d2e3f4g5h"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS employee_credentials (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            org_id UUID NOT NULL,

            -- License
            license_type VARCHAR(50),
            license_number VARCHAR(100),
            license_state VARCHAR(2),
            license_expiration DATE,

            -- Federal identifiers
            npi_number VARCHAR(20),
            dea_number VARCHAR(20),
            dea_expiration DATE,

            -- Board certification
            board_certification VARCHAR(200),
            board_certification_expiration DATE,

            -- Clinical specialty
            clinical_specialty VARCHAR(100),

            -- OIG exclusion tracking
            oig_last_checked DATE,
            oig_status VARCHAR(20) DEFAULT 'not_checked',

            -- Malpractice insurance
            malpractice_carrier VARCHAR(200),
            malpractice_policy_number VARCHAR(100),
            malpractice_expiration DATE,

            -- Health clearances (TB, Hep B, flu, etc.)
            health_clearances JSONB DEFAULT '{}',

            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),

            UNIQUE(employee_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_employee_credentials_org
            ON employee_credentials(org_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_employee_credentials_expiry
            ON employee_credentials(license_expiration)
            WHERE license_expiration IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS employee_credentials")
