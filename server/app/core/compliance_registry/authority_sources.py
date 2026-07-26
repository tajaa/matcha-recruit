from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple  # noqa: F401


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
    # Life Sciences
    "gmp_manufacturing": [
        {"domain": "fda.gov/drugs/pharmaceutical-quality-resources", "name": "FDA Pharmaceutical Quality"},
        {"domain": "ecfr.gov", "name": "21 CFR Parts 210/211 (Drug cGMP)"},
        {"domain": "fda.gov/medical-devices/quality-system-qs-regulationmedical-device-good-manufacturing-practices", "name": "FDA Device QSR"},
    ],
    "glp_nonclinical": [
        {"domain": "fda.gov/science-research/good-laboratory-practices", "name": "FDA GLP"},
        {"domain": "ecfr.gov", "name": "21 CFR Part 58 (GLP)"},
    ],
    "clinical_trials_gcp": [
        {"domain": "fda.gov/science-research/clinical-trials-and-human-subject-protection", "name": "FDA Clinical Trials"},
        {"domain": "ich.org", "name": "ICH E6(R2) GCP Guidelines"},
        {"domain": "clinicaltrials.gov", "name": "ClinicalTrials.gov"},
        {"domain": "ecfr.gov", "name": "21 CFR Part 312 (IND)"},
    ],
    "drug_supply_chain": [
        {"domain": "fda.gov/drugs/drug-supply-chain-integrity/drug-supply-chain-security-act-dscsa", "name": "FDA DSCSA"},
        {"domain": "ecfr.gov", "name": "21 CFR Part 7 (Recalls)"},
        {"domain": "nabp.pharmacy", "name": "NABP Wholesale Distribution"},
    ],
    "sunshine_open_payments": [
        {"domain": "cms.gov/openpayments", "name": "CMS Open Payments"},
        {"domain": "oig.hhs.gov", "name": "OIG Compliance Guidance for Pharma"},
    ],
    "biosafety_lab": [
        {"domain": "cdc.gov/labs/BMBL.html", "name": "CDC BMBL Guidelines"},
        {"domain": "osp.od.nih.gov/biotechnology/nih-guidelines", "name": "NIH rDNA Guidelines"},
        {"domain": "selectagents.gov", "name": "Federal Select Agent Program"},
        {"domain": "osha.gov", "name": "OSHA Lab Standard (29 CFR 1910.1450)"},
    ],
}


