from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple  # noqa: F401

from app.core.compliance_registry._types import ComplianceCategoryDef, RegulationDef
from app.core.compliance_registry.categories import CATEGORIES
from app.core.compliance_registry.regulations import REGULATIONS


# ---------------------------------------------------------------------------
# Derived exports  (computed at module level)
# ---------------------------------------------------------------------------

# Category lookups
CATEGORY_MAP: Dict[str, ComplianceCategoryDef] = {c.key: c for c in CATEGORIES}
CATEGORY_KEYS: FrozenSet[str] = frozenset(c.key for c in CATEGORIES)

# Group sets
LABOR_CATEGORIES: FrozenSet[str] = frozenset(
    c.key for c in CATEGORIES if c.group == "labor"
)
SUPPLEMENTARY_CATEGORIES: FrozenSet[str] = frozenset(
    c.key for c in CATEGORIES if c.group == "supplementary"
)
HEALTHCARE_CATEGORIES: FrozenSet[str] = frozenset(
    c.key for c in CATEGORIES if c.group == "healthcare"
)
ONCOLOGY_CATEGORIES: FrozenSet[str] = frozenset(
    c.key for c in CATEGORIES if c.group == "oncology"
)
MEDICAL_COMPLIANCE_CATEGORIES: FrozenSet[str] = frozenset(
    c.key for c in CATEGORIES if c.group == "medical_compliance"
)
LIFE_SCIENCES_CATEGORIES: FrozenSet[str] = frozenset(
    c.key for c in CATEGORIES if c.group == "life_sciences"
)
MANUFACTURING_CATEGORIES: FrozenSet[str] = frozenset(
    c.key for c in CATEGORIES if c.group == "manufacturing"
)

# Research mode sets
SPECIALTY_CATEGORIES: FrozenSet[str] = frozenset(
    c.key for c in CATEGORIES if c.research_mode == "specialty"
)
HEALTH_SPECS_CATEGORIES: FrozenSet[str] = frozenset(
    c.key for c in CATEGORIES if c.research_mode == "health_specs"
)
DEFAULT_RESEARCH_CATEGORIES: List[str] = sorted(
    c.key for c in CATEGORIES if c.research_mode == "default_sweep"
)

# Label dicts
CATEGORY_LABELS: Dict[str, str] = {c.key: c.label for c in CATEGORIES}
CATEGORY_SHORT_LABELS: Dict[str, str] = {c.key: c.short_label for c in CATEGORIES}

# Industry tags (only non-empty)
INDUSTRY_TAGS: Dict[str, str] = {
    c.key: c.industry_tag for c in CATEGORIES if c.industry_tag
}

# Regulation lookups
REGULATION_MAP: Dict[str, RegulationDef] = {r.key: r for r in REGULATIONS}
REGULATIONS_BY_CATEGORY: Dict[str, List[RegulationDef]] = {}
for _r in REGULATIONS:
    REGULATIONS_BY_CATEGORY.setdefault(_r.category, []).append(_r)
EXPECTED_REGULATION_KEYS: Dict[str, FrozenSet[str]] = {
    cat: frozenset(r.key for r in regs)
    for cat, regs in REGULATIONS_BY_CATEGORY.items()
}

