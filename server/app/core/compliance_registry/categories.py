from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple  # noqa: F401

from app.core.compliance_registry._types import ComplianceCategoryDef




# ---------------------------------------------------------------------------
# CATEGORIES  (79 entries)
# ---------------------------------------------------------------------------

CATEGORIES: List[ComplianceCategoryDef] = [
    # ── Labor (28) ─────────────────────────────────────────────────────────
    ComplianceCategoryDef(
        key="minimum_wage", label="Minimum Wage", short_label="Min Wage",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="overtime", label="Overtime", short_label="OT",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="sick_leave", label="Sick Leave", short_label="Sick",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="meal_breaks", label="Meal & Rest Breaks", short_label="Meals",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="pay_frequency", label="Pay Frequency", short_label="Pay Freq",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="final_pay", label="Final Pay", short_label="Final Pay",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="minor_work_permit", label="Minor Work Permits", short_label="Minor",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="scheduling_reporting", label="Scheduling & Reporting Time", short_label="Sched",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="leave", label="Leave", short_label="Leave",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="workplace_safety", label="Workplace Safety", short_label="Safety",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="workers_comp", label="Workers\' Comp", short_label="Workers\' Comp",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="anti_discrimination", label="Anti-Discrimination", short_label="Anti-Discrim",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="employee_classification", label="Employee Classification", short_label="Classification",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="i9_everify", label="I-9 & E-Verify", short_label="I-9/E-Verify",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="warn_act", label="WARN Act (Plant Closing & Layoffs)", short_label="WARN Act",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="cobra", label="COBRA & Health Coverage Continuation", short_label="COBRA",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="eeo_reporting", label="EEO Reporting & Affirmative Action", short_label="EEO/AA",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="pay_transparency", label="Pay Transparency & Equity", short_label="Pay Transparency",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="background_checks", label="Background Checks & Ban the Box", short_label="Background Checks",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="drug_testing", label="Drug & Alcohol Testing", short_label="Drug Testing",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="non_compete", label="Non-Compete & Restrictive Covenants", short_label="Non-Compete",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="whistleblower", label="Whistleblower Protections", short_label="Whistleblower",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="userra", label="USERRA (Military Reemployment)", short_label="USERRA",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="garnishment", label="Wage Garnishment & Attachment", short_label="Garnishment",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="erisa_benefits", label="ERISA & Benefits Compliance", short_label="ERISA",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="pregnancy_accommodation", label="Pregnancy & Lactation Accommodation", short_label="Pregnancy Accom",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="equal_pay", label="Equal Pay Act & Pay Equity", short_label="Equal Pay",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="nlra_organizing", label="NLRA & Union Organizing Rights", short_label="NLRA/Union",
        group="labor", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),

    # ── Supplementary labor (3) ────────────────────────────────────────────
    ComplianceCategoryDef(
        key="business_license", label="Business License", short_label="Biz License",
        group="supplementary", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="tax_rate", label="Tax Rate", short_label="Tax Rate",
        group="supplementary", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="posting_requirements", label="Posting Requirements", short_label="Posting Reqs",
        group="supplementary", industry_tag="", research_mode="default_sweep", docx_section=None,
    ),

    # ── Healthcare (8) ─────────────────────────────────────────────────────
    ComplianceCategoryDef(
        key="hipaa_privacy", label="HIPAA Privacy & Security", short_label="HIPAA Privacy",
        group="healthcare", industry_tag="healthcare", research_mode="specialty", docx_section=1,
    ),
    ComplianceCategoryDef(
        key="billing_integrity", label="Billing & Financial Integrity", short_label="Billing Integrity",
        group="healthcare", industry_tag="healthcare", research_mode="specialty", docx_section=2,
    ),
    ComplianceCategoryDef(
        key="clinical_safety", label="Clinical & Patient Safety", short_label="Clinical Safety",
        group="healthcare", industry_tag="healthcare", research_mode="specialty", docx_section=3,
    ),
    ComplianceCategoryDef(
        key="healthcare_workforce", label="Healthcare Workforce", short_label="HC Workforce",
        group="healthcare", industry_tag="healthcare", research_mode="specialty", docx_section=4,
    ),
    ComplianceCategoryDef(
        key="corporate_integrity", label="Corporate Integrity & Ethics", short_label="Corp Integrity",
        group="healthcare", industry_tag="healthcare", research_mode="specialty", docx_section=5,
    ),
    ComplianceCategoryDef(
        key="research_consent", label="Research & Informed Consent", short_label="Research Consent",
        group="healthcare", industry_tag="healthcare", research_mode="specialty", docx_section=11,
    ),
    ComplianceCategoryDef(
        key="state_licensing", label="State Licensing & Scope", short_label="State Licensing",
        group="healthcare", industry_tag="healthcare", research_mode="specialty", docx_section=24,
    ),
    ComplianceCategoryDef(
        key="emergency_preparedness", label="Emergency Preparedness", short_label="Emergency Prep",
        group="healthcare", industry_tag="healthcare", research_mode="specialty", docx_section=10,
    ),
    ComplianceCategoryDef(
        key="reimbursement_vbc", label="Reimbursement & Value-Based Care", short_label="Reimbursement/VBC",
        group="healthcare", industry_tag="healthcare:provider", research_mode="health_specs", docx_section=None,
    ),

    # ── Oncology (5) ───────────────────────────────────────────────────────
    ComplianceCategoryDef(
        key="radiation_safety", label="Radiation Safety", short_label="Radiation Safety",
        group="oncology", industry_tag="healthcare:oncology", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="chemotherapy_handling", label="Chemotherapy & Hazardous Drugs", short_label="Chemo Handling",
        group="oncology", industry_tag="healthcare:oncology", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="tumor_registry", label="Tumor Registry Reporting", short_label="Tumor Registry",
        group="oncology", industry_tag="healthcare:oncology", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="oncology_clinical_trials", label="Oncology Clinical Trials", short_label="Onc Trials",
        group="oncology", industry_tag="healthcare:oncology", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="oncology_patient_rights", label="Oncology Patient Rights", short_label="Onc Patient Rights",
        group="oncology", industry_tag="healthcare:oncology", research_mode="specialty", docx_section=None,
    ),

    # ── Medical Compliance (17) ────────────────────────────────────────────
    ComplianceCategoryDef(
        key="health_it", label="Health IT & Interoperability", short_label="Health IT",
        group="medical_compliance", industry_tag="healthcare", research_mode="health_specs", docx_section=6,
    ),
    ComplianceCategoryDef(
        key="quality_reporting", label="Quality Reporting", short_label="Quality Reporting",
        group="medical_compliance", industry_tag="healthcare", research_mode="health_specs", docx_section=7,
    ),
    ComplianceCategoryDef(
        key="cybersecurity", label="Cybersecurity", short_label="Cybersecurity",
        group="medical_compliance", industry_tag="healthcare", research_mode="health_specs", docx_section=8,
    ),
    ComplianceCategoryDef(
        key="environmental_safety", label="Environmental Safety", short_label="Env Safety",
        group="medical_compliance", industry_tag="healthcare", research_mode="health_specs", docx_section=9,
    ),
    ComplianceCategoryDef(
        key="pharmacy_drugs", label="Pharmacy & Controlled Substances", short_label="Pharmacy",
        group="medical_compliance", industry_tag="healthcare:pharmacy", research_mode="health_specs", docx_section=12,
    ),
    ComplianceCategoryDef(
        key="payer_relations", label="Payer Relations", short_label="Payer Relations",
        group="medical_compliance", industry_tag="healthcare:managed_care", research_mode="health_specs", docx_section=13,
    ),
    ComplianceCategoryDef(
        key="reproductive_behavioral", label="Reproductive & Behavioral Health", short_label="Repro & Behavioral",
        group="medical_compliance", industry_tag="healthcare:behavioral_health", research_mode="health_specs", docx_section=14,
    ),
    ComplianceCategoryDef(
        key="pediatric_vulnerable", label="Pediatric & Vulnerable Populations", short_label="Pediatric & Vulnerable",
        group="medical_compliance", industry_tag="healthcare:pediatric", research_mode="health_specs", docx_section=15,
    ),
    ComplianceCategoryDef(
        key="telehealth", label="Telehealth & Digital Health", short_label="Telehealth",
        group="medical_compliance", industry_tag="healthcare:telehealth", research_mode="health_specs", docx_section=16,
    ),
    ComplianceCategoryDef(
        key="medical_devices", label="Medical Device Safety", short_label="Medical Devices",
        group="medical_compliance", industry_tag="healthcare:devices", research_mode="health_specs", docx_section=17,
    ),
    ComplianceCategoryDef(
        key="transplant_organ", label="Transplant & Organ Procurement", short_label="Transplant",
        group="medical_compliance", industry_tag="healthcare:transplant", research_mode="health_specs", docx_section=18,
    ),
    ComplianceCategoryDef(
        key="antitrust", label="Healthcare Antitrust", short_label="Antitrust",
        group="medical_compliance", industry_tag="healthcare", research_mode="health_specs", docx_section=19,
    ),
    ComplianceCategoryDef(
        key="tax_exempt", label="Tax-Exempt Compliance", short_label="Tax-Exempt",
        group="medical_compliance", industry_tag="healthcare:nonprofit", research_mode="health_specs", docx_section=20,
    ),
    ComplianceCategoryDef(
        key="language_access", label="Language Access & Civil Rights", short_label="Language Access",
        group="medical_compliance", industry_tag="healthcare", research_mode="health_specs", docx_section=21,
    ),
    ComplianceCategoryDef(
        key="records_retention", label="Records Retention", short_label="Records Retention",
        group="medical_compliance", industry_tag="healthcare", research_mode="health_specs", docx_section=22,
    ),
    ComplianceCategoryDef(
        key="marketing_comms", label="Marketing & Communications", short_label="Marketing",
        group="medical_compliance", industry_tag="healthcare", research_mode="health_specs", docx_section=23,
    ),
    ComplianceCategoryDef(
        key="emerging_regulatory", label="Emerging Regulatory", short_label="Emerging",
        group="medical_compliance", industry_tag="healthcare", research_mode="health_specs", docx_section=25,
    ),

    # ── Life Sciences (6) ────────────────────────────────────────────────
    ComplianceCategoryDef(
        key="gmp_manufacturing", label="GMP Manufacturing", short_label="GMP",
        group="life_sciences", industry_tag="biotech", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="glp_nonclinical", label="Good Laboratory Practice", short_label="GLP",
        group="life_sciences", industry_tag="biotech", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="clinical_trials_gcp", label="Clinical Trials & GCP", short_label="GCP Trials",
        group="life_sciences", industry_tag="biotech", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="drug_supply_chain", label="Drug Supply Chain (DSCSA)", short_label="DSCSA",
        group="life_sciences", industry_tag="biotech", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="sunshine_open_payments", label="Sunshine Act / Open Payments", short_label="Sunshine Act",
        group="life_sciences", industry_tag="biotech", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="biosafety_lab", label="Biosafety & Lab Safety", short_label="Biosafety",
        group="life_sciences", industry_tag="biotech", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="fda_lifecycle", label="FDA Pre/Post-Market Lifecycle", short_label="FDA Lifecycle",
        group="life_sciences", industry_tag="biotech:pharma", research_mode="specialty", docx_section=None,
    ),

    # ── Manufacturing (8) ────────────────────────────────────────────────────
    ComplianceCategoryDef(
        key="process_safety", label="Process Safety Management", short_label="PSM",
        group="manufacturing", industry_tag="manufacturing", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="environmental_compliance", label="Environmental & Emissions", short_label="Environ",
        group="manufacturing", industry_tag="manufacturing", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="chemical_safety", label="Chemical & Hazardous Materials", short_label="Chemical",
        group="manufacturing", industry_tag="manufacturing", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="machine_safety", label="Machine & Equipment Safety", short_label="Machine",
        group="manufacturing", industry_tag="manufacturing", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="industrial_hygiene", label="Industrial Hygiene & Exposure", short_label="IH",
        group="manufacturing", industry_tag="manufacturing", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="trade_compliance", label="Import/Export & Trade", short_label="Trade",
        group="manufacturing", industry_tag="manufacturing", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="product_safety", label="Product Safety & Standards", short_label="Product",
        group="manufacturing", industry_tag="manufacturing", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="labor_relations", label="Labor Relations", short_label="Labor Rel",
        group="manufacturing", industry_tag="manufacturing", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="quality_systems", label="Quality Management Systems", short_label="QMS",
        group="manufacturing", industry_tag="manufacturing:quality", research_mode="specialty", docx_section=None,
    ),
    ComplianceCategoryDef(
        key="supply_chain", label="Supply Chain & Procurement", short_label="Supply Chain",
        group="manufacturing", industry_tag="manufacturing:procurement", research_mode="specialty", docx_section=None,
    ),
]


