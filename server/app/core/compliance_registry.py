"""
Compliance Registry — single source of truth for all compliance categories,
regulations, research prompts, and category aliases.

Every category, regulation, research prompt and alias lives here.
Other modules import from this file rather than defining their own lists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Set


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ComplianceCategoryDef:
    key: str
    label: str
    short_label: str
    group: str          # "labor" | "healthcare" | "oncology" | "medical_compliance" | "supplementary"
    industry_tag: str   # e.g. "healthcare:pharmacy" or "" for labor
    research_mode: str  # "default_sweep" | "specialty" | "health_specs"
    docx_section: Optional[int]


@dataclass(frozen=True)
class RegulationDef:
    key: str
    category: str
    name: str
    description: str
    enforcing_agency: str
    state_variance: str      # "High" | "Moderate" | "Low/None"
    update_frequency: str
    authority_sources: tuple  # tuple of dicts


# ---------------------------------------------------------------------------
# CATEGORIES  (40 entries)
# ---------------------------------------------------------------------------

CATEGORIES: List[ComplianceCategoryDef] = [
    # ── Labor (12) ─────────────────────────────────────────────────────────
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
]


# ---------------------------------------------------------------------------
# REGULATIONS  (229 entries)
# ---------------------------------------------------------------------------

REGULATIONS: List[RegulationDef] = [
    RegulationDef(
        key="hipaa_privacy_rule",
        category="hipaa_privacy",
        name="HIPAA Privacy Rule (45 CFR Part 160, 164 Subparts A & E)",
        description="Use and disclosure of PHI, minimum necessary standard, patient rights (access, amendment, accounting of disclosures), Notice of Privacy Practices",
        enforcing_agency="HHS OCR",
        state_variance="Moderate",
        update_frequency="Every 2–5 yrs; guidance letters ongoing",
        authority_sources=(
            {"domain": "hhs.gov/hipaa", "name": "hhs.gov/hipaa"},
            {"domain": "federalregister.gov", "name": "search 45 CFR 164"},
        ),
    ),
    RegulationDef(
        key="hipaa_security_rule",
        category="hipaa_privacy",
        name="HIPAA Security Rule (45 CFR Part 164 Subpart C)",
        description="Administrative, physical, and technical safeguards for ePHI; risk analysis requirement; access controls; encryption standards",
        enforcing_agency="HHS OCR",
        state_variance="Low/None",
        update_frequency="Every 3–5 yrs; major update proposed 2024",
        authority_sources=(
            {"domain": "hhs.gov/hipaa/for-professionals/security", "name": "hhs.gov/hipaa/for-professionals/security"},
            {"domain": "healthit.gov", "name": "healthit.gov"},
        ),
    ),
    RegulationDef(
        key="hipaa_breach_notification_rule",
        category="hipaa_privacy",
        name="HIPAA Breach Notification Rule (45 CFR Part 164 Subpart D)",
        description="Notification to individuals, HHS, and media for unsecured PHI breaches; 60-day timeline; risk assessment methodology",
        enforcing_agency="HHS OCR",
        state_variance="Moderate",
        update_frequency="Rarely amended; OCR guidance periodic",
        authority_sources=({"domain": "hhs.gov/hipaa/for-professionals/breach-notification", "name": "hhs.gov/hipaa/for-professionals/breach-notification"},),
    ),
    RegulationDef(
        key="hitech_act",
        category="hipaa_privacy",
        name="HITECH Act (Title XIII of ARRA)",
        description="Strengthened HIPAA enforcement, extended to business associates, meaningful use incentives, increased penalties",
        enforcing_agency="HHS OCR / CMS",
        state_variance="Low/None",
        update_frequency="Rare (enacted 2009; provisions folded into HIPAA updates)",
        authority_sources=({"domain": "hhs.gov/hipaa/for-professionals/special-topics/hitech-act-enforcement-interim-final-rule", "name": "hhs.gov/hipaa/for-professionals/special-topics/hitech-act-enforcement-interim-final-rule"},),
    ),
    RegulationDef(
        key="42_cfr_part_2",
        category="hipaa_privacy",
        name="42 CFR Part 2 (Substance Use Disorder Records)",
        description="Stricter-than-HIPAA protections for SUD treatment records; requires specific written consent for most disclosures",
        enforcing_agency="SAMHSA / HHS OCR",
        state_variance="Moderate",
        update_frequency="Major update 2024 (final rule aligning with HIPAA for TPO); next update uncertain",
        authority_sources=(
            {"domain": "samhsa.gov/about-us/who-we-are/laws-regulations/confidentiality-regulations-faqs", "name": "samhsa.gov/about-us/who-we-are/laws-regulations/confidentiality-regulations-faqs"},
            {"domain": "federalregister.gov", "name": "federalregister.gov"},
        ),
    ),
    RegulationDef(
        key="state_health_privacy_laws",
        category="hipaa_privacy",
        name="State Health Privacy Laws",
        description="Many states impose stricter privacy requirements (e.g., CA CMIA, TX Medical Records Privacy Act, NY SHIELD Act); separate consent for HIV, mental health, genetic info",
        enforcing_agency="State AGs / Health Depts",
        state_variance="High",
        update_frequency="Continuous — state legislatures amend annually",
        authority_sources=(
            {"domain": "Each state legislature website", "name": "Each state legislature website"},
            {"domain": "ncsl.org/health", "name": "National Conference of State Legislatures"},
        ),
    ),
    RegulationDef(
        key="genetic_information_nondiscrimination_act",
        category="hipaa_privacy",
        name="Genetic Information Nondiscrimination Act (GINA)",
        description="Prohibits use of genetic information in health insurance and employment decisions; restricts collection of genetic data",
        enforcing_agency="HHS / EEOC",
        state_variance="Moderate",
        update_frequency="Rarely amended (enacted 2008); state genetic privacy laws update more often",
        authority_sources=(
            {"domain": "eeoc.gov/genetic-information-discrimination", "name": "eeoc.gov/genetic-information-discrimination"},
            {"domain": "genome.gov/about-genomics/policy-issues/Genetic-Discrimination", "name": "genome.gov/about-genomics/policy-issues/Genetic-Discrimination"},
        ),
    ),
    RegulationDef(
        key="ftc_health_breach_notification_rule",
        category="hipaa_privacy",
        name="FTC Health Breach Notification Rule (16 CFR Part 318)",
        description="Applies to non-HIPAA-covered entities handling health data (health apps, consumer devices); breach notification requirements",
        enforcing_agency="FTC",
        state_variance="Low/None",
        update_frequency="Updated 2023; periodic FTC rulemaking",
        authority_sources=({"domain": "ftc.gov/legal-library/browse/rules/health-breach-notification-rule", "name": "ftc.gov/legal-library/browse/rules/health-breach-notification-rule"},),
    ),
    RegulationDef(
        key="coppa",
        category="hipaa_privacy",
        name="COPPA (Children’s Online Privacy Protection Act)",
        description="Applies if collecting online data from children under 13; parental consent; relevant for patient portals and telehealth with minors",
        enforcing_agency="FTC",
        state_variance="Low/None",
        update_frequency="Updated every 3–5 yrs; major update finalized 2024",
        authority_sources=({"domain": "ftc.gov/legal-library/browse/rules/childrens-online-privacy-protection-rule-coppa", "name": "ftc.gov/legal-library/browse/rules/childrens-online-privacy-protection-rule-coppa"},),
    ),
    RegulationDef(
        key="state_biometric_privacy_laws",
        category="hipaa_privacy",
        name="State Biometric Privacy Laws (e.g., IL BIPA, TX CUBI)",
        description="Regulate collection/storage of biometric identifiers (fingerprints, retinal scans for facility access or patient ID)",
        enforcing_agency="State AGs / Private action in IL",
        state_variance="High",
        update_frequency="Active — new states passing laws annually (2023–2026)",
        authority_sources=(
            {"domain": "ilga.gov", "name": "IL BIPA 740 ILCS 14"},
            {"domain": "each state legislature site", "name": "each state legislature site"},
            {"domain": "ncsl.org/technology-and-telecommunication/biometric-data", "name": "ncsl.org/technology-and-telecommunication/biometric-data"},
        ),
    ),
    RegulationDef(
        key="false_claims_act",
        category="billing_integrity",
        name="False Claims Act (31 U.S.C. §§ 3729–3733)",
        description="Civil liability for knowingly submitting false claims to federal programs; qui tam (whistleblower) provisions; treble damages",
        enforcing_agency="DOJ / OIG",
        state_variance="Moderate",
        update_frequency="Rarely amended; DOJ guidance/memos update interpretation annually",
        authority_sources=(
            {"domain": "justice.gov/civil/fraud", "name": "justice.gov/civil/fraud"},
            {"domain": "oig.hhs.gov", "name": "oig.hhs.gov"},
        ),
    ),
    RegulationDef(
        key="antikickback_statute",
        category="billing_integrity",
        name="Anti-Kickback Statute (42 U.S.C. § 1320a-7b(b))",
        description="Criminal prohibition on offering/receiving remuneration for referrals of federal healthcare program business; safe harbors",
        enforcing_agency="OIG / DOJ",
        state_variance="High",
        update_frequency="Safe harbors updated every 3–5 yrs; OIG Advisory Opinions ongoing",
        authority_sources=(
            {"domain": "oig.hhs.gov/compliance/safe-harbor-regulations", "name": "oig.hhs.gov/compliance/safe-harbor-regulations"},
            {"domain": "oig.hhs.gov/compliance/advisory-opinions", "name": "oig.hhs.gov/compliance/advisory-opinions"},
        ),
    ),
    RegulationDef(
        key="stark_law",
        category="billing_integrity",
        name="Stark Law (42 U.S.C. § 1395nn)",
        description="Prohibits physician referrals for designated health services to entities with financial relationship, unless exception applies",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Exceptions updated every 3–5 yrs; major 2021 final rule",
        authority_sources=({"domain": "cms.gov/medicare/fraud-and-abuse/physicianselfreferral", "name": "cms.gov/medicare/fraud-and-abuse/physicianselfreferral"},),
    ),
    RegulationDef(
        key="criminal_health_care_fraud",
        category="billing_integrity",
        name="Criminal Health Care Fraud (18 U.S.C. § 1347)",
        description="Federal criminal offense for executing a scheme to defraud any healthcare benefit program",
        enforcing_agency="DOJ / FBI",
        state_variance="Low/None",
        update_frequency="Rarely amended; DOJ enforcement priorities shift annually",
        authority_sources=({"domain": "justice.gov/criminal-fraud/health-care-fraud-unit", "name": "justice.gov/criminal-fraud/health-care-fraud-unit"},),
    ),
    RegulationDef(
        key="exclusion_statute",
        category="billing_integrity",
        name="Exclusion Statute (42 U.S.C. § 1320a-7)",
        description="Mandatory and permissive exclusion from federal programs; OIG LEIE screening requirements",
        enforcing_agency="OIG",
        state_variance="Low/None",
        update_frequency="LEIE list updated monthly; statute rarely amended",
        authority_sources=(
            {"domain": "oig.hhs.gov/exclusions", "name": "oig.hhs.gov/exclusions"},
            {"domain": "sam.gov", "name": "sam.gov"},
        ),
    ),
    RegulationDef(
        key="civil_monetary_penalties_law",
        category="billing_integrity",
        name="Civil Monetary Penalties Law (42 U.S.C. § 1320a-7a)",
        description="Penalties for false claims, kickbacks, patient inducements, EMTALA violations",
        enforcing_agency="OIG",
        state_variance="Low/None",
        update_frequency="Penalty amounts adjusted annually for inflation",
        authority_sources=({"domain": "oig.hhs.gov/fraud/enforcement/cmp", "name": "oig.hhs.gov/fraud/enforcement/cmp"},),
    ),
    RegulationDef(
        key="no_surprises_act",
        category="billing_integrity",
        name="No Surprises Act (Consolidated Appropriations Act 2021)",
        description="Protects patients from surprise out-of-network bills; IDR process; good faith estimates for uninsured",
        enforcing_agency="CMS / State regulators",
        state_variance="High",
        update_frequency="Active rulemaking 2022–2025; IDR process under litigation/revision",
        authority_sources=(
            {"domain": "cms.gov/nosurprises", "name": "cms.gov/nosurprises"},
            {"domain": "cms.gov/cciio/resources", "name": "cms.gov/cciio/resources"},
        ),
    ),
    RegulationDef(
        key="medicare_conditions_of_payment_billing_rules",
        category="billing_integrity",
        name="Medicare Conditions of Payment / Billing Rules",
        description="Proper use of CPT, HCPCS, ICD-10 codes; medical necessity documentation; timely filing; claims submission",
        enforcing_agency="CMS / MACs",
        state_variance="Low/None",
        update_frequency="Annual code updates (Oct ICD-10, Jan CPT); transmittals ongoing",
        authority_sources=(
            {"domain": "cms.gov/medicare/coding", "name": "cms.gov/medicare/coding"},
            {"domain": "cms.gov/regulations-and-guidance/transmittals", "name": "cms.gov/regulations-and-guidance/transmittals"},
        ),
    ),
    RegulationDef(
        key="medicaid_billing_requirements",
        category="billing_integrity",
        name="Medicaid Billing Requirements",
        description="State-specific fee schedules, prior auth rules, eligibility verification, managed care contracts",
        enforcing_agency="CMS / State Medicaid",
        state_variance="High",
        update_frequency="Continuous — state Medicaid agencies update throughout year",
        authority_sources=(
            {"domain": "medicaid.gov", "name": "medicaid.gov"},
            {"domain": "each state Medicaid agency website", "name": "each state Medicaid agency website"},
        ),
    ),
    RegulationDef(
        key="state_antikickback_selfreferral_laws",
        category="billing_integrity",
        name="State Anti-Kickback & Self-Referral Laws",
        description="Many states have own anti-kickback and self-referral statutes, some broader than federal equivalents",
        enforcing_agency="State AGs / Boards",
        state_variance="High",
        update_frequency="Varies by state; legislative sessions annually",
        authority_sources=(
            {"domain": "Each state legislature", "name": "Each state legislature"},
            {"domain": "oig.hhs.gov/compliance/state-false-claims-act", "name": "oig.hhs.gov/compliance/state-false-claims-act"},
        ),
    ),
    RegulationDef(
        key="state_false_claims_acts",
        category="billing_integrity",
        name="State False Claims Acts",
        description="Over 30 states have own false claims acts with broader scope than federal FCA",
        enforcing_agency="State AGs",
        state_variance="High",
        update_frequency="Updated periodically; OIG maintains qualifying list",
        authority_sources=(
            {"domain": "oig.hhs.gov/fraud/state-false-claims-act", "name": "oig.hhs.gov/fraud/state-false-claims-act"},
            {"domain": "each state AG website", "name": "each state AG website"},
        ),
    ),
    RegulationDef(
        key="medicare_secondary_payer_rules",
        category="billing_integrity",
        name="Medicare Secondary Payer (MSP) Rules",
        description="Coordination of benefits when Medicare is secondary; reporting obligations to BCRC",
        enforcing_agency="CMS / BCRC",
        state_variance="Low/None",
        update_frequency="Reporting thresholds updated periodically; guidance letters ongoing",
        authority_sources=({"domain": "cms.gov/medicare/coordination-of-benefits-and-recovery", "name": "cms.gov/medicare/coordination-of-benefits-and-recovery"},),
    ),
    RegulationDef(
        key="provider_enrollment_revalidation",
        category="billing_integrity",
        name="Provider Enrollment & Revalidation (42 CFR Part 424)",
        description="Medicare enrollment requirements, screening levels, revalidation cycles, reporting changes",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Revalidation cycles every 3–5 yrs; rules updated periodically",
        authority_sources=({"domain": "cms.gov/medicare/provider-enrollment-and-certification", "name": "cms.gov/medicare/provider-enrollment-and-certification"},),
    ),
    RegulationDef(
        key="cms_conditions_of_participation",
        category="clinical_safety",
        name="CMS Conditions of Participation (42 CFR Parts 482–491)",
        description="Minimum health and safety standards for hospitals, SNFs, HHAs, ASCs, and other providers in Medicare/Medicaid",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Updated every 2–5 yrs via rulemaking; Interpretive Guidelines updated more frequently",
        authority_sources=(
            {"domain": "cms.gov/regulations-and-guidance/legislation/cfr", "name": "cms.gov/regulations-and-guidance/legislation/cfr"},
            {"domain": "cms.gov/medicare/provider-enrollment-and-certification/surveycertificationgeninfo", "name": "cms.gov/medicare/provider-enrollment-and-certification/surveycertificationgeninfo"},
        ),
    ),
    RegulationDef(
        key="cms_conditions_for_coverage",
        category="clinical_safety",
        name="CMS Conditions for Coverage (CfCs)",
        description="Standards for ESRD facilities, transplant centers, hospice, CORF, CMHC, OPOs",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Updated every 3–5 yrs",
        authority_sources=({"domain": "cms.gov/regulations-and-guidance/legislation/cfr", "name": "cms.gov/regulations-and-guidance/legislation/cfr"},),
    ),
    RegulationDef(
        key="joint_commission_standards",
        category="clinical_safety",
        name="Joint Commission Standards",
        description="Deemed status for CMS; patient safety goals, medication management, infection prevention, leadership, environment of care",
        enforcing_agency="Joint Commission",
        state_variance="Low/None",
        update_frequency="Annual updates to standards; NPSGs updated annually",
        authority_sources=(
            {"domain": "jointcommission.org/standards", "name": "jointcommission.org/standards"},
            {"domain": "jointcommission.org/resources/patient-safety-topics/national-patient-safety-goals", "name": "jointcommission.org/resources/patient-safety-topics/national-patient-safety-goals"},
        ),
    ),
    RegulationDef(
        key="dnv_gl_healthcare_accreditation",
        category="clinical_safety",
        name="DNV GL Healthcare Accreditation",
        description="Alternative deemed status based on ISO 9001 quality management framework",
        enforcing_agency="DNV GL",
        state_variance="Low/None",
        update_frequency="ISO 9001 updated every 5–7 yrs; DNV standards updated annually",
        authority_sources=({"domain": "dnv.com/assurance/healthcare", "name": "dnv.com/assurance/healthcare"},),
    ),
    RegulationDef(
        key="state_licensure_standards_for_healthcare_facilitie",
        category="clinical_safety",
        name="State Licensure Standards for Healthcare Facilities",
        description="State-specific requirements for hospitals, ASCs, nursing homes, clinics, labs, and other facility types",
        enforcing_agency="State Health Depts",
        state_variance="High",
        update_frequency="Continuous — updated via state regulation and legislation",
        authority_sources=(
            {"domain": "Each state health department website", "name": "Each state health department website"},
            {"domain": "ahd.com", "name": "American Hospital Directory"},
        ),
    ),
    RegulationDef(
        key="emtala",
        category="clinical_safety",
        name="EMTALA (42 U.S.C. § 1395dd)",
        description="Medical screening and stabilization for anyone presenting to ED regardless of ability to pay",
        enforcing_agency="CMS / OIG",
        state_variance="Low/None",
        update_frequency="Rarely amended; CMS Interpretive Guidelines updated periodically",
        authority_sources=({"domain": "cms.gov/medicare/provider-enrollment-and-certification/surveycertificationgeninfo/downloads/sc-letter08-01.pdf", "name": "cms.gov/medicare/provider-enrollment-and-certification/surveycertificationgeninfo/downloads/sc-letter08-01.pdf"},),
    ),
    RegulationDef(
        key="patient_safety_quality_improvement_act",
        category="clinical_safety",
        name="Patient Safety & Quality Improvement Act (PSQIA)",
        description="Privilege and confidentiality protections for patient safety work product reported to PSOs",
        enforcing_agency="AHRQ",
        state_variance="Moderate",
        update_frequency="Rarely amended (enacted 2005); PSO listing updated ongoing",
        authority_sources=({"domain": "pso.ahrq.gov", "name": "pso.ahrq.gov"},),
    ),
    RegulationDef(
        key="npdb_reporting",
        category="clinical_safety",
        name="NPDB Reporting",
        description="Mandatory reporting of malpractice payments, adverse licensure actions, adverse privilege actions",
        enforcing_agency="HRSA",
        state_variance="Low/None",
        update_frequency="Reporting requirements stable; guidebook updated every 2–3 yrs",
        authority_sources=({"domain": "npdb.hrsa.gov", "name": "npdb.hrsa.gov"},),
    ),
    RegulationDef(
        key="sentinel_event_reporting",
        category="clinical_safety",
        name="Sentinel Event Reporting",
        description="Reporting of serious patient safety events per Joint Commission or state requirements",
        enforcing_agency="Joint Commission / State",
        state_variance="High",
        update_frequency="Joint Commission sentinel event policy updated annually; state requirements vary",
        authority_sources=(
            {"domain": "jointcommission.org/resources/patient-safety-topics/sentinel-event", "name": "jointcommission.org/resources/patient-safety-topics/sentinel-event"},
            {"domain": "each state health dept", "name": "each state health dept"},
        ),
    ),
    RegulationDef(
        key="infection_control_prevention_standards",
        category="clinical_safety",
        name="Infection Control & Prevention Standards",
        description="CMS CoP requirements, CDC guidelines (HAI prevention), state-mandated HAI reporting",
        enforcing_agency="CMS / CDC / State",
        state_variance="High",
        update_frequency="CDC guidelines updated continuously; state reporting requirements update annually",
        authority_sources=(
            {"domain": "cdc.gov/hai", "name": "cdc.gov/hai"},
            {"domain": "cms.gov/medicare/infection-control", "name": "cms.gov/medicare/infection-control"},
        ),
    ),
    RegulationDef(
        key="medication_management_controlled_substances",
        category="clinical_safety",
        name="Medication Management & Controlled Substances (21 CFR 1301–1321)",
        description="DEA registration, Schedule II-V prescribing, PDMP requirements, medication storage/dispensing protocols",
        enforcing_agency="DEA / State Pharmacy Boards",
        state_variance="High",
        update_frequency="DEA scheduling actions ongoing; state PDMP laws update annually",
        authority_sources=(
            {"domain": "deadiversion.usdoj.gov", "name": "deadiversion.usdoj.gov"},
            {"domain": "each state pharmacy board", "name": "each state pharmacy board"},
        ),
    ),
    RegulationDef(
        key="clia",
        category="clinical_safety",
        name="CLIA (42 CFR Part 493)",
        description="Certification and quality standards for all clinical laboratories; proficiency testing; personnel requirements",
        enforcing_agency="CMS / CDC / State",
        state_variance="Moderate",
        update_frequency="Updated every 3–5 yrs; proficiency testing updated annually",
        authority_sources=(
            {"domain": "cms.gov/regulations-and-guidance/legislation/clia", "name": "cms.gov/regulations-and-guidance/legislation/clia"},
            {"domain": "cdc.gov/clia", "name": "cdc.gov/clia"},
        ),
    ),
    RegulationDef(
        key="informed_consent_requirements",
        category="clinical_safety",
        name="Informed Consent Requirements",
        description="Federal common rule for research (45 CFR 46); state requirements for surgical/treatment consent, blood, HIV testing",
        enforcing_agency="CMS / State law",
        state_variance="High",
        update_frequency="State laws update frequently; federal common rule updated 2018",
        authority_sources=(
            {"domain": "hhs.gov/ohrp/regulations-and-policy", "name": "hhs.gov/ohrp/regulations-and-policy"},
            {"domain": "each state legislature", "name": "each state legislature"},
        ),
    ),
    RegulationDef(
        key="advance_directives",
        category="clinical_safety",
        name="Advance Directives (Patient Self-Determination Act)",
        description="Requirement to inform patients of advance directive rights; state-specific forms and requirements",
        enforcing_agency="CMS / State law",
        state_variance="High",
        update_frequency="Federal law stable; state forms and laws update every few years",
        authority_sources=(
            {"domain": "Each state legislature", "name": "Each state legislature"},
            {"domain": "caringinfo.org", "name": "NHPCO"},
        ),
    ),
    RegulationDef(
        key="restraint_seclusion_standards",
        category="clinical_safety",
        name="Restraint & Seclusion Standards (42 CFR 482.13(e)–(f))",
        description="CMS rules on physical restraints and seclusion; documentation, monitoring, physician orders, time limits",
        enforcing_agency="CMS / Joint Commission",
        state_variance="Moderate",
        update_frequency="Updated every 3–5 yrs; Joint Commission standards updated annually",
        authority_sources=({"domain": "cms.gov/regulations-and-guidance/legislation/cfr", "name": "cms.gov/regulations-and-guidance/legislation/cfr"},),
    ),
    RegulationDef(
        key="pain_management_opioid_prescribing",
        category="clinical_safety",
        name="Pain Management & Opioid Prescribing",
        description="CDC clinical practice guidelines; state prescribing limits; PDMP check requirements; mandatory prescriber education",
        enforcing_agency="CDC / State Medical Boards",
        state_variance="High",
        update_frequency="CDC guidelines updated 2022; state laws update annually",
        authority_sources=(
            {"domain": "cdc.gov/opioids/healthcare-professionals/prescribing", "name": "cdc.gov/opioids/healthcare-professionals/prescribing"},
            {"domain": "each state medical board", "name": "each state medical board"},
        ),
    ),
    RegulationDef(
        key="antimicrobial_stewardship_programs",
        category="clinical_safety",
        name="Antimicrobial Stewardship Programs",
        description="CMS CoP requirement for hospitals; Joint Commission standards; CDC Core Elements",
        enforcing_agency="CMS / CDC",
        state_variance="Moderate",
        update_frequency="CDC Core Elements updated every 2–3 yrs; CMS CoP updated less frequently",
        authority_sources=({"domain": "cdc.gov/antibiotic-use/core-elements", "name": "cdc.gov/antibiotic-use/core-elements"},),
    ),
    RegulationDef(
        key="medical_staff_credentialing_privileging",
        category="healthcare_workforce",
        name="Medical Staff Credentialing & Privileging",
        description="Verification of education, training, licensure, board cert, malpractice history; initial and reappointment per CMS CoPs",
        enforcing_agency="CMS / Joint Commission / State",
        state_variance="Moderate",
        update_frequency="Accreditation standards updated annually; CMS CoPs every 3–5 yrs",
        authority_sources=(
            {"domain": "jointcommission.org/standards", "name": "jointcommission.org/standards"},
            {"domain": "cms.gov/medicare/provider-enrollment-and-certification", "name": "cms.gov/medicare/provider-enrollment-and-certification"},
        ),
    ),
    RegulationDef(
        key="provider_licensure_scope_of_practice",
        category="healthcare_workforce",
        name="Provider Licensure & Scope of Practice",
        description="State-specific licensing for physicians, nurses, PAs, NPs, allied health; scope of practice boundaries",
        enforcing_agency="State Licensing Boards",
        state_variance="High",
        update_frequency="Continuous — scope of practice bills introduced every legislative session",
        authority_sources=(
            {"domain": "Each state licensing board", "name": "Each state licensing board"},
            {"domain": "ncsbn.org", "name": "nursing"},
            {"domain": "fsmb.org", "name": "medicine"},
        ),
    ),
    RegulationDef(
        key="oig_exclusion_list_screening",
        category="healthcare_workforce",
        name="OIG Exclusion List (LEIE) Screening",
        description="Monthly screening of employees, contractors, vendors against LEIE; SAM.gov screening; immediate action for matches",
        enforcing_agency="OIG",
        state_variance="Low/None",
        update_frequency="LEIE updated monthly",
        authority_sources=(
            {"domain": "oig.hhs.gov/exclusions", "name": "oig.hhs.gov/exclusions"},
            {"domain": "sam.gov", "name": "sam.gov"},
        ),
    ),
    RegulationDef(
        key="npdb_queries",
        category="healthcare_workforce",
        name="NPDB Queries",
        description="Query NPDB for credentialing of physicians, dentists, other practitioners every 2 years minimum",
        enforcing_agency="HRSA",
        state_variance="Low/None",
        update_frequency="Database updated continuously; query requirements stable",
        authority_sources=({"domain": "npdb.hrsa.gov", "name": "npdb.hrsa.gov"},),
    ),
    RegulationDef(
        key="background_check_requirements",
        category="healthcare_workforce",
        name="Background Check Requirements",
        description="Federal requirements for long-term care; state-specific requirements for various healthcare roles",
        enforcing_agency="CMS / State",
        state_variance="High",
        update_frequency="State laws update every 1–3 yrs",
        authority_sources=(
            {"domain": "cms.gov/medicare/provider-enrollment-and-certification", "name": "cms.gov/medicare/provider-enrollment-and-certification"},
            {"domain": "each state health dept", "name": "each state health dept"},
        ),
    ),
    RegulationDef(
        key="osha_workplace_safety",
        category="healthcare_workforce",
        name="OSHA Workplace Safety (29 CFR Part 1910)",
        description="Bloodborne Pathogen Standard; hazard communication; PPE; recordkeeping; general duty clause",
        enforcing_agency="OSHA",
        state_variance="Moderate",
        update_frequency="Standards updated every 3–10 yrs; guidance documents more frequently",
        authority_sources=(
            {"domain": "osha.gov/healthcare", "name": "osha.gov/healthcare"},
            {"domain": "osha.gov/bloodborne-pathogens", "name": "osha.gov/bloodborne-pathogens"},
        ),
    ),
    RegulationDef(
        key="osha_workplace_violence_prevention",
        category="healthcare_workforce",
        name="OSHA Workplace Violence Prevention",
        description="OSHA guidelines for healthcare workers; some states mandate workplace violence prevention programs",
        enforcing_agency="OSHA / State OSHA plans",
        state_variance="High",
        update_frequency="Federal guidance updated periodically; CA SB 1299 and other state laws update actively",
        authority_sources=(
            {"domain": "osha.gov/workplace-violence", "name": "osha.gov/workplace-violence"},
            {"domain": "each state OSHA plan", "name": "each state OSHA plan"},
        ),
    ),
    RegulationDef(
        key="ada",
        category="healthcare_workforce",
        name="ADA (Americans with Disabilities Act)",
        description="Non-discrimination in employment; reasonable accommodations; applies to 15+ employee employers",
        enforcing_agency="EEOC / DOJ",
        state_variance="Moderate",
        update_frequency="ADA Amendments Act 2008; EEOC guidance updated every 2–3 yrs",
        authority_sources=(
            {"domain": "eeoc.gov/ada", "name": "eeoc.gov/ada"},
            {"domain": "ada.gov", "name": "ada.gov"},
        ),
    ),
    RegulationDef(
        key="fmla",
        category="healthcare_workforce",
        name="FMLA (Family and Medical Leave Act)",
        description="12 weeks unpaid leave for eligible employees; many states provide additional leave protections",
        enforcing_agency="DOL",
        state_variance="High",
        update_frequency="Federal FMLA stable; state paid family leave laws rapidly expanding (2020–2026)",
        authority_sources=(
            {"domain": "dol.gov/agencies/whd/fmla", "name": "dol.gov/agencies/whd/fmla"},
            {"domain": "each state labor dept", "name": "each state labor dept"},
        ),
    ),
    RegulationDef(
        key="title_vii_civil_rights_act",
        category="healthcare_workforce",
        name="Title VII / Civil Rights Act",
        description="Prohibition on discrimination based on race, color, religion, sex, national origin; sexual harassment",
        enforcing_agency="EEOC",
        state_variance="Moderate",
        update_frequency="EEOC guidance updated every 2–3 yrs; Bostock (2020) expanded sex discrimination",
        authority_sources=({"domain": "eeoc.gov/laws/statutes/titlevii", "name": "eeoc.gov/laws/statutes/titlevii"},),
    ),
    RegulationDef(
        key="section_1557_of_aca",
        category="healthcare_workforce",
        name="Section 1557 of ACA (Nondiscrimination)",
        description="Prohibits discrimination in health programs receiving federal funding; language access requirements",
        enforcing_agency="HHS OCR",
        state_variance="Low/None",
        update_frequency="Major rulemaking cycles every 3–5 yrs (2016, 2020, 2024 rules)",
        authority_sources=({"domain": "hhs.gov/civil-rights/for-individuals/section-1557", "name": "hhs.gov/civil-rights/for-individuals/section-1557"},),
    ),
    RegulationDef(
        key="flsa",
        category="healthcare_workforce",
        name="FLSA (Fair Labor Standards Act)",
        description="Minimum wage, overtime; nurse and resident physician overtime; state wage laws often more generous",
        enforcing_agency="DOL",
        state_variance="High",
        update_frequency="Federal minimum wage rarely updated; state wage laws change frequently",
        authority_sources=(
            {"domain": "dol.gov/agencies/whd/flsa", "name": "dol.gov/agencies/whd/flsa"},
            {"domain": "each state labor dept", "name": "each state labor dept"},
        ),
    ),
    RegulationDef(
        key="immigration_compliance",
        category="healthcare_workforce",
        name="Immigration Compliance (I-9 / Visa Requirements)",
        description="Employment verification; J-1 waivers for physicians; H-1B for healthcare professionals",
        enforcing_agency="DHS / USCIS / DOL",
        state_variance="Moderate",
        update_frequency="I-9 form updated every 3 yrs; visa policies shift with administrations",
        authority_sources=(
            {"domain": "uscis.gov/i-9", "name": "uscis.gov/i-9"},
            {"domain": "travel.state.gov/j-1", "name": "travel.state.gov/j-1"},
        ),
    ),
    RegulationDef(
        key="mandatory_reporting_obligations",
        category="healthcare_workforce",
        name="Mandatory Reporting Obligations",
        description="Abuse/neglect reporting (child, elder, vulnerable adult); communicable disease; gunshot/stab wound",
        enforcing_agency="State law",
        state_variance="High",
        update_frequency="Continuous — state reporting requirements update annually",
        authority_sources=(
            {"domain": "childwelfare.gov/topics/systemwide/laws-policies/statutes/manda", "name": "childwelfare.gov/topics/systemwide/laws-policies/statutes/manda"},
            {"domain": "each state legislature", "name": "each state legislature"},
        ),
    ),
    RegulationDef(
        key="continuing_education_requirements",
        category="healthcare_workforce",
        name="Continuing Education Requirements",
        description="State-specific CE/CME requirements for license renewal by profession",
        enforcing_agency="State Licensing Boards",
        state_variance="High",
        update_frequency="Updated with each license renewal cycle (1–3 yrs)",
        authority_sources=(
            {"domain": "Each state licensing board", "name": "Each state licensing board"},
            {"domain": "accme.org", "name": "physician CME"},
        ),
    ),
    RegulationDef(
        key="nurse_staffing_ratios_requirements",
        category="healthcare_workforce",
        name="Nurse Staffing Ratios & Requirements",
        description="CA mandated ratios; other states have staffing committees, disclosure requirements, or guidelines",
        enforcing_agency="State law",
        state_variance="High",
        update_frequency="Active legislative area — bills introduced each session",
        authority_sources=(
            {"domain": "Each state legislature", "name": "Each state legislature"},
            {"domain": "nursingworld.org", "name": "ANA"},
        ),
    ),
    RegulationDef(
        key="physician_residency_gme_requirements",
        category="healthcare_workforce",
        name="Physician Residency & GME Requirements",
        description="ACGME accreditation standards; duty hour restrictions; supervision requirements",
        enforcing_agency="ACGME / CMS",
        state_variance="Low/None",
        update_frequency="ACGME Common Program Requirements updated every 2–3 yrs",
        authority_sources=({"domain": "acgme.org/what-we-do/accreditation/common-program-requirements", "name": "acgme.org/what-we-do/accreditation/common-program-requirements"},),
    ),
    RegulationDef(
        key="oig_compliance_program_guidance",
        category="corporate_integrity",
        name="OIG Compliance Program Guidance",
        description="Seven elements of effective compliance: written standards, compliance officer, training, monitoring, enforcement, response, open lines",
        enforcing_agency="OIG",
        state_variance="Low/None",
        update_frequency="Original guidance 1998–2005; General Compliance Program Guidance updated 2023",
        authority_sources=({"domain": "oig.hhs.gov/compliance/compliance-guidance", "name": "oig.hhs.gov/compliance/compliance-guidance"},),
    ),
    RegulationDef(
        key="federal_sentencing_guidelines",
        category="corporate_integrity",
        name="Federal Sentencing Guidelines (§8B2.1)",
        description="Organizational sentencing factors; effective compliance program as mitigating factor; board oversight",
        enforcing_agency="U.S. Sentencing Commission",
        state_variance="Low/None",
        update_frequency="Updated annually (November amendments cycle)",
        authority_sources=({"domain": "ussc.gov/guidelines/organizational-guidelines", "name": "ussc.gov/guidelines/organizational-guidelines"},),
    ),
    RegulationDef(
        key="corporate_integrity_agreements",
        category="corporate_integrity",
        name="Corporate Integrity Agreements (CIAs)",
        description="Post-settlement compliance obligations; IRO reviews, board reporting, claims review",
        enforcing_agency="OIG",
        state_variance="Low/None",
        update_frequency="Each CIA is entity-specific; OIG publishes new CIAs as they are entered",
        authority_sources=({"domain": "oig.hhs.gov/fraud/cia", "name": "oig.hhs.gov/fraud/cia"},),
    ),
    RegulationDef(
        key="whistleblower_protections",
        category="corporate_integrity",
        name="Whistleblower Protections (FCA Qui Tam)",
        description="Protection from retaliation for reporting fraud; 15–30% reward; sealed filing",
        enforcing_agency="DOJ",
        state_variance="Moderate",
        update_frequency="Rarely amended; DOJ policy memos update enforcement priorities",
        authority_sources=({"domain": "justice.gov/civil/fraud/whistleblower", "name": "justice.gov/civil/fraud/whistleblower"},),
    ),
    RegulationDef(
        key="state_whistleblower_protection_laws",
        category="corporate_integrity",
        name="State Whistleblower Protection Laws",
        description="Many states have additional protections beyond federal FCA provisions",
        enforcing_agency="State AGs / Courts",
        state_variance="High",
        update_frequency="Updated via state legislation 1–3 yrs",
        authority_sources=(
            {"domain": "Each state legislature", "name": "Each state legislature"},
            {"domain": "taf.org", "name": "Taxpayers Against Fraud"},
        ),
    ),
    RegulationDef(
        key="deficit_reduction_act_of_2005",
        category="corporate_integrity",
        name="Deficit Reduction Act of 2005 (§6032)",
        description="Entities with $5M+ Medicaid must educate employees about FCA, whistleblower protections",
        enforcing_agency="CMS / State",
        state_variance="Moderate",
        update_frequency="Enacted 2005; rarely amended",
        authority_sources=({"domain": "oig.hhs.gov/compliance/101/files/DRA-Fact-Sheet.pdf", "name": "oig.hhs.gov/compliance/101/files/DRA-Fact-Sheet.pdf"},),
    ),
    RegulationDef(
        key="code_of_conduct_conflict_of_interest",
        category="corporate_integrity",
        name="Code of Conduct & Conflict of Interest",
        description="Expected by OIG, accreditors, payer contracts; board/physician financial disclosure",
        enforcing_agency="OIG / Accreditors",
        state_variance="Low/None",
        update_frequency="Internal policies updated annually; OIG expectations stable",
        authority_sources=({"domain": "oig.hhs.gov/compliance/compliance-guidance", "name": "oig.hhs.gov/compliance/compliance-guidance"},),
    ),
    RegulationDef(
        key="compliance_committee_board_oversight",
        category="corporate_integrity",
        name="Compliance Committee & Board Oversight",
        description="OIG expects board-level compliance oversight; quality/compliance committee reporting to board",
        enforcing_agency="OIG / Accreditors",
        state_variance="Low/None",
        update_frequency="OIG General CPG (2023) reinforced board oversight expectations",
        authority_sources=({"domain": "oig.hhs.gov/compliance/compliance-guidance", "name": "oig.hhs.gov/compliance/compliance-guidance"},),
    ),
    RegulationDef(
        key="internal_investigations_disclosure_protocols",
        category="corporate_integrity",
        name="Internal Investigations & Disclosure Protocols",
        description="Self-disclosure protocols (OIG SDP, CMS SRDP); internal investigation procedures; privilege considerations",
        enforcing_agency="OIG / CMS / DOJ",
        state_variance="Low/None",
        update_frequency="OIG SDP guidance updated every 2–3 yrs; CMS SRDP protocol updated periodically",
        authority_sources=(
            {"domain": "oig.hhs.gov/compliance/self-disclosure-info", "name": "oig.hhs.gov/compliance/self-disclosure-info"},
            {"domain": "cms.gov/medicare/coordination-of-benefits-and-recovery/debt-recovery", "name": "cms.gov/medicare/coordination-of-benefits-and-recovery/debt-recovery"},
        ),
    ),
    RegulationDef(
        key="21st_century_cures_act_information_blocking",
        category="health_it",
        name="21st Century Cures Act — Information Blocking (45 CFR Part 171)",
        description="Prohibition on practices interfering with access/exchange of EHI; eight exceptions; applies to providers, HINs, HIT developers",
        enforcing_agency="ONC / OIG",
        state_variance="Low/None",
        update_frequency="Initial rule 2021; OIG penalties finalized 2023; updates every 2–3 yrs",
        authority_sources=(
            {"domain": "healthit.gov/topic/information-blocking", "name": "healthit.gov/topic/information-blocking"},
            {"domain": "federalregister.gov", "name": "federalregister.gov"},
        ),
    ),
    RegulationDef(
        key="onc_health_it_certification",
        category="health_it",
        name="ONC Health IT Certification (45 CFR Part 170)",
        description="Certification requirements for EHR technology; USCDI data standards; API requirements",
        enforcing_agency="ONC",
        state_variance="Low/None",
        update_frequency="HTI-1 final rule 2024; USCDI updated annually",
        authority_sources=(
            {"domain": "healthit.gov/topic/certification-ehrs/certification-health-it", "name": "healthit.gov/topic/certification-ehrs/certification-health-it"},
            {"domain": "healthit.gov/isa/united-states-core-data-interoperability-uscdi", "name": "healthit.gov/isa/united-states-core-data-interoperability-uscdi"},
        ),
    ),
    RegulationDef(
        key="cms_interoperability_patient_access_rules",
        category="health_it",
        name="CMS Interoperability & Patient Access Rules",
        description="Patient access API, provider directory API, payer-to-payer exchange, prior auth API",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="CMS-9115-F (2020); CMS-0057-F (2024); updates every 2–3 yrs",
        authority_sources=({"domain": "cms.gov/priorities/key-initiatives/burden-reduction/interoperability", "name": "cms.gov/priorities/key-initiatives/burden-reduction/interoperability"},),
    ),
    RegulationDef(
        key="meaningful_use_promoting_interoperability",
        category="health_it",
        name="Meaningful Use / Promoting Interoperability",
        description="EHR incentive program; now part of MIPS; e-prescribing, HIE, patient portal access",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Annual updates via MPFS/IPPS final rules",
        authority_sources=({"domain": "cms.gov/regulations-and-guidance/legislation/ehrincentiveprograms", "name": "cms.gov/regulations-and-guidance/legislation/ehrincentiveprograms"},),
    ),
    RegulationDef(
        key="hl7_fhir_uscdi_standards",
        category="health_it",
        name="HL7 FHIR & USCDI Standards",
        description="Technical standards for health data exchange; USCDI v1–v4 data classes; FHIR R4 API implementation",
        enforcing_agency="ONC / HL7",
        state_variance="Low/None",
        update_frequency="USCDI updated annually; FHIR versions every 2–3 yrs",
        authority_sources=(
            {"domain": "hl7.org/fhir", "name": "hl7.org/fhir"},
            {"domain": "healthit.gov/isa/united-states-core-data-interoperability-uscdi", "name": "healthit.gov/isa/united-states-core-data-interoperability-uscdi"},
        ),
    ),
    RegulationDef(
        key="eprescribing_for_controlled_substances",
        category="health_it",
        name="E-Prescribing for Controlled Substances (EPCS)",
        description="DEA requirements for e-prescribing Schedule II–V; identity proofing; two-factor authentication",
        enforcing_agency="DEA",
        state_variance="High",
        update_frequency="DEA interim final rule 2010; state mandates expanding rapidly",
        authority_sources=(
            {"domain": "deadiversion.usdoj.gov/ecomm/e_rx", "name": "deadiversion.usdoj.gov/ecomm/e_rx"},
            {"domain": "each state pharmacy board", "name": "each state pharmacy board"},
        ),
    ),
    RegulationDef(
        key="state_hie_requirements",
        category="health_it",
        name="State HIE Requirements",
        description="Some states mandate HIE connection; varying consent models (opt-in/opt-out); data submission requirements",
        enforcing_agency="State HIT offices",
        state_variance="High",
        update_frequency="Varies by state; updated with state legislation/regulation",
        authority_sources=(
            {"domain": "Each state HIT/HIE organization", "name": "Each state HIT/HIE organization"},
            {"domain": "healthit.gov/topic/health-it-health-care-settings/health-information-exchange", "name": "healthit.gov/topic/health-it-health-care-settings/health-information-exchange"},
        ),
    ),
    RegulationDef(
        key="electronic_signatures",
        category="health_it",
        name="Electronic Signatures (ESIGN / UETA)",
        description="Federal and state frameworks for electronic signature validity in healthcare",
        enforcing_agency="Federal / State",
        state_variance="Moderate",
        update_frequency="ESIGN (2000) rarely amended; state UETA adoptions vary",
        authority_sources=(
            {"domain": "ftc.gov/legal-library/browse/statutes/electronic-signatures-global-national-commerce-act", "name": "ftc.gov/legal-library/browse/statutes/electronic-signatures-global-national-commerce-act"},
            {"domain": "uniformlaws.org", "name": "uniformlaws.org"},
        ),
    ),
    RegulationDef(
        key="21_cfr_part_11",
        category="health_it",
        name="21 CFR Part 11 (Electronic Records in FDA-Regulated Activities)",
        description="FDA requirements for e-records and e-signatures in trials, device manufacturing, pharma operations",
        enforcing_agency="FDA",
        state_variance="Low/None",
        update_frequency="Original 1997; FDA guidance documents updated periodically",
        authority_sources=({"domain": "fda.gov/regulatory-information/search-fda-guidance-documents/part-11-electronic-records-electronic-signatures", "name": "fda.gov/regulatory-information/search-fda-guidance-documents/part-11-electronic-records-electronic-signatures"},),
    ),
    RegulationDef(
        key="telehealth_technology_standards",
        category="health_it",
        name="Telehealth Technology Standards",
        description="Platform security, audio/video standards, interstate licensing (IMLC, NLC), prescribing via telehealth",
        enforcing_agency="CMS / State Boards / DEA",
        state_variance="High",
        update_frequency="Rapidly evolving post-COVID; state laws update each legislative session",
        authority_sources=(
            {"domain": "cchpca.org", "name": "Center for Connected Health Policy"},
            {"domain": "each state medical board", "name": "each state medical board"},
        ),
    ),
    RegulationDef(
        key="mips_qpp",
        category="quality_reporting",
        name="MIPS / QPP",
        description="Quality, cost, promoting interoperability, improvement activities; payment adjustments based on composite scores",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Annual updates via MPFS final rule (November)",
        authority_sources=(
            {"domain": "qpp.cms.gov", "name": "qpp.cms.gov"},
            {"domain": "cms.gov/medicare/quality/physicians", "name": "cms.gov/medicare/quality/physicians"},
        ),
    ),
    RegulationDef(
        key="advanced_apms",
        category="quality_reporting",
        name="Advanced APMs",
        description="Shared savings/risk models (ACOs, bundled payments); QP thresholds",
        enforcing_agency="CMS / CMMI",
        state_variance="Low/None",
        update_frequency="Updated annually; CMMI model-specific updates ongoing",
        authority_sources=(
            {"domain": "qpp.cms.gov", "name": "qpp.cms.gov"},
            {"domain": "innovation.cms.gov", "name": "innovation.cms.gov"},
        ),
    ),
    RegulationDef(
        key="hospital_iqr_program",
        category="quality_reporting",
        name="Hospital IQR Program",
        description="Mandatory quality measure reporting for IPPS hospitals; pay reduction for non-reporting",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Annual measure updates via IPPS final rule (August)",
        authority_sources=({"domain": "cms.gov/medicare/quality/inpatient-quality-reporting", "name": "cms.gov/medicare/quality/inpatient-quality-reporting"},),
    ),
    RegulationDef(
        key="hospital_oqr_program",
        category="quality_reporting",
        name="Hospital OQR Program",
        description="Quality measures for OPPS hospitals",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Annual updates via OPPS final rule (November)",
        authority_sources=({"domain": "cms.gov/medicare/quality/outpatient-quality-reporting", "name": "cms.gov/medicare/quality/outpatient-quality-reporting"},),
    ),
    RegulationDef(
        key="hospital_vbp_program",
        category="quality_reporting",
        name="Hospital VBP Program",
        description="Payment incentives based on outcomes, patient experience (HCAHPS), safety, efficiency",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Annual domain/measure updates via IPPS final rule",
        authority_sources=({"domain": "cms.gov/medicare/quality/value-based-programs/hospital-purchasing", "name": "cms.gov/medicare/quality/value-based-programs/hospital-purchasing"},),
    ),
    RegulationDef(
        key="hac_reduction_program",
        category="quality_reporting",
        name="HAC Reduction Program",
        description="Payment penalties for hospitals in worst quartile for hospital-acquired conditions",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Annual measure/methodology updates via IPPS final rule",
        authority_sources=({"domain": "cms.gov/medicare/quality/value-based-programs/hac-reduction-program", "name": "cms.gov/medicare/quality/value-based-programs/hac-reduction-program"},),
    ),
    RegulationDef(
        key="hospital_readmissions_reduction_program",
        category="quality_reporting",
        name="Hospital Readmissions Reduction Program",
        description="Payment penalties for excess readmissions for specified conditions",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Annual updates via IPPS final rule",
        authority_sources=({"domain": "cms.gov/medicare/quality/value-based-programs/hospital-readmissions-reduction-program", "name": "cms.gov/medicare/quality/value-based-programs/hospital-readmissions-reduction-program"},),
    ),
    RegulationDef(
        key="snf_quality_reporting_program",
        category="quality_reporting",
        name="SNF Quality Reporting Program",
        description="Quality measures and staffing data for skilled nursing facilities",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Annual updates via SNF PPS final rule",
        authority_sources=({"domain": "cms.gov/medicare/quality/nursing-home-improvement/quality-reporting-program", "name": "cms.gov/medicare/quality/nursing-home-improvement/quality-reporting-program"},),
    ),
    RegulationDef(
        key="home_health_quality_reporting",
        category="quality_reporting",
        name="Home Health Quality Reporting",
        description="OASIS data submission; quality measures for home health agencies",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Annual updates via HH PPS final rule",
        authority_sources=({"domain": "cms.gov/medicare/quality/home-health-quality-reporting-program", "name": "cms.gov/medicare/quality/home-health-quality-reporting-program"},),
    ),
    RegulationDef(
        key="hedis_measures",
        category="quality_reporting",
        name="HEDIS Measures",
        description="Standardized quality measures used by health plans; payer contracts and Star Ratings",
        enforcing_agency="NCQA",
        state_variance="Low/None",
        update_frequency="Updated annually (HEDIS measurement year cycle)",
        authority_sources=({"domain": "ncqa.org/hedis", "name": "ncqa.org/hedis"},),
    ),
    RegulationDef(
        key="cms_star_ratings",
        category="quality_reporting",
        name="CMS Star Ratings",
        description="Public quality ratings for MA plans and hospitals",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Methodology updated annually; ratings published annually",
        authority_sources=({"domain": "cms.gov/medicare/quality/medicare-advantage-part-c-and-d-star-ratings-program", "name": "cms.gov/medicare/quality/medicare-advantage-part-c-and-d-star-ratings-program"},),
    ),
    RegulationDef(
        key="state_quality_reporting_mandates",
        category="quality_reporting",
        name="State Quality Reporting Mandates",
        description="Some states have additional quality reporting, public reporting, and P4P programs",
        enforcing_agency="State Health Depts",
        state_variance="High",
        update_frequency="Varies by state; updated via state legislation/regulation",
        authority_sources=(
            {"domain": "Each state health dept", "name": "Each state health dept"},
            {"domain": "nashp.org", "name": "National Academy for State Health Policy"},
        ),
    ),
    RegulationDef(
        key="hipaa_security_rule_cybersecurity",
        category="cybersecurity",
        name="HIPAA Security Rule (Technical Details)",
        description="Risk analysis, access management, audit controls, integrity, transmission security, encryption, contingency planning",
        enforcing_agency="HHS OCR",
        state_variance="Low/None",
        update_frequency="Major update proposed 2024 (NPRM); finalization expected 2025–2026",
        authority_sources=(
            {"domain": "hhs.gov/hipaa/for-professionals/security", "name": "hhs.gov/hipaa/for-professionals/security"},
            {"domain": "federalregister.gov", "name": "federalregister.gov"},
        ),
    ),
    RegulationDef(
        key="nist_cybersecurity_framework",
        category="cybersecurity",
        name="NIST Cybersecurity Framework (CSF 2.0)",
        description="Identify, Protect, Detect, Respond, Recover, Govern; increasingly expected by HHS",
        enforcing_agency="NIST / HHS",
        state_variance="Low/None",
        update_frequency="CSF 2.0 released Feb 2024; major revisions every 5–7 yrs",
        authority_sources=({"domain": "nist.gov/cyberframework", "name": "nist.gov/cyberframework"},),
    ),
    RegulationDef(
        key="hhs_healthcare_cybersecurity_performance_goals",
        category="cybersecurity",
        name="HHS Healthcare Cybersecurity Performance Goals (HPH CPGs)",
        description="Essential and enhanced goals: asset inventory, email security, MFA, vulnerability management, incident planning",
        enforcing_agency="HHS / CISA",
        state_variance="Low/None",
        update_frequency="Initial publication 2024; expected to update annually",
        authority_sources=({"domain": "hhs.gov/cybersecurity-performance-goals", "name": "hhs.gov/cybersecurity-performance-goals"},),
    ),
    RegulationDef(
        key="cisa_healthcare_guidance",
        category="cybersecurity",
        name="CISA Healthcare Guidance",
        description="Sector-specific guidance; KEV catalog; critical infrastructure designation",
        enforcing_agency="CISA",
        state_variance="Low/None",
        update_frequency="Continuous — advisories and alerts published as needed",
        authority_sources=(
            {"domain": "cisa.gov/healthcare", "name": "cisa.gov/healthcare"},
            {"domain": "cisa.gov/known-exploited-vulnerabilities-catalog", "name": "cisa.gov/known-exploited-vulnerabilities-catalog"},
        ),
    ),
    RegulationDef(
        key="circia",
        category="cybersecurity",
        name="CIRCIA (Cyber Incident Reporting)",
        description="Upcoming mandatory 72-hour reporting for critical infrastructure including healthcare",
        enforcing_agency="CISA",
        state_variance="Low/None",
        update_frequency="Final rule expected 2025–2026; NPRM published 2024",
        authority_sources=({"domain": "cisa.gov/circia", "name": "cisa.gov/circia"},),
    ),
    RegulationDef(
        key="state_data_breach_notification_laws",
        category="cybersecurity",
        name="State Data Breach Notification Laws",
        description="All 50 states have laws; varying definitions, timelines, AG notice requirements",
        enforcing_agency="State AGs",
        state_variance="High",
        update_frequency="Active legislative area — updates every 1–2 yrs per state",
        authority_sources=(
            {"domain": "ncsl.org/technology-and-telecommunication/security-breach-notification-laws", "name": "ncsl.org/technology-and-telecommunication/security-breach-notification-laws"},
            {"domain": "each state AG", "name": "each state AG"},
        ),
    ),
    RegulationDef(
        key="state_cybersecurity_requirements",
        category="cybersecurity",
        name="State Cybersecurity Requirements",
        description="NY SHIELD Act, CA CCPA technical safeguards, MA 201 CMR 17.00, etc.",
        enforcing_agency="State regulators",
        state_variance="High",
        update_frequency="Evolving rapidly; new state laws enacted annually",
        authority_sources=(
            {"domain": "Each state legislature", "name": "Each state legislature"},
            {"domain": "ncsl.org/technology-and-telecommunication/cybersecurity-legislation", "name": "ncsl.org/technology-and-telecommunication/cybersecurity-legislation"},
        ),
    ),
    RegulationDef(
        key="medical_device_cybersecurity",
        category="cybersecurity",
        name="Medical Device Cybersecurity (Section 524B FD&C Act)",
        description="Pre-market cybersecurity for connected devices; SBOM requirements; post-market patching",
        enforcing_agency="FDA",
        state_variance="Low/None",
        update_frequency="Enacted 2023; FDA guidance updated periodically",
        authority_sources=({"domain": "fda.gov/medical-devices/digital-health-center-excellence/cybersecurity", "name": "fda.gov/medical-devices/digital-health-center-excellence/cybersecurity"},),
    ),
    RegulationDef(
        key="ransomware_cyber_extortion_response",
        category="cybersecurity",
        name="Ransomware & Cyber Extortion Response",
        description="HIPAA obligations during ransomware; OCR enforcement for failure to prevent/respond",
        enforcing_agency="HHS OCR / FBI / CISA",
        state_variance="Low/None",
        update_frequency="HHS/CISA guidance updated as threat landscape evolves",
        authority_sources=(
            {"domain": "hhs.gov/hipaa/for-professionals/security/guidance/cybersecurity", "name": "hhs.gov/hipaa/for-professionals/security/guidance/cybersecurity"},
            {"domain": "ic3.gov", "name": "ic3.gov"},
        ),
    ),
    RegulationDef(
        key="cms_life_safety_code",
        category="environmental_safety",
        name="CMS Life Safety Code (NFPA 101)",
        description="Fire safety for healthcare occupancies; egress, alarms, sprinklers, smoke compartments",
        enforcing_agency="CMS / State Fire Marshal",
        state_variance="Moderate",
        update_frequency="CMS adopts NFPA editions every 5–10 yrs; NFPA updates every 3 yrs",
        authority_sources=(
            {"domain": "nfpa.org/101", "name": "nfpa.org/101"},
            {"domain": "cms.gov/medicare/provider-enrollment-and-certification/fire-safety", "name": "cms.gov/medicare/provider-enrollment-and-certification/fire-safety"},
        ),
    ),
    RegulationDef(
        key="nfpa_99",
        category="environmental_safety",
        name="NFPA 99 (Health Care Facilities Code)",
        description="Medical gas systems, electrical systems, HVAC, emergency power",
        enforcing_agency="CMS / Joint Commission",
        state_variance="Low/None",
        update_frequency="NFPA 99 updated every 3 yrs",
        authority_sources=({"domain": "nfpa.org/99", "name": "nfpa.org/99"},),
    ),
    RegulationDef(
        key="ada_accessibility_standards",
        category="environmental_safety",
        name="ADA Accessibility Standards",
        description="Physical accessibility: parking, entrances, exam rooms, equipment",
        enforcing_agency="DOJ",
        state_variance="Moderate",
        update_frequency="2010 ADA Standards; DOJ guidance updated periodically",
        authority_sources=(
            {"domain": "ada.gov", "name": "ada.gov"},
            {"domain": "access-board.gov", "name": "access-board.gov"},
        ),
    ),
    RegulationDef(
        key="epa_medical_waste",
        category="environmental_safety",
        name="EPA Medical Waste (RCRA)",
        description="Hazardous waste ID, storage, transport, disposal; pharmaceutical waste rules",
        enforcing_agency="EPA / State environmental agencies",
        state_variance="High",
        update_frequency="Federal RCRA updates every 3–5 yrs; state regs vary widely",
        authority_sources=(
            {"domain": "epa.gov/rcra", "name": "epa.gov/rcra"},
            {"domain": "epa.gov/hwgenerators/management-pharmaceutical-hazardous-waste", "name": "epa.gov/hwgenerators/management-pharmaceutical-hazardous-waste"},
        ),
    ),
    RegulationDef(
        key="osha_hazardous_chemical_standards",
        category="environmental_safety",
        name="OSHA Hazardous Chemical Standards",
        description="Hazard Communication (GHS); formaldehyde; ethylene oxide; chemotherapy drugs",
        enforcing_agency="OSHA",
        state_variance="Moderate",
        update_frequency="Standards updated every 5–10 yrs; guidance documents more frequently",
        authority_sources=({"domain": "osha.gov/hazardous-chemicals", "name": "osha.gov/hazardous-chemicals"},),
    ),
    RegulationDef(
        key="osha_ionizing_radiation",
        category="environmental_safety",
        name="OSHA Ionizing Radiation (29 CFR 1910.1096)",
        description="Occupational exposure limits, monitoring, signage, restricted areas",
        enforcing_agency="OSHA / NRC / State",
        state_variance="Moderate",
        update_frequency="Federal standards rarely updated; state radiation programs update more frequently",
        authority_sources=(
            {"domain": "osha.gov/ionizing-radiation", "name": "osha.gov/ionizing-radiation"},
            {"domain": "nrc.gov", "name": "nrc.gov"},
        ),
    ),
    RegulationDef(
        key="state_radiation_control_programs",
        category="environmental_safety",
        name="State Radiation Control Programs",
        description="Licensing/inspection of radiation equipment; personnel monitoring; shielding",
        enforcing_agency="State Radiation Control",
        state_variance="High",
        update_frequency="Updated via state regulation every 1–3 yrs",
        authority_sources=(
            {"domain": "crcpd.org", "name": "Conference of Radiation Control Program Directors"},
            {"domain": "each state radiation control program", "name": "each state radiation control program"},
        ),
    ),
    RegulationDef(
        key="legionella_water_management",
        category="environmental_safety",
        name="Legionella / Water Management",
        description="CMS memo requiring water management programs; ASHRAE 188",
        enforcing_agency="CMS / State Health Depts",
        state_variance="Moderate",
        update_frequency="CMS memo 2017; ASHRAE 188 updated every 5 yrs",
        authority_sources=(
            {"domain": "cms.gov/medicare/provider-enrollment-and-certification", "name": "cms.gov/medicare/provider-enrollment-and-certification"},
            {"domain": "ashrae.org", "name": "ashrae.org"},
        ),
    ),
    RegulationDef(
        key="sharps_needlestick_prevention",
        category="environmental_safety",
        name="Sharps & Needlestick Prevention",
        description="Engineering controls, exposure control plans, sharps injury logs",
        enforcing_agency="OSHA",
        state_variance="Low/None",
        update_frequency="Needlestick Safety Act 2000; OSHA guidance updated periodically",
        authority_sources=({"domain": "osha.gov/bloodborne-pathogens/needlestick", "name": "osha.gov/bloodborne-pathogens/needlestick"},),
    ),
    RegulationDef(
        key="construction_renovation",
        category="environmental_safety",
        name="Construction & Renovation (ICRA/FGI)",
        description="Infection Control Risk Assessment; FGI Guidelines for hospital design/construction",
        enforcing_agency="Joint Commission / State",
        state_variance="Moderate",
        update_frequency="FGI Guidelines updated every 4–5 yrs (2022 edition current)",
        authority_sources=({"domain": "fgiguidelines.org", "name": "fgiguidelines.org"},),
    ),
    RegulationDef(
        key="cms_emergency_preparedness_rule",
        category="emergency_preparedness",
        name="CMS Emergency Preparedness Rule (42 CFR 482, 483, 484, 485, 486, 491)",
        description="Risk assessment, emergency plan, policies/procedures, communication plan, annual training/testing",
        enforcing_agency="CMS",
        state_variance="Moderate",
        update_frequency="Final rule 2016; Interpretive Guidelines updated periodically",
        authority_sources=({"domain": "cms.gov/medicare/provider-enrollment-and-certification/emergency-preparedness", "name": "cms.gov/medicare/provider-enrollment-and-certification/emergency-preparedness"},),
    ),
    RegulationDef(
        key="emtala_emergency_obligations",
        category="emergency_preparedness",
        name="EMTALA Emergency Obligations",
        description="Screening/stabilization during declared emergencies; surge capacity",
        enforcing_agency="CMS / OIG",
        state_variance="Low/None",
        update_frequency="Guidance updated after major events (e.g., COVID, hurricanes)",
        authority_sources=({"domain": "cms.gov/medicare/provider-enrollment-and-certification", "name": "cms.gov/medicare/provider-enrollment-and-certification"},),
    ),
    RegulationDef(
        key="hospital_preparedness_program",
        category="emergency_preparedness",
        name="Hospital Preparedness Program (HPP)",
        description="ASPR cooperative agreement; healthcare coalition participation; surge benchmarks",
        enforcing_agency="ASPR / HHS",
        state_variance="Moderate",
        update_frequency="Funding guidance updated annually; capabilities updated every 2–3 yrs",
        authority_sources=({"domain": "phe.gov/preparedness/planning/hpp", "name": "phe.gov/preparedness/planning/hpp"},),
    ),
    RegulationDef(
        key="nims_hics",
        category="emergency_preparedness",
        name="NIMS / HICS",
        description="Standardized incident management; required for federal preparedness funding",
        enforcing_agency="FEMA / ASPR",
        state_variance="Low/None",
        update_frequency="NIMS updated every 5–10 yrs; HICS updated periodically",
        authority_sources=(
            {"domain": "fema.gov/nims", "name": "fema.gov/nims"},
            {"domain": "emsa.ca.gov/hospital-incident-command-system", "name": "emsa.ca.gov/hospital-incident-command-system"},
        ),
    ),
    RegulationDef(
        key="state_emergency_preparedness_requirements",
        category="emergency_preparedness",
        name="State Emergency Preparedness Requirements",
        description="State-specific hospital emergency plans, evacuation plans, mutual aid",
        enforcing_agency="State Health Depts / EM",
        state_variance="High",
        update_frequency="Updated via state regulation and post-event lessons learned",
        authority_sources=({"domain": "Each state health dept and emergency management agency", "name": "Each state health dept and emergency management agency"},),
    ),
    RegulationDef(
        key="pandemic_preparedness",
        category="emergency_preparedness",
        name="Pandemic Preparedness",
        description="Crisis Standards of Care; PPE stockpiling; ventilator allocation; vaccination distribution",
        enforcing_agency="HHS / CDC / State",
        state_variance="High",
        update_frequency="Active post-COVID rulemaking and guidance development",
        authority_sources=(
            {"domain": "cdc.gov/prepare-your-health", "name": "cdc.gov/prepare-your-health"},
            {"domain": "phe.gov/preparedness", "name": "phe.gov/preparedness"},
        ),
    ),
    RegulationDef(
        key="mass_casualty_active_shooter",
        category="emergency_preparedness",
        name="Mass Casualty / Active Shooter",
        description="Joint Commission requirements; active shooter training; behavioral threat assessment",
        enforcing_agency="Joint Commission / State",
        state_variance="Moderate",
        update_frequency="Joint Commission standards updated annually; DHS guidance periodic",
        authority_sources=(
            {"domain": "jointcommission.org", "name": "jointcommission.org"},
            {"domain": "cisa.gov/active-shooter-preparedness", "name": "cisa.gov/active-shooter-preparedness"},
        ),
    ),
    RegulationDef(
        key="common_rule",
        category="research_consent",
        name="Common Rule (45 CFR Part 46)",
        description="Federal policy for human subjects; IRB requirements; informed consent; vulnerable populations",
        enforcing_agency="OHRP / HHS",
        state_variance="Low/None",
        update_frequency="Revised 2018 (effective 2019); next update uncertain",
        authority_sources=({"domain": "hhs.gov/ohrp/regulations-and-policy/regulations/45-cfr-46", "name": "hhs.gov/ohrp/regulations-and-policy/regulations/45-cfr-46"},),
    ),
    RegulationDef(
        key="fda_human_subject_regs",
        category="research_consent",
        name="FDA Human Subject Regs (21 CFR Parts 50, 56)",
        description="Additional protections for FDA-regulated research; IND/IDE requirements",
        enforcing_agency="FDA",
        state_variance="Low/None",
        update_frequency="Updated every 3–5 yrs; FDA guidance documents more frequent",
        authority_sources=({"domain": "fda.gov/regulatory-information/search-fda-guidance-documents", "name": "fda.gov/regulatory-information/search-fda-guidance-documents"},),
    ),
    RegulationDef(
        key="good_clinical_practice",
        category="research_consent",
        name="Good Clinical Practice (ICH E6 R2/R3)",
        description="International standard for clinical trial design, conduct, recording, reporting",
        enforcing_agency="FDA / ICH",
        state_variance="Low/None",
        update_frequency="ICH E6 R3 in development (draft 2023); major revisions every 10 yrs",
        authority_sources=(
            {"domain": "ich.org/page/efficacy-guidelines", "name": "ich.org/page/efficacy-guidelines"},
            {"domain": "fda.gov/science-research/clinical-trials-and-human-subject-protection", "name": "fda.gov/science-research/clinical-trials-and-human-subject-protection"},
        ),
    ),
    RegulationDef(
        key="21_cfr_part_11_research_consent",
        category="research_consent",
        name="21 CFR Part 11 (E-Records & E-Signatures)",
        description="Electronic data capture, audit trails, e-signatures in FDA-regulated research",
        enforcing_agency="FDA",
        state_variance="Low/None",
        update_frequency="Original 1997; FDA guidance documents updated periodically",
        authority_sources=({"domain": "fda.gov/regulatory-information/search-fda-guidance-documents/part-11-electronic-records-electronic-signatures", "name": "fda.gov/regulatory-information/search-fda-guidance-documents/part-11-electronic-records-electronic-signatures"},),
    ),
    RegulationDef(
        key="clinicaltrialsgov_registration",
        category="research_consent",
        name="ClinicalTrials.gov Registration (42 CFR Part 11)",
        description="Mandatory registration of applicable trials; results reporting within 12 months",
        enforcing_agency="NIH / FDA",
        state_variance="Low/None",
        update_frequency="Final rule 2016; ClinicalTrials.gov modernization ongoing",
        authority_sources=(
            {"domain": "clinicaltrials.gov", "name": "clinicaltrials.gov"},
            {"domain": "prsinfo.clinicaltrials.gov", "name": "prsinfo.clinicaltrials.gov"},
        ),
    ),
    RegulationDef(
        key="nih_grants_policy_compliance",
        category="research_consent",
        name="NIH Grants Policy & Compliance",
        description="FCOI (42 CFR Part 50 Subpart F); data sharing; RCR training; Public Access Policy",
        enforcing_agency="NIH",
        state_variance="Low/None",
        update_frequency="NIH Grants Policy Statement updated annually; data management plans required 2023+",
        authority_sources=(
            {"domain": "grants.nih.gov/policy", "name": "grants.nih.gov/policy"},
            {"domain": "sharing.nih.gov", "name": "sharing.nih.gov"},
        ),
    ),
    RegulationDef(
        key="hipaa_research_provisions",
        category="research_consent",
        name="HIPAA Research Provisions",
        description="Research use of PHI; authorization waivers; limited data sets; de-identification",
        enforcing_agency="HHS OCR",
        state_variance="Low/None",
        update_frequency="Updated with HIPAA Privacy Rule amendments",
        authority_sources=({"domain": "hhs.gov/hipaa/for-professionals/special-topics/research", "name": "hhs.gov/hipaa/for-professionals/special-topics/research"},),
    ),
    RegulationDef(
        key="state_research_consent_laws",
        category="research_consent",
        name="State Research & Consent Laws",
        description="Additional requirements for genetic research, minors, embryonic/fetal research",
        enforcing_agency="State law",
        state_variance="High",
        update_frequency="Varies by state; updated via legislation",
        authority_sources=(
            {"domain": "Each state legislature", "name": "Each state legislature"},
            {"domain": "ohrp.hhs.gov", "name": "ohrp.hhs.gov"},
        ),
    ),
    RegulationDef(
        key="institutional_biosafety_committee",
        category="research_consent",
        name="Institutional Biosafety Committee (IBC)",
        description="NIH Guidelines for recombinant DNA, synthetic nucleic acids, select agents; BSL classifications",
        enforcing_agency="NIH / CDC / USDA",
        state_variance="Low/None",
        update_frequency="NIH Guidelines updated every 2–3 yrs",
        authority_sources=(
            {"domain": "osp.od.nih.gov/biotechnology/nih-guidelines", "name": "osp.od.nih.gov/biotechnology/nih-guidelines"},
            {"domain": "selectagents.gov", "name": "selectagents.gov"},
        ),
    ),
    RegulationDef(
        key="dea_registration_controlled_substances",
        category="pharmacy_drugs",
        name="DEA Registration & Controlled Substances (21 CFR 1301–1321)",
        description="Registration; Schedule I–V; prescribing, dispensing, administering, disposing",
        enforcing_agency="DEA",
        state_variance="Moderate",
        update_frequency="Scheduling actions ongoing; registration renewed every 3 yrs",
        authority_sources=(
            {"domain": "deadiversion.usdoj.gov", "name": "deadiversion.usdoj.gov"},
            {"domain": "ecfr.gov/current/title-21/chapter-II", "name": "ecfr.gov/current/title-21/chapter-II"},
        ),
    ),
    RegulationDef(
        key="prescription_drug_monitoring_programs",
        category="pharmacy_drugs",
        name="Prescription Drug Monitoring Programs (PDMPs)",
        description="State databases tracking controlled substance prescriptions; mandatory checking requirements vary",
        enforcing_agency="State Pharmacy Boards / BJA",
        state_variance="High",
        update_frequency="State PDMP laws updated every 1–2 yrs; all states operational",
        authority_sources=(
            {"domain": "pdmpassist.org", "name": "pdmpassist.org"},
            {"domain": "namsdl.org", "name": "namsdl.org"},
            {"domain": "each state PDMP", "name": "each state PDMP"},
        ),
    ),
    RegulationDef(
        key="drug_supply_chain_security_act",
        category="pharmacy_drugs",
        name="Drug Supply Chain Security Act (DSCSA)",
        description="Product tracing; transaction info; verification; serialization; interoperable electronic system",
        enforcing_agency="FDA",
        state_variance="Low/None",
        update_frequency="Phased implementation 2013–2023+; enforcement discretion extensions ongoing",
        authority_sources=({"domain": "fda.gov/drugs/drug-supply-chain-integrity/drug-supply-chain-security-act-dscsa", "name": "fda.gov/drugs/drug-supply-chain-integrity/drug-supply-chain-security-act-dscsa"},),
    ),
    RegulationDef(
        key="340b_drug_pricing_program",
        category="pharmacy_drugs",
        name="340B Drug Pricing Program (42 U.S.C. § 256b)",
        description="Discounted outpatient drug pricing for covered entities; contract pharmacy; HRSA audits",
        enforcing_agency="HRSA",
        state_variance="Moderate",
        update_frequency="HRSA guidance updated 1–2 yrs; active litigation reshaping program",
        authority_sources=(
            {"domain": "hrsa.gov/opa", "name": "hrsa.gov/opa"},
            {"domain": "340bopais.hrsa.gov", "name": "340bopais.hrsa.gov"},
        ),
    ),
    RegulationDef(
        key="usp_compounding_standards",
        category="pharmacy_drugs",
        name="USP Compounding Standards (<795>, <797>, <800>)",
        description="Non-sterile compounding, sterile compounding, hazardous drug handling",
        enforcing_agency="State Pharmacy Boards / CMS",
        state_variance="Moderate",
        update_frequency="USP <797> revised 2023 (enforcement delayed); chapters updated every 5–10 yrs",
        authority_sources=(
            {"domain": "usp.org/compounding", "name": "usp.org/compounding"},
            {"domain": "each state pharmacy board", "name": "each state pharmacy board"},
        ),
    ),
    RegulationDef(
        key="state_pharmacy_practice_acts",
        category="pharmacy_drugs",
        name="State Pharmacy Practice Acts",
        description="Scope of practice; technician ratios; collaborative practice; dispensing requirements",
        enforcing_agency="State Pharmacy Boards",
        state_variance="High",
        update_frequency="Updated every legislative session",
        authority_sources=(
            {"domain": "Each state pharmacy board", "name": "Each state pharmacy board"},
            {"domain": "nabp.pharmacy", "name": "nabp.pharmacy"},
        ),
    ),
    RegulationDef(
        key="fda_rems_programs",
        category="pharmacy_drugs",
        name="FDA REMS Programs",
        description="Risk Evaluation and Mitigation Strategies for high-risk drugs; iPLEDGE, TIRF, opioid REMS",
        enforcing_agency="FDA",
        state_variance="Low/None",
        update_frequency="Individual REMS modified as needed; new REMS established ongoing",
        authority_sources=(
            {"domain": "fda.gov/drugs/drug-safety-and-availability/rems", "name": "fda.gov/drugs/drug-safety-and-availability/rems"},
            {"domain": "accessdata.fda.gov/scripts/cder/rems", "name": "accessdata.fda.gov/scripts/cder/rems"},
        ),
    ),
    RegulationDef(
        key="medication_error_reporting",
        category="pharmacy_drugs",
        name="Medication Error Reporting",
        description="FDA MedWatch; ISMP reporting; state-mandated error reporting; RCA requirements",
        enforcing_agency="FDA / State",
        state_variance="Moderate",
        update_frequency="MedWatch continuous; state reporting mandates update every 2–3 yrs",
        authority_sources=(
            {"domain": "fda.gov/safety/medwatch", "name": "fda.gov/safety/medwatch"},
            {"domain": "ismp.org", "name": "ismp.org"},
        ),
    ),
    RegulationDef(
        key="pharmaceutical_waste_disposal",
        category="pharmacy_drugs",
        name="Pharmaceutical Waste Disposal",
        description="RCRA hazardous waste rules for pharmaceuticals; DEA reverse distribution for controlled substances",
        enforcing_agency="EPA / DEA / State",
        state_variance="High",
        update_frequency="EPA Management Standards for Hazardous Waste Pharmaceuticals (2019); state rules vary",
        authority_sources=(
            {"domain": "epa.gov/hwgenerators/management-pharmaceutical-hazardous-waste", "name": "epa.gov/hwgenerators/management-pharmaceutical-hazardous-waste"},
            {"domain": "deadiversion.usdoj.gov", "name": "deadiversion.usdoj.gov"},
        ),
    ),
    RegulationDef(
        key="drug_diversion_prevention",
        category="pharmacy_drugs",
        name="Drug Diversion Prevention",
        description="Monitoring and preventing controlled substance diversion; ADC audits; random testing",
        enforcing_agency="DEA / State / Joint Commission",
        state_variance="Moderate",
        update_frequency="Best practice guidance updated every 2–3 yrs; DEA enforcement continuous",
        authority_sources=(
            {"domain": "deadiversion.usdoj.gov", "name": "deadiversion.usdoj.gov"},
            {"domain": "jointcommission.org", "name": "jointcommission.org"},
        ),
    ),
    RegulationDef(
        key="medicare_advantage_compliance",
        category="payer_relations",
        name="Medicare Advantage Compliance (42 CFR Part 422)",
        description="Network adequacy; compliance programs; marketing rules; grievances/appeals; RADV audits",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Annual updates via MA Rate Announcement and Call Letter (April); final rule (fall)",
        authority_sources=({"domain": "cms.gov/medicare/health-plans/medicareadvtgspecratestats", "name": "cms.gov/medicare/health-plans/medicareadvtgspecratestats"},),
    ),
    RegulationDef(
        key="medicaid_managed_care",
        category="payer_relations",
        name="Medicaid Managed Care (42 CFR Part 438)",
        description="State plan requirements; MCO obligations; network adequacy; access standards; quality",
        enforcing_agency="CMS / State Medicaid",
        state_variance="High",
        update_frequency="Federal rule updated every 3–5 yrs; state contracts renegotiated every 1–5 yrs",
        authority_sources=(
            {"domain": "medicaid.gov/medicaid/managed-care", "name": "medicaid.gov/medicaid/managed-care"},
            {"domain": "each state Medicaid agency", "name": "each state Medicaid agency"},
        ),
    ),
    RegulationDef(
        key="aca_insurance_market_reforms",
        category="payer_relations",
        name="ACA Insurance Market Reforms",
        description="EHBs; preventive services; pre-existing conditions; premium rating rules",
        enforcing_agency="CMS / State DOIs",
        state_variance="Moderate",
        update_frequency="Annual Notice of Benefit and Payment Parameters; state benchmark plans updated periodically",
        authority_sources=(
            {"domain": "cms.gov/cciio", "name": "cms.gov/cciio"},
            {"domain": "healthcare.gov", "name": "healthcare.gov"},
        ),
    ),
    RegulationDef(
        key="erisa",
        category="payer_relations",
        name="ERISA",
        description="Governs employer-sponsored health plans; preemption; fiduciary duties; claims procedures",
        enforcing_agency="DOL",
        state_variance="Moderate",
        update_frequency="DOL guidance updated every 2–3 yrs; ERISA statute rarely amended",
        authority_sources=({"domain": "dol.gov/agencies/ebsa/laws-and-regulations/laws/erisa", "name": "dol.gov/agencies/ebsa/laws-and-regulations/laws/erisa"},),
    ),
    RegulationDef(
        key="network_adequacy_standards",
        category="payer_relations",
        name="Network Adequacy Standards",
        description="State and federal requirements for adequate networks; time/distance; wait times",
        enforcing_agency="CMS / State DOIs",
        state_variance="High",
        update_frequency="CMS updates via MA/Medicaid managed care rules; states update annually",
        authority_sources=(
            {"domain": "cms.gov", "name": "cms.gov"},
            {"domain": "each state DOI", "name": "each state DOI"},
            {"domain": "naic.org", "name": "naic.org"},
        ),
    ),
    RegulationDef(
        key="prior_authorization_requirements",
        category="payer_relations",
        name="Prior Authorization Requirements",
        description="CMS interop rule requirements; state reform laws; turnaround times; gold carding",
        enforcing_agency="CMS / State DOIs",
        state_variance="High",
        update_frequency="CMS-0057-F (2024); state prior auth reform laws expanding rapidly",
        authority_sources=(
            {"domain": "cms.gov/priorities/key-initiatives/burden-reduction", "name": "cms.gov/priorities/key-initiatives/burden-reduction"},
            {"domain": "each state legislature", "name": "each state legislature"},
            {"domain": "ama-assn.org/prior-authorization", "name": "ama-assn.org/prior-authorization"},
        ),
    ),
    RegulationDef(
        key="cvo_standards",
        category="payer_relations",
        name="CVO Standards",
        description="NCQA CVO certification; delegated credentialing; payer-specific timelines",
        enforcing_agency="NCQA / Payers",
        state_variance="Low/None",
        update_frequency="NCQA standards updated annually",
        authority_sources=({"domain": "ncqa.org/programs/health-plans/credentials-verification-organization", "name": "ncqa.org/programs/health-plans/credentials-verification-organization"},),
    ),
    RegulationDef(
        key="state_insurance_regulation",
        category="payer_relations",
        name="State Insurance Regulation",
        description="State mandates beyond ACA; prompt pay; claims processing; provider contract requirements",
        enforcing_agency="State DOIs",
        state_variance="High",
        update_frequency="Updated every legislative session",
        authority_sources=(
            {"domain": "Each state DOI", "name": "Each state DOI"},
            {"domain": "naic.org", "name": "naic.org"},
        ),
    ),
    RegulationDef(
        key="mental_health_parity",
        category="payer_relations",
        name="Mental Health Parity (MHPAEA)",
        description="Parity between MH/SUD and medical/surgical benefits; NQTL analysis requirements",
        enforcing_agency="DOL / HHS / Treasury",
        state_variance="Moderate",
        update_frequency="2024 final rule on NQTL comparative analysis; enforcement intensifying",
        authority_sources=(
            {"domain": "dol.gov/agencies/ebsa/laws-and-regulations/laws/mental-health-and-substance-use-disorder-parity", "name": "dol.gov/agencies/ebsa/laws-and-regulations/laws/mental-health-and-substance-use-disorder-parity"},
            {"domain": "cms.gov/cciio/programs-and-initiatives/other-insurance-protections/mhpaea", "name": "cms.gov/cciio/programs-and-initiatives/other-insurance-protections/mhpaea"},
        ),
    ),
    RegulationDef(
        key="postdobbs_state_abortion_laws",
        category="reproductive_behavioral",
        name="Post-Dobbs State Abortion Laws",
        description="Wide variation: total bans to codified protections; gestational limits; exceptions; provider liability; travel restrictions",
        enforcing_agency="State law",
        state_variance="High",
        update_frequency="Extremely active — multiple states pass/amend laws each session; ballot initiatives ongoing",
        authority_sources=(
            {"domain": "guttmacher.org/state-policy", "name": "guttmacher.org/state-policy"},
            {"domain": "each state legislature", "name": "each state legislature"},
            {"domain": "reproductiverights.org", "name": "reproductiverights.org"},
        ),
    ),
    RegulationDef(
        key="title_x_family_planning",
        category="reproductive_behavioral",
        name="Title X Family Planning",
        description="Federal funding for family planning; grantee compliance; patient confidentiality",
        enforcing_agency="HHS / OASH",
        state_variance="Moderate",
        update_frequency="Title X regulations updated every 2–4 yrs (administration-dependent)",
        authority_sources=({"domain": "hhs.gov/opa/title-x-family-planning", "name": "hhs.gov/opa/title-x-family-planning"},),
    ),
    RegulationDef(
        key="state_reproductive_health_privacy_laws",
        category="reproductive_behavioral",
        name="State Reproductive Health Privacy Laws",
        description="Privacy protections for reproductive health data; law enforcement access restrictions",
        enforcing_agency="State law",
        state_variance="High",
        update_frequency="Rapidly expanding post-Dobbs (2022–present)",
        authority_sources=(
            {"domain": "Each state legislature", "name": "Each state legislature"},
            {"domain": "ncsl.org/health/reproductive-health", "name": "ncsl.org/health/reproductive-health"},
        ),
    ),
    RegulationDef(
        key="42_cfr_part_2_reproductive_behavioral",
        category="reproductive_behavioral",
        name="42 CFR Part 2 (SUD Records — Detailed)",
        description="Consent, court orders, research disclosures, audit/evaluation; 2024 alignment with HIPAA for TPO",
        enforcing_agency="SAMHSA",
        state_variance="Moderate",
        update_frequency="Major 2024 final rule; next update TBD",
        authority_sources=({"domain": "samhsa.gov/about-us/who-we-are/laws-regulations/confidentiality-regulations-faqs", "name": "samhsa.gov/about-us/who-we-are/laws-regulations/confidentiality-regulations-faqs"},),
    ),
    RegulationDef(
        key="state_mental_health_commitment_laws",
        category="reproductive_behavioral",
        name="State Mental Health Commitment Laws",
        description="Involuntary holds (5150 in CA, Baker Act in FL); criteria, duration, patient rights, judicial review",
        enforcing_agency="State law",
        state_variance="High",
        update_frequency="Updated via state legislation every 1–3 yrs",
        authority_sources=(
            {"domain": "Each state legislature", "name": "Each state legislature"},
            {"domain": "treatmentadvocacycenter.org/state-laws", "name": "treatmentadvocacycenter.org/state-laws"},
        ),
    ),
    RegulationDef(
        key="state_sud_treatment_regulations",
        category="reproductive_behavioral",
        name="State SUD Treatment Regulations",
        description="Licensure of SUD facilities; MAT requirements; counselor credentialing",
        enforcing_agency="State agencies",
        state_variance="High",
        update_frequency="Updated via state regulation",
        authority_sources=(
            {"domain": "Each state substance abuse agency", "name": "Each state substance abuse agency"},
            {"domain": "samhsa.gov", "name": "samhsa.gov"},
        ),
    ),
    RegulationDef(
        key="confidentiality_of_minor_health_records",
        category="reproductive_behavioral",
        name="Confidentiality of Minor Health Records",
        description="Minor consent for STI treatment, contraception, mental health, substance use; parental notification",
        enforcing_agency="State law",
        state_variance="High",
        update_frequency="Updated via state legislation annually",
        authority_sources=(
            {"domain": "guttmacher.org/state-policy/explore/overview-minors-consent-law", "name": "guttmacher.org/state-policy/explore/overview-minors-consent-law"},
            {"domain": "each state legislature", "name": "each state legislature"},
        ),
    ),
    RegulationDef(
        key="hivaids_testing_disclosure_laws",
        category="reproductive_behavioral",
        name="HIV/AIDS Testing & Disclosure Laws",
        description="Consent for testing; disclosure restrictions; partner notification; criminalization provisions",
        enforcing_agency="State law / CDC",
        state_variance="High",
        update_frequency="State laws updated every 1–3 yrs; CDC guidelines updated periodically",
        authority_sources=(
            {"domain": "cdc.gov/hiv", "name": "cdc.gov/hiv"},
            {"domain": "each state legislature", "name": "each state legislature"},
            {"domain": "hivlawandpolicy.org", "name": "hivlawandpolicy.org"},
        ),
    ),
    RegulationDef(
        key="transgender_healthcare_regulations",
        category="reproductive_behavioral",
        name="Transgender Healthcare Regulations",
        description="Gender-affirming care restrictions/protections; minor restrictions; insurance mandates/exclusions; conscience protections",
        enforcing_agency="State law",
        state_variance="High",
        update_frequency="Extremely active legislative area (2023–2026); federal rules shifting",
        authority_sources=(
            {"domain": "Each state legislature", "name": "Each state legislature"},
            {"domain": "hrc.org/resources", "name": "hrc.org/resources"},
            {"domain": "lgbtmap.org/equality-maps", "name": "lgbtmap.org/equality-maps"},
        ),
    ),
    RegulationDef(
        key="conscience_religious_exemption_laws",
        category="reproductive_behavioral",
        name="Conscience & Religious Exemption Laws",
        description="Church/Coats-Snowe/Weldon Amendments (federal); state conscience protections",
        enforcing_agency="HHS OCR / State",
        state_variance="High",
        update_frequency="Federal rules shift with administrations; state laws update periodically",
        authority_sources=(
            {"domain": "hhs.gov/conscience", "name": "hhs.gov/conscience"},
            {"domain": "each state legislature", "name": "each state legislature"},
        ),
    ),
    RegulationDef(
        key="child_abuse_neglect_reporting",
        category="pediatric_vulnerable",
        name="Child Abuse & Neglect Reporting (CAPTA)",
        description="Federal framework; all states mandate reporting; covered reporters; procedures vary",
        enforcing_agency="HHS ACF / State CPS",
        state_variance="High",
        update_frequency="Federal CAPTA reauthorized every 5–7 yrs; state laws update annually",
        authority_sources=(
            {"domain": "childwelfare.gov", "name": "childwelfare.gov"},
            {"domain": "acf.hhs.gov/cb", "name": "acf.hhs.gov/cb"},
            {"domain": "each state CPS", "name": "each state CPS"},
        ),
    ),
    RegulationDef(
        key="elder_abuse_prevention",
        category="pediatric_vulnerable",
        name="Elder Abuse Prevention (Elder Justice Act)",
        description="Mandatory reporting in LTC facilities; 2-hour reporting for serious bodily injury",
        enforcing_agency="HHS ACL / State APS",
        state_variance="High",
        update_frequency="Elder Justice Act 2010; state laws update every 1–3 yrs",
        authority_sources=(
            {"domain": "acl.gov/programs/elder-justice", "name": "acl.gov/programs/elder-justice"},
            {"domain": "ncea.acl.gov", "name": "ncea.acl.gov"},
            {"domain": "each state APS", "name": "each state APS"},
        ),
    ),
    RegulationDef(
        key="adult_protective_services_reporting",
        category="pediatric_vulnerable",
        name="Adult Protective Services Reporting",
        description="Mandatory reporting of abuse/neglect/exploitation of vulnerable adults; varies by state",
        enforcing_agency="State APS",
        state_variance="High",
        update_frequency="State laws update every 1–3 yrs",
        authority_sources=(
            {"domain": "napsa-now.org", "name": "napsa-now.org"},
            {"domain": "each state APS", "name": "each state APS"},
        ),
    ),
    RegulationDef(
        key="nursing_home_reform_act",
        category="pediatric_vulnerable",
        name="Nursing Home Reform Act (OBRA 1987)",
        description="Resident rights, care planning, staffing, quality of life for certified nursing facilities",
        enforcing_agency="CMS",
        state_variance="Moderate",
        update_frequency="CMS CoPs updated every 3–5 yrs; Interpretive Guidelines updated more frequently",
        authority_sources=({"domain": "cms.gov/medicare/provider-enrollment-and-certification/guidanceforlawsandregulations", "name": "cms.gov/medicare/provider-enrollment-and-certification/guidanceforlawsandregulations"},),
    ),
    RegulationDef(
        key="cms_nursing_home_minimum_staffing_rule",
        category="pediatric_vulnerable",
        name="CMS Nursing Home Minimum Staffing Rule (2024)",
        description="Minimum staffing standards; RN 24/7; HPRD minimums; phased implementation",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Final rule 2024; phased implementation through 2027",
        authority_sources=({"domain": "cms.gov/newsroom/fact-sheets/medicare-and-medicaid-programs-minimum-staffing-standards", "name": "cms.gov/newsroom/fact-sheets/medicare-and-medicaid-programs-minimum-staffing-standards"},),
    ),
    RegulationDef(
        key="guardianship_surrogate_decisionmaking",
        category="pediatric_vulnerable",
        name="Guardianship & Surrogate Decision-Making",
        description="Guardianship, conservatorship, healthcare POA, surrogate hierarchies",
        enforcing_agency="State courts / law",
        state_variance="High",
        update_frequency="State laws update every 2–5 yrs; Uniform Guardianship Act adoption varies",
        authority_sources=(
            {"domain": "uniformlaws.org", "name": "uniformlaws.org"},
            {"domain": "each state legislature", "name": "each state legislature"},
        ),
    ),
    RegulationDef(
        key="disability_rights",
        category="pediatric_vulnerable",
        name="Disability Rights (Section 504 / ADA)",
        description="Non-discrimination in treatment; effective communication; service animals",
        enforcing_agency="HHS OCR / DOJ",
        state_variance="Moderate",
        update_frequency="DOJ/HHS guidance updated every 2–3 yrs",
        authority_sources=(
            {"domain": "hhs.gov/civil-rights/for-individuals/disability", "name": "hhs.gov/civil-rights/for-individuals/disability"},
            {"domain": "ada.gov", "name": "ada.gov"},
        ),
    ),
    RegulationDef(
        key="immigrant_undocumented_patient_protections",
        category="pediatric_vulnerable",
        name="Immigrant & Undocumented Patient Protections",
        description="Emergency Medicaid; EMTALA regardless of status; state coverage programs; language access",
        enforcing_agency="CMS / State",
        state_variance="High",
        update_frequency="State immigrant health programs expanding; federal policy shifts with administrations",
        authority_sources=(
            {"domain": "medicaid.gov", "name": "medicaid.gov"},
            {"domain": "each state Medicaid agency", "name": "each state Medicaid agency"},
            {"domain": "nilc.org", "name": "National Immigration Law Center"},
        ),
    ),
    RegulationDef(
        key="interstate_medical_licensure_compact",
        category="telehealth",
        name="Interstate Medical Licensure Compact (IMLC)",
        description="Expedited licensure for physicians across state lines; member states and eligibility",
        enforcing_agency="IMLC Commission",
        state_variance="High",
        update_frequency="New states join periodically; rules updated by Commission",
        authority_sources=({"domain": "imlcc.org", "name": "imlcc.org"},),
    ),
    RegulationDef(
        key="nurse_licensure_compact",
        category="telehealth",
        name="Nurse Licensure Compact (NLC)",
        description="Multistate nursing license for compact member states",
        enforcing_agency="NCSBN",
        state_variance="High",
        update_frequency="New states joining actively (2020–2026); rules updated by NCSBN",
        authority_sources=({"domain": "ncsbn.org/nurse-licensure-compact", "name": "ncsbn.org/nurse-licensure-compact"},),
    ),
    RegulationDef(
        key="psypact",
        category="telehealth",
        name="PSYPACT",
        description="Telepsychology and temporary in-person practice across member states",
        enforcing_agency="PSYPACT Commission",
        state_variance="High",
        update_frequency="Expanding membership; rules updated by Commission",
        authority_sources=({"domain": "psypact.org", "name": "psypact.org"},),
    ),
    RegulationDef(
        key="medicare_telehealth_coverage",
        category="telehealth",
        name="Medicare Telehealth Coverage (§1834(m))",
        description="Covered services, originating site, geographic restrictions; post-COVID flexibilities",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Annual updates via MPFS; COVID flexibilities extended/made permanent incrementally",
        authority_sources=({"domain": "cms.gov/medicare/coverage/telehealth", "name": "cms.gov/medicare/coverage/telehealth"},),
    ),
    RegulationDef(
        key="state_telehealth_parity_laws",
        category="telehealth",
        name="State Telehealth Parity Laws",
        description="Coverage and/or payment parity; modality requirements (audio-only, asynchronous)",
        enforcing_agency="State DOIs / Legislatures",
        state_variance="High",
        update_frequency="Active legislative area — updated every session",
        authority_sources=(
            {"domain": "cchpca.org", "name": "cchpca.org"},
            {"domain": "each state legislature", "name": "each state legislature"},
            {"domain": "telehealth.hhs.gov", "name": "telehealth.hhs.gov"},
        ),
    ),
    RegulationDef(
        key="ryan_haight_act",
        category="telehealth",
        name="Ryan Haight Act (Online Controlled Substance Prescribing)",
        description="DEA requirements for prescribing via telemedicine; in-person exam exceptions; special registration",
        enforcing_agency="DEA",
        state_variance="Moderate",
        update_frequency="Post-COVID flexibilities; DEA proposed rules 2023–2025 for telemedicine registration",
        authority_sources=(
            {"domain": "deadiversion.usdoj.gov", "name": "deadiversion.usdoj.gov"},
            {"domain": "federalregister.gov", "name": "federalregister.gov"},
        ),
    ),
    RegulationDef(
        key="fda_digital_health_samd",
        category="telehealth",
        name="FDA Digital Health / SaMD",
        description="Clinical decision support, mobile medical apps, AI/ML-based SaMD; pre-market review",
        enforcing_agency="FDA",
        state_variance="Low/None",
        update_frequency="FDA Digital Health Center of Excellence guidance updated continuously",
        authority_sources=({"domain": "fda.gov/medical-devices/digital-health-center-excellence", "name": "fda.gov/medical-devices/digital-health-center-excellence"},),
    ),
    RegulationDef(
        key="remote_patient_monitoring",
        category="telehealth",
        name="Remote Patient Monitoring",
        description="Medicare RPM billing (CPT 99453–99458); state licensure for cross-state monitoring; device requirements",
        enforcing_agency="CMS / State",
        state_variance="Moderate",
        update_frequency="Annual MPFS updates; state licensure rules evolving",
        authority_sources=(
            {"domain": "cms.gov/medicare/coverage/telehealth", "name": "cms.gov/medicare/coverage/telehealth"},
            {"domain": "each state medical board", "name": "each state medical board"},
        ),
    ),
    RegulationDef(
        key="state_telehealth_practice_standards",
        category="telehealth",
        name="State Telehealth Practice Standards",
        description="Patient-provider relationship; consent; documentation; follow-up; prescribing limitations",
        enforcing_agency="State Medical Boards",
        state_variance="High",
        update_frequency="Updated every legislative session and via medical board rulemaking",
        authority_sources=(
            {"domain": "fsmb.org/advocacy/telemedicine", "name": "fsmb.org/advocacy/telemedicine"},
            {"domain": "each state medical board", "name": "each state medical board"},
        ),
    ),
    RegulationDef(
        key="aiml_in_clinical_decision_support",
        category="telehealth",
        name="AI/ML in Clinical Decision Support",
        description="FDA SaMD framework; transparency; bias monitoring; state-emerging AI regulations",
        enforcing_agency="FDA / State",
        state_variance="Moderate",
        update_frequency="FDA guidance updated annually; state AI laws emerging rapidly (2024–2026)",
        authority_sources=(
            {"domain": "fda.gov/medical-devices/software-medical-device-samd", "name": "fda.gov/medical-devices/software-medical-device-samd"},
            {"domain": "each state legislature", "name": "each state legislature"},
        ),
    ),
    RegulationDef(
        key="fda_medical_device_reporting",
        category="medical_devices",
        name="FDA Medical Device Reporting (21 CFR Part 803)",
        description="Mandatory reporting of device-related deaths, serious injuries, malfunctions",
        enforcing_agency="FDA",
        state_variance="Low/None",
        update_frequency="Reporting requirements stable; FDA guidance updated periodically",
        authority_sources=({"domain": "fda.gov/medical-devices/postmarket-requirements-devices/mandatory-reporting-requirements-manufacturers-importers-and-device-user-facilities", "name": "fda.gov/medical-devices/postmarket-requirements-devices/mandatory-reporting-requirements-manufacturers-importers-and-device-user-facilities"},),
    ),
    RegulationDef(
        key="medical_device_tracking",
        category="medical_devices",
        name="Medical Device Tracking (21 CFR Part 821)",
        description="Tracking for life-sustaining/life-supporting devices; patient notification",
        enforcing_agency="FDA",
        state_variance="Low/None",
        update_frequency="Rarely amended",
        authority_sources=({"domain": "fda.gov/medical-devices/postmarket-requirements-devices/medical-device-tracking", "name": "fda.gov/medical-devices/postmarket-requirements-devices/medical-device-tracking"},),
    ),
    RegulationDef(
        key="equipment_maintenance_testing",
        category="medical_devices",
        name="Equipment Maintenance & Testing",
        description="CMS CoP; Joint Commission EC standards; preventive maintenance; clinical engineering",
        enforcing_agency="CMS / Joint Commission",
        state_variance="Moderate",
        update_frequency="Joint Commission EC standards updated annually; CMS CoPs less frequently",
        authority_sources=(
            {"domain": "jointcommission.org/standards", "name": "jointcommission.org/standards"},
            {"domain": "cms.gov", "name": "cms.gov"},
        ),
    ),
    RegulationDef(
        key="unique_device_identification",
        category="medical_devices",
        name="Unique Device Identification (UDI)",
        description="Device labeling and tracking; UDI in medical records",
        enforcing_agency="FDA",
        state_variance="Low/None",
        update_frequency="Phased implementation complete; database (GUDID) maintained continuously",
        authority_sources=(
            {"domain": "fda.gov/medical-devices/unique-device-identification-system-udi-system", "name": "fda.gov/medical-devices/unique-device-identification-system-udi-system"},
            {"domain": "accessgudid.nlm.nih.gov", "name": "accessgudid.nlm.nih.gov"},
        ),
    ),
    RegulationDef(
        key="fda_recalls_safety_communications",
        category="medical_devices",
        name="FDA Recalls & Safety Communications",
        description="Facility obligations to respond to recalls; tracking affected patients; corrective actions",
        enforcing_agency="FDA",
        state_variance="Low/None",
        update_frequency="Recalls issued as needed; facility response obligations ongoing",
        authority_sources=({"domain": "fda.gov/safety/recalls-market-withdrawals-safety-alerts", "name": "fda.gov/safety/recalls-market-withdrawals-safety-alerts"},),
    ),
    RegulationDef(
        key="radiationemitting_device_standards",
        category="medical_devices",
        name="Radiation-Emitting Device Standards (21 CFR Subchapter J)",
        description="Performance standards for X-ray, laser, ultrasound devices; reporting",
        enforcing_agency="FDA / State",
        state_variance="Moderate",
        update_frequency="Federal standards updated rarely; state programs inspect annually",
        authority_sources=(
            {"domain": "fda.gov/radiation-emitting-products", "name": "fda.gov/radiation-emitting-products"},
            {"domain": "each state radiation control", "name": "each state radiation control"},
        ),
    ),
    RegulationDef(
        key="safe_medical_devices_act",
        category="medical_devices",
        name="Safe Medical Devices Act (SMDA)",
        description="User facility reporting for device-related incidents; semi-annual summary reports",
        enforcing_agency="FDA",
        state_variance="Low/None",
        update_frequency="Rarely amended (enacted 1990)",
        authority_sources=({"domain": "fda.gov/medical-devices/postmarket-requirements-devices", "name": "fda.gov/medical-devices/postmarket-requirements-devices"},),
    ),
    RegulationDef(
        key="national_organ_transplant_act",
        category="transplant_organ",
        name="National Organ Transplant Act (NOTA)",
        description="Federal framework for procurement, allocation, transplantation; prohibition on organ sales",
        enforcing_agency="HRSA / OPTN",
        state_variance="Low/None",
        update_frequency="Rarely amended; OPTN contract restructuring underway (2024–2026)",
        authority_sources=(
            {"domain": "hrsa.gov/opa", "name": "hrsa.gov/opa"},
            {"domain": "organdonor.gov", "name": "organdonor.gov"},
        ),
    ),
    RegulationDef(
        key="cms_cops_for_transplant_centers",
        category="transplant_organ",
        name="CMS CoPs for Transplant Centers (42 CFR 482.68–104)",
        description="Outcomes, patient selection, organ procurement, living donor protections, SRTR data",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Updated every 3–5 yrs; CMS relaxed outcome requirements 2020",
        authority_sources=({"domain": "cms.gov/regulations-and-guidance/legislation/cfr", "name": "cms.gov/regulations-and-guidance/legislation/cfr"},),
    ),
    RegulationDef(
        key="optnunos_policies_bylaws",
        category="transplant_organ",
        name="OPTN/UNOS Policies & Bylaws",
        description="Allocation policies, listing criteria, waitlist, member obligations, data reporting",
        enforcing_agency="OPTN / UNOS",
        state_variance="Low/None",
        update_frequency="OPTN policies updated continuously (board votes on changes multiple times/yr)",
        authority_sources=({"domain": "optn.transplant.hrsa.gov/policies-bylaws", "name": "optn.transplant.hrsa.gov/policies-bylaws"},),
    ),
    RegulationDef(
        key="tissue_banking",
        category="transplant_organ",
        name="Tissue Banking (FDA 21 CFR Parts 1270, 1271)",
        description="Donor screening, testing, processing, storage, labeling for HCT/Ps",
        enforcing_agency="FDA",
        state_variance="Moderate",
        update_frequency="FDA guidance updated every 2–3 yrs",
        authority_sources=({"domain": "fda.gov/vaccines-blood-biologics/tissue-tissue-products", "name": "fda.gov/vaccines-blood-biologics/tissue-tissue-products"},),
    ),
    RegulationDef(
        key="opo_conditions_for_coverage",
        category="transplant_organ",
        name="OPO Conditions for Coverage",
        description="Performance metrics, governance, hospital agreements, brain death protocols",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Major update 2020 (outcome measures); CMS final rule on OPO performance 2020",
        authority_sources=({"domain": "cms.gov/regulations-and-guidance/legislation/cfr", "name": "cms.gov/regulations-and-guidance/legislation/cfr"},),
    ),
    RegulationDef(
        key="sherman_act_clayton_act",
        category="antitrust",
        name="Sherman Act / Clayton Act",
        description="Price-fixing, market allocation, group boycotts; merger review for hospital consolidation",
        enforcing_agency="DOJ / FTC",
        state_variance="Moderate",
        update_frequency="Statutes rarely amended; enforcement priorities shift with administrations",
        authority_sources=(
            {"domain": "justice.gov/atr", "name": "justice.gov/atr"},
            {"domain": "ftc.gov/enforcement/competition-matters/healthcare", "name": "ftc.gov/enforcement/competition-matters/healthcare"},
        ),
    ),
    RegulationDef(
        key="ftc_act_5",
        category="antitrust",
        name="FTC Act §5",
        description="FTC authority over anticompetitive practices in healthcare",
        enforcing_agency="FTC",
        state_variance="Low/None",
        update_frequency="FTC enforcement priorities updated annually",
        authority_sources=({"domain": "ftc.gov/enforcement", "name": "ftc.gov/enforcement"},),
    ),
    RegulationDef(
        key="hartscottrodino_act",
        category="antitrust",
        name="Hart-Scott-Rodino Act (HSR)",
        description="Pre-merger notification for healthcare transactions above thresholds",
        enforcing_agency="FTC / DOJ",
        state_variance="Low/None",
        update_frequency="Thresholds adjusted annually for GDP; reporting form updated 2024",
        authority_sources=({"domain": "ftc.gov/enforcement/premerger-notification-program", "name": "ftc.gov/enforcement/premerger-notification-program"},),
    ),
    RegulationDef(
        key="certificate_of_need",
        category="antitrust",
        name="Certificate of Need (CON)",
        description="Some states require CON for new facilities, equipment, service expansions",
        enforcing_agency="State Health Planning",
        state_variance="High",
        update_frequency="Active reform area — some states expanding, others repealing CON",
        authority_sources=(
            {"domain": "ncsl.org/health/certificate-of-need-state-health-laws", "name": "ncsl.org/health/certificate-of-need-state-health-laws"},
            {"domain": "each state health planning agency", "name": "each state health planning agency"},
        ),
    ),
    RegulationDef(
        key="state_ag_healthcare_transaction_review",
        category="antitrust",
        name="State AG Healthcare Transaction Review",
        description="Many states require AG review of healthcare mergers/acquisitions, especially nonprofits",
        enforcing_agency="State AGs",
        state_variance="High",
        update_frequency="Growing state AG activity; new review laws enacted annually",
        authority_sources=(
            {"domain": "Each state AG office", "name": "Each state AG office"},
            {"domain": "nashp.org", "name": "nashp.org"},
        ),
    ),
    RegulationDef(
        key="irc_501_for_charitable_hospitals",
        category="tax_exempt",
        name="IRC §501(r) for Charitable Hospitals",
        description="CHNA every 3 yrs; financial assistance policy; charge limitations; billing/collection practices",
        enforcing_agency="IRS",
        state_variance="Moderate",
        update_frequency="IRS final regulations 2014; CHNA cycles every 3 yrs; IRS guidance periodic",
        authority_sources=({"domain": "irs.gov/charities-non-profits/charitable-organizations/requirements-for-501c3-hospitals", "name": "irs.gov/charities-non-profits/charitable-organizations/requirements-for-501c3-hospitals"},),
    ),
    RegulationDef(
        key="irs_form_990_schedule_h",
        category="tax_exempt",
        name="IRS Form 990 Schedule H",
        description="Community benefit reporting; financial assistance; bad debt; Medicare shortfall; community building",
        enforcing_agency="IRS",
        state_variance="Low/None",
        update_frequency="Schedule H updated periodically; filed annually",
        authority_sources=({"domain": "irs.gov/forms-pubs/about-schedule-h-form-990", "name": "irs.gov/forms-pubs/about-schedule-h-form-990"},),
    ),
    RegulationDef(
        key="state_community_benefit_requirements",
        category="tax_exempt",
        name="State Community Benefit Requirements",
        description="Additional reporting, spending minimums, CHNA requirements beyond 501(r)",
        enforcing_agency="State AGs / Health Depts",
        state_variance="High",
        update_frequency="State laws update every 1–3 yrs; growing scrutiny of hospital tax exemptions",
        authority_sources=(
            {"domain": "Each state AG", "name": "Each state AG"},
            {"domain": "hilltopinstitute.org/community-benefit", "name": "hilltopinstitute.org/community-benefit"},
        ),
    ),
    RegulationDef(
        key="state_property_tax_exemptions",
        category="tax_exempt",
        name="State Property Tax Exemptions",
        description="State-specific requirements; community benefit standards; charity care thresholds",
        enforcing_agency="State/Local Tax Authorities",
        state_variance="High",
        update_frequency="Active litigation and legislative reform area",
        authority_sources=({"domain": "Each state revenue/tax authority", "name": "Each state revenue/tax authority"},),
    ),
    RegulationDef(
        key="ubit",
        category="tax_exempt",
        name="UBIT (Unrelated Business Income Tax)",
        description="Tax on income from non-exempt activities; parking, laundry, pharmacy sales to nonpatients",
        enforcing_agency="IRS",
        state_variance="Low/None",
        update_frequency="TCJA 2017 changes; IRS guidance updated periodically",
        authority_sources=({"domain": "irs.gov/charities-non-profits/unrelated-business-income-tax", "name": "irs.gov/charities-non-profits/unrelated-business-income-tax"},),
    ),
    RegulationDef(
        key="title_vi",
        category="language_access",
        name="Title VI (Language Access)",
        description="Meaningful access for LEP individuals; qualified interpreters; translated vital documents; signage",
        enforcing_agency="HHS OCR",
        state_variance="Moderate",
        update_frequency="HHS LEP guidance updated every 5–10 yrs; OCR enforcement ongoing",
        authority_sources=(
            {"domain": "hhs.gov/civil-rights/for-individuals/special-topics/limited-english-proficiency", "name": "hhs.gov/civil-rights/for-individuals/special-topics/limited-english-proficiency"},
            {"domain": "lep.gov", "name": "lep.gov"},
        ),
    ),
    RegulationDef(
        key="section_1557_aca",
        category="language_access",
        name="Section 1557 ACA (Detailed)",
        description="Comprehensive nondiscrimination; sex (including gender identity); disability; age",
        enforcing_agency="HHS OCR",
        state_variance="Low/None",
        update_frequency="Major rulemaking cycles: 2016, 2020, 2024",
        authority_sources=({"domain": "hhs.gov/civil-rights/for-individuals/section-1557", "name": "hhs.gov/civil-rights/for-individuals/section-1557"},),
    ),
    RegulationDef(
        key="ada_effective_communication",
        category="language_access",
        name="ADA Effective Communication",
        description="Auxiliary aids for disabilities; interpreters; accessible formats; relay services",
        enforcing_agency="DOJ / HHS OCR",
        state_variance="Low/None",
        update_frequency="ADA Title II/III guidance updated periodically",
        authority_sources=(
            {"domain": "ada.gov", "name": "ada.gov"},
            {"domain": "hhs.gov/civil-rights", "name": "hhs.gov/civil-rights"},
        ),
    ),
    RegulationDef(
        key="state_language_access_laws",
        category="language_access",
        name="State Language Access Laws",
        description="Specific interpreter qualifications; translated document requirements; enhanced access",
        enforcing_agency="State law",
        state_variance="High",
        update_frequency="Updated via state legislation every 1–3 yrs",
        authority_sources=(
            {"domain": "Each state legislature", "name": "Each state legislature"},
            {"domain": "ncsl.org", "name": "ncsl.org"},
        ),
    ),
    RegulationDef(
        key="clas_standards",
        category="language_access",
        name="CLAS Standards",
        description="National standards for culturally competent care; governance, communication, engagement",
        enforcing_agency="HHS OMH",
        state_variance="Low/None",
        update_frequency="CLAS Standards released 2013; OMH resources updated periodically",
        authority_sources=({"domain": "thinkculturalhealth.hhs.gov/clas", "name": "thinkculturalhealth.hhs.gov/clas"},),
    ),
    RegulationDef(
        key="religious_accommodation_in_healthcare",
        category="language_access",
        name="Religious Accommodation in Healthcare",
        description="Title VII employee accommodation; patient dietary, dress, blood product, end-of-life preferences",
        enforcing_agency="EEOC / HHS OCR",
        state_variance="Moderate",
        update_frequency="EEOC guidance updated periodically; Groff v. DeJoy (2023) raised accommodation standard",
        authority_sources=(
            {"domain": "eeoc.gov/religious-discrimination", "name": "eeoc.gov/religious-discrimination"},
            {"domain": "hhs.gov/conscience", "name": "hhs.gov/conscience"},
        ),
    ),
    RegulationDef(
        key="medical_records_retention",
        category="records_retention",
        name="Medical Records Retention",
        description="No single federal standard; CMS requires policies; HIPAA 6 yrs for compliance docs; state laws 5–30+ yrs; minors longer",
        enforcing_agency="CMS / State law",
        state_variance="High",
        update_frequency="State retention laws update every 3–5 yrs",
        authority_sources=(
            {"domain": "Each state legislature", "name": "Each state legislature"},
            {"domain": "ahima.org/topics/retention-and-destruction", "name": "ahima.org/topics/retention-and-destruction"},
        ),
    ),
    RegulationDef(
        key="hipaa_documentation_requirements",
        category="records_retention",
        name="HIPAA Documentation Requirements",
        description="6-year retention for policies, procedures, training, BAAs, risk assessments",
        enforcing_agency="HHS OCR",
        state_variance="Low/None",
        update_frequency="Stable requirement since HIPAA implementation",
        authority_sources=({"domain": "hhs.gov/hipaa/for-professionals/privacy/guidance/documentation", "name": "hhs.gov/hipaa/for-professionals/privacy/guidance/documentation"},),
    ),
    RegulationDef(
        key="medical_records_content_standards",
        category="records_retention",
        name="Medical Records Content Standards",
        description="CMS CoP requirements; authentication; verbal orders; documentation per accreditor",
        enforcing_agency="CMS / Accreditors",
        state_variance="Moderate",
        update_frequency="Updated with CMS CoP and accreditor standard revisions",
        authority_sources=(
            {"domain": "cms.gov", "name": "cms.gov"},
            {"domain": "jointcommission.org/standards", "name": "jointcommission.org/standards"},
        ),
    ),
    RegulationDef(
        key="patient_access_to_records",
        category="records_retention",
        name="Patient Access to Records (HIPAA Right of Access)",
        description="30-day response; reasonable fees; electronic copies; OCR Right of Access Initiative",
        enforcing_agency="HHS OCR",
        state_variance="Moderate",
        update_frequency="OCR enforcement initiative launched 2019; active enforcement ongoing",
        authority_sources=({"domain": "hhs.gov/hipaa/for-professionals/privacy/guidance/access", "name": "hhs.gov/hipaa/for-professionals/privacy/guidance/access"},),
    ),
    RegulationDef(
        key="state_medical_records_laws",
        category="records_retention",
        name="State Medical Records Laws",
        description="Content, retention, access, amendment, fees, destruction methods",
        enforcing_agency="State law",
        state_variance="High",
        update_frequency="Updated via state legislation every 2–5 yrs",
        authority_sources=(
            {"domain": "Each state legislature", "name": "Each state legislature"},
            {"domain": "ahima.org", "name": "ahima.org"},
        ),
    ),
    RegulationDef(
        key="legal_hold_litigation_preservation",
        category="records_retention",
        name="Legal Hold & Litigation Preservation",
        description="Preservation upon litigation notice; spoliation consequences; e-discovery",
        enforcing_agency="Courts / DOJ",
        state_variance="Moderate",
        update_frequency="Case law evolves continuously; FRCP amendments periodic",
        authority_sources=({"domain": "uscourts.gov/rules-policies/current-rules-practice-procedure", "name": "uscourts.gov/rules-policies/current-rules-practice-procedure"},),
    ),
    RegulationDef(
        key="baa_requirements",
        category="records_retention",
        name="BAA Requirements",
        description="HIPAA-mandated contracts with vendors accessing PHI; required provisions; breach obligations",
        enforcing_agency="HHS OCR",
        state_variance="Low/None",
        update_frequency="Requirements stable since 2013 Omnibus Rule; OCR template available",
        authority_sources=({"domain": "hhs.gov/hipaa/for-professionals/covered-entities/sample-business-associate-agreement-provisions", "name": "hhs.gov/hipaa/for-professionals/covered-entities/sample-business-associate-agreement-provisions"},),
    ),
    RegulationDef(
        key="hipaa_marketing_restrictions",
        category="marketing_comms",
        name="HIPAA Marketing Restrictions",
        description="Marketing vs. treatment communications; authorization requirements; refill/face-to-face exceptions",
        enforcing_agency="HHS OCR",
        state_variance="Low/None",
        update_frequency="Stable since Omnibus Rule 2013",
        authority_sources=({"domain": "hhs.gov/hipaa/for-professionals/privacy/guidance/marketing", "name": "hhs.gov/hipaa/for-professionals/privacy/guidance/marketing"},),
    ),
    RegulationDef(
        key="medicare_marketing_guidelines",
        category="marketing_comms",
        name="Medicare Marketing Guidelines (MCMG)",
        description="MA and Part D marketing rules; prohibited activities; disclaimers; CMS pre-review",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Updated annually (published with MA Rate Announcement)",
        authority_sources=({"domain": "cms.gov/medicare/health-plans/managedcaremarketing", "name": "cms.gov/medicare/health-plans/managedcaremarketing"},),
    ),
    RegulationDef(
        key="tcpa",
        category="marketing_comms",
        name="TCPA",
        description="Consent for autodialed calls/texts; healthcare exception is narrow; state mini-TCPAs",
        enforcing_agency="FCC / State",
        state_variance="High",
        update_frequency="FCC orders updated periodically; 1-to-1 consent rule 2025; state laws expanding",
        authority_sources=(
            {"domain": "fcc.gov/general/telemarketing-and-robocalls", "name": "fcc.gov/general/telemarketing-and-robocalls"},
            {"domain": "each state legislature", "name": "each state legislature"},
        ),
    ),
    RegulationDef(
        key="canspam_act",
        category="marketing_comms",
        name="CAN-SPAM Act",
        description="Commercial email requirements; opt-out; sender ID",
        enforcing_agency="FTC",
        state_variance="Low/None",
        update_frequency="Rarely amended (enacted 2003)",
        authority_sources=({"domain": "ftc.gov/legal-library/browse/rules/can-spam-rule", "name": "ftc.gov/legal-library/browse/rules/can-spam-rule"},),
    ),
    RegulationDef(
        key="state_consumer_protection_deceptive_practices",
        category="marketing_comms",
        name="State Consumer Protection / Deceptive Practices",
        description="State laws on deceptive healthcare advertising; testimonials; price transparency",
        enforcing_agency="State AGs / DOIs",
        state_variance="High",
        update_frequency="Updated via state legislation/AG enforcement",
        authority_sources=({"domain": "Each state AG office", "name": "Each state AG office"},),
    ),
    RegulationDef(
        key="ftc_endorsement_guidelines",
        category="marketing_comms",
        name="FTC Endorsement Guidelines",
        description="Physician endorsements; social media disclosure; patient testimonials",
        enforcing_agency="FTC",
        state_variance="Low/None",
        update_frequency="Updated 2023; next update in several years",
        authority_sources=({"domain": "ftc.gov/legal-library/browse/rules/guides-concerning-endorsements-testimonials", "name": "ftc.gov/legal-library/browse/rules/guides-concerning-endorsements-testimonials"},),
    ),
    RegulationDef(
        key="price_transparency",
        category="marketing_comms",
        name="Price Transparency (Hospital & Insurance)",
        description="Hospital machine-readable files, shoppable services; Transparency in Coverage for insurers",
        enforcing_agency="CMS",
        state_variance="Low/None",
        update_frequency="Hospital rule effective 2021; insurer rule phased 2022–2024; CMS enforcement increasing",
        authority_sources=(
            {"domain": "cms.gov/hospital-price-transparency", "name": "cms.gov/hospital-price-transparency"},
            {"domain": "cms.gov/healthplan-price-transparency", "name": "cms.gov/healthplan-price-transparency"},
        ),
    ),
    RegulationDef(
        key="state_facility_licensure",
        category="state_licensing",
        name="State Facility Licensure",
        description="State-specific licensing for hospitals, ASCs, clinics, behavioral health, HHAs, hospice, LTC, urgent care, imaging",
        enforcing_agency="State Health Depts",
        state_variance="High",
        update_frequency="Continuous — updated via state regulation and legislation",
        authority_sources=({"domain": "Each state health department", "name": "Each state health department"},),
    ),
    RegulationDef(
        key="medicaremedicaid_certification",
        category="state_licensing",
        name="Medicare/Medicaid Certification",
        description="Federal certification for program participation; survey process; deficiency correction",
        enforcing_agency="CMS / State Survey Agencies",
        state_variance="Low/None",
        update_frequency="Survey protocols updated every 2–3 yrs; Interpretive Guidelines updated ongoing",
        authority_sources=({"domain": "cms.gov/medicare/provider-enrollment-and-certification", "name": "cms.gov/medicare/provider-enrollment-and-certification"},),
    ),
    RegulationDef(
        key="certificate_of_need_programs",
        category="state_licensing",
        name="Certificate of Need (CON) Programs",
        description="35+ states require CON for new facilities, capital expenditures, beds, new services",
        enforcing_agency="State Health Planning",
        state_variance="High",
        update_frequency="Active reform area; some states repealing, others strengthening",
        authority_sources=({"domain": "ncsl.org/health/certificate-of-need-state-health-laws", "name": "ncsl.org/health/certificate-of-need-state-health-laws"},),
    ),
    RegulationDef(
        key="corporate_practice_of_medicine_doctrine",
        category="state_licensing",
        name="Corporate Practice of Medicine Doctrine",
        description="State prohibitions on corporate employment of physicians or control of clinical decisions; MSO structures",
        enforcing_agency="State Medical Boards / Courts",
        state_variance="High",
        update_frequency="Evolves via case law and AG opinions; varies dramatically by state",
        authority_sources=(
            {"domain": "Each state medical board", "name": "Each state medical board"},
            {"domain": "state AG opinions", "name": "state AG opinions"},
        ),
    ),
    RegulationDef(
        key="feesplitting_prohibitions",
        category="state_licensing",
        name="Fee-Splitting Prohibitions",
        description="Restrictions on dividing fees with non-licensed persons; impact on practice management",
        enforcing_agency="State Medical Boards",
        state_variance="High",
        update_frequency="Updated via state statute and medical board rules",
        authority_sources=({"domain": "Each state medical board", "name": "Each state medical board"},),
    ),
    RegulationDef(
        key="nonprofit_healthcare_governance",
        category="state_licensing",
        name="Nonprofit Healthcare Governance",
        description="State requirements for nonprofit hospital boards; fiduciary duties; conflicts; AG oversight of conversions",
        enforcing_agency="State AGs",
        state_variance="High",
        update_frequency="Growing AG scrutiny of nonprofit hospital transactions and governance",
        authority_sources=({"domain": "Each state AG office", "name": "Each state AG office"},),
    ),
    RegulationDef(
        key="medical_staff_bylaws_selfgovernance",
        category="state_licensing",
        name="Medical Staff Bylaws & Self-Governance",
        description="CMS CoP organized medical staff; bylaws; fair hearing/appeal; peer review protections (HCQIA)",
        enforcing_agency="CMS / State",
        state_variance="Moderate",
        update_frequency="HCQIA (1986) stable; CMS CoPs updated every 3–5 yrs; state peer review protections vary",
        authority_sources=(
            {"domain": "cms.gov", "name": "cms.gov"},
            {"domain": "npdb.hrsa.gov/resources/aboutHcqia.jsp", "name": "npdb.hrsa.gov/resources/aboutHcqia.jsp"},
        ),
    ),
    RegulationDef(
        key="ai_algorithmic_decisionmaking",
        category="emerging_regulatory",
        name="AI & Algorithmic Decision-Making",
        description="FDA SaMD framework; CMS coverage of AI diagnostics; state AI transparency/bias laws; liability",
        enforcing_agency="FDA / CMS / State",
        state_variance="High",
        update_frequency="Extremely active — FDA guidance, state laws, and EU AI Act developments continuously",
        authority_sources=(
            {"domain": "fda.gov/medical-devices/software-medical-device-samd", "name": "fda.gov/medical-devices/software-medical-device-samd"},
            {"domain": "each state legislature", "name": "each state legislature"},
            {"domain": "ai.gov", "name": "ai.gov"},
        ),
    ),
    RegulationDef(
        key="social_determinants_of_health_data",
        category="emerging_regulatory",
        name="Social Determinants of Health (SDOH) Data",
        description="CMS SDOH screening (Z-codes); ONC USCDI SDOH elements; privacy considerations",
        enforcing_agency="CMS / ONC",
        state_variance="Low/None",
        update_frequency="USCDI SDOH elements expanding annually; CMS guidance periodic",
        authority_sources=(
            {"domain": "cms.gov/priorities/health-equity", "name": "cms.gov/priorities/health-equity"},
            {"domain": "healthit.gov/isa/uscdi", "name": "healthit.gov/isa/uscdi"},
        ),
    ),
    RegulationDef(
        key="health_equity_compliance",
        category="emerging_regulatory",
        name="Health Equity Compliance",
        description="CMS health equity initiatives; accreditation standards; disparities reporting; cultural competency",
        enforcing_agency="CMS / Accreditors",
        state_variance="Moderate",
        update_frequency="CMS health equity framework 2022; accreditor requirements expanding",
        authority_sources=(
            {"domain": "cms.gov/priorities/health-equity", "name": "cms.gov/priorities/health-equity"},
            {"domain": "jointcommission.org/resources/health-equity", "name": "jointcommission.org/resources/health-equity"},
        ),
    ),
    RegulationDef(
        key="cannabis_medical_marijuana",
        category="emerging_regulatory",
        name="Cannabis / Medical Marijuana",
        description="Federal Schedule I vs. state programs; employer testing conflicts; patient accommodations; banking",
        enforcing_agency="DEA / State",
        state_variance="High",
        update_frequency="Federal scheduling review underway; state programs update continuously",
        authority_sources=(
            {"domain": "deadiversion.usdoj.gov", "name": "deadiversion.usdoj.gov"},
            {"domain": "each state cannabis regulatory agency", "name": "each state cannabis regulatory agency"},
            {"domain": "ncsl.org/health/state-medical-cannabis-laws", "name": "ncsl.org/health/state-medical-cannabis-laws"},
        ),
    ),
    RegulationDef(
        key="genomic_medicine_precision_health",
        category="emerging_regulatory",
        name="Genomic Medicine & Precision Health",
        description="Genetic testing (CLIA, FDA); genetic counseling licensure; GINA; genetic data privacy; DTC testing",
        enforcing_agency="FDA / CLIA / State",
        state_variance="High",
        update_frequency="FDA oversight evolving; state genetic privacy laws expanding; GINA stable",
        authority_sources=(
            {"domain": "fda.gov/medical-devices/in-vitro-diagnostics/direct-consumer-tests", "name": "fda.gov/medical-devices/in-vitro-diagnostics/direct-consumer-tests"},
            {"domain": "genome.gov", "name": "genome.gov"},
        ),
    ),
    RegulationDef(
        key="clinical_decision_support_exemptions",
        category="emerging_regulatory",
        name="Clinical Decision Support (CDS) Exemptions",
        description="21st Century Cures CDS exemptions from device regulation; four-criteria test; locked vs. adaptive CDS",
        enforcing_agency="FDA",
        state_variance="Low/None",
        update_frequency="FDA guidance finalized 2022; updates as technology evolves",
        authority_sources=({"domain": "fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software", "name": "fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software"},),
    ),
    RegulationDef(
        key="autonomous_robotic_surgery_systems",
        category="emerging_regulatory",
        name="Autonomous & Robotic Surgery Systems",
        description="FDA clearance; credentialing for robotic procedures; facility requirements; reporting",
        enforcing_agency="FDA / State",
        state_variance="Moderate",
        update_frequency="FDA clearances ongoing; facility standards evolving with technology",
        authority_sources=(
            {"domain": "fda.gov/medical-devices", "name": "fda.gov/medical-devices"},
            {"domain": "each state health dept", "name": "each state health dept"},
        ),
    ),
    RegulationDef(
        key="right_to_try_act",
        category="emerging_regulatory",
        name="Right to Try Act (21 U.S.C. § 360bbb-0a)",
        description="Patient access to investigational drugs outside trials; eligibility; manufacturer reporting; state laws",
        enforcing_agency="FDA / State",
        state_variance="Moderate",
        update_frequency="Federal law enacted 2018; state laws enacted 2014–2018; relatively stable now",
        authority_sources=({"domain": "fda.gov/patients/learn-about-expanded-access-and-other-treatment-options/right-try", "name": "fda.gov/patients/learn-about-expanded-access-and-other-treatment-options/right-try"},),
    ),
    RegulationDef(
        key="interstate_practice_multistate_compliance",
        category="emerging_regulatory",
        name="Interstate Practice & Multi-State Compliance",
        description="Challenges of multi-state operations; varying licensure, scope, mandates, privacy laws; compacts",
        enforcing_agency="Multiple",
        state_variance="High",
        update_frequency="Continuous — each state has independent update cycle",
        authority_sources=(
            {"domain": "imlcc.org", "name": "imlcc.org"},
            {"domain": "ncsbn.org", "name": "ncsbn.org"},
            {"domain": "cchpca.org", "name": "cchpca.org"},
            {"domain": "each state legislature", "name": "each state legislature"},
        ),
    ),
    RegulationDef(
        key="environmental_sustainability_reporting",
        category="emerging_regulatory",
        name="Environmental Sustainability Reporting",
        description="Emerging requirements for healthcare carbon footprint, sustainable procurement, environmental impact",
        enforcing_agency="EPA / State / Voluntary",
        state_variance="Moderate",
        update_frequency="Voluntary frameworks evolving; some state mandates emerging",
        authority_sources=(
            {"domain": "epa.gov", "name": "epa.gov"},
            {"domain": "practicegreenhealth.org", "name": "practicegreenhealth.org"},
            {"domain": "jointcommission.org", "name": "jointcommission.org"},
        ),
    ),
]


# ---------------------------------------------------------------------------
# RESEARCH_PROMPTS — category-specific Gemini research instructions
# ---------------------------------------------------------------------------

RESEARCH_PROMPTS: Dict[str, str] = {
    "minimum_wage": """Research MINIMUM WAGE requirements.
