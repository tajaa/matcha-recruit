from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple  # noqa: F401




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

    # ── Life Sciences ────────────────────────────────────────────────────
    "gmp_manufacturing": """Research GOOD MANUFACTURING PRACTICE (GMP) requirements for pharmaceutical/biotech manufacturers in this jurisdiction.
Cover: 21 CFR Parts 210/211 (drug cGMP), 21 CFR Part 820 (device QSR), FDA facility registration (21 CFR 207),
process validation requirements (FDA 2011 guidance), annual product quality review,
supplier qualification, FDA inspection types (pre-approval, routine, for-cause),
and any STATE-specific drug manufacturing, compounding facility, or pharmaceutical production requirements.
Include state drug manufacturer licensing if required separately from wholesale distribution.
Set current_value to a SHORT summary (under 80 chars).""",

    "glp_nonclinical": """Research GOOD LABORATORY PRACTICE (GLP) requirements for nonclinical studies in this jurisdiction.
Cover: 21 CFR Part 58 (GLP for Nonclinical Laboratory Studies), study director responsibilities,
Quality Assurance Unit requirements, specimen archiving and retention,
equipment calibration and maintenance standards, protocol amendment procedures,
OECD GLP Principles where applicable, and any STATE-specific laboratory certification,
accreditation, or registration requirements (e.g., CLIA, CAP, state lab licensing).
Set current_value to a SHORT summary (under 80 chars).""",

    "clinical_trials_gcp": """Research CLINICAL TRIAL AND GOOD CLINICAL PRACTICE requirements in this jurisdiction.
Cover: ICH E6(R2) GCP guidelines, IND application requirements (21 CFR 312),
sponsor responsibilities (21 CFR 312.50-312.70), IND safety reporting (21 CFR 312.32),
informed consent (21 CFR Part 50), IRB oversight (21 CFR Part 56),
21 CFR Part 11 electronic records and signatures for clinical data,
and any STATE-specific clinical trial registration, notification, or patient protection requirements.
Note: This complements research_consent by focusing on drug/device-specific trial regulations.
Set current_value to a SHORT summary (under 80 chars).""",

    "drug_supply_chain": """Research DRUG SUPPLY CHAIN SECURITY requirements in this jurisdiction.
Cover: Drug Supply Chain Security Act (DSCSA) serialization, verification, and tracing requirements,
wholesale drug distributor licensing (state and federal), NABP VAWD accreditation,
Good Distribution Practice (GDP) storage and transport standards,
DEA suspicious order monitoring obligations,
FDA drug recall procedures (21 CFR Part 7),
and any STATE-specific wholesale distribution, third-party logistics, or drug pedigree requirements.
Many states have separate wholesale distributor licensing with unique requirements.
Set current_value to a SHORT summary (under 80 chars).""",

    "sunshine_open_payments": """Research SUNSHINE ACT AND OPEN PAYMENTS requirements in this jurisdiction.
Cover: Federal Physician Payments Sunshine Act (42 USC 1320a-7h), CMS Open Payments reporting,
aggregate spend tracking and annual submission deadlines,
teaching hospital payment reporting requirements,
covered recipient identification rules,
and any STATE-specific physician gift ban laws, pharmaceutical marketing disclosure requirements,
or industry payment reporting mandates that EXCEED federal requirements.
States like MA, MN, VT, CT, NV have stricter gift bans. Identify state-specific thresholds and reporting.
Set current_value to a SHORT summary (under 80 chars).""",

    "biosafety_lab": """Research BIOSAFETY AND LABORATORY SAFETY requirements in this jurisdiction.
Cover: CDC/NIH Biosafety in Microbiological and Biomedical Laboratories (BMBL) guidelines,
Biosafety Level (BSL) classification requirements, Institutional Biosafety Committee (IBC) requirements,
NIH Guidelines for Research Involving Recombinant or Synthetic Nucleic Acid Molecules,
Select Agent Regulations (42 CFR Part 73 / 7 CFR Part 331 / 9 CFR Part 121),
OSHA Bloodborne Pathogens Standard for laboratory settings (29 CFR 1910.1030),
OSHA Laboratory Standard / Chemical Hygiene Plan (29 CFR 1910.1450),
and any STATE-specific biosafety, lab registration, or hazardous materials requirements.
Set current_value to a SHORT summary (under 80 chars).""",
}


