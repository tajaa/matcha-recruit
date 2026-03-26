"""Seed expansion key definitions: FDA lifecycle, reimbursement/VBC,
quality systems, supply chain, and expanded medical_devices/cybersecurity/environmental.

Adds 4 new compliance_categories and ~63 new regulation_key_definitions.

Revision ID: u6v7w8x9y0z1
Revises: 2c12cf3aaab4
Create Date: 2026-03-25
"""

from alembic import op
from sqlalchemy import text

revision = "u6v7w8x9y0z1"
down_revision = "2c12cf3aaab4"
branch_labels = None
depends_on = None


def upgrade():
    _seed_new_categories()
    _seed_expansion_keys()


def downgrade():
    op.execute("""
        DELETE FROM regulation_key_definitions
        WHERE category_slug IN ('fda_lifecycle', 'reimbursement_vbc', 'quality_systems', 'supply_chain')
    """)
    op.execute("""
        DELETE FROM compliance_categories
        WHERE slug IN ('fda_lifecycle', 'reimbursement_vbc', 'quality_systems', 'supply_chain')
    """)


def _seed_new_categories():
    # Add new domain enum values
    for val in ('life_sciences', 'healthcare', 'manufacturing', 'quality'):
        op.execute(f"""
            DO $$ BEGIN
                ALTER TYPE category_domain_enum ADD VALUE IF NOT EXISTS '{val}';
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$
        """)

    # Need to commit so the new enum values are visible
    op.execute("COMMIT")
    op.execute("BEGIN")

    op.execute("""
        INSERT INTO compliance_categories (slug, name, description, domain, "group", industry_tag, sort_order)
        VALUES
            ('fda_lifecycle', 'FDA Pre/Post-Market Lifecycle',
             'Drug and biologic approval pathways, post-market surveillance, pharmacovigilance, REMS, FDA 483 observations',
             'life_sciences', 'life_sciences', 'biotech:pharma', 700),
            ('reimbursement_vbc', 'Reimbursement & Value-Based Care',
             'CMS quality programs, payment models, MIPS/APMs, bundled payments, price transparency, No Surprises Act',
             'clinical', 'healthcare', 'healthcare:provider', 140),
            ('quality_systems', 'Quality Management Systems',
             'ISO certifications (13485, 9001, 15189, 14001), CLIA, CAP, Joint Commission accreditation',
             'manufacturing', 'manufacturing', 'manufacturing:quality', 900),
            ('supply_chain', 'Supply Chain & Procurement',
             'Conflict minerals, REACH/RoHS, forced labor prevention, supplier audit, anti-bribery, green procurement',
             'manufacturing', 'manufacturing', 'manufacturing:procurement', 910)
        ON CONFLICT (slug) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description
    """)


