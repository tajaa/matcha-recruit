"""add training_requirements and training_records tables

Revision ID: t2u3v4w5x6y7
Revises: c6d7e8f9a0b1
Create Date: 2026-03-08
"""

from alembic import op


revision = "t2u3v4w5x6y7"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS training_requirements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            training_type VARCHAR(50) NOT NULL,
            jurisdiction VARCHAR(50),
            frequency_months INTEGER,
            applies_to VARCHAR(50) DEFAULT 'all',
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS training_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            requirement_id UUID REFERENCES training_requirements(id) ON DELETE SET NULL,
            title VARCHAR(255) NOT NULL,
            training_type VARCHAR(50) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'assigned',
            assigned_date DATE NOT NULL DEFAULT CURRENT_DATE,
            due_date DATE,
            completed_date DATE,
            expiration_date DATE,
            provider VARCHAR(255),
            certificate_number VARCHAR(100),
            score DECIMAL(5,2),
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS idx_training_records_company ON training_records(company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_records_employee ON training_records(employee_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_records_status ON training_records(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_records_due_date ON training_records(due_date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_requirements_company ON training_requirements(company_id)")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_training_records_active_assignment
        ON training_records(employee_id, requirement_id)
        WHERE status IN ('assigned', 'in_progress')
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS training_records")
    op.execute("DROP TABLE IF EXISTS training_requirements")
