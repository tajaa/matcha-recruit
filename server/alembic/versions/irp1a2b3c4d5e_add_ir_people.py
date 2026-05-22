"""add ir_people registry + ir_incident_people junction

Lightweight, auto-built people index for matcha-lite IR. People named in
incidents (reporter / involved / witness / interviewee) get a stable id
WITHOUT standing up the full employees roster — identity is derived from
the typed name (normalized for dedup), so per-person incident history works
on the IR feature alone. Distinct from `ir_incidents.involved_employee_ids`,
which targets the real `employees` roster (full-platform path).

Revision ID: irp1a2b3c4d5e
Revises: salespipe0001
Create Date: 2026-05-21
"""

from alembic import op


revision = "irp1a2b3c4d5e"
down_revision = "salespipe0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS ir_people (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            display_name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            email TEXT,
            verified BOOLEAN NOT NULL DEFAULT false,
            first_seen TIMESTAMP DEFAULT NOW(),
            last_seen TIMESTAMP DEFAULT NOW()
        )
    """)
    # Dedup + prefix autocomplete both ride this unique index.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ir_people_company_norm
        ON ir_people (company_id, normalized_name)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS ir_incident_people (
            incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
            person_id UUID NOT NULL REFERENCES ir_people(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('reporter', 'involved', 'witness', 'interviewee')),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (incident_id, person_id, role)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ir_incident_people_person
        ON ir_incident_people (person_id)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS ir_incident_people")
    op.execute("DROP TABLE IF EXISTS ir_people")
