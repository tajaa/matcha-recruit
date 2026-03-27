"""add 31 missing healthcare regulation key definitions

Revision ID: zb3c4d5e6f7g
Revises: x9y0z1a2b3c4
Create Date: 2026-03-26
"""

from alembic import op

revision = "zb3c4d5e6f7g"
down_revision = "za2b3c4d5e6f"
branch_labels = None
depends_on = None

KEYS = [
    # billing_integrity
    ("billing_integrity", "340b_drug_pricing_compliance", "340B Drug Pricing Program Compliance", "HRSA 340B program: contract pharmacy rules, duplicate discount prohibition, manufacturer obligations, covered entity eligibility.", "HRSA / OPA", "High"),
    ("billing_integrity", "surprise_billing_state_laws", "State Surprise Billing Protections", "State laws exceeding No Surprises Act: broader provider types, lower thresholds, additional patient protections, state IDR processes.", "State DOI / AG", "High"),
    ("billing_integrity", "medicare_advantage_billing", "Medicare Advantage Billing & Encounter Data", "MA plan-specific billing rules, encounter data submission, risk adjustment coding compliance, MLR requirements.", "CMS", "Moderate"),
    ("billing_integrity", "medicaid_managed_care_billing", "Medicaid Managed Care Billing Requirements", "State Medicaid MCO billing rules, prior authorization, timely filing, state-specific claim adjudication standards.", "CMS / State Medicaid", "High"),
    ("billing_integrity", "charity_care_financial_assistance", "Charity Care & Financial Assistance Policies", "IRS 501(r) financial assistance requirements plus state charity care mandates (NJ Charity Care Act, IL Hospital Uninsured Patient Discount Act).", "IRS / State", "High"),

    # clinical_safety
    ("clinical_safety", "blood_bank_transfusion_safety", "Blood Bank & Transfusion Safety", "AABB standards, FDA blood establishment registration, state blood safety laws, transfusion reaction reporting.", "FDA / AABB / State", "Moderate"),
    ("clinical_safety", "surgical_safety_protocols", "Surgical Safety Protocols & Universal Protocol", "WHO Surgical Safety Checklist, Joint Commission Universal Protocol, time-out requirements, wrong-site surgery prevention.", "Joint Commission / CMS", "Moderate"),
    ("clinical_safety", "patient_identification_standards", "Patient Identification Standards", "Two-patient-identifier requirements (Joint Commission NPSG.01.01.01), wristband standards, patient matching protocols.", "Joint Commission / CMS", "Low/None"),
    ("clinical_safety", "diagnostic_error_reporting", "Diagnostic Error Reporting & Safety", "State requirements for diagnostic error disclosure, cognitive bias mitigation programs, diagnostic safety culture.", "State Health Depts / AHRQ", "High"),
    ("clinical_safety", "nursing_home_ltc_safety", "Nursing Home & Long-Term Care Safety Standards", "SNF/LTC-specific CMS requirements (42 CFR 483), state survey standards, staffing minimums, abuse prevention.", "CMS / State Health Depts", "High"),
    ("clinical_safety", "radiation_therapy_safety", "Radiation Therapy Safety & QA", "Linear accelerator safety, treatment planning QA, NRC/state agreement requirements for therapeutic radiation, medical physicist oversight.", "NRC / State / FDA", "High"),

    # hipaa_privacy
    ("hipaa_privacy", "information_blocking", "Information Blocking (21st Century Cures Act)", "ONC information blocking rules prohibiting practices that interfere with access/exchange/use of EHI. Applies to providers, health IT developers, HIEs.", "ONC / HHS", "Moderate"),
    ("hipaa_privacy", "patient_right_of_access", "Patient Right of Access (45 CFR 164.524)", "HIPAA right of access requirements, state-specific access timelines, OCR enforcement priority, fee limitations for copies.", "HHS OCR / State", "High"),
    ("hipaa_privacy", "research_data_use_agreements", "Research Data Use Agreements & De-identification", "Limited data set DUAs, de-identification standards (Safe Harbor vs Expert Determination), data sharing for research purposes.", "HHS OCR / OHRP", "Moderate"),

    # healthcare_workforce
    ("healthcare_workforce", "locum_tenens_temporary_staffing", "Locum Tenens & Temporary Staffing Requirements", "Temporary/locum credentialing rules, state-specific compact licenses, CMS 60-day locum tenens rule, staffing agency regulations.", "CMS / State Boards", "High"),
    ("healthcare_workforce", "physician_noncompete_restrictions", "Physician Non-Compete Restrictions", "FTC noncompete rule (if upheld), state physician noncompete laws (CA ban, IL/MA restrictions, CO limitations).", "FTC / State", "High"),
    ("healthcare_workforce", "healthcare_worker_vaccination_requirements", "Healthcare Worker Vaccination Requirements", "CMS COVID vaccination mandate, state-specific healthcare worker immunization requirements (flu, HepB, MMR, varicella).", "CMS / State Health Depts", "High"),
    ("healthcare_workforce", "safe_staffing_legislation", "Safe Staffing Legislation", "State safe staffing laws beyond nurse ratios: CA mandated ratios, MA ballot measure, OR/WA staffing committees, minimum staffing standards.", "State Legislature / CMS", "High"),

    # reimbursement_vbc
    ("reimbursement_vbc", "mssp_aco_compliance", "Medicare Shared Savings Program (MSSP/ACO) Compliance", "ACO participation requirements, beneficiary assignment rules, quality benchmarks, shared savings/losses calculations.", "CMS", "Low/None"),
    ("reimbursement_vbc", "medicaid_supplemental_payments", "Medicaid Supplemental Payments (DSH/UPL/Directed)", "State Medicaid DSH allotments, upper payment limits, directed payments, provider taxes and assessments.", "CMS / State Medicaid", "High"),
    ("reimbursement_vbc", "episode_based_payment", "Episode-Based Payment Models", "CMS episode-based models (TEAM, mandatory bundled payments), state Medicaid episode programs, gainsharing arrangements.", "CMS", "Moderate"),
    ("reimbursement_vbc", "drug_rebate_program", "Medicaid Drug Rebate Program (MDRP)", "Manufacturer rebate obligations, best price calculations, covered outpatient drug definitions, state supplemental rebates.", "CMS / State Medicaid", "Moderate"),
    ("reimbursement_vbc", "site_neutral_payment", "Site-Neutral Payment Policies", "CMS site-neutral payment rules, off-campus PBD billing restrictions, 340B payment adjustments, excepted vs non-excepted status.", "CMS", "Moderate"),

    # emergency_preparedness
    ("emergency_preparedness", "cybersecurity_incident_response", "Healthcare Cybersecurity Incident Response", "HC3 advisories, CISA healthcare alerts, ransomware playbooks, state breach notification timelines for healthcare.", "CISA / HC3 / State", "High"),
    ("emergency_preparedness", "continuity_of_operations", "Continuity of Operations (COOP) Planning", "Essential function identification, alternate facility plans, devolution planning, recovery time objectives for healthcare.", "CMS / FEMA / State", "Moderate"),

    # state_licensing
    ("state_licensing", "ambulatory_surgery_center_licensing", "Ambulatory Surgery Center (ASC) Licensing", "ASC-specific state licensure requirements separate from hospital, Medicare ASC Conditions for Coverage, accreditation standards.", "State Health Depts / CMS", "High"),
    ("state_licensing", "home_health_hospice_licensing", "Home Health & Hospice Agency Licensing", "Home health agency and hospice state licensing, CMS Conditions of Participation (42 CFR 484), surveyor standards.", "State Health Depts / CMS", "High"),
    ("state_licensing", "behavioral_health_facility_licensing", "Behavioral Health Facility Licensing", "State behavioral health and substance use disorder facility licensing, separate from general hospital licensure, SAMHSA standards.", "State Health Depts / SAMHSA", "High"),
    ("state_licensing", "clinical_laboratory_licensing", "Clinical Laboratory State Licensing", "State lab licensing beyond federal CLIA (NY CLEP, CA, FL have their own programs), proficiency testing, personnel requirements.", "State Health Depts / CMS", "High"),

    # corporate_integrity
    ("corporate_integrity", "compliance_risk_assessment", "Compliance Risk Assessment", "Annual compliance risk assessment per OIG guidance, board-level risk reporting, enterprise risk management integration.", "OIG / Accreditors", "Moderate"),
    ("corporate_integrity", "physician_arrangement_tracking", "Physician Arrangement & FMV Tracking", "Fair market value documentation, physician compensation tracking, Stark/AKS arrangement management, centralized tracking systems.", "OIG / CMS", "Moderate"),
]


def upgrade():
    for cat_slug, key, name, desc, agency, variance in KEYS:
        op.execute(f"""
            INSERT INTO regulation_key_definitions
                (id, key, category_slug, category_id, name, description,
                 enforcing_agency, state_variance, base_weight,
                 staleness_warning_days, staleness_critical_days, staleness_expired_days,
                 applies_to_levels, created_at, updated_at)
            VALUES (
                gen_random_uuid(),
                '{key}',
                '{cat_slug}',
                (SELECT id FROM compliance_categories WHERE slug = '{cat_slug}' LIMIT 1),
                '{name.replace("'", "''")}',
                '{desc.replace("'", "''")}',
                '{agency.replace("'", "''")}',
                '{variance}',
                1.0,
                90, 180, 365,
                '{{state,city}}',
                NOW(), NOW()
            )
            ON CONFLICT (category_slug, key) DO NOTHING
        """)


def downgrade():
    keys_list = ", ".join(f"'{k[1]}'" for k in KEYS)
    op.execute(f"DELETE FROM regulation_key_definitions WHERE key IN ({keys_list})")
