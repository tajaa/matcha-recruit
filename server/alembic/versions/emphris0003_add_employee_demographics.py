"""add_employee_demographics_table

Revision ID: emphris0003
Revises: emphris0002
Create Date: 2026-07-17 10:05:00.000000

Protected-class demographics from the HRIS `individual` payload — the input a
real pay-equity gap needs. Finch already returns these on a payload we fetch in
full; we discarded them at the normalizer.

Its own table, not columns on `employees`, and that is the whole point: these are
protected-class fields under Title VII / EEO reporting. A column on `employees`
would ride along in every existing SELECT, every roster export, and every
broker-facing dump by default, and staying clean would mean remembering to filter
it out forever. A separate table can only leak if someone writes a JOIN — reads
are confined to pay_equity_analysis.analyze.

Columns are exactly what Finch's individual payload carries (2020-09-17 schema):
dob, gender, ethnicity. No veteran/disability columns — Finch has no such fields,
and a column nothing populates is a lie the schema tells. `ssn`/`encrypted_ssn`
sit on the same payload and are deliberately not taken.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'emphris0003'
down_revision: Union[str, Sequence[str], None] = 'emphris0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS employee_demographics (
            employee_id   UUID PRIMARY KEY REFERENCES employees(id) ON DELETE CASCADE,
            org_id        UUID NOT NULL,
            date_of_birth DATE,
            gender        VARCHAR(32),
            ethnicity     VARCHAR(64),
            source        VARCHAR(16),
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    # Tenant-scoped reads (the pay-equity analysis joins on org_id).
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_employee_demographics_org
        ON employee_demographics (org_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_employee_demographics_org")
    op.execute("DROP TABLE IF EXISTS employee_demographics")