# Labor + supplementary categories don't have full RegulationDef objects but need
# stable keys for Gemini dedup. Add them directly.
_LABOR_REGULATION_KEYS: Dict[str, FrozenSet[str]] = {
    "minimum_wage": frozenset([
        "national_minimum_wage",
        "state_minimum_wage", "tipped_minimum_wage", "exempt_salary_threshold",
        # Sub-state regional tier (NY downstate). MUST be listed here, not only
        # as a RegulationDef: this dict REPLACES the RegulationDef-derived set
        # for its categories (see the update() below), so a key missing here is
        # an `invalid_key` tagging finding on every row that carries it.
        "exempt_salary_threshold_regional",
        "fast_food_minimum_wage", "healthcare_minimum_wage", "large_employer_minimum_wage",
        "small_employer_minimum_wage", "youth_minimum_wage", "tip_credit_prohibition",
        "local_minimum_wage",
    ]),
    "overtime": frozenset([
        "daily_weekly_overtime", "double_time", "seventh_day_overtime",
        "exempt_salary_threshold", "alternative_workweek", "healthcare_overtime",
        "mandatory_overtime_restrictions", "comp_time",
    ]),
    "leave": frozenset([
        "fmla", "state_family_leave", "state_paid_family_leave",
        "state_disability_insurance", "pregnancy_disability_leave",
        "paid_sick_leave", "bereavement_leave", "organ_donor_leave",
        "domestic_violence_leave", "jury_duty_leave", "military_leave",
        "voting_leave", "school_activity_leave", "reproductive_loss_leave",
        "bone_marrow_donor_leave",
    ]),
    "sick_leave": frozenset([
        "state_paid_sick_leave", "accrual_and_usage_caps", "local_sick_leave",
    ]),
    "meal_breaks": frozenset([
        "meal_break", "rest_break", "lactation_break",
        "on_duty_meal_agreement", "healthcare_meal_waiver", "missed_break_penalty",
    ]),
    "pay_frequency": frozenset([
        "standard_pay_frequency", "final_pay_termination", "final_pay_resignation",
        "exempt_monthly_pay", "payday_posting", "wage_notice",
    ]),
    "final_pay": frozenset([
        "final_pay_termination", "final_pay_resignation", "final_pay_layoff",
        "waiting_time_penalty",
    ]),
    "minor_work_permit": frozenset([
        "work_permit", "hour_limits_14_15", "hour_limits_16_17",
        "prohibited_occupations", "entertainment_permits", "recordkeeping",
    ]),
    "scheduling_reporting": frozenset([
        "reporting_time_pay", "predictive_scheduling", "split_shift_premium",
        "on_call_pay", "spread_of_hours",
    ]),
    "workplace_safety": frozenset([
        "osha_general_duty", "injury_illness_recordkeeping", "heat_illness_prevention",
        "workplace_violence_prevention", "hazard_communication",
    ]),
    "workers_comp": frozenset([
        "mandatory_coverage", "claim_filing", "return_to_work",
        "anti_retaliation", "posting_requirements",
    ]),
    "anti_discrimination": frozenset([
        "protected_classes", "pay_transparency", "salary_history_ban",
        "harassment_prevention_training", "reasonable_accommodation",
        "whistleblower_protection", "age_discrimination_adea",
        "genetic_information_gina",
    ]),
    # ── Federal-baseline categories (baseline_masterlist.py). These 12 labor
    # categories had no enumerated keys; the baseline master-list references
    # these, and baseline01 seeds regulation_key_definitions rows for them.
    # Non-focused categories (not in any INDUSTRY_CATEGORY_SET, no ≥0.85 profile
    # weight) → their completeness misses are `warn`, not `critical`, so widening
    # the vocabulary drops scores but does NOT flip onboarding readiness.
    "employee_classification": frozenset([
        "flsa_recordkeeping", "exempt_classification",
    ]),
    "pregnancy_accommodation": frozenset([
        "pregnancy_accommodation", "pump_act_lactation",
    ]),
    "equal_pay": frozenset(["federal_equal_pay"]),
    "warn_act": frozenset(["federal_warn_notice"]),
    "i9_everify": frozenset(["form_i9_verification"]),
    "erisa_benefits": frozenset(["spd_disclosure", "form_5500"]),
    "cobra": frozenset(["cobra_continuation"]),
    "nlra_organizing": frozenset(["protected_concerted_activity"]),
    "userra": frozenset(["userra_reemployment"]),
    "background_checks": frozenset([
        "fcra_disclosure_authorization", "adverse_action_process",
    ]),
    "eeo_reporting": frozenset(["eeo1_report"]),
    "garnishment": frozenset(["garnishment_limits"]),
    "business_license": frozenset([
        "state_business_registration", "local_business_license",
        "professional_licensing", "dba_registration",
    ]),
    "tax_rate": frozenset([
        "corporate_income_tax", "franchise_tax", "unemployment_insurance_tax",
        "disability_insurance_tax", "employment_training_tax",
        "sales_use_tax", "local_tax",
    ]),
    "posting_requirements": frozenset([
        "minimum_wage_poster", "discrimination_poster", "osha_poster",
        "workers_comp_poster", "paid_sick_leave_poster", "family_leave_poster",
        "whistleblower_poster", "wage_order_poster", "workplace_violence_poster",
    ]),
}
EXPECTED_REGULATION_KEYS.update(_LABOR_REGULATION_KEYS)

