"""add employment_status, status_changed_at, status_reason to employees

Revision ID: s1t2u3v4w5x6
Revises: c6d7e8f9a0b1
Create Date: 2026-03-08
"""
from typing import Sequence, Union

from alembic import op


revision: str = 's1t2u3v4w5x6'
down_revision: Union[str, Sequence[str], None] = 'c6d7e8f9a0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE employees ADD COLUMN IF NOT EXISTS employment_status VARCHAR(30) DEFAULT 'active'
    """)
    op.execute("""
        UPDATE employees SET employment_status = 'terminated'
        WHERE termination_date IS NOT NULL AND (employment_status IS NULL OR employment_status = 'active')
    """)
    op.execute("""
        UPDATE employees SET employment_status = 'active' WHERE employment_status IS NULL
    """)
    op.execute("""
        ALTER TABLE employees ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMP
    """)
    op.execute("""
        ALTER TABLE employees ADD COLUMN IF NOT EXISTS status_reason TEXT
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS status_reason")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS status_changed_at")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS employment_status")