Always include the STATE baseline minimum wage.
If a county/city minimum wage ordinance exists (and is allowed), also include the local override.
Return SEPARATE requirements for each rate type that exists at each applicable level:
- "general" - standard minimum wage (ALWAYS include for state baseline)
- "tipped" - if tip credits allowed
- "exempt_salary" - minimum exempt salary threshold for overtime exemption (ALWAYS include; if only federal applies, explicitly say so)
- "hotel", "fast_food", "healthcare" - if special rates exist
- "large_employer" / "small_employer" - if rates differ by size
For tipped requirements, explicitly describe whether tip crediting is allowed and how it works (cash wage + tip credit structure).
Provide numeric_value for rates/salary thresholds when possible.""",

    "overtime": """Research OVERTIME requirements.
Always include the STATE baseline overtime rules.
If a county/city overtime ordinance exists (and is allowed), also include the local override.
Include daily/weekly overtime thresholds and multipliers.""",

    "sick_leave": """Research PAID SICK LEAVE requirements.
Always include the STATE baseline sick leave rules.
If a county/city sick leave ordinance exists (and is allowed), also include the local override.
Include accrual rate, cap, and usage rules.""",

    "meal_breaks": """Research MEAL AND REST BREAK requirements.
Always include the STATE baseline meal/rest break rules.
If a county/city ordinance exists (and is allowed), also include the local override.
Include timing, duration, and waiver conditions.""",

    "pay_frequency": """Research PAY FREQUENCY requirements.