# Oncology categories — these previously had ZERO expected keys.
# Now defined to enable gap detection and key-level coverage tracking.
_ONCOLOGY_REGULATION_KEYS: Dict[str, FrozenSet[str]] = {
    "radiation_safety": frozenset([
        "state_radiation_control_programs", "radiation_safety_officer",
        "linear_accelerator_qa", "brachytherapy_safety",
        "radiation_oncology_safety_team", "radioactive_materials_license",
    ]),
    "chemotherapy_handling": frozenset([
        "usp_compounding_standards", "closed_system_transfer",
        "hazardous_drug_assessment", "spill_management",
        "hazardous_waste_disposal",
    ]),
    "tumor_registry": frozenset([
        "cancer_registry_reporting", "reporting_timelines",
        "electronic_reporting_format", "registry_data_quality",
    ]),
    "oncology_clinical_trials": frozenset([
        "clinical_trial_coverage_mandates", "right_to_try",
        "protocol_deviation_reporting", "adverse_event_reporting",
        "investigational_drug_access",
    ]),
    "oncology_patient_rights": frozenset([
        "patient_rights_declarations", "hospice_palliative_care",
        "advance_directives", "fertility_preservation_counseling",
        "cancer_treatment_consent",
    ]),
}
EXPECTED_REGULATION_KEYS.update(_ONCOLOGY_REGULATION_KEYS)

_LIFE_SCIENCES_REGULATION_KEYS: Dict[str, FrozenSet[str]] = {
    "gmp_manufacturing": frozenset([
        "cgmp_drugs_21cfr210_211", "cgmp_devices_21cfr820", "process_validation",
        "fda_facility_registration", "annual_product_review",
        "supplier_qualification", "fda_inspection_readiness",
    ]),
    "glp_nonclinical": frozenset([
        "glp_21cfr58", "study_director_responsibilities", "glp_qa_unit",
        "specimen_archiving", "equipment_calibration_glp",
        "protocol_amendments_deviations",
    ]),
    "clinical_trials_gcp": frozenset([
        "ich_e6r2_gcp", "ind_application_21cfr312", "sponsor_responsibilities",
        "adverse_event_reporting_ind", "informed_consent_21cfr50",
        "irb_oversight_21cfr56", "clinical_data_integrity_part11",
    ]),
    "drug_supply_chain": frozenset([
        "dscsa_serialization", "dscsa_verification", "dscsa_tracing",
        "wholesale_distribution_license", "gdp_storage_transport",
        "suspicious_order_monitoring", "drug_recall_procedures",
    ]),
    "sunshine_open_payments": frozenset([
        "physician_payments_reporting", "aggregate_spend_tracking",
        "cms_open_payments_submission", "teaching_hospital_reporting",
        "state_gift_ban_laws", "covered_recipient_identification",
    ]),
    "biosafety_lab": frozenset([
        "bsl_classifications", "institutional_biosafety_committee",
        "nih_rdna_guidelines", "select_agent_regulations",
        "bloodborne_pathogen_lab", "chemical_hygiene_plan",
    ]),
}
EXPECTED_REGULATION_KEYS.update(_LIFE_SCIENCES_REGULATION_KEYS)

