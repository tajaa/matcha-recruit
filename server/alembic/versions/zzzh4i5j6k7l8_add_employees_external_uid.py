"""Add external_uid to employees for HR-internal badge/employee number.

IR-only customers identify involved employees by an internal UID (badge
number) rather than UUID. Stored on employees alongside email/name and
resolved server-side when an incident's involved_employee_ids contains a
non-UUID string.

Revision ID: zzzh4i5j6k7l8
Revises: zzzg3h4i5j6k7
Create Date: 2026-04-29
"""
from alembic import op

revision = "zzzh4i5j6k7l8"
down_revision = "zzzg3h4i5j6k7"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS external_uid VARCHAR(64)")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_employees_org_uid
        ON employees(org_id, external_uid)
        WHERE external_uid IS NOT NULL
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_employees_org_uid")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS external_uid")
