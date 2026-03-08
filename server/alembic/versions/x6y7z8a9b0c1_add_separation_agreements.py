"""add separation_agreements table for ADEA period tracking

Revision ID: x6y7z8a9b0c1
Revises: o0p1q2r3s4t5
Create Date: 2026-03-08
"""

from alembic import op


revision = "x6y7z8a9b0c1"
down_revision = "o0p1q2r3s4t5"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS separation_agreements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            offboarding_case_id UUID,
            pre_term_check_id UUID,
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            severance_amount DECIMAL(12,2),
            severance_weeks INTEGER,
            severance_description TEXT,
            additional_terms JSONB,
            employee_age_at_separation INTEGER,
            is_adea_applicable BOOLEAN DEFAULT false,
            is_group_layoff BOOLEAN DEFAULT false,
            presented_date DATE,
            consideration_period_days INTEGER,
            consideration_deadline DATE,
            signed_date DATE,
            revocation_period_days INTEGER DEFAULT 7,
            revocation_deadline DATE,
            effective_date DATE,
            revoked_date DATE,
            decisional_unit TEXT,
            group_disclosure JSONB,
            created_by UUID REFERENCES users(id),
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_separation_agreements_company
        ON separation_agreements(company_id)
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_separation_agreements_employee
        ON separation_agreements(employee_id)
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_separation_agreements_status
        ON separation_agreements(status)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_separation_agreements_status")
    op.execute("DROP INDEX IF EXISTS idx_separation_agreements_employee")
    op.execute("DROP INDEX IF EXISTS idx_separation_agreements_company")
    op.execute("DROP TABLE IF EXISTS separation_agreements")
