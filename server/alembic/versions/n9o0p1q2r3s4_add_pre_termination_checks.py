"""add pre_termination_checks table

Revision ID: n9o0p1q2r3s4
Revises: m8n9o0p1q2r3
Create Date: 2026-03-08
"""

from alembic import op


revision = "n9o0p1q2r3s4"
down_revision = "m8n9o0p1q2r3"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pre_termination_checks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            initiated_by UUID NOT NULL REFERENCES users(id),

            -- Scoring
            overall_score INT NOT NULL,
            overall_band VARCHAR(20) NOT NULL CHECK (overall_band IN ('low', 'moderate', 'high', 'critical')),
            dimensions JSONB NOT NULL,

            -- AI narrative
            ai_narrative TEXT,
            recommended_actions JSONB,

            -- Acknowledgment (for high/critical)
            requires_acknowledgment BOOLEAN NOT NULL DEFAULT false,
            acknowledged BOOLEAN NOT NULL DEFAULT false,
            acknowledged_by UUID REFERENCES users(id),
            acknowledged_at TIMESTAMPTZ,
            acknowledgment_notes TEXT,

            -- Outcome tracking
            outcome VARCHAR(30) CHECK (outcome IN ('proceeded', 'modified', 'abandoned', 'pending')),
            offboarding_case_id UUID,

            -- Separation context
            separation_reason TEXT,
            is_voluntary BOOLEAN NOT NULL DEFAULT false,

            computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pre_term_checks_employee
            ON pre_termination_checks(employee_id, computed_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pre_term_checks_company
            ON pre_termination_checks(company_id, computed_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pre_term_checks_band
            ON pre_termination_checks(company_id, overall_band)
        """
    )

    op.execute(
        """
        ALTER TABLE offboarding_cases
            ADD COLUMN IF NOT EXISTS pre_termination_check_id UUID
        """
    )


def downgrade():
    op.execute("ALTER TABLE offboarding_cases DROP COLUMN IF EXISTS pre_termination_check_id")
    op.execute("DROP INDEX IF EXISTS idx_pre_term_checks_band")
    op.execute("DROP INDEX IF EXISTS idx_pre_term_checks_company")
    op.execute("DROP INDEX IF EXISTS idx_pre_term_checks_employee")
    op.execute("DROP TABLE IF EXISTS pre_termination_checks")
