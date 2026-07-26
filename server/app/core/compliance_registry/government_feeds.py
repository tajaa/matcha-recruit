from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple  # noqa: F401


# ---------------------------------------------------------------------------
# CATEGORY_FEDERAL_REGISTER_AGENCIES — maps categories to Federal Register
# agency slugs, CFR titles, and keywords for direct API fetching
# ---------------------------------------------------------------------------

CATEGORY_FEDERAL_REGISTER_AGENCIES: Dict[str, Dict] = {
    # ── Labor ──────────────────────────────────────────────────────────────
    "minimum_wage": {
        "agencies": ["wage-and-hour-division", "labor-department"],
        "cfr_titles": [29],
        # 29 CFR 780 = FLSA agricultural/exempt salary threshold (keys to minimum_wage:exempt_salary)
        # 29 CFR 516 and 531 are recordkeeping/wage-payment regs already covered under
        # pay_frequency, posting_requirements, and final_pay — remove them here to avoid
        # minimum_wage:general key collision (minimum_wage uses rate_type keys, not title keys)
        "cfr_parts": {29: [780]},
        "keywords": ["minimum wage", "FLSA", "Fair Labor Standards"],
    },
    "overtime": {
        "agencies": ["wage-and-hour-division"],
        "cfr_titles": [29],
        "cfr_parts": {29: [541, 778, 785]},
        "keywords": ["overtime", "exempt", "salary threshold"],
    },
    "sick_leave": {
        "agencies": ["wage-and-hour-division", "labor-department"],
        "cfr_titles": [29],
        "cfr_parts": {29: [825]},
        "keywords": ["paid sick leave", "sick time", "earned sick"],
    },
    "meal_breaks": {
        "agencies": ["wage-and-hour-division"],
        "cfr_titles": [29],
        "cfr_parts": {29: [785]},
        "keywords": ["meal period", "rest break", "break time for nursing"],
    },
    "pay_frequency": {
        "agencies": ["wage-and-hour-division"],
        "cfr_titles": [29],
        "cfr_parts": {29: [516]},
        "keywords": ["pay frequency", "payday", "wage payment"],
    },
    "final_pay": {
        "agencies": ["wage-and-hour-division"],
        "cfr_titles": [29],
        "cfr_parts": {29: [531]},
        "keywords": ["final pay", "final wages", "wage payment upon separation"],
    },
    "minor_work_permit": {
        "agencies": ["wage-and-hour-division"],
        "cfr_titles": [29],
        "cfr_parts": {29: [570]},
        "keywords": ["child labor", "minor employment", "youth employment"],
    },
    "scheduling_reporting": {
        "agencies": ["wage-and-hour-division", "labor-department"],
        "cfr_titles": [29],
        "cfr_parts": {29: [516, 785]},
        "keywords": ["scheduling", "reporting time", "predictive scheduling"],
    },
    "leave": {
        "agencies": ["wage-and-hour-division", "labor-department"],
        "cfr_titles": [29],
        "cfr_parts": {29: [825]},
        "keywords": ["FMLA", "family leave", "medical leave", "paid leave"],
    },
    "workplace_safety": {
        "agencies": ["occupational-safety-and-health-administration"],
        "cfr_titles": [29],
        "cfr_parts": {29: [1903, 1904, 1910]},
        "keywords": ["OSHA", "workplace safety", "recordkeeping", "general duty"],
    },
    "workers_comp": {
        "agencies": ["labor-department", "workers-compensation-programs-office"],
        "cfr_titles": [20],
        "cfr_parts": {20: [10, 702]},
        "keywords": ["workers compensation", "work injury", "occupational injury"],
    },
    "anti_discrimination": {
        "agencies": ["equal-employment-opportunity-commission"],
        "cfr_titles": [29],
        "cfr_parts": {29: [1600, 1604, 1605, 1606, 1607, 1608]},
        "keywords": ["discrimination", "EEO", "Title VII", "ADA", "harassment"],
    },
    # ── Business / Tax ────────────────────────────────────────────────────
    "business_license": {
        "agencies": ["small-business-administration"],
        "cfr_titles": [13],
        "cfr_parts": {13: [121, 124]},
        "keywords": ["business license", "business registration"],
    },
    "tax_rate": {
        "agencies": ["internal-revenue-service", "treasury-department"],
        "cfr_titles": [26],
        "cfr_parts": {26: [31, 54]},
        "keywords": ["employer tax", "payroll tax", "FICA", "FUTA"],
    },
    "posting_requirements": {
        "agencies": ["wage-and-hour-division", "equal-employment-opportunity-commission", "occupational-safety-and-health-administration"],
        "cfr_titles": [29],
        "cfr_parts": {29: [516]},
        "keywords": ["workplace poster", "posting requirement", "notice posting"],
    },
    # ── Healthcare ────────────────────────────────────────────────────────
    "hipaa_privacy": {
        "agencies": ["health-and-human-services-department"],
        "cfr_titles": [45],
        "cfr_parts": {45: [160, 164]},
        "keywords": ["HIPAA", "privacy rule", "protected health information"],
    },
    "billing_integrity": {
        "agencies": ["centers-for-medicare-medicaid-services", "health-and-human-services-department"],
        "cfr_titles": [42],
        "cfr_parts": {42: [1001, 1003]},
        "keywords": ["billing fraud", "false claims", "anti-kickback", "Stark law"],
    },
    "clinical_safety": {
        "agencies": ["centers-for-medicare-medicaid-services", "food-and-drug-administration"],
        "cfr_titles": [42],
        "cfr_parts": {42: [482, 483, 484, 485]},
        "keywords": ["patient safety", "conditions of participation", "clinical quality"],
    },
    "healthcare_workforce": {
        "agencies": ["health-and-human-services-department", "centers-for-medicare-medicaid-services"],
        "cfr_titles": [42],
        "cfr_parts": {42: [482, 488]},
        "keywords": ["healthcare staffing", "nurse staffing", "provider enrollment"],
    },
    "corporate_integrity": {
        "agencies": ["health-and-human-services-department"],
        "cfr_titles": [42],
        "cfr_parts": {42: [1001]},
        "keywords": ["corporate integrity", "OIG compliance", "compliance program"],
    },
    "research_consent": {
        "agencies": ["health-and-human-services-department", "food-and-drug-administration"],
        "cfr_titles": [45, 21],
        "cfr_parts": {45: [46], 21: [50, 56]},
        "keywords": ["informed consent", "common rule", "human subjects", "IRB"],
    },
    "state_licensing": {
        "agencies": ["centers-for-medicare-medicaid-services", "health-and-human-services-department"],
        "cfr_titles": [42],
        "cfr_parts": {42: [482, 489]},
        "keywords": ["provider licensing", "facility licensing", "certification"],
    },
    "emergency_preparedness": {
        "agencies": ["centers-for-medicare-medicaid-services", "health-and-human-services-department"],
        "cfr_titles": [42],
        "cfr_parts": {42: [482, 485]},
        "keywords": ["emergency preparedness", "disaster planning", "EMTALA"],
    },
    # ── Oncology ──────────────────────────────────────────────────────────
    "radiation_safety": {
        "agencies": ["nuclear-regulatory-commission", "occupational-safety-and-health-administration"],
        "cfr_titles": [10, 29],
        "cfr_parts": {10: [20, 35], 29: [1910]},
        "keywords": ["radiation safety", "ionizing radiation", "radioactive materials"],
    },
    "chemotherapy_handling": {
        "agencies": ["occupational-safety-and-health-administration", "food-and-drug-administration"],
        "cfr_titles": [29, 21],
        "cfr_parts": {29: [1910], 21: [210, 211]},
        "keywords": ["hazardous drugs", "chemotherapy", "cytotoxic", "USP 800"],
    },
    "tumor_registry": {
        "agencies": ["health-and-human-services-department", "centers-for-medicare-medicaid-services"],
        "cfr_titles": [42],
        "cfr_parts": {42: [482]},
        "keywords": ["tumor registry", "cancer registry", "cancer reporting"],
    },
    "oncology_clinical_trials": {
        "agencies": ["food-and-drug-administration", "health-and-human-services-department"],
        "cfr_titles": [21, 42],
        "cfr_parts": {21: [50, 56, 312], 42: [11]},
        "keywords": ["clinical trial", "oncology trial", "investigational drug"],
    },
    "oncology_patient_rights": {
        "agencies": ["centers-for-medicare-medicaid-services", "health-and-human-services-department"],
        "cfr_titles": [42],
        "cfr_parts": {42: [482]},
        "keywords": ["patient rights", "oncology patient", "cancer patient rights"],
    },
    # ── Medical Compliance ────────────────────────────────────────────────
    "health_it": {
        "agencies": ["health-and-human-services-department"],
        "cfr_titles": [45],
        "cfr_parts": {45: [170]},
        "keywords": ["health IT", "electronic health record", "interoperability", "HITECH"],
    },
    "quality_reporting": {
        "agencies": ["centers-for-medicare-medicaid-services"],
        "cfr_titles": [42],
        "cfr_parts": {42: [414, 415]},
        "keywords": ["quality reporting", "MIPS", "QPP", "value-based"],
    },
    "cybersecurity": {
        "agencies": ["health-and-human-services-department"],
        "cfr_titles": [45],
        "cfr_parts": {45: [164]},
        "keywords": ["cybersecurity", "HIPAA security", "breach notification"],
    },
    "environmental_safety": {
        "agencies": ["environmental-protection-agency", "occupational-safety-and-health-administration"],
        "cfr_titles": [40, 29],
        "cfr_parts": {40: [260, 261, 262], 29: [1910]},
        "keywords": ["medical waste", "hazardous waste", "environmental compliance"],
    },
    "pharmacy_drugs": {
        "agencies": ["food-and-drug-administration", "drug-enforcement-administration"],
        "cfr_titles": [21],
        "cfr_parts": {21: [1301, 1306, 1308]},
        "keywords": ["pharmacy", "controlled substance", "drug scheduling", "REMS"],
    },
    "payer_relations": {
        "agencies": ["centers-for-medicare-medicaid-services"],
        "cfr_titles": [42],
        "cfr_parts": {42: [422, 423]},
        "keywords": ["payer", "managed care", "network adequacy", "Medicare Advantage"],
    },
    "reproductive_behavioral": {
        "agencies": ["health-and-human-services-department", "substance-abuse-and-mental-health-services-administration"],
        "cfr_titles": [42],
        "cfr_parts": {42: [2, 438]},
        "keywords": ["reproductive health", "behavioral health", "mental health parity", "substance abuse"],
    },
    "pediatric_vulnerable": {
        "agencies": ["health-and-human-services-department", "centers-for-medicare-medicaid-services"],
        "cfr_titles": [42, 45],
        "cfr_parts": {42: [441, 483], 45: [1340]},
        "keywords": ["pediatric", "vulnerable populations", "elder abuse", "child abuse"],
    },
    "telehealth": {
        "agencies": ["centers-for-medicare-medicaid-services", "health-and-human-services-department"],
        "cfr_titles": [42],
        "cfr_parts": {42: [410, 414]},
        "keywords": ["telehealth", "telemedicine", "remote patient monitoring"],
    },
    "medical_devices": {
        "agencies": ["food-and-drug-administration"],
        "cfr_titles": [21],
        "cfr_parts": {21: [800, 801, 807, 820]},
        "keywords": ["medical device", "device safety", "510(k)", "premarket"],
    },
    "transplant_organ": {
        "agencies": ["health-and-human-services-department", "centers-for-medicare-medicaid-services"],
        "cfr_titles": [42],
        "cfr_parts": {42: [486]},
        "keywords": ["organ transplant", "organ procurement", "UNOS", "transplant center"],
    },
    # ── Supplementary ────────────────────────────────────────────────────
    "antitrust": {
        "agencies": ["federal-trade-commission", "justice-department"],
        "cfr_titles": [16],
        "cfr_parts": {16: [801, 802]},
        "keywords": ["antitrust", "healthcare merger", "competition", "FTC"],
    },
    "tax_exempt": {
        "agencies": ["internal-revenue-service", "treasury-department"],
        "cfr_titles": [26],
        "cfr_parts": {26: [1, 53]},
        "keywords": ["tax exempt", "501(c)(3)", "nonprofit hospital", "community benefit"],
    },
    "language_access": {
        "agencies": ["health-and-human-services-department"],
        "cfr_titles": [45],
        "cfr_parts": {45: [80, 84]},
        "keywords": ["language access", "LEP", "limited English", "interpreter"],
    },
    "records_retention": {
        "agencies": ["health-and-human-services-department", "centers-for-medicare-medicaid-services"],
        "cfr_titles": [42, 45],
        "cfr_parts": {42: [485], 45: [164]},
        "keywords": ["records retention", "medical records", "document retention"],
    },
    "marketing_comms": {
        "agencies": ["federal-trade-commission", "food-and-drug-administration"],
        "cfr_titles": [16, 21],
        "cfr_parts": {16: [255], 21: [202]},
        "keywords": ["healthcare marketing", "advertising", "FTC health claims"],
    },
    "emerging_regulatory": {
        "agencies": ["health-and-human-services-department", "food-and-drug-administration"],
        "cfr_titles": [42, 21],
        "cfr_parts": {45: [170], 21: [890]},
        "keywords": ["AI health", "digital health", "emerging technology", "precision medicine"],
    },
}

# Healthcare-related categories for CMS data fetching
CMS_CATEGORIES: FrozenSet[str] = frozenset(
    k for k, v in CATEGORY_FEDERAL_REGISTER_AGENCIES.items()
    if any(a in ("centers-for-medicare-medicaid-services",) for a in v["agencies"])
)

# OpenStates subject keywords for state bill tracking
CATEGORY_OPENSTATES_SUBJECTS: Dict[str, List[str]] = {
    "minimum_wage": ["minimum wage", "FLSA"],
    "overtime": ["overtime pay", "overtime exemption"],
    "sick_leave": ["sick leave", "paid sick leave"],
    "leave": ["family leave", "parental leave", "FMLA"],
    "workplace_safety": ["workplace safety", "OSHA"],
    "workers_comp": ["workers compensation", "workers comp"],
    "anti_discrimination": ["employment discrimination", "equal pay", "civil rights employment"],
    "scheduling_reporting": ["fair scheduling", "predictive scheduling", "advance notice scheduling"],
    "posting_requirements": ["labor law posting", "workplace notice"],
    "business_license": ["business license", "business registration"],
    "minor_work_permit": ["child labor", "youth employment", "minor work permit"],
}
