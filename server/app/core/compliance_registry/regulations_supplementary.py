from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple  # noqa: F401

from app.core.compliance_registry._types import RegulationDef


REGULATIONS_SUPPLEMENTARY: List[RegulationDef] = [

    # ── Supplementary: posting_requirements ───────────────────────────────
    RegulationDef(
        key="minimum_wage_poster",
        category="posting_requirements",
        name="Minimum Wage Poster",
        description="Federal and state requirements to display minimum wage posters in the workplace",
        enforcing_agency="WHD / State labor agencies",
        state_variance="Low/None",
        update_frequency="Updated when wage rates change",
        authority_sources=(
            {"domain": "dol.gov/agencies/whd/posters", "name": "WHD Workplace Posters"},
        ),
    ),
    RegulationDef(
        key="discrimination_poster",
        category="posting_requirements",
        name="EEO / Discrimination Poster",
        description="Federal 'EEO is the Law' poster and state equivalents; required in all workplaces with covered employees",
        enforcing_agency="EEOC / State civil rights agencies",
        state_variance="Low/None",
        update_frequency="Updated when laws change; federal poster revised 2022",
        authority_sources=(
            {"domain": "eeoc.gov/poster", "name": "EEOC Poster"},
        ),
    ),
    RegulationDef(
        key="osha_poster",
        category="posting_requirements",
        name="OSHA Safety Poster",
        description="Federal OSHA 'Job Safety and Health' poster and state-plan equivalents",
        enforcing_agency="OSHA / State plan states",
        state_variance="Low/None",
        update_frequency="Rarely updated; current version effective since 2013",
        authority_sources=(
            {"domain": "osha.gov/publications/poster", "name": "OSHA Poster"},
        ),
    ),
    RegulationDef(
        key="workers_comp_poster",
        category="posting_requirements",
        name="Workers' Compensation Poster",
        description="State-mandated poster with workers' comp carrier information and claim filing instructions",
        enforcing_agency="State WC boards",
        state_variance="Low/None",
        update_frequency="Updated when carrier changes or state revises poster",
        authority_sources=(
            {"domain": "dol.gov/general/topic/workcomp", "name": "DOL Workers' Comp"},
        ),
    ),
    RegulationDef(
        key="paid_sick_leave_poster",
        category="posting_requirements",
        name="Paid Sick Leave Poster",
        description="State/local requirements to post paid sick leave notice with accrual rates, usage rights, and complaint information",
        enforcing_agency="State / Local government",
        state_variance="Low/None",
        update_frequency="Updated when sick leave laws change",
        authority_sources=(
            {"domain": "ncsl.org/labor-and-employment/paid-sick-leave", "name": "NCSL Paid Sick Leave"},
        ),
    ),
    RegulationDef(
        key="family_leave_poster",
        category="posting_requirements",
        name="FMLA / Family Leave Poster",
        description="Federal FMLA poster and state family leave posting requirements",
        enforcing_agency="WHD / State labor agencies",
        state_variance="Low/None",
        update_frequency="Updated when leave laws change; federal poster revised periodically",
        authority_sources=(
            {"domain": "dol.gov/agencies/whd/fmla/posters", "name": "WHD FMLA Poster"},
        ),
    ),
    RegulationDef(
        key="whistleblower_poster",
        category="posting_requirements",
        name="Whistleblower Protection Poster",
        description="State requirements to post whistleblower/retaliation protection notices",
        enforcing_agency="State labor agencies",
        state_variance="Low/None",
        update_frequency="Updated when whistleblower laws change",
        authority_sources=(
            {"domain": "osha.gov/whistleblower", "name": "OSHA Whistleblower"},
        ),
    ),
    RegulationDef(
        key="wage_order_poster",
        category="posting_requirements",
        name="Wage Order / IWC Poster (CA)",
        description="California requirement to post applicable IWC Wage Order covering industry-specific rules for wages, hours, and working conditions",
        enforcing_agency="State labor agencies",
        state_variance="Low/None",
        update_frequency="IWC wage orders are frozen since 2004; poster requirement persists",
        authority_sources=(
            {"domain": "dir.ca.gov/iwc", "name": "CA DIR IWC"},
        ),
    ),
    RegulationDef(
        key="workplace_violence_poster",
        category="posting_requirements",
        name="Workplace Violence Prevention Poster",
        description="State requirements to post workplace violence prevention plan information (CA SB 553 and similar)",
        enforcing_agency="OSHA / State plan states",
        state_variance="Low/None",
        update_frequency="New requirement — CA effective 2024; other states may follow",
        authority_sources=(
            {"domain": "dir.ca.gov/dosh/workplace-violence", "name": "CA DOSH Workplace Violence"},
        ),
    ),

    # ── Supplementary: business_license ───────────────────────────────────
    RegulationDef(
        key="state_business_registration",
        category="business_license",
        name="State Business Entity Registration",
        description="State requirements for business entity formation and annual registration (LLC, Corp, LP filings with Secretary of State)",
        enforcing_agency="Secretary of State",
        state_variance="Moderate",
        update_frequency="Filing requirements and fees updated periodically",
        authority_sources=(
            {"domain": "sos.ca.gov/business-programs", "name": "CA Secretary of State"},
        ),
    ),
    RegulationDef(
        key="local_business_license",
        category="business_license",
        name="City / County Business License / Tax Registration",
        description="Local business license, tax registration certificate, and home occupation permits; renewal requirements vary",
        enforcing_agency="Local government",
        state_variance="High",
        update_frequency="Fees and requirements updated annually; vary widely by jurisdiction",
        authority_sources=(
            {"domain": "sba.gov/business-guide/launch-your-business/apply-licenses-permits", "name": "SBA Licenses"},
        ),
    ),
    RegulationDef(
        key="professional_licensing",
        category="business_license",
        name="Professional / Occupational Licensing",
        description="State licensing requirements for regulated professions (healthcare, legal, accounting, real estate, contractors, etc.)",
        enforcing_agency="State licensing boards",
        state_variance="Moderate",
        update_frequency="Licensing requirements updated periodically; reciprocity compacts expanding",
        authority_sources=(
            {"domain": "ncsl.org/labor-and-employment/occupational-licensing", "name": "NCSL Occupational Licensing"},
        ),
    ),
    RegulationDef(
        key="dba_registration",
        category="business_license",
        name="DBA / Fictitious Business Name Registration",
        description="Requirements to register doing-business-as or fictitious business names with county clerk or Secretary of State",
        enforcing_agency="County clerk / Secretary of State",
        state_variance="Low/None",
        update_frequency="Well-established; renewal periods vary (typically 5 years)",
        authority_sources=(
            {"domain": "sba.gov/business-guide/launch-your-business/choose-your-business-name", "name": "SBA Business Name"},
        ),
    ),

    # ── Supplementary: tax_rate ───────────────────────────────────────────
    RegulationDef(
        key="corporate_income_tax",
        category="tax_rate",
        name="State Corporate Income Tax Rates",
        description="State-level corporate income tax rates, apportionment methods, and filing requirements",
        enforcing_agency="State revenue department",
        state_variance="High",
        update_frequency="Rates adjusted by legislature; some states phasing down or eliminating",
        authority_sources=(
            {"domain": "taxfoundation.org/state-corporate-income-tax-rates", "name": "Tax Foundation Corporate Rates"},
        ),
    ),
    RegulationDef(
        key="franchise_tax",
        category="tax_rate",
        name="Franchise / Privilege Tax",
        description="State franchise, privilege, or capital stock taxes imposed on the right to do business (e.g., TX franchise tax, DE franchise tax)",
        enforcing_agency="State revenue department",
        state_variance="Moderate",
        update_frequency="Rates and thresholds adjusted periodically by legislature",
        authority_sources=(
            {"domain": "taxfoundation.org", "name": "Tax Foundation"},
        ),
    ),
    RegulationDef(
        key="unemployment_insurance_tax",
        category="tax_rate",
        name="State Unemployment Insurance Tax Rates",
        description="Employer UI tax rates based on experience rating; taxable wage base and rate schedules vary by state",
        enforcing_agency="State workforce agency",
        state_variance="High",
        update_frequency="Rates adjusted annually based on trust fund solvency and employer experience",
        authority_sources=(
            {"domain": "dol.gov/agencies/eta/unemployment-insurance-payment-accuracy", "name": "DOL UI"},
        ),
    ),
    RegulationDef(
        key="disability_insurance_tax",
        category="tax_rate",
        name="State Disability Insurance Tax Rates",
        description="Employee/employer contributions for state disability insurance (CA SDI, NJ TDI, NY DBL, HI TDI, RI TDI, PR SINOT)",
        enforcing_agency="State workforce agency",
        state_variance="High",
        update_frequency="Rates and taxable wage bases adjusted annually",
        authority_sources=(
            {"domain": "edd.ca.gov/disability", "name": "CA EDD Disability"},
        ),
    ),
    RegulationDef(
        key="employment_training_tax",
        category="tax_rate",
        name="Employment Training Tax / Fund",
        description="State-imposed taxes funding workforce training programs (e.g., CA ETT, NJ WFD)",
        enforcing_agency="State workforce agency",
        state_variance="Moderate",
        update_frequency="Rates are generally small and stable; adjusted periodically",
        authority_sources=(
            {"domain": "edd.ca.gov/employers/ett", "name": "CA EDD ETT"},
        ),
    ),
    RegulationDef(
        key="sales_use_tax",
        category="tax_rate",
        name="State / Local Sales and Use Tax",
        description="State and local sales/use tax rates, nexus rules, marketplace facilitator laws, and exemptions",
        enforcing_agency="State revenue department",
        state_variance="Moderate",
        update_frequency="Rates and nexus rules change frequently; marketplace laws expanding post-Wayfair",
        authority_sources=(
            {"domain": "taxfoundation.org/state-sales-tax-rates", "name": "Tax Foundation Sales Tax"},
        ),
    ),
    RegulationDef(
        key="local_tax",
        category="tax_rate",
        name="Local Income / Payroll Taxes",
        description="City, county, or school district income/payroll taxes (e.g., NYC, Philadelphia, OH municipalities, SF payroll tax)",
        enforcing_agency="Local government",
        state_variance="Moderate",
        update_frequency="Rates adjusted by local authority; new taxes enacted periodically",
        authority_sources=(
            {"domain": "taxfoundation.org", "name": "Tax Foundation"},
        ),
    ),

    # ── International: healthcare categories ──────────────────────────────
    RegulationDef(
        key="national_health_privacy_law",
        category="hipaa_privacy",
        name="National Health Data Privacy Law (International)",
        description="Country-level health data privacy legislation equivalent to or beyond HIPAA (e.g., GDPR health provisions, LFPDPPP, PDPA)",
        enforcing_agency="National DPA / Data protection authority",
        state_variance="Moderate",
        update_frequency="Active globally — major updates as data protection frameworks evolve",
        authority_sources=(
            {"domain": "ilo.org", "name": "ILO"},
        ),
    ),
    RegulationDef(
        key="lfpdppp_health_data",
        category="hipaa_privacy",
        name="LFPDPPP Health Data Provisions (Mexico)",
        description="Mexico's Federal Law on Protection of Personal Data (LFPDPPP) provisions for sensitive health data; consent and security requirements",
        enforcing_agency="INAI",
        state_variance="Moderate",
        update_frequency="LFPDPPP enacted 2010; INAI issues interpretive guidance periodically",
        authority_sources=(
            {"domain": "gob.mx/inai", "name": "INAI Mexico"},
        ),
    ),
    RegulationDef(
        key="cofepris_facility_standards",
        category="clinical_safety",
        name="COFEPRIS Healthcare Facility Standards (Mexico)",
        description="Mexico COFEPRIS standards for healthcare facility operation, equipment, hygiene, and personnel qualifications",
        enforcing_agency="COFEPRIS",
        state_variance="Moderate",
        update_frequency="NOM standards updated periodically; COFEPRIS inspections ongoing",
        authority_sources=(
            {"domain": "gob.mx/cofepris", "name": "COFEPRIS Mexico"},
        ),
    ),
    RegulationDef(
        key="national_whistleblower_protection",
        category="corporate_integrity",
        name="National Whistleblower Protection (International)",
        description="Country-level whistleblower protection laws for healthcare and corporate fraud reporting",
        enforcing_agency="National labor authority / Anti-corruption body",
        state_variance="Moderate",
        update_frequency="Expanding globally; EU Whistleblower Directive (2019) driving adoption",
        authority_sources=(
            {"domain": "ilo.org", "name": "ILO"},
        ),
    ),
    RegulationDef(
        key="national_emergency_preparedness",
        category="emergency_preparedness",
        name="National Emergency / Disaster Preparedness (International)",
        description="Country-level emergency and disaster preparedness requirements for healthcare facilities and employers",
        enforcing_agency="National civil protection authority",
        state_variance="Moderate",
        update_frequency="Updated after major events; national frameworks reviewed periodically",
        authority_sources=(
            {"domain": "ilo.org", "name": "ILO"},
        ),
    ),
    RegulationDef(
        key="national_anti_corruption_healthcare",
        category="billing_integrity",
        name="National Anti-Corruption in Healthcare (International)",
        description="Country-level anti-corruption and anti-bribery laws applicable to healthcare sector; fraud prevention requirements",
        enforcing_agency="National anti-corruption body",
        state_variance="Moderate",
        update_frequency="Active globally — enforcement and legislation expanding",
        authority_sources=(
            {"domain": "ilo.org", "name": "ILO"},
        ),
    ),
    RegulationDef(
        key="cofepris_sanitary_license",
        category="state_licensing",
        name="COFEPRIS Sanitary License (Mexico)",
        description="Mexico COFEPRIS sanitary license (licencia sanitaria) required for healthcare facilities, pharmacies, and labs",
        enforcing_agency="COFEPRIS",
        state_variance="High",
        update_frequency="License requirements updated periodically; renewal obligations ongoing",
        authority_sources=(
            {"domain": "gob.mx/cofepris", "name": "COFEPRIS Mexico"},
        ),
    ),
    RegulationDef(
        key="national_research_consent_law",
        category="research_consent",
        name="National Research Consent / Bioethics Law (International)",
        description="Country-level laws governing research consent, bioethics committees, and human subjects protections",
        enforcing_agency="National bioethics committee",
        state_variance="Moderate",
        update_frequency="Frameworks evolving; many countries aligning with ICH-GCP and Declaration of Helsinki",
        authority_sources=(
            {"domain": "ilo.org", "name": "ILO"},
        ),
    ),
    RegulationDef(
        key="cofepris_research_authorization",
        category="research_consent",
        name="COFEPRIS Clinical Research Authorization (Mexico)",
        description="Mexico COFEPRIS authorization required for clinical research involving human subjects, drugs, devices, or biologics",
        enforcing_agency="COFEPRIS",
        state_variance="Moderate",
        update_frequency="Authorization requirements updated periodically; aligned with ICH-GCP",
        authority_sources=(
            {"domain": "gob.mx/cofepris", "name": "COFEPRIS Mexico"},
        ),
    ),
]