Always include the STATE baseline pay frequency rules.
If a county/city ordinance exists (and is allowed), also include the local override.
Include required pay periods and final pay rules.""",

    "final_pay": """Research FINAL PAY requirements.
Always include the STATE baseline final paycheck rules.
If local (county/city) final-pay rules exist and are allowed, include local overrides.
Cover BOTH voluntary resignations and involuntary terminations, including timing and payout method requirements.
Explicitly state whether accrued vacation/PTO must be paid out, and whether accrued sick leave must be paid out at separation.""",

    "minor_work_permit": """Research MINOR WORK PERMIT / YOUTH EMPLOYMENT requirements.
Always include the STATE baseline minor-work authorization rules.
If local (county/city) rules exist and are allowed, include local overrides.
Include whether work permits are required, age thresholds, hour limits (school-day/non-school-day), prohibited occupations, and who issues permits.""",

    "scheduling_reporting": """Research SCHEDULING AND REPORTING TIME requirements.
Always include the STATE baseline rules.
If local fair-workweek/predictive-scheduling ordinances exist (and are allowed), include local overrides.
Include advance-schedule notice windows, penalties for schedule changes, reporting/show-up pay rules, on-call restrictions, and spread-of-hours pay if applicable.
If no specific scheduling/reporting-time law applies, explicitly say so.""",

    "leave": """Research LEAVE OF ABSENCE programs and entitlements.
