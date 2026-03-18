"""06: Insert additive precedence rules for healthcare billing categories

Revision ID: za1b2c3d4e5f6
Revises: zp4q5r6s7t8u
Create Date: 2026-03-17
"""

from alembic import op


revision = "za1b2c3d4e5f6"
down_revision = "zp4q5r6s7t8u"
branch_labels = None
depends_on = None

# Healthcare categories that use additive precedence
ADDITIVE_CATEGORIES = (
    "billing_integrity",
    "clinical_safety",
    "healthcare_workforce",
    "quality_reporting",
    "payer_relations",
)

REASONING = (
    "Healthcare compliance is additive: federal baseline (HIPAA, Anti-Kickback, "
    "False Claims Act, CMS CoPs) applies alongside state and local requirements. "
    "Unlike labor compliance where a city minimum wage can preempt the state rate, "
    "all healthcare regulatory layers apply simultaneously."
)


def upgrade():
    # Insert one additive precedence rule per healthcare category.
    # Links the federal jurisdiction to all children via applies_to_all_children.
    for cat_slug in ADDITIVE_CATEGORIES:
        op.execute(f"""
            INSERT INTO precedence_rules (
                category_id,
                higher_jurisdiction_id,
                applies_to_all_children,
                precedence_type,
                reasoning_text,
                status
            )
            SELECT
                cc.id,
                j.id,
                true,
                'additive',
                '{REASONING.replace("'", "''")}',
                'active'
            FROM compliance_categories cc
            CROSS JOIN jurisdictions j
            WHERE cc.slug = '{cat_slug}'
              AND j.level = 'federal'
              AND j.state = 'US'
              AND NOT EXISTS (
                  SELECT 1 FROM precedence_rules pr
                  WHERE pr.category_id = cc.id
                    AND pr.higher_jurisdiction_id = j.id
                    AND pr.precedence_type = 'additive'
                    AND pr.applies_to_all_children = true
              )
        """)


def downgrade():
    for cat_slug in ADDITIVE_CATEGORIES:
        op.execute(f"""
            DELETE FROM precedence_rules
            WHERE precedence_type = 'additive'
              AND applies_to_all_children = true
              AND category_id = (
                  SELECT id FROM compliance_categories WHERE slug = '{cat_slug}'
              )
              AND higher_jurisdiction_id = (
                  SELECT id FROM jurisdictions WHERE level = 'federal' AND state = 'US' LIMIT 1
              )
        """)