# ---------------------------------------------------------------------------
# CATEGORY_DOMAIN_MAP — maps category key → CategoryDomain enum value
# Used for seeding the compliance_categories table in migrations.
# ---------------------------------------------------------------------------

CATEGORY_DOMAIN_MAP: Dict[str, str] = {
    # Labor + supplementary → labor
    "minimum_wage": "labor", "overtime": "labor", "sick_leave": "labor",
    "meal_breaks": "labor", "pay_frequency": "labor", "final_pay": "labor",
    "minor_work_permit": "labor", "scheduling_reporting": "labor",
    "leave": "labor", "workplace_safety": "labor", "workers_comp": "labor",
    "anti_discrimination": "labor", "business_license": "labor",
    "tax_rate": "labor", "posting_requirements": "labor",
    # Healthcare → per-category domains
    "hipaa_privacy": "privacy", "billing_integrity": "billing",
    "clinical_safety": "clinical", "healthcare_workforce": "clinical",
    "corporate_integrity": "corporate_integrity",
    "research_consent": "clinical", "state_licensing": "licensing",
    "emergency_preparedness": "emergency",
    # Oncology
    "radiation_safety": "safety", "chemotherapy_handling": "safety",
    "tumor_registry": "reporting", "oncology_clinical_trials": "clinical",
    "oncology_patient_rights": "clinical",
    # Medical compliance
    "health_it": "clinical", "quality_reporting": "reporting",
    "cybersecurity": "safety", "environmental_safety": "safety",
    "pharmacy_drugs": "clinical", "payer_relations": "billing",
    "reproductive_behavioral": "clinical", "pediatric_vulnerable": "clinical",
    "telehealth": "clinical", "medical_devices": "safety",
    "transplant_organ": "clinical", "antitrust": "corporate_integrity",
    "tax_exempt": "billing", "language_access": "clinical",
    "records_retention": "clinical", "marketing_comms": "corporate_integrity",
    "emerging_regulatory": "safety",
    # Life Sciences
    "gmp_manufacturing": "safety", "glp_nonclinical": "safety",
    "clinical_trials_gcp": "clinical", "drug_supply_chain": "safety",
    "sunshine_open_payments": "corporate_integrity", "biosafety_lab": "safety",
    "fda_lifecycle": "safety",
    # Healthcare expansion
    "reimbursement_vbc": "billing",
    # Manufacturing expansion
    "quality_systems": "safety", "supply_chain": "safety",
}


