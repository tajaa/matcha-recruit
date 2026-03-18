"""05: Add explainability to compliance_requirements + create employee_jurisdictions + RLS

Revision ID: zp4q5r6s7t8u
Revises: zo3p4q5r6s7t
Create Date: 2026-03-17
"""

from alembic import op


revision = "zp4q5r6s7t8u"
down_revision = "zo3p4q5r6s7t"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Add explainability columns to compliance_requirements ──────────
    op.execute("""
        ALTER TABLE compliance_requirements
        ADD COLUMN IF NOT EXISTS governing_jurisdiction_level VARCHAR(20)
    """)
    op.execute("""
        ALTER TABLE compliance_requirements
        ADD COLUMN IF NOT EXISTS governing_precedence_rule_id UUID REFERENCES precedence_rules(id)
    """)
    op.execute("""
        ALTER TABLE compliance_requirements
        ADD COLUMN IF NOT EXISTS governance_source VARCHAR(20) NOT NULL DEFAULT 'not_evaluated'
    """)

    # ── 2. Create employee_jurisdictions table ────────────────────────────
    op.execute("""
        CREATE TABLE employee_jurisdictions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            jurisdiction_id UUID NOT NULL REFERENCES jurisdictions(id) ON DELETE CASCADE,
            relationship_type employee_jurisdiction_rel_type_enum NOT NULL,
            effective_date DATE,
            end_date DATE,
            created_at TIMESTAMP DEFAULT NOW(),

            CONSTRAINT uq_employee_jurisdictions_emp_jur_rel
                UNIQUE (employee_id, jurisdiction_id, relationship_type)
        )
    """)
    op.execute("CREATE INDEX ix_employee_jurisdictions_employee_id ON employee_jurisdictions(employee_id)")
    op.execute("CREATE INDEX ix_employee_jurisdictions_jurisdiction_id ON employee_jurisdictions(jurisdiction_id)")
    op.execute("CREATE INDEX ix_employee_jurisdictions_relationship_type ON employee_jurisdictions(relationship_type)")

    # ── 3. Migrate work_state → employee_jurisdictions ────────────────────
    # For each employee with a work_state, insert a 'works_at' relationship
    # to the matching state-level jurisdiction
    op.execute("""
        INSERT INTO employee_jurisdictions (employee_id, jurisdiction_id, relationship_type)
        SELECT e.id, j.id, 'works_at'::employee_jurisdiction_rel_type_enum
        FROM employees e
        JOIN jurisdictions j ON j.state = e.work_state AND j.level = 'state'
        WHERE e.work_state IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM employee_jurisdictions ej
            WHERE ej.employee_id = e.id
            AND ej.jurisdiction_id = j.id
            AND ej.relationship_type = 'works_at'
        )
    """)

    # ── 4. Migrate work_location_id → city-level jurisdiction links ───────
    op.execute("""
        INSERT INTO employee_jurisdictions (employee_id, jurisdiction_id, relationship_type)
        SELECT e.id, bl.jurisdiction_id, 'works_at'::employee_jurisdiction_rel_type_enum
        FROM employees e
        JOIN business_locations bl ON bl.id = e.work_location_id
        WHERE e.work_location_id IS NOT NULL
        AND bl.jurisdiction_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM employee_jurisdictions ej
            WHERE ej.employee_id = e.id
            AND ej.jurisdiction_id = bl.jurisdiction_id
            AND ej.relationship_type = 'works_at'
        )
    """)

    # ── 5. Add RLS policy on employee_jurisdictions ───────────────────────
    op.execute("""
        ALTER TABLE employee_jurisdictions ENABLE ROW LEVEL SECURITY
    """)
    op.execute("""
        ALTER TABLE employee_jurisdictions FORCE ROW LEVEL SECURITY
    """)
    op.execute("""
        CREATE POLICY tenant_isolation ON employee_jurisdictions
            USING (
                employee_id IN (
                    SELECT id FROM employees
                    WHERE org_id::text = current_setting('app.current_tenant_id', true)
                )
                OR current_setting('app.is_admin', true) = 'true'
            )
    """)

    # ── 6. Add deprecation comment on employees.work_state ────────────────
    op.execute("""
        COMMENT ON COLUMN employees.work_state IS
        'DEPRECATED: Use employee_jurisdictions table instead. Kept for backward compat.'
    """)


def downgrade():
    # Remove deprecation comment
    op.execute("COMMENT ON COLUMN employees.work_state IS NULL")

    # Remove RLS
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON employee_jurisdictions")
    op.execute("ALTER TABLE employee_jurisdictions DISABLE ROW LEVEL SECURITY")

    # Drop employee_jurisdictions
    op.execute("DROP TABLE IF EXISTS employee_jurisdictions")

    # Remove explainability columns
    op.execute("ALTER TABLE compliance_requirements DROP COLUMN IF EXISTS governance_source")
    op.execute("ALTER TABLE compliance_requirements DROP COLUMN IF EXISTS governing_precedence_rule_id")
    op.execute("ALTER TABLE compliance_requirements DROP COLUMN IF EXISTS governing_jurisdiction_level")