Return EACH qualifying leave program as a SEPARATE requirement.
Common programs: state paid family/medical leave (PFML), state disability insurance (SDI/TDI),
state family leave acts, pregnancy disability leave.
Do NOT include federal FMLA (handled separately).

For EACH program, include these additional JSON fields:
- "paid": true or false
- "max_weeks": integer (maximum weeks of leave)
- "wage_replacement_pct": number or null (e.g., 60 for 60%)
- "job_protection": true or false
- "employer_size_threshold": integer or null (minimum employees)
- "employee_tenure_months": integer or null (minimum months employed)
- "employee_hours_threshold": integer or null (minimum hours worked)

Set numeric_value to max_weeks. Set current_value to a SHORT summary (under 80 chars) like "8 weeks, 60% pay, job protected".
Set description to a longer explanation of the program if needed.""",

    "workplace_safety": """Research WORKPLACE SAFETY requirements (OSHA and state equivalents).
Always include federal OSHA applicability (employers with 1+ employees).
If the state operates its own OSHA-approved State Plan, include state-specific requirements.
Cover: injury/illness recording (OSHA 300 log), reporting requirements (fatalities, hospitalizations),
mandatory safety training, hazard communication (GHS/SDS), required workplace posters,
bloodborne pathogen standards if applicable, and any industry-specific safety rules.
Include employee count thresholds where they apply (e.g., OSHA 300 log exemptions for <10 employees).
Set current_value to a SHORT summary (under 80 chars).""",

    "workers_comp": """Research WORKERS' COMPENSATION INSURANCE requirements.
