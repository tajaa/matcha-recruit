"""Make idx_bl_company_city_state partial to source='employee_derived'

Old behavior: UNIQUE(company_id, lower(city), upper(state)) for ALL rows.
That broke IR onboarding for tenants with multiple physical sites in the
same city (e.g. two clinics in Los Angeles, CA): the second add silently
overwrote the first via the IR upsert's ON CONFLICT DO UPDATE.

New behavior: index covers only employee_derived rows, so compliance's
auto-derive path stays idempotent ("one jurisdiction-anchor per
city/state per company") while user-managed manual rows can repeat.

Revision ID: zzzm9n0o1p2q3
Revises: zzzl8m9n0o1p2
Create Date: 2026-04-30
"""

from typing import Sequence, Union

from alembic import op


revision: str = "zzzm9n0o1p2q3"
down_revision: Union[str, None] = "zzzl8m9n0o1p2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_bl_company_city_state")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_bl_company_city_state "
        "ON business_locations (company_id, LOWER(city), UPPER(state)) "
        "WHERE source = 'employee_derived'"
    )


def downgrade() -> None:
    # Best-effort revert. If manual rows now share (company, city, state)
    # the unique recreation will fail; the operator must dedupe first.
    op.execute("DROP INDEX IF EXISTS idx_bl_company_city_state")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_bl_company_city_state "
        "ON business_locations (company_id, LOWER(city), UPPER(state))"
    )
