# Policy Registry

Every policy tracked in our system. Organized by group > category > policy key.
Each policy has a data schema that defines the fields stored per jurisdiction.

## How Jurisdictions Use These Keys

Not every jurisdiction has all 483 keys. Policies are stored at the **most specific level that has a distinct rule**, and lower levels inherit upward via a parent chain.

### Hierarchy

```
Federal (US)          — baseline policies that apply nationally
  └── State (CA)      — only keys where the state differs from / exceeds federal
       └── City (SF)  — only keys where the city differs from / exceeds state
```

### What gets stored where

| Level | What it stores | Example |
|-------|---------------|---------|
| Federal | Federal-baseline keys | `fmla`, `hipaa_security_rule_cybersecurity`, `osha_general_duty` |
| State | State-specific overrides/additions | CA has `state_telehealth_parity_laws` (AB 744), `state_paid_sick_leave` |
| City | City-specific overrides/additions | SF has `local_minimum_wage` ($18.67 vs CA's $16.50), `local_sick_leave` |

### Inheritance

Cities don't duplicate state or federal data. When the system needs the full compliance picture for a location (e.g., San Francisco), it walks the `parent_id` chain:

```
San Francisco → California → United States (federal)
```

The `resolve_jurisdiction_stack` query assembles all requirements from every level in the chain. If the same key exists at multiple levels (e.g., `state_minimum_wage` at both federal and state), precedence rules determine which governs.

### International jurisdictions

The system is not US-only. International jurisdictions follow the same hierarchy model but with country-level roots:

```
Mexico City → CDMX (state) → Mexico (national)
London → England (region) → United Kingdom (national)
Paris → Ile-de-France (region) → France (national)
Singapore → Singapore (city-state, no parent)
```

Key definitions have an `applicable_countries` field:
- `NULL` = universal (applies to all countries) — 362 keys
- `['MX']` = Mexico-only — 28 keys (e.g., `imss_employer_contribution`, `aguinaldo_christmas_bonus`, `nom_035_psychosocial_risk`)
- `['GB']` = UK-only — 4 keys (e.g., `social_insurance_employee`, `uk_auto_enrolment_pension`)
- `['SG']` = Singapore-only — 2 keys (e.g., `cpf_employer_contribution`, `foreign_worker_levy`)

When researching or ingesting data for an international jurisdiction, only keys matching that country (or universal keys) are eligible.

### Key coverage in practice

- A **well-covered US state** like California might have 40-80 state-level keys across labor + healthcare categories
- A **US city with local ordinances** like San Francisco might add 5-15 city-level keys on top
- A **US city without local ordinances** inherits everything from state and has 0 city-level keys
- The **federal jurisdiction** has the national baselines �� roughly 100-150 keys
- **Mexico City** has 57 requirements using MX-specific + universal keys
- **London** has 28 requirements using GB-specific + universal keys
- **Paris** has 18 requirements using universal keys (no FR-specific defs yet)
- **Singapore** has 17 requirements using SG-specific + universal keys

### When we add data for a key

We only create a `jurisdiction_requirements` row when:
1. The key is defined in `regulation_key_definitions` (this registry)
2. The key's `applicable_countries` includes this jurisdiction's country (or is NULL/universal)
3. The jurisdiction has a **specific law or rule** for that key that differs from the parent level
4. The data includes a source citation

We never create rows just to say "this jurisdiction follows the federal default" — that's implied by inheritance.

### Current coverage (as of 2026-03-25)

**US jurisdictions:**

| Level | Jurisdictions | Requirements |
|-------|--------------|-------------|
| Federal | 1 | 17 |
| State | 26 | 297 |
| County | 5 | 14 |
| City (US) | 16 | 107 |

**International jurisdictions:**

| Jurisdiction | Country | Requirements |
|---|---|---|
| Mexico City | MX | 57 |
| London | GB | 28 |
| Paris | FR | 18 |
| Singapore | SG | 17 |

**Totals:** 52 jurisdictions, 555 requirements, 396 key definitions (of 483 in code), 0 unkeyed

---

## Data Schema (per jurisdiction instance)

Every policy key, when applied to a jurisdiction, stores this data:

| Field | Type | Description |
|-------|------|-------------|
| title | VARCHAR(500) | Jurisdiction-specific title |
| description | TEXT | Full explanation of the state/city-specific rule |
| current_value | VARCHAR(500) | Short summary of current state |
| previous_value | VARCHAR(500) | What current_value was before last update |
| previous_description | TEXT | What description was before last update |
| change_status | ENUM | new / changed / unchanged / needs_review |
| effective_date | DATE | When this rule took/takes effect |
| source_url | VARCHAR(500) | Authoritative URL |
| source_name | VARCHAR(100) | Source label |
| requires_written_policy | BOOLEAN | Employer must have a written policy |
| numeric_value | DECIMAL | For wages/rates/thresholds |
| rate_type | VARCHAR(50) | For minimum_wage variants (general, tipped, etc.) |
| last_verified_at | TIMESTAMP | When this data was last checked |
| last_changed_at | TIMESTAMP | When an actual change was detected |
| fetch_hash | VARCHAR(64) | Content hash for quick change detection |

---

## Healthcare (9 categories)

### HIPAA Privacy & Security (hipaa_privacy)

**Industry**: healthcare
**Keys**: 12

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| 42_cfr_part_2 | 42 CFR Part 2 (Substance Use Disorder Records) | SAMHSA / HHS OCR | Moderate |
| coppa | COPPA (Children’s Online Privacy Protection Act) | FTC | Low/None |
| ftc_health_breach_notification_rule | FTC Health Breach Notification Rule (16 CFR Part 318) | FTC | Low/None |
| genetic_information_nondiscrimination_act | Genetic Information Nondiscrimination Act (GINA) | HHS / EEOC | Moderate |
| hipaa_breach_notification_rule | HIPAA Breach Notification Rule (45 CFR Part 164 Subpart D) | HHS OCR | Moderate |
| hipaa_privacy_rule | HIPAA Privacy Rule (45 CFR Part 160, 164 Subparts A & E) | HHS OCR | Moderate |
| hipaa_security_rule | HIPAA Security Rule (45 CFR Part 164 Subpart C) | HHS OCR | Low/None |
| hitech_act | HITECH Act (Title XIII of ARRA) | HHS OCR / CMS | Low/None |
| lfpdppp_health_data | LFPDPPP Health Data Provisions (Mexico) | INAI | Moderate |
| national_health_privacy_law | National Health Data Privacy Law (International) | National DPA / Data protection authority | Moderate |
| state_biometric_privacy_laws | State Biometric Privacy Laws (e.g., IL BIPA, TX CUBI) | State AGs / Private action in IL | High |
| state_health_privacy_laws | State Health Privacy Laws | State AGs / Health Depts | High |

### Billing & Financial Integrity (billing_integrity)

**Industry**: healthcare
**Keys**: 14

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| antikickback_statute | Anti-Kickback Statute (42 U.S.C. § 1320a-7b(b)) | OIG / DOJ | High |
| civil_monetary_penalties_law | Civil Monetary Penalties Law (42 U.S.C. § 1320a-7a) | OIG | Low/None |
| criminal_health_care_fraud | Criminal Health Care Fraud (18 U.S.C. § 1347) | DOJ / FBI | Low/None |
| exclusion_statute | Exclusion Statute (42 U.S.C. § 1320a-7) | OIG | Low/None |
| false_claims_act | False Claims Act (31 U.S.C. §§ 3729–3733) | DOJ / OIG | Moderate |
| medicaid_billing_requirements | Medicaid Billing Requirements | CMS / State Medicaid | High |
| medicare_conditions_of_payment_billing_rules | Medicare Conditions of Payment / Billing Rules | CMS / MACs | Low/None |
| medicare_secondary_payer_rules | Medicare Secondary Payer (MSP) Rules | CMS / BCRC | Low/None |
| national_anti_corruption_healthcare | National Anti-Corruption in Healthcare (International) | National anti-corruption body | Moderate |
| no_surprises_act | No Surprises Act (Consolidated Appropriations Act 2021) | CMS / State regulators | High |
| provider_enrollment_revalidation | Provider Enrollment & Revalidation (42 CFR Part 424) | CMS | Low/None |
| stark_law | Stark Law (42 U.S.C. § 1395nn) | CMS | Low/None |
| state_antikickback_selfreferral_laws | State Anti-Kickback & Self-Referral Laws | State AGs / Boards | High |
| state_false_claims_acts | State False Claims Acts | State AGs | High |

### Clinical & Patient Safety (clinical_safety)

**Industry**: healthcare
**Keys**: 18

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| advance_directives | Advance Directives (Patient Self-Determination Act) | CMS / State law | High |
| antimicrobial_stewardship_programs | Antimicrobial Stewardship Programs | CMS / CDC | Moderate |
| clia | CLIA (42 CFR Part 493) | CMS / CDC / State | Moderate |
| cms_conditions_for_coverage | CMS Conditions for Coverage (CfCs) | CMS | Low/None |
| cms_conditions_of_participation | CMS Conditions of Participation (42 CFR Parts 482–491) | CMS | Low/None |
| cofepris_facility_standards | COFEPRIS Healthcare Facility Standards (Mexico) | COFEPRIS | Moderate |
| dnv_gl_healthcare_accreditation | DNV GL Healthcare Accreditation | DNV GL | Low/None |
| emtala | EMTALA (42 U.S.C. § 1395dd) | CMS / OIG | Low/None |
| infection_control_prevention_standards | Infection Control & Prevention Standards | CMS / CDC / State | High |
| informed_consent_requirements | Informed Consent Requirements | CMS / State law | High |
| joint_commission_standards | Joint Commission Standards | Joint Commission | Low/None |
| medication_management_controlled_substances | Medication Management & Controlled Substances (21 CFR 1301–1321) | DEA / State Pharmacy Boards | High |
| npdb_reporting | NPDB Reporting | HRSA | Low/None |
| pain_management_opioid_prescribing | Pain Management & Opioid Prescribing | CDC / State Medical Boards | High |
| patient_safety_quality_improvement_act | Patient Safety & Quality Improvement Act (PSQIA) | AHRQ | Moderate |
| restraint_seclusion_standards | Restraint & Seclusion Standards (42 CFR 482.13(e)–(f)) | CMS / Joint Commission | Moderate |
| sentinel_event_reporting | Sentinel Event Reporting | Joint Commission / State | High |
| state_licensure_standards_for_healthcare_facilitie | State Licensure Standards for Healthcare Facilities | State Health Depts | High |

### Healthcare Workforce (healthcare_workforce)

**Industry**: healthcare
**Keys**: 18

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| ada | ADA (Americans with Disabilities Act) | EEOC / DOJ | Moderate |
| background_check_requirements | Background Check Requirements | CMS / State | High |
| continuing_education_requirements | Continuing Education Requirements | State Licensing Boards | High |
| flsa | FLSA (Fair Labor Standards Act) | DOL | High |
| fmla | FMLA (Family and Medical Leave Act) | DOL | High |
| immigration_compliance | Immigration Compliance (I-9 / Visa Requirements) | DHS / USCIS / DOL | Moderate |
| mandatory_reporting_obligations | Mandatory Reporting Obligations | State law | High |
| medical_staff_credentialing_privileging | Medical Staff Credentialing & Privileging | CMS / Joint Commission / State | Moderate |
| npdb_queries | NPDB Queries | HRSA | Low/None |
| nurse_staffing_ratios_requirements | Nurse Staffing Ratios & Requirements | State law | High |
| oig_exclusion_list_screening | OIG Exclusion List (LEIE) Screening | OIG | Low/None |
| osha_workplace_safety | OSHA Workplace Safety (29 CFR Part 1910) | OSHA | Moderate |
| osha_workplace_violence_prevention | OSHA Workplace Violence Prevention | OSHA / State OSHA plans | High |
| physician_residency_gme_requirements | Physician Residency & GME Requirements | ACGME / CMS | Low/None |
| professional_licensing | Professional / Occupational Licensing | State licensing boards | Moderate |
| provider_licensure_scope_of_practice | Provider Licensure & Scope of Practice | State Licensing Boards | High |
| section_1557_of_aca | Section 1557 of ACA (Nondiscrimination) | HHS OCR | Low/None |
| title_vii_civil_rights_act | Title VII / Civil Rights Act | EEOC | Moderate |

### Corporate Integrity & Ethics (corporate_integrity)

**Industry**: healthcare
**Keys**: 10

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| code_of_conduct_conflict_of_interest | Code of Conduct & Conflict of Interest | OIG / Accreditors | Low/None |
| compliance_committee_board_oversight | Compliance Committee & Board Oversight | OIG / Accreditors | Low/None |
| corporate_integrity_agreements | Corporate Integrity Agreements (CIAs) | OIG | Low/None |
| deficit_reduction_act_of_2005 | Deficit Reduction Act of 2005 (§6032) | CMS / State | Moderate |
| federal_sentencing_guidelines | Federal Sentencing Guidelines (§8B2.1) | U.S. Sentencing Commission | Low/None |
| internal_investigations_disclosure_protocols | Internal Investigations & Disclosure Protocols | OIG / CMS / DOJ | Low/None |
| national_whistleblower_protection | National Whistleblower Protection (International) | National labor authority / Anti-corruption body | Moderate |
| oig_compliance_program_guidance | OIG Compliance Program Guidance | OIG | Low/None |
| state_whistleblower_protection_laws | State Whistleblower Protection Laws | State AGs / Courts | High |
| whistleblower_protections | Whistleblower Protections (FCA Qui Tam) | DOJ | Moderate |

### Research & Informed Consent (research_consent)

**Industry**: healthcare
**Keys**: 11

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| 21_cfr_part_11_research_consent | 21 CFR Part 11 (E-Records & E-Signatures) | FDA | Low/None |
| clinicaltrialsgov_registration | ClinicalTrials.gov Registration (42 CFR Part 11) | NIH / FDA | Low/None |
| cofepris_research_authorization | COFEPRIS Clinical Research Authorization (Mexico) | COFEPRIS | Moderate |
| common_rule | Common Rule (45 CFR Part 46) | OHRP / HHS | Low/None |
| fda_human_subject_regs | FDA Human Subject Regs (21 CFR Parts 50, 56) | FDA | Low/None |
| good_clinical_practice | Good Clinical Practice (ICH E6 R2/R3) | FDA / ICH | Low/None |
| hipaa_research_provisions | HIPAA Research Provisions | HHS OCR | Low/None |
| institutional_biosafety_committee | Institutional Biosafety Committee (IBC) | NIH / CDC / USDA | Low/None |
| national_research_consent_law | National Research Consent / Bioethics Law (International) | National bioethics committee | Moderate |
| nih_grants_policy_compliance | NIH Grants Policy & Compliance | NIH | Low/None |
| state_research_consent_laws | State Research & Consent Laws | State law | High |

### State Licensing & Scope (state_licensing)

**Industry**: healthcare
**Keys**: 8

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| certificate_of_need_programs | Certificate of Need (CON) Programs | State Health Planning | High |
| cofepris_sanitary_license | COFEPRIS Sanitary License (Mexico) | COFEPRIS | High |
| corporate_practice_of_medicine_doctrine | Corporate Practice of Medicine Doctrine | State Medical Boards / Courts | High |
| feesplitting_prohibitions | Fee-Splitting Prohibitions | State Medical Boards | High |
| medical_staff_bylaws_selfgovernance | Medical Staff Bylaws & Self-Governance | CMS / State | Moderate |
| medicaremedicaid_certification | Medicare/Medicaid Certification | CMS / State Survey Agencies | Low/None |
| nonprofit_healthcare_governance | Nonprofit Healthcare Governance | State AGs | High |
| state_facility_licensure | State Facility Licensure | State Health Depts | High |

### Emergency Preparedness (emergency_preparedness)

**Industry**: healthcare
**Keys**: 8

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| cms_emergency_preparedness_rule | CMS Emergency Preparedness Rule (42 CFR 482, 483, 484, 485, 486, 491) | CMS | Moderate |
| emtala_emergency_obligations | EMTALA Emergency Obligations | CMS / OIG | Low/None |
| hospital_preparedness_program | Hospital Preparedness Program (HPP) | ASPR / HHS | Moderate |
| mass_casualty_active_shooter | Mass Casualty / Active Shooter | Joint Commission / State | Moderate |
| national_emergency_preparedness | National Emergency / Disaster Preparedness (International) | National civil protection authority | Moderate |
| nims_hics | NIMS / HICS | FEMA / ASPR | Low/None |
| pandemic_preparedness | Pandemic Preparedness | HHS / CDC / State | High |
| state_emergency_preparedness_requirements | State Emergency Preparedness Requirements | State Health Depts / EM | High |

### Reimbursement & Value-Based Care (reimbursement_vbc)

**Industry**: healthcare:provider
**Keys**: 10

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| apm_participation | Alternative Payment Model (APM) Participation | CMS | Low/None |
| bundled_payment_compliance | Bundled Payment Program Compliance (BPCI-A) | CMS | Low/None |
| cms_star_ratings | CMS Star Ratings Compliance | CMS | Low/None |
| drg_coding_compliance | DRG/CPT Coding Compliance & Auditing | CMS/OIG | Low/None |
| good_faith_estimates | Good Faith Estimates | CMS | Low/None |
| hedis_quality_measures | HEDIS Quality Measures | NCQA | Low/None |
| macra_mips_reporting | MACRA/MIPS Quality Reporting | CMS | Low/None |
| no_surprises_act | No Surprises Act (Consolidated Appropriations Act 2021) | CMS / State regulators | High |
| price_transparency_rule | Hospital Price Transparency Rule | CMS | Low/None |
| value_based_contract_requirements | Value-Based Contract Requirements | CMS/Payers | Moderate |

## Labor (12 categories)

### Minimum Wage (minimum_wage)

**Keys**: 12

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| exempt_salary_threshold | Exempt Employee Salary Threshold (FLSA + State) | WHD / State labor agencies | High |
| fast_food_minimum_wage | Fast Food Industry Minimum Wage | State labor agencies | High |
| healthcare_minimum_wage | Healthcare Worker Minimum Wage | State labor agencies | High |
| large_employer_minimum_wage | Large Employer Minimum Wage Tier | State / Local government | High |
| local_minimum_wage | City / County Minimum Wage Ordinances | Local government | High |
| national_minimum_wage | National Minimum Wage (International) | National government / Labor ministry | Moderate |
| small_employer_minimum_wage | Small Employer Minimum Wage Tier | State / Local government | High |
| state_minimum_wage | State Minimum Wage | WHD / State labor agencies | High |
| tip_credit_prohibition | Tip Credit Prohibition | State legislatures | High |
| tipped_minimum_wage | Tipped Employee Minimum Wage / Tip Credit | WHD / State labor agencies | High |
| youth_minimum_wage | Youth / Training Sub-Minimum Wage | WHD / State labor agencies | Moderate |
| zlfn_border_zone_minimum_wage | Mexico Free Zone Border Minimum Wage (ZLFN) | CONASAMI | High |

### Overtime (overtime)

**Keys**: 8

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| alternative_workweek | Alternative Workweek Schedule Elections | State labor agencies | Moderate |
| comp_time | Compensatory Time Off in Lieu of Overtime Pay | WHD / State labor agencies | Moderate |
| daily_weekly_overtime | Daily and Weekly Overtime Thresholds and Rates | WHD / State labor agencies | High |
| double_time | Double-Time Pay Requirements | State labor agencies | High |
| exempt_salary_threshold | Exempt Employee Salary Threshold (FLSA + State) | WHD / State labor agencies | High |
| healthcare_overtime | Healthcare Overtime Restrictions | State legislatures | Moderate |
| mandatory_overtime_restrictions | Restrictions on Mandatory Overtime | State legislatures | High |
| seventh_day_overtime | Seventh Consecutive Day Overtime | State labor agencies | High |

### Sick Leave (sick_leave)

**Keys**: 5

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| accrual_and_usage_caps | Sick Leave Accrual Rates and Usage Caps | State / Local government | High |
| imss_sick_leave | IMSS Social Security Sick Leave (Mexico) | IMSS | Moderate |
| local_sick_leave | City / County Sick Leave Ordinances | Local government | High |
| state_paid_sick_leave | State-Mandated Paid Sick Leave | State labor agencies | High |
| statutory_sick_leave | National Statutory Sick Pay (International) | National government | Moderate |

### Meal & Rest Breaks (meal_breaks)

**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| healthcare_meal_waiver | Healthcare Industry Meal Break Waivers | State labor agencies | Moderate |
| lactation_break | Lactation / Nursing Break Requirements | WHD / State labor agencies | Moderate |
| meal_break | Meal / Lunch Break Requirements | WHD / State labor agencies | High |
| missed_break_penalty | Penalty Pay for Missed Breaks (CA Premium Pay) | State labor agencies | High |
| on_duty_meal_agreement | On-Duty Meal Period Agreements | State labor agencies | Moderate |
| rest_break | Rest / Coffee Break Requirements | WHD / State labor agencies | High |

### Pay Frequency (pay_frequency)

**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| exempt_monthly_pay | Exempt Employee Monthly Pay Option | State labor agencies | Moderate |
| final_pay_resignation | Final Pay Timing — Voluntary Resignation | State labor agencies | High |
| final_pay_termination | Final Pay Timing — Involuntary Termination | State labor agencies | High |
| payday_posting | Payday Posting / Notification Requirements | State labor agencies | Low/None |
| standard_pay_frequency | Required Pay Frequency (Weekly, Biweekly, etc.) | State labor agencies | Moderate |
| wage_notice | Wage Theft Prevention Notice Requirements | State labor agencies | Moderate |

### Final Pay (final_pay)

**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| final_pay_layoff | Final Pay Timing — Layoff / Reduction in Force | State labor agencies | High |
| final_pay_resignation | Final Pay Timing — Voluntary Resignation | State labor agencies | High |
| final_pay_termination | Final Pay Timing — Involuntary Termination | State labor agencies | High |
| finiquito | Voluntary Separation Settlement (Mexico Finiquito) | STPS / Conciliation centers | Moderate |
| liquidacion | Involuntary Termination Settlement (Mexico Liquidacion) | Labor courts | Moderate |
| waiting_time_penalty | Penalty for Late Final Pay (CA Waiting Time Penalties) | State labor agencies | High |

### Minor Work Permits (minor_work_permit)

**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| entertainment_permits | Entertainment Industry Permits for Minors | State labor agencies | Moderate |
| hour_limits_14_15 | Working Hour Limits Ages 14-15 | WHD / State labor agencies | Moderate |
| hour_limits_16_17 | Working Hour Limits Ages 16-17 | WHD / State labor agencies | Moderate |
| prohibited_occupations | Hazardous Occupations for Minors | WHD / State labor agencies | Moderate |
| recordkeeping | Youth Employment Recordkeeping Requirements | WHD / State labor agencies | Low/None |
| work_permit | Youth Employment Work Permit / Certificate | State labor agencies | Moderate |

### Scheduling & Reporting Time (scheduling_reporting)

**Keys**: 7

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| maximum_working_hours | Maximum Daily / Weekly Working Hours (International) | National government / Labor ministry | Moderate |
| on_call_pay | On-Call Compensation Requirements | State labor agencies | Moderate |
| predictive_scheduling | Fair Workweek / Predictive Scheduling | State / Local government | High |
| reporting_time_pay | Reporting / Show-Up Time Pay | State labor agencies | High |
| split_shift_premium | Split Shift Premium Pay | State labor agencies | High |
| spread_of_hours | Spread of Hours Premium (NY) | State labor agencies | High |
| sunday_premium | Sunday Premium Pay (Mexico 25%) | STPS | Moderate |

### Leave (leave)

**Keys**: 26

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| adoption_leave | Statutory Adoption Leave (International) | National government | Moderate |
| aguinaldo_christmas_bonus | Christmas Bonus / 13th Month Pay (Mexico Aguinaldo) | STPS | Moderate |
| annual_leave_entitlement | Statutory Annual Leave (International) | National government / Labor ministry | Moderate |
| bereavement_leave | Bereavement / Funeral Leave | State legislatures | Moderate |
| bone_marrow_donor_leave | Bone Marrow Donation Leave | State legislatures | Moderate |
| domestic_violence_leave | Leave for Domestic Violence / Sexual Assault Victims | State legislatures | Moderate |
| fmla | FMLA (Family and Medical Leave Act) | DOL | High |
| jury_duty_leave | Jury Duty Leave Protections | State legislatures | Low/None |
| military_leave | Military / USERRA Leave | DOL / State labor agencies | Low/None |
| organ_donor_leave | Organ / Bone Marrow Donor Leave | State legislatures | Moderate |
| paid_sick_leave | Paid Sick Leave Mandates | State / Local government | High |
| pregnancy_disability_leave | Pregnancy Disability Leave | State / EEOC | High |
| ptu_profit_sharing | Worker Profit Sharing (Mexico PTU 10%) | STPS | Moderate |
| reproductive_loss_leave | Reproductive Loss Leave | State legislatures | Moderate |
| school_activity_leave | School Activity / Parent Involvement Leave | State legislatures | Moderate |
| seniority_premium | Seniority Premium on Separation (Mexico) | STPS | Moderate |
| severance_pay | Statutory Severance Pay (International) | National labor courts / Labor ministry | Moderate |
| shared_parental_leave | Shared Parental Leave (UK) | HMRC / ACAS | Moderate |
| state_disability_insurance | State Temporary Disability Insurance (CA SDI, NJ TDI, etc.) | State agencies | High |
| state_family_leave | State Family / Medical Leave Beyond FMLA | State labor agencies | High |
| state_paid_family_leave | State Paid Family Leave Insurance Programs | State agencies | High |
| statutory_maternity_leave | Statutory Maternity Leave (International) | National government / ILO | Moderate |
| statutory_notice_period_employer | Statutory Notice Period (International) | National labor law / Labor courts | Moderate |
| statutory_paternity_leave | Statutory Paternity Leave (International) | National government | Moderate |
| vacation_premium | Vacation Premium Pay (Mexico 25%) | STPS | Moderate |
| voting_leave | Time Off to Vote | State legislatures | Moderate |

### Workplace Safety (workplace_safety)

**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| hazard_communication | HazCom / GHS Right-to-Know | OSHA | Low/None |
| heat_illness_prevention | Heat Illness Prevention Programs | OSHA / State plan states | High |
| injury_illness_recordkeeping | OSHA 300/300A Injury and Illness Recordkeeping | OSHA | Moderate |
| osha_general_duty | OSHA General Duty Clause (Section 5(a)(1)) | OSHA / State plan states | Moderate |
| stps_nom_standards | STPS NOM Occupational Safety Standards (Mexico) | STPS | Moderate |
| workplace_violence_prevention | Workplace Violence Prevention Plans | OSHA / State plan states (CA SB 553) | Moderate |

### Workers' Comp (workers_comp)

**Keys**: 13

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| anti_retaliation | Anti-Retaliation for Workers' Comp Claims | State WC boards | Moderate |
| claim_filing | Workers' Comp Claim Filing Procedures / Deadlines | State WC boards | Moderate |
| cpf_employer_contribution | CPF Employer Contribution Rates (Singapore) | CPF Board | High |
| foreign_worker_levy | Foreign Worker Levy (Singapore) | MOM Singapore | High |
| imss_employer_contribution | IMSS Employer Contribution Rates (Mexico) | IMSS | High |
| infonavit_contribution | INFONAVIT Housing Fund Contribution (Mexico) | INFONAVIT | Moderate |
| mandatory_coverage | Mandatory Workers' Compensation Coverage | State WC boards | High |
| posting_requirements | Workers' Comp Posting Requirements | State WC boards | Low/None |
| return_to_work | Return-to-Work Programs | State WC boards | Moderate |
| sar_retirement_contribution | SAR Retirement Savings Contribution (Mexico) | CONSAR | Moderate |
| social_insurance_employee | Employee Social Insurance Deductions (International) | National social security authority | Moderate |
| social_insurance_employer | Employer Social Insurance Contributions (International) | National social security authority | Moderate |
| uk_auto_enrolment_pension | UK Auto-Enrolment Pension (Workplace Pension) | The Pensions Regulator | High |

### Anti-Discrimination (anti_discrimination)

**Keys**: 7

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| harassment_prevention_training | Sexual Harassment Prevention Training Mandates | State labor agencies | Moderate |
| nom_035_psychosocial_risk | NOM-035 Psychosocial Risk Factors (Mexico) | STPS | Moderate |
| pay_transparency | Pay Transparency / Range Disclosure | State labor agencies | High |
| protected_classes | State Protected Classes Beyond Federal | State civil rights agencies | High |
| reasonable_accommodation | Reasonable Accommodation Requirements | EEOC / State civil rights agencies | Moderate |
| salary_history_ban | Salary History Inquiry Ban | State / Local government | High |
| whistleblower_protection | Whistleblower / Retaliation Protections | State labor agencies | Moderate |

## Life Sciences (7 categories)

### GMP Manufacturing (gmp_manufacturing)

**Industry**: biotech
**Keys**: 7

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| annual_product_review | Annual Product Quality Review (21 CFR 211.180(e)) | FDA | Low/None |
| cgmp_devices_21cfr820 | 21 CFR Part 820 (Quality System Regulation for Medical Devices) | FDA | Low/None |
| cgmp_drugs_21cfr210_211 | 21 CFR Parts 210 & 211 (cGMP for Finished Pharmaceuticals) | FDA | Low/None |
| fda_facility_registration | FDA Facility Registration (21 CFR Part 207) | FDA | Low/None |
| fda_inspection_readiness | FDA Inspection Types: Pre-Approval, Routine, For-Cause | FDA | Low/None |
| process_validation | FDA Process Validation Guidance (2011) | FDA | Low/None |
| supplier_qualification | Supplier Qualification & Incoming Material Testing | FDA | Low/None |

### Good Laboratory Practice (glp_nonclinical)

**Industry**: biotech
**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| equipment_calibration_glp | Equipment Calibration & Maintenance for GLP Studies | FDA | Low/None |
| glp_21cfr58 | 21 CFR Part 58 (Good Laboratory Practice for Nonclinical Studies) | FDA | Low/None |
| glp_qa_unit | Quality Assurance Unit Requirements | FDA | Low/None |
| protocol_amendments_deviations | Protocol Amendments & Deviation Reporting | FDA | Low/None |
| specimen_archiving | Test Article & Specimen Retention/Archiving | FDA | Low/None |
| study_director_responsibilities | Study Director Qualifications & Responsibilities | FDA | Low/None |

### Clinical Trials & GCP (clinical_trials_gcp)

**Industry**: biotech
**Keys**: 7

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| adverse_event_reporting_ind | IND Safety Reporting (21 CFR 312.32) | FDA | Low/None |
| clinical_data_integrity_part11 | 21 CFR Part 11 (Electronic Records & Signatures in Clinical Trials) | FDA | Low/None |
| ich_e6r2_gcp | ICH E6(R2) Good Clinical Practice | FDA / ICH | Low/None |
| ind_application_21cfr312 | IND Application (21 CFR Part 312) | FDA | Low/None |
| informed_consent_21cfr50 | Informed Consent (21 CFR Part 50) | FDA | Moderate |
| irb_oversight_21cfr56 | IRB Requirements (21 CFR Part 56) | FDA | Moderate |
| sponsor_responsibilities | Sponsor Responsibilities (21 CFR 312.50-312.70) | FDA | Low/None |

### Drug Supply Chain (DSCSA) (drug_supply_chain)

**Industry**: biotech
**Keys**: 7

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| drug_recall_procedures | Drug Recall Procedures (21 CFR Part 7) | FDA | Low/None |
| dscsa_serialization | DSCSA Serialization Requirements | FDA | Low/None |
| dscsa_tracing | DSCSA Transaction Documentation & Tracing | FDA | Low/None |
| dscsa_verification | DSCSA Product Verification | FDA | Low/None |
| gdp_storage_transport | GDP Storage & Transport Conditions | FDA / USP | Low/None |
| suspicious_order_monitoring | Suspicious Order Monitoring (DEA) | DEA | Low/None |
| wholesale_distribution_license | Wholesale Drug Distribution Licensing | State Pharmacy Boards / FDA | High |

### Sunshine Act / Open Payments (sunshine_open_payments)

**Industry**: biotech
**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| aggregate_spend_tracking | Aggregate Spend Tracking & Reporting | CMS | Moderate |
| cms_open_payments_submission | CMS Open Payments Data Submission | CMS | Low/None |
| covered_recipient_identification | Covered Recipient Identification Requirements | CMS | Low/None |
| physician_payments_reporting | Physician Payments Sunshine Act (42 USC 1320a-7h) | CMS | Moderate |
| state_gift_ban_laws | State Physician Gift Ban & Disclosure Laws | State AGs / State Legislatures | High |
| teaching_hospital_reporting | Teaching Hospital Payment Reporting | CMS | Low/None |

### Biosafety & Lab Safety (biosafety_lab)

**Industry**: biotech
**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| bloodborne_pathogen_lab | OSHA Bloodborne Pathogens Standard for Lab Settings (29 CFR 1910.1030) | OSHA | Moderate |
| bsl_classifications | Biosafety Level (BSL) Classifications 1-4 | CDC / NIH | Low/None |
| chemical_hygiene_plan | OSHA Laboratory Standard / Chemical Hygiene Plan (29 CFR 1910.1450) | OSHA | Moderate |
| institutional_biosafety_committee | Institutional Biosafety Committee (IBC) Requirements | NIH | Low/None |
| nih_rdna_guidelines | NIH Guidelines for Research Involving Recombinant or Synthetic Nucleic Acid Molecules | NIH | Low/None |
| select_agent_regulations | Select Agent Regulations (42 CFR Part 73 / 7 CFR Part 331 / 9 CFR Part 121) | CDC / APHIS | Low/None |

### FDA Pre/Post-Market Lifecycle (fda_lifecycle)

**Industry**: biotech:pharma
**Keys**: 12

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| anda_generic_pathway | ANDA Generic Drug Pathway (Hatch-Waxman) | FDA/CDER | Low/None |
| fda_483_observations | FDA 483 Observations & CAPA Management | FDA | Low/None |
| fda_breakthrough_accelerated | Breakthrough/Fast Track/Accelerated Approval | FDA | Low/None |
| fda_priority_review | Priority Review & Voucher Programs | FDA | Low/None |
| nda_bla_submission | NDA/BLA Submission Requirements | FDA/CDER/CBER | Low/None |
| orphan_drug_exclusivity | Orphan Drug Designation & Exclusivity | FDA | Low/None |
| patent_exclusivity_orange_book | Patent/Exclusivity Listings (Orange Book/Purple Book) | FDA | Low/None |
| pediatric_study_requirements | Pediatric Study Requirements (PREA/BPCA) | FDA | Low/None |
| pharmacovigilance_safety_reporting | Pharmacovigilance & Safety Reporting | FDA/EMA | Low/None |
| post_market_surveillance_faers | Post-Market Surveillance (FAERS/MedWatch) | FDA | Low/None |
| product_labeling_pi_medication_guide | Product Labeling (PI, Medication Guides, Black Box) | FDA | Low/None |
| rems_lifecycle | REMS (Risk Evaluation & Mitigation Strategies) | FDA | Low/None |

## Manufacturing (10 categories)

### Process Safety Management (process_safety)

**Industry**: manufacturing
**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| emergency_action_plan | Emergency Action Plan | OSHA | Low/None |
| management_of_change | Management of Change (MOC) | OSHA | Low/None |
| mechanical_integrity | Mechanical Integrity | OSHA | Low/None |
| osha_psm | OSHA Process Safety Management | OSHA | Moderate |
| pre_startup_review | Pre-Startup Safety Review | OSHA | Low/None |
| process_hazard_analysis | Process Hazard Analysis | OSHA | Low/None |

### Environmental & Emissions (environmental_compliance)

**Industry**: manufacturing
**Keys**: 14

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| air_quality_permit | Air Quality Operating Permit | EPA/State | High |
| cercla_superfund_liability | CERCLA/Superfund Liability | EPA | Moderate |
| clean_air_act_title_v | Clean Air Act Title V Permitting | EPA/State | High |
| clean_water_act_npdes | Clean Water Act NPDES Permitting | EPA/State | High |
| emissions_reporting | Emissions Reporting Requirements | EPA/State | Moderate |
| epa_risk_management_program | EPA Risk Management Program (RMP) | EPA | Moderate |
| epcra_tri_reporting | EPCRA/TRI Reporting | EPA | Moderate |
| hazardous_waste_rcra | Hazardous Waste Management (RCRA) | EPA/State | High |
| neshap_compliance | NESHAP Compliance | EPA | Moderate |
| rcra_hazardous_waste | RCRA Hazardous Waste Generator Requirements | EPA/State | High |
| spcc_oil_spill_prevention | SPCC Oil Spill Prevention | EPA | Low/None |
| stormwater_permit | Stormwater Discharge Permit | EPA/State | High |
| tsca_toxic_substances | TSCA Toxic Substances Control Act | EPA | Moderate |
| wastewater_discharge | Wastewater Discharge Permit | EPA/State | High |

### Chemical & Hazardous Materials (chemical_safety)

**Industry**: manufacturing
**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| chemical_inventory_reporting | Chemical Inventory Reporting | EPA/State | Moderate |
| hazardous_substance_storage | Hazardous Substance Storage Requirements | EPA/OSHA/State | High |
| hazcom_ghs | Hazard Communication / GHS | OSHA | Low/None |
| pfas_restrictions | PFAS Restrictions | EPA/State | High |
| right_to_know | Right-to-Know Laws | OSHA/State | High |
| sds_management | Safety Data Sheet Management | OSHA | Low/None |

### Machine & Equipment Safety (machine_safety)

**Industry**: manufacturing
**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| confined_space | Confined Space Entry | OSHA | Low/None |
| crane_hoist_safety | Crane & Hoist Safety | OSHA | Low/None |
| electrical_safety | Electrical Safety | OSHA/NFPA | Low/None |
| lockout_tagout | Lockout/Tagout (LOTO) | OSHA | Low/None |
| machine_guarding | Machine Guarding | OSHA | Low/None |
| powered_industrial_trucks | Powered Industrial Trucks | OSHA | Low/None |

### Industrial Hygiene & Exposure (industrial_hygiene)

**Industry**: manufacturing
**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| ergonomics | Ergonomics Programs | OSHA/State (CA) | Moderate |
| heat_illness_prevention | Industrial Heat Illness Prevention | OSHA/State | High |
| noise_exposure | Noise Exposure / Hearing Conservation | OSHA | Low/None |
| permissible_exposure_limits | Permissible Exposure Limits (PELs) | OSHA | Low/None |
| personal_protective_equipment | Personal Protective Equipment (PPE) | OSHA | Low/None |
| respiratory_protection | Respiratory Protection Program | OSHA | Low/None |

### Import/Export & Trade (trade_compliance)

**Industry**: manufacturing
**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| anti_dumping_duties | Anti-Dumping & Countervailing Duties | ITC/Commerce | Moderate |
| country_of_origin | Country of Origin Marking | CBP | Low/None |
| customs_tariff | Customs & Tariff Classification | CBP | Moderate |
| export_controls | Export Controls (EAR/ITAR) | BIS/DDTC | Low/None |
| sanctions_screening | Sanctions Screening | OFAC/Treasury | Low/None |
| trade_agreements | Trade Agreement Compliance | USTR/CBP | Moderate |

### Product Safety & Standards (product_safety)

**Industry**: manufacturing
**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| consumer_safety_standards | Consumer Safety Standards | CPSC | Moderate |
| labeling_requirements | Product Labeling Requirements | CPSC/FTC | Moderate |
| product_certification | Product Certification | CPSC/NRTL | Moderate |
| quality_system_requirements | Product Quality System Requirements | Various | Moderate |
| recall_procedures | Product Recall Procedures | CPSC/FDA | Low/None |
| type_approval | Type Approval / Conformity Assessment | National regulators | Moderate |

### Labor Relations (labor_relations)

**Industry**: manufacturing
**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| collective_bargaining | Collective Bargaining Agreements | NLRB | Low/None |
| employee_representation | Employee Representation Rights | NLRB/National | Low/None |
| right_to_work | Right-to-Work Laws | State legislatures | High |
| strike_lockout_rules | Strike & Lockout Rules | NLRB | Low/None |
| union_notification | Union Notification Requirements | DOL/NLRB | Low/None |
| works_council | Works Council / Employee Representation | National labor ministry | Moderate |

### Quality Management Systems (quality_systems)

**Industry**: manufacturing:quality
**Keys**: 9

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| cap_accreditation | CAP (College of American Pathologists) Accreditation | CAP | Low/None |
| clia_lab_certification | CLIA Laboratory Certification | CMS/CDC | Moderate |
| iso_13485_medical_devices | ISO 13485 Medical Device QMS | Notified Bodies/Registrars | Low/None |
| iso_14001_environmental | ISO 14001 Environmental Management System | Registrars | Low/None |
| iso_15189_clinical_labs | ISO 15189 Clinical Laboratory QMS | Accreditation Bodies | Low/None |
| iso_27001_information_security | ISO 27001 Information Security Management | Registrars | Low/None |
| iso_45001_ohs | ISO 45001 Occupational Health & Safety | Registrars | Low/None |
| iso_9001_general_qms | ISO 9001 General Quality Management System | Registrars | Low/None |
| joint_commission_accreditation | Joint Commission Accreditation | The Joint Commission | Low/None |

### Supply Chain & Procurement (supply_chain)

**Industry**: manufacturing:procurement
**Keys**: 8

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| antibribery_fcpa_uk_bribery | Anti-Bribery (FCPA / UK Bribery Act) | DOJ/SFO | Low/None |
| conflict_minerals_dodd_frank | Conflict Minerals (Dodd-Frank §1502) | SEC | Low/None |
| gpp_green_procurement | Green Procurement / Environmentally Preferable Purchasing | EPA/GSA | Low/None |
| reach_regulation | REACH Chemical Registration (EU) | ECHA | Low/None |
| rohs_directive | RoHS Directive | EU Member States | Low/None |
| supplier_qualification_audit | Supplier Qualification & Audit Requirements | FDA/ISO | Moderate |
| track_trace_serialization | Track & Trace / Serialization | FDA | Low/None |
| uyghur_forced_labor_prevention | Uyghur Forced Labor Prevention Act (UFLPA) | CBP/DHS | Low/None |

## Medical Compliance (17 categories)

### Health IT & Interoperability (health_it)

**Industry**: healthcare
**Keys**: 10

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| 21_cfr_part_11 | 21 CFR Part 11 (Electronic Records in FDA-Regulated Activities) | FDA | Low/None |
| 21st_century_cures_act_information_blocking | 21st Century Cures Act — Information Blocking (45 CFR Part 171) | ONC / OIG | Low/None |
| cms_interoperability_patient_access_rules | CMS Interoperability & Patient Access Rules | CMS | Low/None |
| electronic_signatures | Electronic Signatures (ESIGN / UETA) | Federal / State | Moderate |
| eprescribing_for_controlled_substances | E-Prescribing for Controlled Substances (EPCS) | DEA | High |
| hl7_fhir_uscdi_standards | HL7 FHIR & USCDI Standards | ONC / HL7 | Low/None |
| meaningful_use_promoting_interoperability | Meaningful Use / Promoting Interoperability | CMS | Low/None |
| onc_health_it_certification | ONC Health IT Certification (45 CFR Part 170) | ONC | Low/None |
| state_hie_requirements | State HIE Requirements | State HIT offices | High |
| telehealth_technology_standards | Telehealth Technology Standards | CMS / State Boards / DEA | High |

### Quality Reporting (quality_reporting)

**Industry**: healthcare
**Keys**: 12

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| advanced_apms | Advanced APMs | CMS / CMMI | Low/None |
| cms_star_ratings | CMS Star Ratings | CMS | Low/None |
| hac_reduction_program | HAC Reduction Program | CMS | Low/None |
| hedis_measures | HEDIS Measures | NCQA | Low/None |
| home_health_quality_reporting | Home Health Quality Reporting | CMS | Low/None |
| hospital_iqr_program | Hospital IQR Program | CMS | Low/None |
| hospital_oqr_program | Hospital OQR Program | CMS | Low/None |
| hospital_readmissions_reduction_program | Hospital Readmissions Reduction Program | CMS | Low/None |
| hospital_vbp_program | Hospital VBP Program | CMS | Low/None |
| mips_qpp | MIPS / QPP | CMS | Low/None |
| snf_quality_reporting_program | SNF Quality Reporting Program | CMS | Low/None |
| state_quality_reporting_mandates | State Quality Reporting Mandates | State Health Depts | High |

### Cybersecurity (cybersecurity)

**Industry**: healthcare
**Keys**: 17

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| circia | CIRCIA (Cyber Incident Reporting) | CISA | Low/None |
| cisa_healthcare_guidance | CISA Healthcare Guidance | CISA | Low/None |
| fda_device_cybersecurity_guidance | FDA Pre/Post-Market Cybersecurity Guidance (Devices) | FDA | Low/None |
| gdpr_health_data | GDPR — Health Data Processing | EU Data Protection Authorities | Low/None |
| hhs_healthcare_cybersecurity_performance_goals | HHS Healthcare Cybersecurity Performance Goals (HPH CPGs) | HHS / CISA | Low/None |
| hipaa_security_rule_cybersecurity | HIPAA Security Rule (Technical Details) | HHS OCR | Low/None |
| incident_response_plan | Cybersecurity Incident Response Plan Requirements | Multiple | Moderate |
| medical_device_cybersecurity | Medical Device Cybersecurity (Section 524B FD&C Act) | FDA | Low/None |
| nist_csf_implementation | NIST Cybersecurity Framework Implementation | NIST (voluntary) | Low/None |
| nist_cybersecurity_framework | NIST Cybersecurity Framework (CSF 2.0) | NIST / HHS | Low/None |
| patch_act_medical_devices | PATCH Act — Medical Device Cybersecurity | FDA / Congress | Low/None |
| ransomware_cyber_extortion_response | Ransomware & Cyber Extortion Response | HHS OCR / FBI / CISA | Low/None |
| soc2_type2_compliance | SOC 2 Type II Compliance | AICPA / Auditors | Low/None |
| state_consumer_privacy_acts | State Consumer Privacy Acts (CCPA, CPA, CTDPA, etc.) | State AGs | High |
| state_cybersecurity_requirements | State Cybersecurity Requirements | State regulators | High |
| state_data_breach_notification_laws | State Data Breach Notification Laws | State AGs | High |
| third_party_risk_management | Third-Party / Vendor Risk Management | Multiple | Moderate |

### Environmental Safety (environmental_safety)

**Industry**: healthcare
**Keys**: 10

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| ada_accessibility_standards | ADA Accessibility Standards | DOJ | Moderate |
| cms_life_safety_code | CMS Life Safety Code (NFPA 101) | CMS / State Fire Marshal | Moderate |
| construction_renovation | Construction & Renovation (ICRA/FGI) | Joint Commission / State | Moderate |
| epa_medical_waste | EPA Medical Waste (RCRA) | EPA / State environmental agencies | High |
| legionella_water_management | Legionella / Water Management | CMS / State Health Depts | Moderate |
| nfpa_99 | NFPA 99 (Health Care Facilities Code) | CMS / Joint Commission | Low/None |
| osha_hazardous_chemical_standards | OSHA Hazardous Chemical Standards | OSHA | Moderate |
| osha_ionizing_radiation | OSHA Ionizing Radiation (29 CFR 1910.1096) | OSHA / NRC / State | Moderate |
| sharps_needlestick_prevention | Sharps & Needlestick Prevention | OSHA | Low/None |
| state_radiation_control_programs | State Radiation Control Programs | State Radiation Control | High |

### Pharmacy & Controlled Substances (pharmacy_drugs)

**Industry**: healthcare:pharmacy
**Keys**: 10

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| 340b_drug_pricing_program | 340B Drug Pricing Program (42 U.S.C. § 256b) | HRSA | Moderate |
| dea_registration_controlled_substances | DEA Registration & Controlled Substances (21 CFR 1301–1321) | DEA | Moderate |
| drug_diversion_prevention | Drug Diversion Prevention | DEA / State / Joint Commission | Moderate |
| drug_supply_chain_security_act | Drug Supply Chain Security Act (DSCSA) | FDA | Low/None |
| fda_rems_programs | FDA REMS Programs | FDA | Low/None |
| medication_error_reporting | Medication Error Reporting | FDA / State | Moderate |
| pharmaceutical_waste_disposal | Pharmaceutical Waste Disposal | EPA / DEA / State | High |
| prescription_drug_monitoring_programs | Prescription Drug Monitoring Programs (PDMPs) | State Pharmacy Boards / BJA | High |
| state_pharmacy_practice_acts | State Pharmacy Practice Acts | State Pharmacy Boards | High |
| usp_compounding_standards | USP Compounding Standards (<795>, <797>, <800>) | State Pharmacy Boards / CMS | Moderate |

### Payer Relations (payer_relations)

**Industry**: healthcare:managed_care
**Keys**: 9

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| aca_insurance_market_reforms | ACA Insurance Market Reforms | CMS / State DOIs | Moderate |
| cvo_standards | CVO Standards | NCQA / Payers | Low/None |
| erisa | ERISA | DOL | Moderate |
| medicaid_managed_care | Medicaid Managed Care (42 CFR Part 438) | CMS / State Medicaid | High |
| medicare_advantage_compliance | Medicare Advantage Compliance (42 CFR Part 422) | CMS | Low/None |
| mental_health_parity | Mental Health Parity (MHPAEA) | DOL / HHS / Treasury | Moderate |
| network_adequacy_standards | Network Adequacy Standards | CMS / State DOIs | High |
| prior_authorization_requirements | Prior Authorization Requirements | CMS / State DOIs | High |
| state_insurance_regulation | State Insurance Regulation | State DOIs | High |

### Reproductive & Behavioral Health (reproductive_behavioral)

**Industry**: healthcare:behavioral_health
**Keys**: 10

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| 42_cfr_part_2_reproductive_behavioral | 42 CFR Part 2 (SUD Records — Detailed) | SAMHSA | Moderate |
| confidentiality_of_minor_health_records | Confidentiality of Minor Health Records | State law | High |
| conscience_religious_exemption_laws | Conscience & Religious Exemption Laws | HHS OCR / State | High |
| hivaids_testing_disclosure_laws | HIV/AIDS Testing & Disclosure Laws | State law / CDC | High |
| postdobbs_state_abortion_laws | Post-Dobbs State Abortion Laws | State law | High |
| state_mental_health_commitment_laws | State Mental Health Commitment Laws | State law | High |
| state_reproductive_health_privacy_laws | State Reproductive Health Privacy Laws | State law | High |
| state_sud_treatment_regulations | State SUD Treatment Regulations | State agencies | High |
| title_x_family_planning | Title X Family Planning | HHS / OASH | Moderate |
| transgender_healthcare_regulations | Transgender Healthcare Regulations | State law | High |

### Pediatric & Vulnerable Populations (pediatric_vulnerable)

**Industry**: healthcare:pediatric
**Keys**: 8

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| adult_protective_services_reporting | Adult Protective Services Reporting | State APS | High |
| child_abuse_neglect_reporting | Child Abuse & Neglect Reporting (CAPTA) | HHS ACF / State CPS | High |
| cms_nursing_home_minimum_staffing_rule | CMS Nursing Home Minimum Staffing Rule (2024) | CMS | Low/None |
| disability_rights | Disability Rights (Section 504 / ADA) | HHS OCR / DOJ | Moderate |
| elder_abuse_prevention | Elder Abuse Prevention (Elder Justice Act) | HHS ACL / State APS | High |
| guardianship_surrogate_decisionmaking | Guardianship & Surrogate Decision-Making | State courts / law | High |
| immigrant_undocumented_patient_protections | Immigrant & Undocumented Patient Protections | CMS / State | High |
| nursing_home_reform_act | Nursing Home Reform Act (OBRA 1987) | CMS | Moderate |

### Telehealth & Digital Health (telehealth)

**Industry**: healthcare:telehealth
**Keys**: 10

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| aiml_in_clinical_decision_support | AI/ML in Clinical Decision Support | FDA / State | Moderate |
| fda_digital_health_samd | FDA Digital Health / SaMD | FDA | Low/None |
| interstate_medical_licensure_compact | Interstate Medical Licensure Compact (IMLC) | IMLC Commission | High |
| medicare_telehealth_coverage | Medicare Telehealth Coverage (§1834(m)) | CMS | Low/None |
| nurse_licensure_compact | Nurse Licensure Compact (NLC) | NCSBN | High |
| psypact | PSYPACT | PSYPACT Commission | High |
| remote_patient_monitoring | Remote Patient Monitoring | CMS / State | Moderate |
| ryan_haight_act | Ryan Haight Act (Online Controlled Substance Prescribing) | DEA | Moderate |
| state_telehealth_parity_laws | State Telehealth Parity Laws | State DOIs / Legislatures | High |
| state_telehealth_practice_standards | State Telehealth Practice Standards | State Medical Boards | High |

### Medical Device Safety (medical_devices)

**Industry**: healthcare:devices
**Keys**: 15

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| 510k_pma_de_novo | 510(k) / PMA / De Novo Classification Pathways | FDA / CDRH | Low/None |
| cybersecurity_medical_devices | Cybersecurity for Medical Devices (FDA Guidance + PATCH Act) | FDA | Low/None |
| design_controls_21cfr820 | Design Controls (21 CFR 820 Subpart C) | FDA | Low/None |
| device_establishment_registration | Device Establishment Registration & Listing | FDA | Low/None |
| device_master_record | Device Master Record (DMR) & Device History Record (DHR) | FDA | Low/None |
| equipment_maintenance_testing | Equipment Maintenance & Testing | CMS / Joint Commission | Moderate |
| fda_medical_device_reporting | FDA Medical Device Reporting (21 CFR Part 803) | FDA | Low/None |
| fda_recalls_safety_communications | FDA Recalls & Safety Communications | FDA | Low/None |
| human_factors_usability | Human Factors / Usability Engineering (IEC 62366) | FDA | Low/None |
| medical_device_tracking | Medical Device Tracking (21 CFR Part 821) | FDA | Low/None |
| radiationemitting_device_standards | Radiation-Emitting Device Standards (21 CFR Subchapter J) | FDA / State | Moderate |
| safe_medical_devices_act | Safe Medical Devices Act (SMDA) | FDA | Low/None |
| software_as_medical_device | Software as a Medical Device (SaMD) — IEC 62304 | FDA / IEC | Low/None |
| unique_device_identification | Unique Device Identification (UDI) | FDA | Low/None |
| unique_device_identification_udi | Unique Device Identification (UDI) System | FDA | Low/None |

### Transplant & Organ Procurement (transplant_organ)

**Industry**: healthcare:transplant
**Keys**: 5

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| cms_cops_for_transplant_centers | CMS CoPs for Transplant Centers (42 CFR 482.68–104) | CMS | Low/None |
| national_organ_transplant_act | National Organ Transplant Act (NOTA) | HRSA / OPTN | Low/None |
| opo_conditions_for_coverage | OPO Conditions for Coverage | CMS | Low/None |
| optnunos_policies_bylaws | OPTN/UNOS Policies & Bylaws | OPTN / UNOS | Low/None |
| tissue_banking | Tissue Banking (FDA 21 CFR Parts 1270, 1271) | FDA | Moderate |

### Healthcare Antitrust (antitrust)

**Industry**: healthcare
**Keys**: 5

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| certificate_of_need | Certificate of Need (CON) | State Health Planning | High |
| ftc_act_5 | FTC Act §5 | FTC | Low/None |
| hartscottrodino_act | Hart-Scott-Rodino Act (HSR) | FTC / DOJ | Low/None |
| sherman_act_clayton_act | Sherman Act / Clayton Act | DOJ / FTC | Moderate |
| state_ag_healthcare_transaction_review | State AG Healthcare Transaction Review | State AGs | High |

### Tax-Exempt Compliance (tax_exempt)

**Industry**: healthcare:nonprofit
**Keys**: 5

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| irc_501_for_charitable_hospitals | IRC §501(r) for Charitable Hospitals | IRS | Moderate |
| irs_form_990_schedule_h | IRS Form 990 Schedule H | IRS | Low/None |
| state_community_benefit_requirements | State Community Benefit Requirements | State AGs / Health Depts | High |
| state_property_tax_exemptions | State Property Tax Exemptions | State/Local Tax Authorities | High |
| ubit | UBIT (Unrelated Business Income Tax) | IRS | Low/None |

### Language Access & Civil Rights (language_access)

**Industry**: healthcare
**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| ada_effective_communication | ADA Effective Communication | DOJ / HHS OCR | Low/None |
| clas_standards | CLAS Standards | HHS OMH | Low/None |
| religious_accommodation_in_healthcare | Religious Accommodation in Healthcare | EEOC / HHS OCR | Moderate |
| section_1557_aca | Section 1557 ACA (Detailed) | HHS OCR | Low/None |
| state_language_access_laws | State Language Access Laws | State law | High |
| title_vi | Title VI (Language Access) | HHS OCR | Moderate |

### Records Retention (records_retention)

**Industry**: healthcare
**Keys**: 7

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| baa_requirements | BAA Requirements | HHS OCR | Low/None |
| hipaa_documentation_requirements | HIPAA Documentation Requirements | HHS OCR | Low/None |
| legal_hold_litigation_preservation | Legal Hold & Litigation Preservation | Courts / DOJ | Moderate |
| medical_records_content_standards | Medical Records Content Standards | CMS / Accreditors | Moderate |
| medical_records_retention | Medical Records Retention | CMS / State law | High |
| patient_access_to_records | Patient Access to Records (HIPAA Right of Access) | HHS OCR | Moderate |
| state_medical_records_laws | State Medical Records Laws | State law | High |

### Marketing & Communications (marketing_comms)

**Industry**: healthcare
**Keys**: 7

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| canspam_act | CAN-SPAM Act | FTC | Low/None |
| ftc_endorsement_guidelines | FTC Endorsement Guidelines | FTC | Low/None |
| hipaa_marketing_restrictions | HIPAA Marketing Restrictions | HHS OCR | Low/None |
| medicare_marketing_guidelines | Medicare Marketing Guidelines (MCMG) | CMS | Low/None |
| price_transparency | Price Transparency (Hospital & Insurance) | CMS | Low/None |
| state_consumer_protection_deceptive_practices | State Consumer Protection / Deceptive Practices | State AGs / DOIs | High |
| tcpa | TCPA | FCC / State | High |

### Emerging Regulatory (emerging_regulatory)

**Industry**: healthcare
**Keys**: 10

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| ai_algorithmic_decisionmaking | AI & Algorithmic Decision-Making | FDA / CMS / State | High |
| autonomous_robotic_surgery_systems | Autonomous & Robotic Surgery Systems | FDA / State | Moderate |
| cannabis_medical_marijuana | Cannabis / Medical Marijuana | DEA / State | High |
| clinical_decision_support_exemptions | Clinical Decision Support (CDS) Exemptions | FDA | Low/None |
| environmental_sustainability_reporting | Environmental Sustainability Reporting | EPA / State / Voluntary | Moderate |
| genomic_medicine_precision_health | Genomic Medicine & Precision Health | FDA / CLIA / State | High |
| health_equity_compliance | Health Equity Compliance | CMS / Accreditors | Moderate |
| interstate_practice_multistate_compliance | Interstate Practice & Multi-State Compliance | Multiple | High |
| right_to_try_act | Right to Try Act (21 U.S.C. § 360bbb-0a) | FDA / State | Moderate |
| social_determinants_of_health_data | Social Determinants of Health (SDOH) Data | CMS / ONC | Low/None |

## Oncology (5 categories)

### Radiation Safety (radiation_safety)

**Industry**: healthcare:oncology
**Keys**: 7

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| brachytherapy_safety | Brachytherapy Safety Standards | NRC/State | Moderate |
| linear_accelerator_qa | Linear Accelerator QA Requirements | NRC/State | Moderate |
| national_radiation_control | National Radiation Control (International) | National nuclear authority | Moderate |
| radiation_oncology_safety_team | Radiation Oncology Safety Team | ACR/ASTRO | Moderate |
| radiation_safety_officer | Radiation Safety Officer Requirements | NRC/State | Moderate |
| radioactive_materials_license | Radioactive Materials License | NRC/Agreement States | High |
| state_radiation_control_programs | State Radiation Control Programs | State Radiation Control | High |

### Chemotherapy & Hazardous Drugs (chemotherapy_handling)

**Industry**: healthcare:oncology
**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| closed_system_transfer | Closed System Transfer Devices | NIOSH/USP | Moderate |
| hazardous_drug_assessment | Hazardous Drug Assessment | NIOSH | Low/None |
| hazardous_waste_disposal | Hazardous Drug Waste Disposal | EPA/State | Moderate |
| national_hazardous_drug_handling | National Hazardous Drug Handling (International) | National health authority | Moderate |
| spill_management | Hazardous Drug Spill Management | OSHA/USP | Low/None |
| usp_compounding_standards | USP Compounding Standards (<795>, <797>, <800>) | State Pharmacy Boards / CMS | Moderate |

### Tumor Registry Reporting (tumor_registry)

**Industry**: healthcare:oncology
**Keys**: 5

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| cancer_registry_reporting | Cancer Registry Reporting | State cancer registries/CDC | High |
| electronic_reporting_format | Electronic Reporting Format | NAACCR | Moderate |
| national_cancer_registry | National Cancer Registry (International) | National health authority | Moderate |
| registry_data_quality | Registry Data Quality | NAACCR/State | Moderate |
| reporting_timelines | Registry Reporting Timelines | State cancer registries | High |

### Oncology Clinical Trials (oncology_clinical_trials)

**Industry**: healthcare:oncology
**Keys**: 5

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| adverse_event_reporting | Adverse Event Reporting | FDA | Low/None |
| clinical_trial_coverage_mandates | Clinical Trial Coverage Mandates | State legislatures | High |
| investigational_drug_access | Investigational Drug Access | FDA | Low/None |
| protocol_deviation_reporting | Protocol Deviation Reporting | FDA/IRB | Low/None |
| right_to_try | Right to Try Act | FDA | Low/None |

### Oncology Patient Rights (oncology_patient_rights)

**Industry**: healthcare:oncology
**Keys**: 6

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| advance_directives | Advance Directives (Patient Self-Determination Act) | CMS / State law | High |
| cancer_treatment_consent | Cancer Treatment Consent | State/TJC | Moderate |
| fertility_preservation_counseling | Fertility Preservation Counseling | ASCO/State | Moderate |
| hospice_palliative_care | Hospice & Palliative Care | CMS/State | Moderate |
| palliative_care_access | Palliative Care Access (International) | National health authority | Moderate |
| patient_rights_declarations | Patient Rights Declarations | State/TJC | Moderate |

## Supplementary (3 categories)

### Business License (business_license)

**Keys**: 4

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| dba_registration | DBA / Fictitious Business Name Registration | County clerk / Secretary of State | Low/None |
| local_business_license | City / County Business License / Tax Registration | Local government | High |
| professional_licensing | Professional / Occupational Licensing | State licensing boards | Moderate |
| state_business_registration | State Business Entity Registration | Secretary of State | Moderate |

### Tax Rate (tax_rate)

**Keys**: 7

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| corporate_income_tax | State Corporate Income Tax Rates | State revenue department | High |
| disability_insurance_tax | State Disability Insurance Tax Rates | State workforce agency | High |
| employment_training_tax | Employment Training Tax / Fund | State workforce agency | Moderate |
| franchise_tax | Franchise / Privilege Tax | State revenue department | Moderate |
| local_tax | Local Income / Payroll Taxes | Local government | Moderate |
| sales_use_tax | State / Local Sales and Use Tax | State revenue department | Moderate |
| unemployment_insurance_tax | State Unemployment Insurance Tax Rates | State workforce agency | High |

### Posting Requirements (posting_requirements)

**Keys**: 9

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| discrimination_poster | EEO / Discrimination Poster | EEOC / State civil rights agencies | Low/None |
| family_leave_poster | FMLA / Family Leave Poster | WHD / State labor agencies | Low/None |
| minimum_wage_poster | Minimum Wage Poster | WHD / State labor agencies | Low/None |
| osha_poster | OSHA Safety Poster | OSHA / State plan states | Low/None |
| paid_sick_leave_poster | Paid Sick Leave Poster | State / Local government | Low/None |
| wage_order_poster | Wage Order / IWC Poster (CA) | State labor agencies | Low/None |
| whistleblower_poster | Whistleblower Protection Poster | State labor agencies | Low/None |
| workers_comp_poster | Workers' Compensation Poster | State WC boards | Low/None |
| workplace_violence_poster | Workplace Violence Prevention Poster | OSHA / State plan states | Low/None |

---

**Total**: 7 groups, 63 categories, 546 policy keys

*Generated from compliance_registry.py on 2026-03-25*