def _seed_expansion_keys():
    """Seed ~63 new key definitions using the Python registry for metadata."""
    from app.core.compliance_registry import REGULATIONS, CATEGORY_MAP

    reg_lookup = {(r.category, r.key): r for r in REGULATIONS}

    # All new keys to seed: (category_slug, key)
    _NEW_KEYS = {
        # fda_lifecycle (12)
        ("fda_lifecycle", "nda_bla_submission"),
        ("fda_lifecycle", "anda_generic_pathway"),
        ("fda_lifecycle", "fda_breakthrough_accelerated"),
        ("fda_lifecycle", "fda_priority_review"),
        ("fda_lifecycle", "post_market_surveillance_faers"),
        ("fda_lifecycle", "pharmacovigilance_safety_reporting"),
        ("fda_lifecycle", "rems_lifecycle"),
        ("fda_lifecycle", "fda_483_observations"),
        ("fda_lifecycle", "product_labeling_pi_medication_guide"),
        ("fda_lifecycle", "pediatric_study_requirements"),
        ("fda_lifecycle", "orphan_drug_exclusivity"),
        ("fda_lifecycle", "patent_exclusivity_orange_book"),
        # reimbursement_vbc (10)
        ("reimbursement_vbc", "macra_mips_reporting"),
        ("reimbursement_vbc", "apm_participation"),
        ("reimbursement_vbc", "bundled_payment_compliance"),
        ("reimbursement_vbc", "cms_star_ratings"),
        ("reimbursement_vbc", "hedis_quality_measures"),
        ("reimbursement_vbc", "value_based_contract_requirements"),
        ("reimbursement_vbc", "drg_coding_compliance"),
        ("reimbursement_vbc", "price_transparency_rule"),
        ("reimbursement_vbc", "no_surprises_act"),
        ("reimbursement_vbc", "good_faith_estimates"),
        # quality_systems (9)
        ("quality_systems", "iso_13485_medical_devices"),
        ("quality_systems", "iso_9001_general_qms"),
        ("quality_systems", "iso_15189_clinical_labs"),
        ("quality_systems", "iso_14001_environmental"),
        ("quality_systems", "iso_45001_ohs"),
        ("quality_systems", "iso_27001_information_security"),
        ("quality_systems", "clia_lab_certification"),
        ("quality_systems", "cap_accreditation"),
        ("quality_systems", "joint_commission_accreditation"),
        # supply_chain (8)
        ("supply_chain", "conflict_minerals_dodd_frank"),
        ("supply_chain", "reach_regulation"),
        ("supply_chain", "rohs_directive"),
        ("supply_chain", "uyghur_forced_labor_prevention"),
        ("supply_chain", "supplier_qualification_audit"),
        ("supply_chain", "track_trace_serialization"),
        ("supply_chain", "gpp_green_procurement"),
        ("supply_chain", "antibribery_fcpa_uk_bribery"),
        # medical_devices expansion (8)
        ("medical_devices", "510k_pma_de_novo"),
        ("medical_devices", "design_controls_21cfr820"),
        ("medical_devices", "device_master_record"),
        ("medical_devices", "unique_device_identification_udi"),
        ("medical_devices", "device_establishment_registration"),
        ("medical_devices", "software_as_medical_device"),
        ("medical_devices", "cybersecurity_medical_devices"),
        ("medical_devices", "human_factors_usability"),
        # cybersecurity expansion (8)
        ("cybersecurity", "nist_csf_implementation"),
        ("cybersecurity", "soc2_type2_compliance"),
        ("cybersecurity", "gdpr_health_data"),
        ("cybersecurity", "fda_device_cybersecurity_guidance"),
        ("cybersecurity", "patch_act_medical_devices"),
        ("cybersecurity", "state_consumer_privacy_acts"),
        ("cybersecurity", "incident_response_plan"),
        ("cybersecurity", "third_party_risk_management"),
        # environmental_compliance expansion (8)
        ("environmental_compliance", "tsca_toxic_substances"),
        ("environmental_compliance", "cercla_superfund_liability"),
        ("environmental_compliance", "clean_air_act_title_v"),
        ("environmental_compliance", "epa_risk_management_program"),
        ("environmental_compliance", "epcra_tri_reporting"),
        ("environmental_compliance", "rcra_hazardous_waste"),
        ("environmental_compliance", "clean_water_act_npdes"),
        ("environmental_compliance", "spcc_oil_spill_prevention"),
    }

    conn = op.get_bind()

    cat_rows = conn.execute(text("SELECT id, slug FROM compliance_categories")).fetchall()
    cat_id_map = {r[1]: str(r[0]) for r in cat_rows}

    existing = conn.execute(text("SELECT category_slug, key FROM regulation_key_definitions")).fetchall()
    existing_set = {(r[0], r[1]) for r in existing}

    inserted = 0
    for cat_slug, key in sorted(_NEW_KEYS):
        if (cat_slug, key) in existing_set:
            continue

        cat_id = cat_id_map.get(cat_slug)
        if not cat_id:
            continue

        reg = reg_lookup.get((cat_slug, key))
        if reg:
            name = reg.name.replace("'", "''")
            desc = (reg.description or "").replace("'", "''")
            agency = (reg.enforcing_agency or "").replace("'", "''")
            variance = reg.state_variance
            freq = (reg.update_frequency or "").replace("'", "''")
        else:
            name = key.replace("_", " ").title().replace("'", "''")
            desc = ""
            agency = ""
            variance = "Moderate"
            freq = ""

        weight = 1.5 if variance == "High" else 1.0

        op.execute(f"""
            INSERT INTO regulation_key_definitions
                (key, category_slug, category_id, name, description,
                 enforcing_agency, state_variance, base_weight, update_frequency,
                 staleness_warning_days, staleness_critical_days, staleness_expired_days)
            VALUES (
                '{key}', '{cat_slug}', '{cat_id}',
                '{name}', '{desc}',
                '{agency}', '{variance}', {weight}, '{freq}',
                90, 180, 365
            )
            ON CONFLICT (category_slug, key) DO NOTHING
        """)
        inserted += 1

    print(f"Seeded {inserted} new key definitions")
