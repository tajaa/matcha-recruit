"""add involved_employee_ids UUID array to ir_incidents

Revision ID: i4j5k6l7m8n9
Revises: h3i4j5k6l7m8
Create Date: 2026-03-07
"""

from alembic import op


revision = "i4j5k6l7m8n9"
down_revision = "h3i4j5k6l7m8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE ir_incidents
        ADD COLUMN IF NOT EXISTS involved_employee_ids UUID[] DEFAULT '{}'
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ir_incidents_involved_employee_ids
        ON ir_incidents USING GIN (involved_employee_ids)
    """)
    # Backfill: match reporters by email to employee records
    op.execute("""
        UPDATE ir_incidents i
        SET involved_employee_ids = matched.emp_ids
        FROM (
            SELECT i2.id AS incident_id,
                   array_agg(DISTINCT e.id) AS emp_ids
            FROM ir_incidents i2
            JOIN employees e ON e.org_id = i2.company_id
              AND (
                i2.reported_by_email IS NOT NULL AND i2.reported_by_email IN (e.email, e.personal_email)
                OR LOWER(i2.reported_by_name) = LOWER(e.first_name || ' ' || e.last_name)
              )
            WHERE i2.involved_employee_ids = '{}'
            GROUP BY i2.id
        ) matched
        WHERE i.id = matched.incident_id
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_ir_incidents_involved_employee_ids")
    op.execute("ALTER TABLE ir_incidents DROP COLUMN IF EXISTS involved_employee_ids")
