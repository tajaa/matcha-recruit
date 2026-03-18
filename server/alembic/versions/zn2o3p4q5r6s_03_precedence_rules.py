"""03: Create precedence_rules table and migrate state_preemption_rules data

Revision ID: zn2o3p4q5r6s
Revises: zm1n2o3p4q5r
Create Date: 2026-03-17
"""

from alembic import op


revision = "zn2o3p4q5r6s"
down_revision = "zm1n2o3p4q5r"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Create precedence_rules table ──────────────────────────────────
    op.execute("""
        CREATE TABLE precedence_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            category_id UUID NOT NULL REFERENCES compliance_categories(id),
            higher_jurisdiction_id UUID NOT NULL REFERENCES jurisdictions(id),
            lower_jurisdiction_id UUID REFERENCES jurisdictions(id),
            applies_to_all_children BOOLEAN NOT NULL DEFAULT false,
            precedence_type precedence_type_enum NOT NULL,
            trigger_condition JSONB,
            reasoning_text TEXT,
            legal_citation VARCHAR(500),
            effective_date DATE,
            sunset_date DATE,
            last_verified_at TIMESTAMP,
            status precedence_rule_status_enum NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),

            CONSTRAINT ck_precedence_rules_children_xor_lower CHECK (
                (applies_to_all_children = true AND lower_jurisdiction_id IS NULL)
                OR (applies_to_all_children = false AND lower_jurisdiction_id IS NOT NULL)
            )
        )
    """)

    # Indexes
    op.execute("CREATE INDEX ix_precedence_rules_category_id ON precedence_rules(category_id)")
    op.execute("CREATE INDEX ix_precedence_rules_status ON precedence_rules(status)")
    op.execute("CREATE INDEX ix_precedence_rules_lower_jurisdiction_id ON precedence_rules(lower_jurisdiction_id)")
    op.execute("CREATE INDEX ix_precedence_rules_higher_jurisdiction_id ON precedence_rules(higher_jurisdiction_id)")

    # ── 2. Migrate from state_preemption_rules ────────────────────────────
    # Each state_preemption_rule becomes a blanket precedence rule:
    #   - higher_jurisdiction_id = the state's jurisdiction row
    #   - lower_jurisdiction_id = NULL (blanket)
    #   - applies_to_all_children = true
    #   - allows_local_override = true → floor
    #   - allows_local_override = false → ceiling
    op.execute("""
        INSERT INTO precedence_rules (
            category_id,
            higher_jurisdiction_id,
            lower_jurisdiction_id,
            applies_to_all_children,
            precedence_type,
            reasoning_text,
            legal_citation,
            status
        )
        SELECT
            cc.id AS category_id,
            j.id AS higher_jurisdiction_id,
            NULL AS lower_jurisdiction_id,
            true AS applies_to_all_children,
            CASE
                WHEN spr.allows_local_override = true THEN 'floor'::precedence_type_enum
                ELSE 'ceiling'::precedence_type_enum
            END AS precedence_type,
            spr.notes AS reasoning_text,
            spr.source_url AS legal_citation,
            'active'::precedence_rule_status_enum AS status
        FROM state_preemption_rules spr
        JOIN jurisdictions j ON j.state = spr.state AND j.level = 'state'
        JOIN compliance_categories cc ON cc.slug = spr.category
    """)

    # Do NOT drop state_preemption_rules — kept for backward compat


def downgrade():
    op.execute("DROP TABLE IF EXISTS precedence_rules")
