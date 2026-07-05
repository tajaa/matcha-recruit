"""Seed the 8 orphaned manufacturing compliance_categories rows.

`admin.py`'s manufacturing domain definition lists 10 categories
(process_safety, environmental_compliance, chemical_safety, machine_safety,
industrial_hygiene, trade_compliance, product_safety, labor_relations,
quality_systems, supply_chain) but migration u6v7w8x9y0z1 only ever seeded the
last 2. Every research pass for the other 8 (including environmental_compliance
— arguably the most legally significant of the set) was silently dropped by the
ingest scripts, which skip any category with no `compliance_categories` row.
Data-only migration, mirrors u6v7w8x9y0z1's seed pattern. No DDL.

Revision ID: mfgcat01
Revises: legaldef02
Create Date: 2026-07-04
"""

from alembic import op

revision = "mfgcat01"
down_revision = "legaldef02"
branch_labels = None
depends_on = None


# (slug, name, description, industry_tag, sort_order)
_NEW_CATEGORIES = [
    ("process_safety", "Process Safety Management",
     "OSHA PSM / EPA RMP, major-accident hazard prevention, mechanical integrity, "
     "process hazard analysis for chemical/hazardous manufacturing.",
     "manufacturing:process_safety", 810),
    ("environmental_compliance", "Environmental & Emissions",
     "Air/water/waste permitting beyond baseline EPA rules — state-delegated NPDES, "
     "air toxics programs, hazardous waste generator requirements.",
     "manufacturing:environmental", 820),
    ("chemical_safety", "Chemical & Hazardous Materials",
     "Hazard communication (GHS/HazCom), EPCRA/Tier II reporting, chemical "
     "right-to-know, REACH/RoHS-style substance restrictions.",
     "manufacturing:chemical", 830),
    ("machine_safety", "Machine & Equipment Safety",
     "Lockout/tagout, machine guarding, equipment certification (OSHA LOTO, "
     "UK PUWER/LOLER-equivalent requirements).",
     "manufacturing:machine_safety", 840),
    ("industrial_hygiene", "Industrial Hygiene & Exposure",
     "Noise, respiratory, and chemical exposure limits; permissible exposure "
     "limits and monitoring/recordkeeping obligations.",
     "manufacturing:industrial_hygiene", 850),
    ("trade_compliance", "Import/Export & Trade",
     "Customs, tariffs, anti-dumping, export controls, and free-trade-agreement "
     "compliance for manufactured goods.",
     "manufacturing:trade", 860),
    ("product_safety", "Product Safety & Standards",
     "Product certification and safety standards (e.g. NHTSA/FMVSS, UNECE type "
     "approval, consumer product safety requirements).",
     "manufacturing:product_safety", 870),
    ("labor_relations", "Labor Relations",
     "Union recognition, collective bargaining, and employment-relations rules "
     "specific to manufacturing workforces (NLRA and state/foreign equivalents).",
     "manufacturing:labor_relations", 880),
]


def upgrade():
    for slug, name, description, industry_tag, sort_order in _NEW_CATEGORIES:
        desc_escaped = description.replace("'", "''")
        op.execute(f"""
            INSERT INTO compliance_categories (slug, name, description, domain, "group", industry_tag, sort_order)
            VALUES ('{slug}', '{name}', '{desc_escaped}', 'manufacturing', 'manufacturing',
                    '{industry_tag}', {sort_order})
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description
        """)


def downgrade():
    slugs = ", ".join(f"'{slug}'" for slug, *_ in _NEW_CATEGORIES)
    op.execute(f"DELETE FROM compliance_categories WHERE slug IN ({slugs})")
