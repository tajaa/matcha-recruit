"""add_row_level_security

Revision ID: e72bfad5eca9
Revises: db9963457338
Create Date: 2026-03-04 19:07:35.147391

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e72bfad5eca9'
down_revision: Union[str, Sequence[str], None] = 'db9963457338'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables that use company_id as the tenant column
COMPANY_ID_TABLES = [
    "ir_incidents",
    "offer_letters",
    "positions",
    "policies",
    "er_cases",
]

# Tables that use org_id instead of company_id
ORG_ID_TABLES = [
    "employees",
    "onboarding_tasks",
    "enps_surveys",
]


def upgrade() -> None:
    """Enable row-level security on all tenant-scoped tables."""
    for table in COMPANY_ID_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (company_id::text = current_setting('app.current_tenant_id', true))"
        )

    for table in ORG_ID_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (org_id::text = current_setting('app.current_tenant_id', true))"
        )


def downgrade() -> None:
    """Remove row-level security from all tenant-scoped tables."""
    for table in COMPANY_ID_TABLES + ORG_ID_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