Always include the STATE baseline workers' comp requirements.
Cover: whether coverage is mandatory or elective, employee count thresholds for mandatory coverage,
exempt categories (e.g., sole proprietors, independent contractors, domestic workers, agricultural),
state fund vs. private insurance options, penalty for non-compliance,
and any special industry requirements (e.g., construction must cover all workers).
Include the state agency that administers the program.
Set current_value to a SHORT summary (under 80 chars).""",

    "anti_discrimination": """Research ANTI-DISCRIMINATION AND EQUAL EMPLOYMENT requirements.
Always include the STATE baseline anti-discrimination laws.
If local (county/city) human rights ordinances add protections, include local overrides.
Cover: protected classes beyond federal Title VII (e.g., sexual orientation, gender identity, marital status),
employer size thresholds for state law applicability, harassment prevention training requirements,
pay equity/transparency laws, reasonable accommodation requirements (disability, pregnancy, religion),
mandatory anti-harassment policy requirements, and complaint filing agencies/deadlines.
Do NOT duplicate federal Title VII or ADA — focus on state and local additions.
Set current_value to a SHORT summary (under 80 chars).""",

    "hipaa_privacy": """Research HIPAA PRIVACY AND SECURITY requirements as they apply in this jurisdiction.
Cover: HIPAA Privacy Rule (45 CFR Part 164 Subpart E), HIPAA Security Rule (45 CFR Part 164 Subpart C),
HITECH Act breach notification requirements (timing, state AG notification),
42 CFR Part 2 requirements for substance use disorder records where applicable,
and any STATE health privacy laws that EXCEED federal HIPAA protections
(e.g., CA CMIA, TX HB 300, NY SHIELD Act health data provisions).
Include stricter consent, redisclosure, segregation, and patient-access rules for Part 2 records
when they go beyond standard HIPAA handling.
Include state-specific breach notification timelines if shorter than HIPAA's 60-day window.
Include penalties for non-compliance at both federal and state levels.
Set current_value to a SHORT summary (under 80 chars).""",

    "billing_integrity": """Research BILLING AND FINANCIAL INTEGRITY requirements for healthcare entities in this jurisdiction.
