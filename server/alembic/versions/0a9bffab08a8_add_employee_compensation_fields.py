"""add_employee_compensation_fields

Revision ID: 0a9bffab08a8
Revises: 5ede773fd831
Create Date: 2026-03-01 20:54:06.899861

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a9bffab08a8'
down_revision: Union[str, Sequence[str], None] = '5ede773fd831'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE employees ADD COLUMN pay_classification VARCHAR(10) CHECK (pay_classification IN ('hourly', 'exempt'))")
    op.execute("ALTER TABLE employees ADD COLUMN pay_rate DECIMAL(12, 2)")
    op.execute("ALTER TABLE employees ADD COLUMN work_city VARCHAR(100)")
    op.create_index("idx_employees_pay_classification", "employees", ["pay_classification"])
    op.create_index("idx_employees_work_city", "employees", ["work_city"])


def downgrade() -> None:
    op.drop_index("idx_employees_work_city", table_name="employees")
    op.drop_index("idx_employees_pay_classification", table_name="employees")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS work_city")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS pay_rate")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS pay_classification")