_MANUFACTURING_REGULATION_KEYS: Dict[str, FrozenSet[str]] = {
    "process_safety": frozenset([
        "osha_psm", "process_hazard_analysis", "management_of_change",
        "pre_startup_review", "mechanical_integrity", "emergency_action_plan",
    ]),
    "environmental_compliance": frozenset([
        "air_quality_permit", "neshap_compliance", "wastewater_discharge",
        "hazardous_waste_rcra", "stormwater_permit", "emissions_reporting",
        # Expansion
        "tsca_toxic_substances", "cercla_superfund_liability", "clean_air_act_title_v",
        "epa_risk_management_program", "epcra_tri_reporting", "rcra_hazardous_waste",
        "clean_water_act_npdes", "spcc_oil_spill_prevention",
    ]),
    "chemical_safety": frozenset([
        "hazcom_ghs", "chemical_inventory_reporting", "right_to_know",
        "sds_management", "hazardous_substance_storage", "pfas_restrictions",
    ]),
    "machine_safety": frozenset([
        "lockout_tagout", "machine_guarding", "powered_industrial_trucks",
        "crane_hoist_safety", "electrical_safety", "confined_space",
    ]),
    "industrial_hygiene": frozenset([
        "noise_exposure", "respiratory_protection", "heat_illness_prevention",
        "permissible_exposure_limits", "personal_protective_equipment", "ergonomics",
    ]),
    "trade_compliance": frozenset([
        "customs_tariff", "export_controls", "anti_dumping_duties",
        "country_of_origin", "trade_agreements", "sanctions_screening",
    ]),
    "product_safety": frozenset([
        "product_certification", "recall_procedures", "quality_system_requirements",
        "consumer_safety_standards", "labeling_requirements", "type_approval",
    ]),
    "labor_relations": frozenset([
        "collective_bargaining", "right_to_work", "union_notification",
        "strike_lockout_rules", "works_council", "employee_representation",
    ]),
}
EXPECTED_REGULATION_KEYS.update(_MANUFACTURING_REGULATION_KEYS)

_EXPANSION_REGULATION_KEYS: Dict[str, FrozenSet[str]] = {
    "fda_lifecycle": frozenset([
        "nda_bla_submission", "anda_generic_pathway", "fda_breakthrough_accelerated",
        "fda_priority_review", "post_market_surveillance_faers",
        "pharmacovigilance_safety_reporting", "rems_lifecycle", "fda_483_observations",
        "product_labeling_pi_medication_guide", "pediatric_study_requirements",
        "orphan_drug_exclusivity", "patent_exclusivity_orange_book",
    ]),
    "reimbursement_vbc": frozenset([
        "macra_mips_reporting", "apm_participation", "bundled_payment_compliance",
        "cms_star_ratings", "hedis_quality_measures", "value_based_contract_requirements",
        "drg_coding_compliance", "price_transparency_rule", "no_surprises_act",
        "good_faith_estimates",
    ]),
    "quality_systems": frozenset([
        "iso_13485_medical_devices", "iso_9001_general_qms", "iso_15189_clinical_labs",
        "iso_14001_environmental", "iso_45001_ohs", "iso_27001_information_security",
        "clia_lab_certification", "cap_accreditation", "joint_commission_accreditation",
    ]),
    "supply_chain": frozenset([
        "conflict_minerals_dodd_frank", "reach_regulation", "rohs_directive",
        "uyghur_forced_labor_prevention", "supplier_qualification_audit",
        "track_trace_serialization", "gpp_green_procurement", "antibribery_fcpa_uk_bribery",
    ]),
}
EXPECTED_REGULATION_KEYS.update(_EXPANSION_REGULATION_KEYS)