Cover: Federal False Claims Act (31 U.S.C. §§ 3729–3733), Anti-Kickback Statute (42 U.S.C. § 1320a-7b),
Physician Self-Referral Law (Stark Law, 42 U.S.C. § 1395nn), Medicare/Medicaid billing requirements,
Mental Health Parity and Addiction Equity Act (MHPAEA) obligations as enforced through payer coverage,
utilization management, medical necessity, and reimbursement rules,
and any STATE false claims acts, anti-kickback laws, parity laws, or fee-splitting prohibitions.
Include state-specific billing fraud statutes and qui tam provisions.
Set current_value to a SHORT summary (under 80 chars).""",

    "clinical_safety": """Research CLINICAL AND PATIENT SAFETY requirements for healthcare facilities in this jurisdiction.
Cover: CMS Conditions of Participation (42 CFR Parts 482-485), Joint Commission accreditation standards,
medication management and DEA controlled substance requirements,
OSHA Bloodborne Pathogens Standard (29 CFR 1910.1030), infection control and prevention requirements,
EPA and STATE medical waste disposal / regulated medical waste handling requirements,
and any STATE patient safety reporting requirements (e.g., adverse event reporting, sentinel events).
Include state health department inspection and survey requirements.
Set current_value to a SHORT summary (under 80 chars).""",

    "healthcare_workforce": """Research HEALTHCARE WORKFORCE compliance requirements in this jurisdiction.
