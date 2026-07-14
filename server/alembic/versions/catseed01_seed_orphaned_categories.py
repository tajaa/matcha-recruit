"""Seed the 10 registry categories that have no compliance_categories row.

The code registry (compliance_registry.CATEGORIES, 79 keys) and the
migration-seeded compliance_categories table have drifted three times now
(baseline01, mfgcat01, and this). Ten registry categories were never seeded:

  labor (all four in REQUIRED_LABOR_CATEGORIES, i.e. the default research
  sweep): pay_transparency, drug_testing, non_compete, whistleblower

  life_sciences (biotech specialty set): biosafety_lab, clinical_trials_gcp,
  drug_supply_chain, glp_nonclinical, gmp_manufacturing, sunshine_open_payments

Under the old arbitrary-COALESCE upsert these rows landed with a WRONG
category_id (random row) but a correct `category` text column; under the
fixed upsert they fall back to the `uncategorized` row with a warning. Either
way the real fix is rows existing for them. Data-only migration, mirrors
mfgcat01's pattern. No DDL beyond the enum-value add (idempotent).

NOT applied by this commit — author only, per the repo's production-safety
rule. Chains off scoperg02 (this branch's other authored-only migrations).

Revision ID: catseed01
Revises: scoperg02
Create Date: 2026-07-13
"""
from alembic import op

revision = "catseed01"
down_revision = "scoperg02"
branch_labels = None
depends_on = None


# (slug, name, description, domain, group, industry_tag, sort_order)
_NEW_CATEGORIES = [
    ("pay_transparency", "Pay Transparency & Equity",
     "Salary-range disclosure in postings, pay-data reporting, pay-equity "
     "audit and anti-retaliation rules (e.g. CO EPEWA, CA SB 1162, NYC 32-A).",
     "labor", "labor", "", 910),
    ("drug_testing", "Drug & Alcohol Testing",
     "Pre-employment/random/post-accident testing limits, off-duty cannabis "
     "protections, DOT-regulated testing carve-outs.",
     "labor", "labor", "", 920),
    ("non_compete", "Non-Compete & Restrictive Covenants",
     "Non-compete enforceability, salary thresholds, notice requirements, and "
     "bans (e.g. CA B&P 16600, MN/OK bans, FTC rule status).",
     "labor", "labor", "", 930),
    ("whistleblower", "Whistleblower Protections",
     "Anti-retaliation protections for reporting violations — SOX/Dodd-Frank, "
     "state whistleblower acts, internal-reporting channel requirements.",
     "labor", "labor", "", 940),
    ("gmp_manufacturing", "GMP Manufacturing",
     "Current Good Manufacturing Practice for drugs/biologics/devices — "
     "21 CFR 210/211/820, quality units, batch records, data integrity.",
     "life_sciences", "life_sciences", "biotech", 950),
    ("glp_nonclinical", "Good Laboratory Practice",
     "GLP for nonclinical safety studies — 21 CFR 58, study director duties, "
     "QAU, protocol/records requirements.",
     "life_sciences", "life_sciences", "biotech", 955),
    ("clinical_trials_gcp", "Clinical Trials & GCP",
     "Good Clinical Practice — IRB/IEC oversight, informed consent, IND/IDE "
     "obligations, ClinicalTrials.gov registration and results reporting.",
     "life_sciences", "life_sciences", "biotech", 960),
    ("drug_supply_chain", "Drug Supply Chain (DSCSA)",
     "Drug Supply Chain Security Act — serialization, verification, suspect/"
     "illegitimate product handling, trading-partner licensure.",
     "life_sciences", "life_sciences", "biotech", 965),
    ("sunshine_open_payments", "Sunshine Act / Open Payments",
     "Physician-payment transparency — CMS Open Payments reporting, state "
     "gift-ban/disclosure laws (VT, MA, MN).",
     "life_sciences", "life_sciences", "biotech", 970),
    ("biosafety_lab", "Biosafety & Lab Safety",
     "Biosafety levels, select agents (42 CFR 73), bloodborne pathogens, "
     "institutional biosafety committees, lab-specific OSHA standards.",
     "life_sciences", "life_sciences", "biotech", 975),
]


def upgrade():
    # life_sciences was added by u6v7w8x9y0z1; idempotent re-add for safety.
    op.execute("""
        DO $$ BEGIN
            ALTER TYPE category_domain_enum ADD VALUE IF NOT EXISTS 'life_sciences';
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("COMMIT")
    op.execute("BEGIN")

    # The `uncategorized` sentinel is the upserts' last-resort parking slot for
    # a category whose seed row doesn't exist yet. zo3p4q5r6s7t was supposed to
    # create it but it is ABSENT on dev (verified) — so without this the drift
    # fallback has nowhere to park and the row is dropped after all. Belt and
    # braces: this migration is precisely about categories that went missing.
    op.execute("""
        INSERT INTO compliance_categories (slug, name, description, domain, "group", sort_order)
        SELECT 'uncategorized', 'Uncategorized',
               'Last-resort parking slot for requirements whose category has no seed row yet.',
               'labor', 'supplementary', 999
        WHERE NOT EXISTS (SELECT 1 FROM compliance_categories WHERE slug = 'uncategorized')
    """)

    for slug, name, description, domain, group, industry_tag, sort_order in _NEW_CATEGORIES:
        desc_escaped = description.replace("'", "''")
        op.execute(f"""
            INSERT INTO compliance_categories (slug, name, description, domain, "group", industry_tag, sort_order)
            VALUES ('{slug}', '{name}', '{desc_escaped}', '{domain}', '{group}',
                    '{industry_tag}', {sort_order})
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description
        """)

    # Re-home any rows the old arbitrary-COALESCE fallback mis-tagged, and any
    # rows parked on `uncategorized`, now that their true category rows exist.
    op.execute("""
        UPDATE jurisdiction_requirements jr
        SET category_id = cc.id
        FROM compliance_categories cc
        WHERE cc.slug = jr.category
          AND jr.category_id IS DISTINCT FROM cc.id
    """)


def downgrade():
    slugs = ", ".join(f"'{slug}'" for slug, *_ in _NEW_CATEGORIES)
    # Park dependent rows on uncategorized before deleting the category rows
    # (jurisdiction_requirements.category_id is NOT NULL).
    op.execute(f"""
        UPDATE jurisdiction_requirements jr
        SET category_id = (SELECT id FROM compliance_categories WHERE slug = 'uncategorized')
        FROM compliance_categories cc
        WHERE cc.id = jr.category_id AND cc.slug IN ({slugs})
    """)
    op.execute(f"DELETE FROM compliance_categories WHERE slug IN ({slugs})")