_HEALTHCARE_EXPANSION_KEYS: Dict[str, FrozenSet[str]] = {
    "billing_integrity": frozenset([
        "340b_drug_pricing_compliance", "surprise_billing_state_laws",
        "medicare_advantage_billing", "medicaid_managed_care_billing",
        "charity_care_financial_assistance",
    ]),
    "clinical_safety": frozenset([
        "blood_bank_transfusion_safety", "surgical_safety_protocols",
        "patient_identification_standards", "diagnostic_error_reporting",
        "nursing_home_ltc_safety", "radiation_therapy_safety",
    ]),
    "hipaa_privacy": frozenset([
        "information_blocking", "patient_right_of_access",
        "research_data_use_agreements",
    ]),
    "healthcare_workforce": frozenset([
        "locum_tenens_temporary_staffing", "physician_noncompete_restrictions",
        "healthcare_worker_vaccination_requirements", "safe_staffing_legislation",
    ]),
    "reimbursement_vbc": frozenset([
        "mssp_aco_compliance", "medicaid_supplemental_payments",
        "episode_based_payment", "drug_rebate_program", "site_neutral_payment",
    ]),
    "emergency_preparedness": frozenset([
        "cybersecurity_incident_response", "continuity_of_operations",
    ]),
    "state_licensing": frozenset([
        "ambulatory_surgery_center_licensing", "home_health_hospice_licensing",
        "behavioral_health_facility_licensing", "clinical_laboratory_licensing",
    ]),
    "corporate_integrity": frozenset([
        "compliance_risk_assessment", "physician_arrangement_tracking",
    ]),
}
EXPECTED_REGULATION_KEYS.update(
    {k: v | EXPECTED_REGULATION_KEYS.get(k, frozenset())
     for k, v in _HEALTHCARE_EXPANSION_KEYS.items()}
)

_INTERNATIONAL_REGULATION_KEYS: Dict[str, FrozenSet[str]] = {
    "minimum_wage": frozenset(["national_minimum_wage", "zlfn_border_zone_minimum_wage"]),
    "sick_leave": frozenset(["statutory_sick_leave", "imss_sick_leave"]),
    "leave": frozenset([
        "annual_leave_entitlement", "vacation_premium", "statutory_maternity_leave",
        "statutory_paternity_leave", "aguinaldo_christmas_bonus", "ptu_profit_sharing",
        "severance_pay", "seniority_premium", "shared_parental_leave",
        "statutory_notice_period_employer", "adoption_leave",
    ]),
    "final_pay": frozenset(["finiquito", "liquidacion"]),
    "scheduling_reporting": frozenset(["maximum_working_hours", "sunday_premium"]),
    "workers_comp": frozenset([
        "social_insurance_employer", "imss_employer_contribution",
        "infonavit_contribution", "sar_retirement_contribution",
        "uk_auto_enrolment_pension", "social_insurance_employee",
        "cpf_employer_contribution", "foreign_worker_levy",
    ]),
    "workplace_safety": frozenset(["stps_nom_standards"]),
    "anti_discrimination": frozenset(["nom_035_psychosocial_risk"]),
    "hipaa_privacy": frozenset(["national_health_privacy_law", "lfpdppp_health_data"]),
    "clinical_safety": frozenset(["cofepris_facility_standards"]),
    "state_licensing": frozenset(["cofepris_sanitary_license"]),
    "research_consent": frozenset(["national_research_consent_law", "cofepris_research_authorization"]),
    "radiation_safety": frozenset(["national_radiation_control"]),
    "chemotherapy_handling": frozenset(["national_hazardous_drug_handling"]),
    "tumor_registry": frozenset(["national_cancer_registry"]),
    "billing_integrity": frozenset(["national_anti_corruption_healthcare"]),
    "corporate_integrity": frozenset(["national_whistleblower_protection"]),
    "emergency_preparedness": frozenset(["national_emergency_preparedness"]),
    "oncology_patient_rights": frozenset(["palliative_care_access"]),
    "healthcare_workforce": frozenset(["professional_licensing"]),
    "oncology_clinical_trials": frozenset(["clinical_trial_coverage_mandates"]),
}
EXPECTED_REGULATION_KEYS.update(
    {k: v | EXPECTED_REGULATION_KEYS.get(k, frozenset())
     for k, v in _INTERNATIONAL_REGULATION_KEYS.items()}
)

