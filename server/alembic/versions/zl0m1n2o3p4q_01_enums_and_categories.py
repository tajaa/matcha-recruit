"""01: Create compliance ENUM types and compliance_categories table

Revision ID: zl0m1n2o3p4q
Revises: zk9l0m1n2o3p
Create Date: 2026-03-17
"""

from alembic import op


revision = "zl0m1n2o3p4q"
down_revision = "zk9l0m1n2o3p"
branch_labels = None
depends_on = None


def upgrade():
    # ── Create 9 PostgreSQL ENUM types ────────────────────────────────────
    op.execute("""
        CREATE TYPE jurisdiction_level_enum AS ENUM (
            'federal', 'state', 'county', 'city', 'special_district', 'regulatory_body'
        )
    """)
    op.execute("""
        CREATE TYPE precedence_type_enum AS ENUM (
            'floor', 'ceiling', 'supersede', 'additive'
        )
    """)
    op.execute("""
        CREATE TYPE precedence_rule_status_enum AS ENUM (
            'active', 'pending_review', 'repealed'
        )
    """)
    op.execute("""
        CREATE TYPE requirement_status_enum AS ENUM (
            'active', 'pending', 'repealed', 'superseded', 'under_review'
        )
    """)
    op.execute("""
        CREATE TYPE source_tier_enum AS ENUM (
            'tier_1_government', 'tier_2_official_secondary', 'tier_3_aggregator'
        )
    """)
    op.execute("""
        CREATE TYPE change_source_enum AS ENUM (
            'ai_fetch', 'manual_review', 'legislative_update', 'system_migration'
        )
    """)
    op.execute("""
        CREATE TYPE employee_jurisdiction_rel_type_enum AS ENUM (
            'licensed_in', 'works_at', 'telehealth_coverage', 'historical'
        )
    """)
    op.execute("""
        CREATE TYPE category_domain_enum AS ENUM (
            'labor', 'privacy', 'clinical', 'billing', 'licensing',
            'safety', 'reporting', 'emergency', 'corporate_integrity'
        )
    """)
    op.execute("""
        CREATE TYPE governance_source_enum AS ENUM (
            'precedence_rule', 'default_local', 'not_evaluated'
        )
    """)

    # ── Create compliance_categories table ────────────────────────────────
    op.execute("""
        CREATE TABLE compliance_categories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug VARCHAR(60) NOT NULL UNIQUE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            parent_category_id UUID REFERENCES compliance_categories(id) ON DELETE SET NULL,
            domain category_domain_enum NOT NULL,
            "group" VARCHAR(30) NOT NULL,
            industry_tag VARCHAR(60),
            research_mode VARCHAR(30) DEFAULT 'default_sweep',
            docx_section INTEGER,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_compliance_categories_domain ON compliance_categories(domain)")
    op.execute('CREATE INDEX ix_compliance_categories_group ON compliance_categories("group")')

    # ── Seed 45 categories ────────────────────────────────────────────────
    # Domain mapping:
    #   labor, supplementary → labor
    #   healthcare → per-category (see below)
    #   oncology → safety
    #   medical_compliance → per-category (see below)
    categories = [
        # Labor (12)
        ("minimum_wage", "Minimum Wage", "labor", "labor", "", "default_sweep", None),
        ("overtime", "Overtime", "labor", "labor", "", "default_sweep", None),
        ("sick_leave", "Sick Leave", "labor", "labor", "", "default_sweep", None),
        ("meal_breaks", "Meal & Rest Breaks", "labor", "labor", "", "default_sweep", None),
        ("pay_frequency", "Pay Frequency", "labor", "labor", "", "default_sweep", None),
        ("final_pay", "Final Pay", "labor", "labor", "", "default_sweep", None),
        ("minor_work_permit", "Minor Work Permits", "labor", "labor", "", "default_sweep", None),
        ("scheduling_reporting", "Scheduling & Reporting Time", "labor", "labor", "", "default_sweep", None),
        ("leave", "Leave", "labor", "labor", "", "default_sweep", None),
        ("workplace_safety", "Workplace Safety", "labor", "labor", "", "default_sweep", None),
        ("workers_comp", "Workers'' Comp", "labor", "labor", "", "default_sweep", None),
        ("anti_discrimination", "Anti-Discrimination", "labor", "labor", "", "default_sweep", None),
        # Supplementary (3) → labor domain
        ("business_license", "Business License", "labor", "supplementary", "", "default_sweep", None),
        ("tax_rate", "Tax Rate", "labor", "supplementary", "", "default_sweep", None),
        ("posting_requirements", "Posting Requirements", "labor", "supplementary", "", "default_sweep", None),
        # Healthcare (8)
        ("hipaa_privacy", "HIPAA Privacy & Security", "privacy", "healthcare", "healthcare", "specialty", 1),
        ("billing_integrity", "Billing & Financial Integrity", "billing", "healthcare", "healthcare", "specialty", 2),
        ("clinical_safety", "Clinical & Patient Safety", "clinical", "healthcare", "healthcare", "specialty", 3),
        ("healthcare_workforce", "Healthcare Workforce", "clinical", "healthcare", "healthcare", "specialty", 4),
        ("corporate_integrity", "Corporate Integrity & Ethics", "corporate_integrity", "healthcare", "healthcare", "specialty", 5),
        ("research_consent", "Research & Informed Consent", "clinical", "healthcare", "healthcare", "specialty", 11),
        ("state_licensing", "State Licensing & Scope", "licensing", "healthcare", "healthcare", "specialty", 24),
        ("emergency_preparedness", "Emergency Preparedness", "emergency", "healthcare", "healthcare", "specialty", 10),
        # Oncology (5) → safety domain
        ("radiation_safety", "Radiation Safety", "safety", "oncology", "healthcare:oncology", "specialty", None),
        ("chemotherapy_handling", "Chemotherapy & Hazardous Drugs", "safety", "oncology", "healthcare:oncology", "specialty", None),
        ("tumor_registry", "Tumor Registry Reporting", "reporting", "oncology", "healthcare:oncology", "specialty", None),
        ("oncology_clinical_trials", "Oncology Clinical Trials", "clinical", "oncology", "healthcare:oncology", "specialty", None),
        ("oncology_patient_rights", "Oncology Patient Rights", "clinical", "oncology", "healthcare:oncology", "specialty", None),
        # Medical Compliance (17)
        ("health_it", "Health IT & Interoperability", "clinical", "medical_compliance", "healthcare", "health_specs", 6),
        ("quality_reporting", "Quality Reporting", "reporting", "medical_compliance", "healthcare", "health_specs", 7),
        ("cybersecurity", "Cybersecurity", "safety", "medical_compliance", "healthcare", "health_specs", 8),
        ("environmental_safety", "Environmental Safety", "safety", "medical_compliance", "healthcare", "health_specs", 9),
        ("pharmacy_drugs", "Pharmacy & Controlled Substances", "clinical", "medical_compliance", "healthcare:pharmacy", "health_specs", 12),
        ("payer_relations", "Payer Relations", "billing", "medical_compliance", "healthcare:managed_care", "health_specs", 13),
        ("reproductive_behavioral", "Reproductive & Behavioral Health", "clinical", "medical_compliance", "healthcare:behavioral_health", "health_specs", 14),
        ("pediatric_vulnerable", "Pediatric & Vulnerable Populations", "clinical", "medical_compliance", "healthcare:pediatric", "health_specs", 15),
        ("telehealth", "Telehealth & Digital Health", "clinical", "medical_compliance", "healthcare:telehealth", "health_specs", 16),
        ("medical_devices", "Medical Device Safety", "safety", "medical_compliance", "healthcare:devices", "health_specs", 17),
        ("transplant_organ", "Transplant & Organ Procurement", "clinical", "medical_compliance", "healthcare:transplant", "health_specs", 18),
        ("antitrust", "Healthcare Antitrust", "corporate_integrity", "medical_compliance", "healthcare", "health_specs", 19),
        ("tax_exempt", "Tax-Exempt Compliance", "billing", "medical_compliance", "healthcare:nonprofit", "health_specs", 20),
        ("language_access", "Language Access & Civil Rights", "clinical", "medical_compliance", "healthcare", "health_specs", 21),
        ("records_retention", "Records Retention", "clinical", "medical_compliance", "healthcare", "health_specs", 22),
        ("marketing_comms", "Marketing & Communications", "corporate_integrity", "medical_compliance", "healthcare", "health_specs", 23),
        ("emerging_regulatory", "Emerging Regulatory", "safety", "medical_compliance", "healthcare", "health_specs", 25),
    ]

    for i, (slug, name, domain, group, industry_tag, research_mode, docx_section) in enumerate(categories):
        docx_val = "NULL" if docx_section is None else str(docx_section)
        industry_val = "NULL" if not industry_tag else f"'{industry_tag}'"
        op.execute(f"""
            INSERT INTO compliance_categories (slug, name, domain, "group", industry_tag, research_mode, docx_section, sort_order)
            VALUES ('{slug}', '{name}', '{domain}', '{group}', {industry_val}, '{research_mode}', {docx_val}, {i})
        """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS compliance_categories")
    op.execute("DROP TYPE IF EXISTS governance_source_enum")
    op.execute("DROP TYPE IF EXISTS category_domain_enum")
    op.execute("DROP TYPE IF EXISTS employee_jurisdiction_rel_type_enum")
    op.execute("DROP TYPE IF EXISTS change_source_enum")
    op.execute("DROP TYPE IF EXISTS source_tier_enum")
    op.execute("DROP TYPE IF EXISTS requirement_status_enum")
    op.execute("DROP TYPE IF EXISTS precedence_rule_status_enum")
    op.execute("DROP TYPE IF EXISTS precedence_type_enum")
    op.execute("DROP TYPE IF EXISTS jurisdiction_level_enum")
