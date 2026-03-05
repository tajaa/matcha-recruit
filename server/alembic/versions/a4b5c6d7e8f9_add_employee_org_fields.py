"""add employee org fields (job_title, department)

Revision ID: a4b5c6d7e8f9
Revises: af9078057ed5
Create Date: 2026-03-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, Sequence[str], None] = 'af9078057ed5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS job_title VARCHAR(150)")
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS department VARCHAR(100)")
    op.create_index("idx_employees_job_title", "employees", ["job_title"])
    op.create_index("idx_employees_department", "employees", ["department"])


def downgrade() -> None:
    op.drop_index("idx_employees_department", table_name="employees")
    op.drop_index("idx_employees_job_title", table_name="employees")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS department")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS job_title")