# Country scope for international keys — used by get_missing_regulations()
# None = universal (all countries). Otherwise list of country codes.
_KEY_COUNTRY_SCOPE: Dict[str, Optional[list]] = {
    # Universal
    "national_minimum_wage": None, "statutory_sick_leave": None,
    "annual_leave_entitlement": None, "statutory_maternity_leave": None,
    "statutory_paternity_leave": None, "severance_pay": None,
    "statutory_notice_period_employer": None, "social_insurance_employer": None,
    "maximum_working_hours": None,
    # Mexico
    "zlfn_border_zone_minimum_wage": ["MX"], "imss_sick_leave": ["MX"],
    "vacation_premium": ["MX"], "aguinaldo_christmas_bonus": ["MX"],
    "ptu_profit_sharing": ["MX"], "seniority_premium": ["MX"],
    "finiquito": ["MX"], "liquidacion": ["MX"], "sunday_premium": ["MX"],
    "imss_employer_contribution": ["MX"], "infonavit_contribution": ["MX"],
    "sar_retirement_contribution": ["MX"], "stps_nom_standards": ["MX"],
    "nom_035_psychosocial_risk": ["MX"], "national_health_privacy_law": ["MX"],
    "lfpdppp_health_data": ["MX"], "cofepris_facility_standards": ["MX"],
    "cofepris_sanitary_license": ["MX"], "national_research_consent_law": ["MX"],
    "cofepris_research_authorization": ["MX"], "national_radiation_control": ["MX"],
    "national_hazardous_drug_handling": ["MX"], "national_cancer_registry": ["MX"],
    "national_anti_corruption_healthcare": ["MX"], "national_whistleblower_protection": ["MX"],
    "national_emergency_preparedness": ["MX"], "palliative_care_access": ["MX"],
    "professional_licensing": ["MX"], "clinical_trial_coverage_mandates": ["MX"],
    # UK
    "shared_parental_leave": ["GB"], "adoption_leave": ["GB"],
    "uk_auto_enrolment_pension": ["GB"], "social_insurance_employee": ["GB"],
    # Singapore
    "cpf_employer_contribution": ["SG"], "foreign_worker_levy": ["SG"],
}


# Keys that exist only in NAMED STATES. The country scope above can't express
# this, and without it a state-specific concept is EXPECTED of every US state:
# `exempt_salary_threshold_regional` (NY's downstate tier) would emit a
# missing_key finding against the other 49 and drag every state's completeness
# score for something they will never have. The key must stay in
# EXPECTED_REGULATION_KEYS regardless — that set doubles as the VALIDITY
# vocabulary, and dropping it there would brand NY's real row `invalid_key`.
#
# A jurisdiction with no state (federal, or a country-level row) never expects
# a state-scoped key.
_KEY_STATE_SCOPE: Dict[str, list] = {
    "exempt_salary_threshold_regional": ["NY"],
}


def _key_applies_to_country(key: str, category: str, country_code: str) -> bool:
    """Check if a regulation key applies to a given country.

    Keys explicitly listed in _KEY_COUNTRY_SCOPE with None = universal (all countries).
    Keys explicitly listed with a country list = only those countries.
    Keys NOT in _KEY_COUNTRY_SCOPE = US-only (the 353 legacy US keys).
    """
    if key not in _KEY_COUNTRY_SCOPE:
        # Not in scope dict → legacy US key, only applies to US
        return country_code == "US"
    scope = _KEY_COUNTRY_SCOPE[key]
    if scope is None:
        return True  # Explicitly universal
    return country_code in scope


def _key_applies_to_state(key: str, state: Optional[str]) -> bool:
    """Is this key expected of a jurisdiction in `state`?

    Only constrains keys listed in _KEY_STATE_SCOPE; everything else is
    state-agnostic. `state=None` (federal / country-level) never expects a
    state-scoped key.
    """
    scope = _KEY_STATE_SCOPE.get(key)
    if scope is None:
        return True
    return bool(state) and state.upper() in scope