Cover: provider credentialing and privileging requirements, OIG List of Excluded Individuals/Entities (LEIE) screening obligations,
mandatory reporter obligations (child abuse, elder abuse, domestic violence),
healthcare-specific labor rules (nurse staffing ratios, mandatory overtime bans for healthcare workers),
and state-specific scope-of-practice rules for nurses, PAs, and allied health.
Include frequency requirements for OIG exclusion screening and credentialing verification.
Set current_value to a SHORT summary (under 80 chars).""",

    "corporate_integrity": """Research CORPORATE INTEGRITY AND ETHICS requirements for healthcare organizations in this jurisdiction.
Cover: OIG Compliance Program Guidance for hospitals/healthcare entities,
corporate integrity agreement (CIA) common requirements, code of conduct mandates,
conflict of interest disclosure requirements, whistleblower protections and qui tam provisions
(federal False Claims Act qui tam + state equivalents),
and any STATE healthcare compliance program requirements.
Include state-specific whistleblower protections for healthcare workers.
Set current_value to a SHORT summary (under 80 chars).""",

    "research_consent": """Research RESEARCH AND INFORMED CONSENT requirements in this jurisdiction.
Cover: IRB oversight requirements (45 CFR Part 46 — Common Rule), Good Clinical Practice (ICH-GCP) standards,
FDA investigational regulations (21 CFR Parts 50, 56, 312, 812),
21 CFR Part 11 (electronic records/signatures), and any STATE-specific informed consent requirements,
research subject protections, or bioethics laws that exceed federal standards.
Include state requirements for genetic testing consent and biospecimen research.
Set current_value to a SHORT summary (under 80 chars).""",

    "state_licensing": """Research STATE LICENSING AND SCOPE OF PRACTICE requirements for healthcare in this jurisdiction.
Cover: facility licensure requirements (hospitals, clinics, ASCs, nursing facilities),
provider licensing and renewal requirements (physicians, nurses, allied health),
telehealth and cross-state practice regulations (interstate compacts like IMLC, NLC),
post-Dobbs abortion-service restrictions or protections that affect providers or facilities,
ADA physical accessibility and plant/facility standards enforced through health facility rules,
and any recent changes to scope-of-practice laws (e.g., NP independent practice authority).
Include state health department facility licensing categories and renewal timelines.
Set current_value to a SHORT summary (under 80 chars).""",

    "emergency_preparedness": """Research EMERGENCY PREPAREDNESS requirements for healthcare facilities in this jurisdiction.
Cover: EMTALA (Emergency Medical Treatment and Labor Act, 42 U.S.C. § 1395dd) — screening, stabilization, and transfer requirements;
CMS Emergency Preparedness Rule (42 CFR § 482.15) — emergency plan, communication plan, policies/procedures, training/testing;
NFPA fire and life safety code requirements adopted through CMS, accrediting bodies, or STATE health/facility regulators;
and any STATE-specific emergency preparedness requirements for healthcare facilities.
Include penalties for EMTALA violations and state emergency management mandates.
Set current_value to a SHORT summary (under 80 chars).""",

    "health_it": """Research HEALTH INFORMATION TECHNOLOGY requirements for healthcare in this jurisdiction.
