"""add_employee_portal_tables

Revision ID: 7c1de748641e
Revises: 
Create Date: 2026-01-13 21:49:09.441465

"""
from typing import Sequence, Union

from alembic import op

revision = '7c1de748641e'
down_revision = None
branch_labels = None
depends_on = None
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c1de748641e'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create employees table
    op.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            email VARCHAR(255) NOT NULL,
            first_name VARCHAR(100) NOT NULL,
            last_name VARCHAR(100) NOT NULL,
            work_state VARCHAR(2),
            employment_type VARCHAR(20),
            start_date DATE,
            termination_date DATE,
            manager_id UUID REFERENCES employees(id) ON DELETE SET NULL,
            phone VARCHAR(50),
            address TEXT,
            emergency_contact JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT check_employment_type CHECK (
                employment_type IN ('full_time', 'part_time', 'contractor', 'intern')
            )
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_employees_org_id ON employees(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_employees_user_id ON employees(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_employees_email ON employees(email)")

    # Create PTO balances table
    op.execute("""
        CREATE TABLE IF NOT EXISTS pto_balances (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            balance_hours DECIMAL(6,2) DEFAULT 0,
            accrued_hours DECIMAL(6,2) DEFAULT 0,
            used_hours DECIMAL(6,2) DEFAULT 0,
            year INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(employee_id, year)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_pto_balances_employee_id ON pto_balances(employee_id)")

    # Create PTO requests table
    op.execute("""
        CREATE TABLE IF NOT EXISTS pto_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            request_type VARCHAR(20) NOT NULL DEFAULT 'vacation',
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            hours DECIMAL(6,2) NOT NULL,
            reason TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            approved_by UUID REFERENCES employees(id) ON DELETE SET NULL,
            approved_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT check_pto_request_type CHECK (
                request_type IN ('vacation', 'sick', 'personal', 'other')
            ),
            CONSTRAINT check_pto_status CHECK (
                status IN ('pending', 'approved', 'denied', 'cancelled')
            ),
            CONSTRAINT check_date_range CHECK (end_date >= start_date)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_pto_requests_employee_id ON pto_requests(employee_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pto_requests_status ON pto_requests(status)")

    # Create employee documents table
    op.execute("""
        CREATE TABLE IF NOT EXISTS employee_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            doc_type VARCHAR(50) NOT NULL,
            title VARCHAR(255) NOT NULL,
            storage_path VARCHAR(500),
            content TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            expires_at DATE,
            signed_at TIMESTAMP,
            signed_ip VARCHAR(45),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT check_document_status CHECK (
                status IN ('draft', 'pending_signature', 'signed', 'expired')
            )
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_employee_documents_org_id ON employee_documents(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_employee_documents_employee_id ON employee_documents(employee_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_employee_documents_status ON employee_documents(status)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS employee_documents CASCADE")
    op.execute("DROP TABLE IF EXISTS pto_requests CASCADE")
    op.execute("DROP TABLE IF EXISTS pto_balances CASCADE")
    op.execute("DROP TABLE IF EXISTS employees CASCADE")
