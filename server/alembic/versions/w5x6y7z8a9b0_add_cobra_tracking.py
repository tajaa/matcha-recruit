"""add cobra qualifying event tracking

Revision ID: w5x6y7z8a9b0
Revises: a8b9c0d1e2f
Create Date: 2026-03-08
"""

from alembic import op


revision = "w5x6y7z8a9b0"
down_revision = "a8b9c0d1e2f"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cobra_qualifying_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            event_type VARCHAR(50) NOT NULL,
            event_date DATE NOT NULL,
            employer_notice_deadline DATE NOT NULL,
            administrator_notice_deadline DATE NOT NULL,
            election_deadline DATE NOT NULL,
            continuation_months INTEGER NOT NULL DEFAULT 18,
            continuation_end_date DATE NOT NULL,
            employer_notice_sent BOOLEAN DEFAULT false,
            employer_notice_sent_date DATE,
            administrator_notified BOOLEAN DEFAULT false,
            administrator_notified_date DATE,
            election_received BOOLEAN,
            election_received_date DATE,
            status VARCHAR(30) NOT NULL DEFAULT 'pending_notice',
            beneficiary_count INTEGER DEFAULT 1,
            notes TEXT,
            offboarding_case_id UUID,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cobra_events_company ON cobra_qualifying_events(company_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cobra_events_employee ON cobra_qualifying_events(employee_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cobra_events_deadline ON cobra_qualifying_events(employer_notice_deadline)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cobra_events_status ON cobra_qualifying_events(status)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_cobra_events_status")
    op.execute("DROP INDEX IF EXISTS idx_cobra_events_deadline")
    op.execute("DROP INDEX IF EXISTS idx_cobra_events_employee")
    op.execute("DROP INDEX IF EXISTS idx_cobra_events_company")
    op.execute("DROP TABLE IF EXISTS cobra_qualifying_events")