Cover: 21st Century Cures Act information blocking rules (ONC Final Rule),
ONC Health IT Certification Program (§ 170.315),
TEFCA (Trusted Exchange Framework and Common Agreement) participation requirements,
state health information exchange (HIE) participation mandates,
EHR meaningful use / Promoting Interoperability requirements,
and state-specific health IT interoperability or data sharing laws.
Set current_value to a SHORT summary (under 80 chars).""",

    "quality_reporting": """Research QUALITY REPORTING AND VALUE-BASED CARE requirements for healthcare in this jurisdiction.
Cover: MIPS (Merit-based Incentive Payment System) and QPP (Quality Payment Program) requirements,
HEDIS (Healthcare Effectiveness Data and Information Set) measures,
Hospital Value-Based Purchasing (VBP) program,
Hospital-Acquired Condition (HAC) Reduction Program,
Hospital Readmissions Reduction Program (HRRP),
CMS Star Ratings, and state-specific quality reporting mandates.
Set current_value to a SHORT summary (under 80 chars).""",

    "cybersecurity": """Research HEALTHCARE CYBERSECURITY requirements for healthcare in this jurisdiction.
Cover: NIST Cybersecurity Framework (CSF) as applied to healthcare,
Health Care Industry Cybersecurity (HCIC) Act (Public Law 116-321),
HIPAA Security Rule technical safeguards (45 CFR § 164.312),
state data breach notification laws specific to healthcare/PHI,
and any state-specific cybersecurity requirements for healthcare entities.
Set current_value to a SHORT summary (under 80 chars).""",

    "environmental_safety": """Research ENVIRONMENTAL AND FACILITY SAFETY requirements for healthcare facilities in this jurisdiction.
Cover: NFPA 101 (Life Safety Code) and NFPA 99 (Health Care Facilities Code) as adopted by CMS,
OSHA healthcare-specific standards (bloodborne pathogens 29 CFR 1910.1030, hazard communication),
EPA medical waste management (RCRA regulated medical waste),
state medical waste disposal and tracking requirements,
and CMS/Joint Commission environment of care standards.
Set current_value to a SHORT summary (under 80 chars).""",

    "pharmacy_drugs": """Research PHARMACY AND CONTROLLED SUBSTANCES requirements in this jurisdiction.
Cover: DEA registration and Schedule II-V prescribing/dispensing requirements (21 CFR Parts 1301-1321),
state PDMP (Prescription Drug Monitoring Program) mandates and interstate data sharing,
340B Drug Pricing Program compliance for covered entities,
DSCSA (Drug Supply Chain Security Act) serialization and verification requirements,
USP compounding standards (USP <795>, <797>, <800>),
and state pharmacy practice act requirements.
Set current_value to a SHORT summary (under 80 chars).""",

    "payer_relations": """Research PAYER RELATIONS AND MANAGED CARE requirements in this jurisdiction.
Cover: Medicare Advantage (MA) regulatory requirements (42 CFR Part 422),
Medicaid managed care organization (MCO) requirements (42 CFR Part 438),
No Surprises Act (NSA) requirements including independent dispute resolution (IDR),
state surprise billing protections,
network adequacy requirements,
and state-specific managed care regulations and prompt payment laws.
Set current_value to a SHORT summary (under 80 chars).""",

    "reproductive_behavioral": """Research REPRODUCTIVE AND BEHAVIORAL HEALTH requirements in this jurisdiction.
Cover: post-Dobbs state abortion laws (restrictions, protections, shield laws),
42 CFR Part 2 (Confidentiality of Substance Use Disorder Patient Records),
Mental Health Parity and Addiction Equity Act (MHPAEA) compliance,
state behavioral health licensure and practice requirements,
state reproductive health privacy protections,
and any state-specific mental health or substance abuse treatment mandates.
Set current_value to a SHORT summary (under 80 chars).""",

    "pediatric_vulnerable": """Research PEDIATRIC AND VULNERABLE POPULATION requirements in this jurisdiction.
Cover: CAPTA (Child Abuse Prevention and Treatment Act) mandatory reporting requirements,
Elder Justice Act provisions for healthcare settings,
state mandatory reporting laws for child/elder abuse,
emancipated minor and mature minor consent rules,
pediatric-specific consent and privacy requirements,
and state-specific protections for vulnerable populations in healthcare.
Set current_value to a SHORT summary (under 80 chars).""",

    "telehealth": """Research TELEHEALTH AND DIGITAL HEALTH requirements in this jurisdiction.
Cover: Interstate Medical Licensure Compact (IMLC) participation,
Nurse Licensure Compact (NLC) participation,
remote patient monitoring (RPM) reimbursement and licensure rules,
state telehealth parity laws (coverage and reimbursement),
state-specific telehealth prescribing rules (especially controlled substances),
and state requirements for provider-patient relationship establishment via telehealth.
Set current_value to a SHORT summary (under 80 chars).""",

    "medical_devices": """Research MEDICAL DEVICE AND EQUIPMENT requirements in this jurisdiction.
Cover: FDA Medical Device Reporting (MDR) requirements (21 CFR Part 803),
Unique Device Identification (UDI) system requirements,
radiation-emitting product standards (21 CFR Parts 1000-1050),
state radiation machine registration and inspection requirements,
and state-specific medical device or equipment safety regulations.
Set current_value to a SHORT summary (under 80 chars).""",

    "transplant_organ": """Research TRANSPLANT AND ORGAN PROCUREMENT requirements in this jurisdiction.
Cover: National Organ Transplant Act (NOTA, 42 U.S.C. § 274),
OPTN (Organ Procurement and Transplantation Network) bylaws and policies,
CMS transplant program Conditions of Participation (42 CFR § 482.68-104),
state anatomical gift acts (based on Revised Uniform Anatomical Gift Act),
and state-specific organ/tissue donation and transplant regulations.
Set current_value to a SHORT summary (under 80 chars).""",

    "antitrust": """Research HEALTHCARE ANTITRUST AND COMPETITION requirements in this jurisdiction.
Cover: Sherman Antitrust Act application to healthcare (price fixing, market allocation),
FTC and DOJ healthcare merger enforcement and guidelines,
state Certificate of Need (CON) laws and requirements,
state antitrust exemptions or immunities for healthcare entities,
and any state-specific healthcare competition regulations.
Set current_value to a SHORT summary (under 80 chars).""",

    "tax_exempt": """Research TAX-EXEMPT HEALTHCARE ORGANIZATION requirements in this jurisdiction.
Cover: IRC § 501(r) requirements for charitable hospitals (community benefit, financial assistance policies, billing/collections limitations),
Community Health Needs Assessment (CHNA) requirements,
IRS Schedule H reporting obligations,
state property tax exemptions for healthcare organizations,
and state-specific charitable organization requirements for healthcare entities.
Set current_value to a SHORT summary (under 80 chars).""",

    "language_access": """Research LANGUAGE ACCESS AND CIVIL RIGHTS requirements for healthcare in this jurisdiction.
Cover: Title VI of the Civil Rights Act (language access for LEP patients),
Section 1557 of the ACA (nondiscrimination in health programs),
ADA Title III requirements for healthcare facilities,
state language access laws for healthcare settings,
and state-specific civil rights protections in healthcare.
Set current_value to a SHORT summary (under 80 chars).""",

    "records_retention": """Research MEDICAL RECORDS RETENTION requirements in this jurisdiction.
Cover: state medical records retention periods (adult and minor patients),
HIPAA 6-year retention requirement for policies and documentation (45 CFR § 164.530(j)),
EMTALA log retention requirements,
state-specific requirements for electronic health record retention and destruction,
and any profession-specific records retention requirements.
Set current_value to a SHORT summary (under 80 chars).""",

    "marketing_comms": """Research HEALTHCARE MARKETING AND COMMUNICATIONS requirements in this jurisdiction.
Cover: HIPAA marketing authorization requirements (45 CFR § 164.508(a)(3)),
Medicare Communications and Marketing Guidelines (MCMG),
TCPA (Telephone Consumer Protection Act) as applied to healthcare communications,
state anti-kickback and fee-splitting laws as they relate to marketing,
and state-specific healthcare advertising regulations.
Set current_value to a SHORT summary (under 80 chars).""",

    "emerging_regulatory": """Research EMERGING REGULATORY requirements for healthcare in this jurisdiction.
Cover: AI and Software as a Medical Device (SaMD) regulations (FDA framework),
Social Determinants of Health (SDOH) screening and reporting requirements,
ESG (Environmental, Social, Governance) reporting requirements for healthcare,
state genomic data privacy laws,
state cannabis/marijuana laws affecting healthcare employers and drug testing,
and any other emerging healthcare regulatory trends in this jurisdiction.
Set current_value to a SHORT summary (under 80 chars).""",
}


# ---------------------------------------------------------------------------
# CATEGORY_ALIASES — map common misspellings / variants to canonical keys
# ---------------------------------------------------------------------------

CATEGORY_ALIASES: Dict[str, str] = {
    "meal_rest_breaks": "meal_breaks",
    "meal_and_rest_breaks": "meal_breaks",
    "meal_periods": "meal_breaks",
    "rest_breaks": "meal_breaks",
    "payday_frequency": "pay_frequency",
    "pay_day_frequency": "pay_frequency",
    "final_wage": "final_pay",
    "final_wages": "final_pay",
    "final_paycheck": "final_pay",
    "final_paychecks": "final_pay",
    "minor_work_permits": "minor_work_permit",
    "work_permit": "minor_work_permit",
    "work_permits": "minor_work_permit",
    "youth_employment": "minor_work_permit",
    "youth_work_permit": "minor_work_permit",
    "scheduling_and_reporting_time": "scheduling_reporting",
    "reporting_time": "scheduling_reporting",
    "predictive_scheduling": "scheduling_reporting",
    "fair_workweek": "scheduling_reporting",
    "leave_of_absence": "leave",
    "family_leave": "leave",
    "medical_leave": "leave",
    "pfml": "leave",
    "paid_family_leave": "leave",
    "family_medical_leave": "leave",
    "osha": "workplace_safety",
    "occupational_safety": "workplace_safety",
    "safety": "workplace_safety",
    "workplace_health": "workplace_safety",
    "workers_compensation": "workers_comp",
    "worker_comp": "workers_comp",
    "workman_comp": "workers_comp",
    "workmen_comp": "workers_comp",
    "discrimination": "anti_discrimination",
    "harassment": "anti_discrimination",
    "equal_pay": "anti_discrimination",
    "pay_equity": "anti_discrimination",
    "ada": "anti_discrimination",
    "ada_accommodations": "anti_discrimination",
    # Healthcare categories
    "hipaa": "hipaa_privacy",
    "hipaa_security": "hipaa_privacy",
    "hitech": "hipaa_privacy",
    "phi": "hipaa_privacy",
    "42_cfr_part_2": "hipaa_privacy",
    "part_2": "hipaa_privacy",
    "substance_use_records": "hipaa_privacy",
    "false_claims": "billing_integrity",
    "anti_kickback": "billing_integrity",
    "stark_law": "billing_integrity",
    "medicare_billing": "billing_integrity",
    "mhpaea": "billing_integrity",
    "mental_health_parity": "billing_integrity",
    "joint_commission": "clinical_safety",
    "cms_conditions": "clinical_safety",
    "infection_control": "clinical_safety",
    "bloodborne_pathogens": "clinical_safety",
    "medical_waste": "clinical_safety",
    "epa_medical_waste": "clinical_safety",
    "credentialing": "healthcare_workforce",
    "oig_exclusion": "healthcare_workforce",
    "mandatory_reporter": "healthcare_workforce",
    "oig_compliance": "corporate_integrity",
    "qui_tam": "corporate_integrity",
    "irb": "research_consent",
    "gcp": "research_consent",
    "facility_licensure": "state_licensing",
    "abortion": "state_licensing",
    "dobbs": "state_licensing",
    "ada_accessibility": "state_licensing",
    "emtala": "emergency_preparedness",
    "nfpa": "emergency_preparedness",
    "life_safety_code": "emergency_preparedness",
}


# ---------------------------------------------------------------------------
# CATEGORY_AUTHORITY_SOURCES — authoritative federal / national sources
# per category, aggregated from regulation authority_sources and manual entries
# ---------------------------------------------------------------------------

CATEGORY_AUTHORITY_SOURCES: Dict[str, List[Dict[str, str]]] = {
    # Healthcare
    "hipaa_privacy": [
        {"domain": "hhs.gov/hipaa", "name": "HHS Office for Civil Rights (HIPAA)"},
        {"domain": "ecfr.gov", "name": "45 CFR Part 164 (Privacy Rule)"},
    ],
    "billing_integrity": [
        {"domain": "oig.hhs.gov", "name": "HHS Office of Inspector General"},
        {"domain": "cms.gov", "name": "CMS Billing & Coding"},
        {"domain": "ftc.gov", "name": "FTC Healthcare Billing"},
    ],
    "clinical_safety": [
        {"domain": "jointcommission.org", "name": "The Joint Commission"},
        {"domain": "cms.gov", "name": "CMS Conditions of Participation"},
        {"domain": "ahrq.gov", "name": "AHRQ Patient Safety"},
    ],
    "healthcare_workforce": [
        {"domain": "hrsa.gov", "name": "HRSA Health Workforce"},
        {"domain": "bls.gov", "name": "BLS Occupational Outlook"},
        {"domain": "cms.gov", "name": "CMS Staffing Requirements"},
    ],
    "corporate_integrity": [
        {"domain": "oig.hhs.gov/compliance", "name": "OIG Corporate Integrity Agreements"},
        {"domain": "hhs.gov", "name": "HHS Compliance Guidance"},
    ],
    "research_consent": [
        {"domain": "hhs.gov/ohrp", "name": "HHS Office for Human Research Protections"},
        {"domain": "fda.gov", "name": "FDA 21 CFR Part 50 (Informed Consent)"},
        {"domain": "ecfr.gov", "name": "45 CFR Part 46 (Common Rule)"},
    ],
    "state_licensing": [
        {"domain": "hhs.gov", "name": "HHS State Health Licensing"},
        {"domain": "cms.gov", "name": "CMS Provider Enrollment"},
    ],
    "emergency_preparedness": [
        {"domain": "aspr.hhs.gov", "name": "ASPR (HHS Office of Preparedness)"},
        {"domain": "cms.gov", "name": "CMS Emergency Preparedness Rule"},
        {"domain": "cdc.gov", "name": "CDC Public Health Emergency"},
    ],
    # Oncology
    "radiation_safety": [
        {"domain": "nrc.gov", "name": "Nuclear Regulatory Commission"},
        {"domain": "cdc.gov/niosh", "name": "NIOSH Radiation Safety"},
        {"domain": "osha.gov", "name": "OSHA Ionizing Radiation (29 CFR 1910.1096)"},
    ],
    "chemotherapy_handling": [
        {"domain": "cdc.gov/niosh", "name": "NIOSH Hazardous Drug Alert (2004-165)"},
        {"domain": "usp.org", "name": "USP 800 Hazardous Drugs Standard"},
        {"domain": "osha.gov", "name": "OSHA Hazardous Drugs in Healthcare"},
    ],
    "tumor_registry": [
        {"domain": "naaccr.org", "name": "NAACCR (North American Cancer Registries)"},
        {"domain": "seer.cancer.gov", "name": "NCI SEER Program"},
        {"domain": "cdc.gov/cancer", "name": "CDC National Program of Cancer Registries"},
    ],
    "oncology_clinical_trials": [
        {"domain": "clinicaltrials.gov", "name": "ClinicalTrials.gov"},
        {"domain": "nci.nih.gov", "name": "National Cancer Institute"},
        {"domain": "fda.gov", "name": "FDA IND/Clinical Trial Regulations"},
    ],
    "oncology_patient_rights": [
        {"domain": "cancer.gov", "name": "NCI Patient Rights"},
        {"domain": "cms.gov", "name": "CMS Patient Rights (Conditions of Participation)"},
        {"domain": "hhs.gov/ocr", "name": "HHS Office for Civil Rights"},
    ],
    # Medical Compliance
    "health_it": [
        {"domain": "healthit.gov", "name": "ONC Health IT"},
        {"domain": "congress.gov", "name": "21st Century Cures Act"},
        {"domain": "rce.sequoiaproject.org", "name": "TEFCA RCE"},
    ],
    "quality_reporting": [
        {"domain": "qpp.cms.gov", "name": "CMS Quality Payment Program"},
        {"domain": "ncqa.org", "name": "NCQA HEDIS Measures"},
        {"domain": "cms.gov", "name": "CMS Value-Based Programs"},
    ],
    "cybersecurity": [
        {"domain": "nist.gov", "name": "NIST Cybersecurity Framework"},
        {"domain": "hhs.gov/hipaa", "name": "HHS HIPAA Security Rule"},
        {"domain": "cisa.gov", "name": "CISA Healthcare Cybersecurity"},
    ],
    "environmental_safety": [
        {"domain": "nfpa.org", "name": "NFPA Life Safety Code"},
        {"domain": "osha.gov", "name": "OSHA Healthcare Standards"},
        {"domain": "epa.gov", "name": "EPA Medical Waste (RCRA)"},
    ],
    "pharmacy_drugs": [
        {"domain": "deadiversion.usdoj.gov", "name": "DEA Diversion Control"},
        {"domain": "hrsa.gov/opa", "name": "HRSA 340B Program"},
        {"domain": "fda.gov", "name": "FDA DSCSA / Drug Safety"},
    ],
    "payer_relations": [
        {"domain": "cms.gov", "name": "CMS Medicare Advantage / Medicaid MCO"},
        {"domain": "cms.gov/nosurprises", "name": "No Surprises Act (CMS)"},
    ],
    "reproductive_behavioral": [
        {"domain": "samhsa.gov", "name": "SAMHSA (42 CFR Part 2)"},
        {"domain": "cms.gov", "name": "CMS Mental Health Parity"},
        {"domain": "hhs.gov/ocr", "name": "HHS Office for Civil Rights"},
    ],
    "pediatric_vulnerable": [
        {"domain": "acf.hhs.gov", "name": "ACF (CAPTA / Child Welfare)"},
        {"domain": "acl.gov", "name": "ACL Elder Justice"},
        {"domain": "childwelfare.gov", "name": "Child Welfare Information Gateway"},
    ],
    "telehealth": [
        {"domain": "imlcc.org", "name": "Interstate Medical Licensure Compact"},
        {"domain": "ncsbn.org/nlc", "name": "Nurse Licensure Compact"},
        {"domain": "cchpca.org", "name": "CCHP Telehealth Policy"},
    ],
    "medical_devices": [
        {"domain": "fda.gov/medicaldevices", "name": "FDA Medical Devices"},
        {"domain": "accessdata.fda.gov", "name": "FDA MDR / UDI Database"},
    ],
    "transplant_organ": [
        {"domain": "optn.transplant.hrsa.gov", "name": "OPTN / UNOS"},
        {"domain": "cms.gov", "name": "CMS Transplant CoPs"},
        {"domain": "organdonor.gov", "name": "HRSA Organ Donation"},
    ],
    "antitrust": [
        {"domain": "ftc.gov", "name": "FTC Healthcare Competition"},
        {"domain": "justice.gov/atr", "name": "DOJ Antitrust Division"},
    ],
    "tax_exempt": [
        {"domain": "irs.gov", "name": "IRS \u00a7 501(r) / Schedule H"},
        {"domain": "aha.org", "name": "AHA Community Benefit"},
    ],
    "language_access": [
        {"domain": "hhs.gov/ocr", "name": "HHS OCR Section 1557"},
        {"domain": "lep.gov", "name": "Federal LEP Resources"},
        {"domain": "ada.gov", "name": "ADA Title III"},
    ],
    "records_retention": [
        {"domain": "hhs.gov/hipaa", "name": "HIPAA Retention Requirements"},
        {"domain": "ahima.org", "name": "AHIMA Retention Guidelines"},
    ],
    "marketing_comms": [
        {"domain": "hhs.gov/hipaa", "name": "HIPAA Marketing Rules"},
        {"domain": "cms.gov", "name": "CMS Marketing Guidelines (MCMG)"},
        {"domain": "fcc.gov", "name": "FCC TCPA Enforcement"},
    ],
    "emerging_regulatory": [
        {"domain": "fda.gov", "name": "FDA AI/SaMD Framework"},
        {"domain": "cms.gov", "name": "CMS SDOH Initiatives"},
        {"domain": "hhs.gov", "name": "HHS Emerging Policy"},
    ],
}


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


# ---------------------------------------------------------------------------
# Completeness helper
# ---------------------------------------------------------------------------

def get_missing_regulations(
    category: str, existing_keys: Set[str]
) -> List[RegulationDef]:
    """Return regulations in this category not yet present in the DB."""
    expected = EXPECTED_REGULATION_KEYS.get(category, frozenset())
    missing_keys = expected - existing_keys
    return [REGULATION_MAP[k] for k in sorted(missing_keys) if k in REGULATION_MAP]
