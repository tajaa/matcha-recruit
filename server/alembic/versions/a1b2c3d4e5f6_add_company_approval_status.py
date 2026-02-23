"""add_company_approval_status

Revision ID: a1b2c3d4e5f6
Revises: 9d4e8f7a6b5c
Create Date: 2026-01-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = '9d4e8f7a6b5c'
branch_labels = None
depends_on = None
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '9d4e8f7a6b5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add approval workflow columns to companies table."""

    # Add status column (default 'approved' for existing companies)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'companies' AND column_name = 'status'
            ) THEN
                ALTER TABLE companies ADD COLUMN status VARCHAR(20) DEFAULT 'approved';
            END IF;
        END $$;
    """)

    # Add approved_at column
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'companies' AND column_name = 'approved_at'
            ) THEN
                ALTER TABLE companies ADD COLUMN approved_at TIMESTAMPTZ;
            END IF;
        END $$;
    """)

    # Add approved_by column (references users)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'companies' AND column_name = 'approved_by'
            ) THEN
                ALTER TABLE companies ADD COLUMN approved_by UUID REFERENCES users(id);
            END IF;
        END $$;
    """)

    # Add rejection_reason column
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'companies' AND column_name = 'rejection_reason'
            ) THEN
                ALTER TABLE companies ADD COLUMN rejection_reason TEXT;
            END IF;
        END $$;
    """)

    # Create index on status for filtering
    op.execute("CREATE INDEX IF NOT EXISTS idx_companies_status ON companies(status)")


def downgrade() -> None:
    """Remove approval workflow columns from companies table."""
    op.execute("DROP INDEX IF EXISTS idx_companies_status")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS rejection_reason")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS approved_by")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS approved_at")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS status")
