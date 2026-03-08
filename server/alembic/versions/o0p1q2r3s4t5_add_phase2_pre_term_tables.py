"""add progressive_discipline, agency_charges, post_termination_claims tables and vesting_schedules column

Revision ID: o0p1q2r3s4t5
Revises: n9o0p1q2r3s4
Create Date: 2026-03-08
"""

from alembic import op


revision = "o0p1q2r3s4t5"
down_revision = "n9o0p1q2r3s4"
branch_labels = None
depends_on = None


def upgrade():
    # Progressive Discipline table
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS progressive_discipline (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            discipline_type VARCHAR(30) NOT NULL CHECK (discipline_type IN ('verbal_warning', 'written_warning', 'pip', 'final_warning', 'suspension')),
            issued_date DATE NOT NULL,
            issued_by UUID NOT NULL REFERENCES users(id),
            description TEXT,
            expected_improvement TEXT,
            review_date DATE,
            status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'expired', 'escalated')),
            outcome_notes TEXT,
            documents JSONB DEFAULT '[]',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_progressive_discipline_employee
            ON progressive_discipline(employee_id, issued_date DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_progressive_discipline_company
            ON progressive_discipline(company_id)
        """
    )

    # Agency Charges table
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agency_charges (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            charge_type VARCHAR(30) NOT NULL CHECK (charge_type IN ('eeoc', 'nlrb', 'osha', 'state_agency', 'other')),
            charge_number VARCHAR(100),
            filing_date DATE NOT NULL,
            agency_name VARCHAR(255),
            status VARCHAR(30) NOT NULL DEFAULT 'filed' CHECK (status IN ('filed', 'investigating', 'mediation', 'resolved', 'dismissed', 'litigated')),
            description TEXT,
            resolution_amount NUMERIC(12, 2),
            resolution_date DATE,
            resolution_notes TEXT,
            documents JSONB DEFAULT '[]',
            created_by UUID NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agency_charges_employee
            ON agency_charges(employee_id, filing_date DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agency_charges_company
            ON agency_charges(company_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agency_charges_status
            ON agency_charges(company_id, status)
        """
    )

    # Post-Termination Claims table
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS post_termination_claims (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            pre_termination_check_id UUID REFERENCES pre_termination_checks(id) ON DELETE SET NULL,
            offboarding_case_id UUID,
            claim_type VARCHAR(50) NOT NULL,
            filed_date DATE NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'filed' CHECK (status IN ('filed', 'investigating', 'mediation', 'settled', 'dismissed', 'litigated', 'judgment')),
            resolution_amount NUMERIC(12, 2),
            resolution_date DATE,
            description TEXT,
            created_by UUID NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_post_term_claims_employee
            ON post_termination_claims(employee_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_post_term_claims_company
            ON post_termination_claims(company_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_post_term_claims_check
            ON post_termination_claims(pre_termination_check_id)
        """
    )

    # Add vesting_schedules column to companies
    op.execute(
        """
        ALTER TABLE companies ADD COLUMN IF NOT EXISTS vesting_schedules JSONB DEFAULT '[]'
        """
    )


def downgrade():
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS vesting_schedules")
    op.execute("DROP INDEX IF EXISTS idx_post_term_claims_check")
    op.execute("DROP INDEX IF EXISTS idx_post_term_claims_company")
    op.execute("DROP INDEX IF EXISTS idx_post_term_claims_employee")
    op.execute("DROP TABLE IF EXISTS post_termination_claims")
    op.execute("DROP INDEX IF EXISTS idx_agency_charges_status")
    op.execute("DROP INDEX IF EXISTS idx_agency_charges_company")
    op.execute("DROP INDEX IF EXISTS idx_agency_charges_employee")
    op.execute("DROP TABLE IF EXISTS agency_charges")
    op.execute("DROP INDEX IF EXISTS idx_progressive_discipline_company")
    op.execute("DROP INDEX IF EXISTS idx_progressive_discipline_employee")
    op.execute("DROP TABLE IF EXISTS progressive_discipline")
