"""add_i9_tracking

Revision ID: u3v4w5x6y7z8
Revises: c6d7e8f9a0b1
Create Date: 2026-03-08

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'u3v4w5x6y7z8'
down_revision: Union[str, Sequence[str], None] = 'c6d7e8f9a0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS i9_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            status VARCHAR(30) NOT NULL DEFAULT 'pending_section1',
            section1_completed_date DATE,
            section2_completed_date DATE,
            section2_completed_by UUID REFERENCES users(id),
            document_title VARCHAR(100),
            list_used VARCHAR(10),
            document_number VARCHAR(100),
            issuing_authority VARCHAR(100),
            expiration_date DATE,
            reverification_date DATE,
            reverification_document VARCHAR(100),
            reverification_expiration DATE,
            reverification_by UUID REFERENCES users(id),
            everify_case_number VARCHAR(50),
            everify_status VARCHAR(30),
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(employee_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_i9_records_company ON i9_records(company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_i9_records_expiration ON i9_records(expiration_date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_i9_records_status ON i9_records(status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS i9_records")
