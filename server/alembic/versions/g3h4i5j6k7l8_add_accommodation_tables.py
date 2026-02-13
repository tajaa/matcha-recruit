"""add_accommodation_tables

Revision ID: g3h4i5j6k7l8
Revises: f2g3h4i5j6k7
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g3h4i5j6k7l8'
down_revision: Union[str, Sequence[str]] = 'f2g3h4i5j6k7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create accommodation_cases, accommodation_documents, accommodation_analysis,
    accommodation_audit_log tables and add FK on leave_deadlines."""

    # -- accommodation_cases --
    op.execute("""
        CREATE TABLE IF NOT EXISTS accommodation_cases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            case_number VARCHAR(50) NOT NULL UNIQUE,
            org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            linked_leave_id UUID REFERENCES leave_requests(id),
            title VARCHAR(255) NOT NULL,
            description TEXT,
            disability_category VARCHAR(50),
            status VARCHAR(50) NOT NULL DEFAULT 'requested',
            requested_accommodation TEXT,
            approved_accommodation TEXT,
            denial_reason TEXT,
            undue_hardship_analysis TEXT,
            assigned_to UUID REFERENCES users(id),
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            closed_at TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_accommodation_cases_status ON accommodation_cases(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_accommodation_cases_employee ON accommodation_cases(employee_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_accommodation_cases_org ON accommodation_cases(org_id)")

    # -- accommodation_documents --
    op.execute("""
        CREATE TABLE IF NOT EXISTS accommodation_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id UUID NOT NULL REFERENCES accommodation_cases(id) ON DELETE CASCADE,
            document_type VARCHAR(50) NOT NULL,
            filename VARCHAR(255) NOT NULL,
            file_path VARCHAR(500) NOT NULL,
            mime_type VARCHAR(100),
            file_size INTEGER,
            uploaded_by UUID REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_accommodation_documents_case ON accommodation_documents(case_id)")

    # -- accommodation_analysis --
    op.execute("""
        CREATE TABLE IF NOT EXISTS accommodation_analysis (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id UUID NOT NULL REFERENCES accommodation_cases(id) ON DELETE CASCADE,
            analysis_type VARCHAR(50) NOT NULL,
            analysis_data JSONB NOT NULL,
            generated_by UUID REFERENCES users(id),
            generated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(case_id, analysis_type)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_accommodation_analysis_case ON accommodation_analysis(case_id)")

    # -- accommodation_audit_log --
    op.execute("""
        CREATE TABLE IF NOT EXISTS accommodation_audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id UUID REFERENCES accommodation_cases(id) ON DELETE SET NULL,
            user_id UUID REFERENCES users(id),
            action VARCHAR(100) NOT NULL,
            entity_type VARCHAR(50),
            entity_id UUID,
            details JSONB,
            ip_address VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_accommodation_audit_case ON accommodation_audit_log(case_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_accommodation_audit_user ON accommodation_audit_log(user_id)")

    # -- FK on leave_deadlines --
    op.execute("""
        ALTER TABLE leave_deadlines
        ADD COLUMN IF NOT EXISTS accommodation_case_id UUID REFERENCES accommodation_cases(id) ON DELETE SET NULL
    """)


def downgrade() -> None:
    """Drop accommodation tables and FK column."""
    op.execute("ALTER TABLE leave_deadlines DROP COLUMN IF EXISTS accommodation_case_id")
    op.execute("DROP TABLE IF EXISTS accommodation_audit_log")
    op.execute("DROP TABLE IF EXISTS accommodation_analysis")
    op.execute("DROP TABLE IF EXISTS accommodation_documents")
    op.execute("DROP TABLE IF EXISTS accommodation_cases")
