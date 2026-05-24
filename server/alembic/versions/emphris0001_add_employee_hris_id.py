"""add_employee_hris_id_column

Revision ID: emphris0001
Revises: gustowh0001
Create Date: 2026-05-24 16:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'emphris0001'
down_revision: Union[str, Sequence[str], None] = 'gustowh0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS hris_id TEXT")
    # Partial unique: one Gusto UUID per org, but allow many NULLs (non-HRIS employees)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_employees_org_hris_id
        ON employees (org_id, hris_id)
        WHERE hris_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_employees_org_hris_id")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS hris_id")
