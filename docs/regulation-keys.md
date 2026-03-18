# Compliance Regulation Keys Reference

This document lists all **328 canonical regulation keys** used for stable deduplication
across the jurisdiction requirements system. Keys are organized by category group.

Each key represents a distinct regulation or requirement type. The same key (e.g.,
`state_paid_sick_leave`) is used across all jurisdictions — the jurisdiction is tracked
by which `jurisdiction_id` the row belongs to, not in the key itself.

When Gemini researches a jurisdiction, it tags each requirement with one of these keys.
The key is used as the dedup identifier: `UNIQUE(jurisdiction_id, category:regulation_key)`.

## Labor (79 keys)

### Anti-Discrimination (`anti_discrimination`)

6 keys:

- `harassment_prevention_training` — Harassment Prevention Training
- `pay_transparency` — Pay Transparency
- `protected_classes` — Protected Classes
- `reasonable_accommodation` — Reasonable Accommodation
- `salary_history_ban` — Salary History Ban
- `whistleblower_protection` — Whistleblower Protection

### Final Pay (`final_pay`)

4 keys:

- `final_pay_layoff` — Final Pay Layoff
- `final_pay_resignation` — Final Pay Resignation
- `final_pay_termination` — Final Pay Termination
- `waiting_time_penalty` — Waiting Time Penalty

### Leave (`leave`)

15 keys:

- `bereavement_leave` — Bereavement Leave
- `bone_marrow_donor_leave` — Bone Marrow Donor Leave
- `domestic_violence_leave` — Domestic Violence Leave
- `fmla` — Fmla
- `jury_duty_leave` — Jury Duty Leave
- `military_leave` — Military Leave
- `organ_donor_leave` — Organ Donor Leave
- `paid_sick_leave` — Paid Sick Leave
- `pregnancy_disability_leave` — Pregnancy Disability Leave
- `reproductive_loss_leave` — Reproductive Loss Leave
- `school_activity_leave` — School Activity Leave
- `state_disability_insurance` — State Disability Insurance
- `state_family_leave` — State Family Leave
- `state_paid_family_leave` — State Paid Family Leave
- `voting_leave` — Voting Leave

### Meal & Rest Breaks (`meal_breaks`)

6 keys:

- `healthcare_meal_waiver` — Healthcare Meal Waiver
- `lactation_break` — Lactation Break
- `meal_break` — Meal Break
- `missed_break_penalty` — Missed Break Penalty
- `on_duty_meal_agreement` — On Duty Meal Agreement
- `rest_break` — Rest Break

### Minimum Wage (`minimum_wage`)

10 keys:

- `exempt_salary_threshold` — Exempt Salary Threshold
- `fast_food_minimum_wage` — Fast Food Minimum Wage
- `healthcare_minimum_wage` — Healthcare Minimum Wage
- `large_employer_minimum_wage` — Large Employer Minimum Wage
- `local_minimum_wage` — Local Minimum Wage
- `small_employer_minimum_wage` — Small Employer Minimum Wage
- `state_minimum_wage` — State Minimum Wage
- `tip_credit_prohibition` — Tip Credit Prohibition
- `tipped_minimum_wage` — Tipped Minimum Wage
- `youth_minimum_wage` — Youth Minimum Wage

### Minor Work Permits (`minor_work_permit`)

6 keys:

- `entertainment_permits` — Entertainment Permits
- `hour_limits_14_15` — Hour Limits 14 15
- `hour_limits_16_17` — Hour Limits 16 17
- `prohibited_occupations` — Prohibited Occupations
- `recordkeeping` — Recordkeeping
- `work_permit` — Work Permit

### Overtime (`overtime`)

8 keys:

- `alternative_workweek` — Alternative Workweek
- `comp_time` — Comp Time
- `daily_weekly_overtime` — Daily Weekly Overtime
- `double_time` — Double Time
- `exempt_salary_threshold` — Exempt Salary Threshold
- `healthcare_overtime` — Healthcare Overtime
- `mandatory_overtime_restrictions` — Mandatory Overtime Restrictions
- `seventh_day_overtime` — Seventh Day Overtime

### Pay Frequency (`pay_frequency`)

6 keys:

- `exempt_monthly_pay` — Exempt Monthly Pay
- `final_pay_resignation` — Final Pay Resignation
- `final_pay_termination` — Final Pay Termination
- `payday_posting` — Payday Posting
- `standard_pay_frequency` — Standard Pay Frequency
- `wage_notice` — Wage Notice

### Scheduling & Reporting Time (`scheduling_reporting`)

5 keys:

- `on_call_pay` — On Call Pay
- `predictive_scheduling` — Predictive Scheduling
- `reporting_time_pay` — Reporting Time Pay
- `split_shift_premium` — Split Shift Premium
- `spread_of_hours` — Spread Of Hours

### Sick Leave (`sick_leave`)

3 keys:

- `accrual_and_usage_caps` — Accrual And Usage Caps
- `local_sick_leave` — Local Sick Leave
- `state_paid_sick_leave` — State Paid Sick Leave

### Workers' Comp (`workers_comp`)

5 keys:

- `anti_retaliation` — Anti Retaliation
- `claim_filing` — Claim Filing
- `mandatory_coverage` — Mandatory Coverage
- `posting_requirements` — Posting Requirements
- `return_to_work` — Return To Work

### Workplace Safety (`workplace_safety`)

5 keys:

- `hazard_communication` — Hazard Communication
- `heat_illness_prevention` — Heat Illness Prevention
- `injury_illness_recordkeeping` — Injury Illness Recordkeeping
- `osha_general_duty` — Osha General Duty
- `workplace_violence_prevention` — Workplace Violence Prevention

## Supplementary (20 keys)

### Business License (`business_license`)

4 keys:

- `dba_registration` — Dba Registration
- `local_business_license` — Local Business License
- `professional_licensing` — Professional Licensing
- `state_business_registration` — State Business Registration

### Posting Requirements (`posting_requirements`)

9 keys:

- `discrimination_poster` — Discrimination Poster
- `family_leave_poster` — Family Leave Poster
- `minimum_wage_poster` — Minimum Wage Poster
- `osha_poster` — Osha Poster
- `paid_sick_leave_poster` — Paid Sick Leave Poster
- `wage_order_poster` — Wage Order Poster
- `whistleblower_poster` — Whistleblower Poster
- `workers_comp_poster` — Workers Comp Poster
- `workplace_violence_poster` — Workplace Violence Poster

### Tax Rate (`tax_rate`)

7 keys:

- `corporate_income_tax` — Corporate Income Tax
- `disability_insurance_tax` — Disability Insurance Tax
- `employment_training_tax` — Employment Training Tax
- `franchise_tax` — Franchise Tax
- `local_tax` — Local Tax
- `sales_use_tax` — Sales Use Tax
- `unemployment_insurance_tax` — Unemployment Insurance Tax

## Healthcare (89 keys)

### Billing & Financial Integrity (`billing_integrity`) — `healthcare`

13 keys:

- `antikickback_statute` — Anti-Kickback Statute (42 U.S.C. § 1320a-7b(b))
- `civil_monetary_penalties_law` — Civil Monetary Penalties Law (42 U.S.C. § 1320a-7a)
- `criminal_health_care_fraud` — Criminal Health Care Fraud (18 U.S.C. § 1347)
- `exclusion_statute` — Exclusion Statute (42 U.S.C. § 1320a-7)
- `false_claims_act` — False Claims Act (31 U.S.C. §§ 3729–3733)
- `medicaid_billing_requirements` — Medicaid Billing Requirements
- `medicare_conditions_of_payment_billing_rules` — Medicare Conditions of Payment / Billing Rules
- `medicare_secondary_payer_rules` — Medicare Secondary Payer (MSP) Rules
- `no_surprises_act` — No Surprises Act (Consolidated Appropriations Act 2021)
- `provider_enrollment_revalidation` — Provider Enrollment & Revalidation (42 CFR Part 424)
- `stark_law` — Stark Law (42 U.S.C. § 1395nn)
- `state_antikickback_selfreferral_laws` — State Anti-Kickback & Self-Referral Laws
- `state_false_claims_acts` — State False Claims Acts

### Clinical & Patient Safety (`clinical_safety`) — `healthcare`

17 keys:

- `advance_directives` — Advance Directives (Patient Self-Determination Act)
- `antimicrobial_stewardship_programs` — Antimicrobial Stewardship Programs
- `clia` — CLIA (42 CFR Part 493)
- `cms_conditions_for_coverage` — CMS Conditions for Coverage (CfCs)
- `cms_conditions_of_participation` — CMS Conditions of Participation (42 CFR Parts 482–491)
- `dnv_gl_healthcare_accreditation` — DNV GL Healthcare Accreditation
- `emtala` — EMTALA (42 U.S.C. § 1395dd)
- `infection_control_prevention_standards` — Infection Control & Prevention Standards
- `informed_consent_requirements` — Informed Consent Requirements
- `joint_commission_standards` — Joint Commission Standards
- `medication_management_controlled_substances` — Medication Management & Controlled Substances (21 CFR 1301–1321)
- `npdb_reporting` — NPDB Reporting
- `pain_management_opioid_prescribing` — Pain Management & Opioid Prescribing
- `patient_safety_quality_improvement_act` — Patient Safety & Quality Improvement Act (PSQIA)
- `restraint_seclusion_standards` — Restraint & Seclusion Standards (42 CFR 482.13(e)–(f))
- `sentinel_event_reporting` — Sentinel Event Reporting
- `state_licensure_standards_for_healthcare_facilitie` — State Licensure Standards for Healthcare Facilities

### Corporate Integrity & Ethics (`corporate_integrity`) — `healthcare`

9 keys:

- `code_of_conduct_conflict_of_interest` — Code of Conduct & Conflict of Interest
- `compliance_committee_board_oversight` — Compliance Committee & Board Oversight
- `corporate_integrity_agreements` — Corporate Integrity Agreements (CIAs)
- `deficit_reduction_act_of_2005` — Deficit Reduction Act of 2005 (§6032)
- `federal_sentencing_guidelines` — Federal Sentencing Guidelines (§8B2.1)
- `internal_investigations_disclosure_protocols` — Internal Investigations & Disclosure Protocols
- `oig_compliance_program_guidance` — OIG Compliance Program Guidance
- `state_whistleblower_protection_laws` — State Whistleblower Protection Laws
- `whistleblower_protections` — Whistleblower Protections (FCA Qui Tam)

### Emergency Preparedness (`emergency_preparedness`) — `healthcare`

7 keys:

- `cms_emergency_preparedness_rule` — CMS Emergency Preparedness Rule (42 CFR 482, 483, 484, 485, 486, 491)
- `emtala_emergency_obligations` — EMTALA Emergency Obligations
- `hospital_preparedness_program` — Hospital Preparedness Program (HPP)
- `mass_casualty_active_shooter` — Mass Casualty / Active Shooter
- `nims_hics` — NIMS / HICS
- `pandemic_preparedness` — Pandemic Preparedness
- `state_emergency_preparedness_requirements` — State Emergency Preparedness Requirements

### Healthcare Workforce (`healthcare_workforce`) — `healthcare`

17 keys:

- `ada` — ADA (Americans with Disabilities Act)
- `background_check_requirements` — Background Check Requirements
- `continuing_education_requirements` — Continuing Education Requirements
- `flsa` — FLSA (Fair Labor Standards Act)
- `fmla` — FMLA (Family and Medical Leave Act)
- `immigration_compliance` — Immigration Compliance (I-9 / Visa Requirements)
- `mandatory_reporting_obligations` — Mandatory Reporting Obligations
- `medical_staff_credentialing_privileging` — Medical Staff Credentialing & Privileging
- `npdb_queries` — NPDB Queries
- `nurse_staffing_ratios_requirements` — Nurse Staffing Ratios & Requirements
- `oig_exclusion_list_screening` — OIG Exclusion List (LEIE) Screening
- `osha_workplace_safety` — OSHA Workplace Safety (29 CFR Part 1910)
- `osha_workplace_violence_prevention` — OSHA Workplace Violence Prevention
- `physician_residency_gme_requirements` — Physician Residency & GME Requirements
- `provider_licensure_scope_of_practice` — Provider Licensure & Scope of Practice
- `section_1557_of_aca` — Section 1557 of ACA (Nondiscrimination)
- `title_vii_civil_rights_act` — Title VII / Civil Rights Act

### HIPAA Privacy & Security (`hipaa_privacy`) — `healthcare`

10 keys:

- `42_cfr_part_2` — 42 CFR Part 2 (Substance Use Disorder Records)
- `coppa` — COPPA (Children’s Online Privacy Protection Act)
- `ftc_health_breach_notification_rule` — FTC Health Breach Notification Rule (16 CFR Part 318)
- `genetic_information_nondiscrimination_act` — Genetic Information Nondiscrimination Act (GINA)
- `hipaa_breach_notification_rule` — HIPAA Breach Notification Rule (45 CFR Part 164 Subpart D)
- `hipaa_privacy_rule` — HIPAA Privacy Rule (45 CFR Part 160, 164 Subparts A & E)
- `hipaa_security_rule` — HIPAA Security Rule (45 CFR Part 164 Subpart C)
- `hitech_act` — HITECH Act (Title XIII of ARRA)
- `state_biometric_privacy_laws` — State Biometric Privacy Laws (e.g., IL BIPA, TX CUBI)
- `state_health_privacy_laws` — State Health Privacy Laws

### Research & Informed Consent (`research_consent`) — `healthcare`

9 keys:

- `21_cfr_part_11_research_consent` — 21 CFR Part 11 (E-Records & E-Signatures)
- `clinicaltrialsgov_registration` — ClinicalTrials.gov Registration (42 CFR Part 11)
- `common_rule` — Common Rule (45 CFR Part 46)
- `fda_human_subject_regs` — FDA Human Subject Regs (21 CFR Parts 50, 56)
- `good_clinical_practice` — Good Clinical Practice (ICH E6 R2/R3)
- `hipaa_research_provisions` — HIPAA Research Provisions
- `institutional_biosafety_committee` — Institutional Biosafety Committee (IBC)
- `nih_grants_policy_compliance` — NIH Grants Policy & Compliance
- `state_research_consent_laws` — State Research & Consent Laws

### State Licensing & Scope (`state_licensing`) — `healthcare`

7 keys:

- `certificate_of_need_programs` — Certificate of Need (CON) Programs
- `corporate_practice_of_medicine_doctrine` — Corporate Practice of Medicine Doctrine
- `feesplitting_prohibitions` — Fee-Splitting Prohibitions
- `medical_staff_bylaws_selfgovernance` — Medical Staff Bylaws & Self-Governance
- `medicaremedicaid_certification` — Medicare/Medicaid Certification
- `nonprofit_healthcare_governance` — Nonprofit Healthcare Governance
- `state_facility_licensure` — State Facility Licensure

## Medical Compliance (140 keys)

### Healthcare Antitrust (`antitrust`) — `healthcare`

5 keys:

- `certificate_of_need` — Certificate of Need (CON)
- `ftc_act_5` — FTC Act §5
- `hartscottrodino_act` — Hart-Scott-Rodino Act (HSR)
- `sherman_act_clayton_act` — Sherman Act / Clayton Act
- `state_ag_healthcare_transaction_review` — State AG Healthcare Transaction Review

### Cybersecurity (`cybersecurity`) — `healthcare`

9 keys:

- `circia` — CIRCIA (Cyber Incident Reporting)
- `cisa_healthcare_guidance` — CISA Healthcare Guidance
- `hhs_healthcare_cybersecurity_performance_goals` — HHS Healthcare Cybersecurity Performance Goals (HPH CPGs)
- `hipaa_security_rule_cybersecurity` — HIPAA Security Rule (Technical Details)
- `medical_device_cybersecurity` — Medical Device Cybersecurity (Section 524B FD&C Act)
- `nist_cybersecurity_framework` — NIST Cybersecurity Framework (CSF 2.0)
- `ransomware_cyber_extortion_response` — Ransomware & Cyber Extortion Response
- `state_cybersecurity_requirements` — State Cybersecurity Requirements
- `state_data_breach_notification_laws` — State Data Breach Notification Laws

### Emerging Regulatory (`emerging_regulatory`) — `healthcare`

10 keys:

- `ai_algorithmic_decisionmaking` — AI & Algorithmic Decision-Making
- `autonomous_robotic_surgery_systems` — Autonomous & Robotic Surgery Systems
- `cannabis_medical_marijuana` — Cannabis / Medical Marijuana
- `clinical_decision_support_exemptions` — Clinical Decision Support (CDS) Exemptions
- `environmental_sustainability_reporting` — Environmental Sustainability Reporting
- `genomic_medicine_precision_health` — Genomic Medicine & Precision Health
- `health_equity_compliance` — Health Equity Compliance
- `interstate_practice_multistate_compliance` — Interstate Practice & Multi-State Compliance
- `right_to_try_act` — Right to Try Act (21 U.S.C. § 360bbb-0a)
- `social_determinants_of_health_data` — Social Determinants of Health (SDOH) Data

### Environmental Safety (`environmental_safety`) — `healthcare`

10 keys:

- `ada_accessibility_standards` — ADA Accessibility Standards
- `cms_life_safety_code` — CMS Life Safety Code (NFPA 101)
- `construction_renovation` — Construction & Renovation (ICRA/FGI)
- `epa_medical_waste` — EPA Medical Waste (RCRA)
- `legionella_water_management` — Legionella / Water Management
- `nfpa_99` — NFPA 99 (Health Care Facilities Code)
- `osha_hazardous_chemical_standards` — OSHA Hazardous Chemical Standards
- `osha_ionizing_radiation` — OSHA Ionizing Radiation (29 CFR 1910.1096)
- `sharps_needlestick_prevention` — Sharps & Needlestick Prevention
- `state_radiation_control_programs` — State Radiation Control Programs

### Health IT & Interoperability (`health_it`) — `healthcare`

10 keys:

- `21_cfr_part_11` — 21 CFR Part 11 (Electronic Records in FDA-Regulated Activities)
- `21st_century_cures_act_information_blocking` — 21st Century Cures Act — Information Blocking (45 CFR Part 171)
- `cms_interoperability_patient_access_rules` — CMS Interoperability & Patient Access Rules
- `electronic_signatures` — Electronic Signatures (ESIGN / UETA)
- `eprescribing_for_controlled_substances` — E-Prescribing for Controlled Substances (EPCS)
- `hl7_fhir_uscdi_standards` — HL7 FHIR & USCDI Standards
- `meaningful_use_promoting_interoperability` — Meaningful Use / Promoting Interoperability
- `onc_health_it_certification` — ONC Health IT Certification (45 CFR Part 170)
- `state_hie_requirements` — State HIE Requirements
- `telehealth_technology_standards` — Telehealth Technology Standards

### Language Access & Civil Rights (`language_access`) — `healthcare`

6 keys:

- `ada_effective_communication` — ADA Effective Communication
- `clas_standards` — CLAS Standards
- `religious_accommodation_in_healthcare` — Religious Accommodation in Healthcare
- `section_1557_aca` — Section 1557 ACA (Detailed)
- `state_language_access_laws` — State Language Access Laws
- `title_vi` — Title VI (Language Access)

### Marketing & Communications (`marketing_comms`) — `healthcare`

7 keys:

- `canspam_act` — CAN-SPAM Act
- `ftc_endorsement_guidelines` — FTC Endorsement Guidelines
- `hipaa_marketing_restrictions` — HIPAA Marketing Restrictions
- `medicare_marketing_guidelines` — Medicare Marketing Guidelines (MCMG)
- `price_transparency` — Price Transparency (Hospital & Insurance)
- `state_consumer_protection_deceptive_practices` — State Consumer Protection / Deceptive Practices
- `tcpa` — TCPA

### Medical Device Safety (`medical_devices`) — `healthcare:devices`

7 keys:

- `equipment_maintenance_testing` — Equipment Maintenance & Testing
- `fda_medical_device_reporting` — FDA Medical Device Reporting (21 CFR Part 803)
- `fda_recalls_safety_communications` — FDA Recalls & Safety Communications
- `medical_device_tracking` — Medical Device Tracking (21 CFR Part 821)
- `radiationemitting_device_standards` — Radiation-Emitting Device Standards (21 CFR Subchapter J)
- `safe_medical_devices_act` — Safe Medical Devices Act (SMDA)
- `unique_device_identification` — Unique Device Identification (UDI)

### Payer Relations (`payer_relations`) — `healthcare:managed_care`

9 keys:

- `aca_insurance_market_reforms` — ACA Insurance Market Reforms
- `cvo_standards` — CVO Standards
- `erisa` — ERISA
- `medicaid_managed_care` — Medicaid Managed Care (42 CFR Part 438)
- `medicare_advantage_compliance` — Medicare Advantage Compliance (42 CFR Part 422)
- `mental_health_parity` — Mental Health Parity (MHPAEA)
- `network_adequacy_standards` — Network Adequacy Standards
- `prior_authorization_requirements` — Prior Authorization Requirements
- `state_insurance_regulation` — State Insurance Regulation

### Pediatric & Vulnerable Populations (`pediatric_vulnerable`) — `healthcare:pediatric`

8 keys:

- `adult_protective_services_reporting` — Adult Protective Services Reporting
- `child_abuse_neglect_reporting` — Child Abuse & Neglect Reporting (CAPTA)
- `cms_nursing_home_minimum_staffing_rule` — CMS Nursing Home Minimum Staffing Rule (2024)
- `disability_rights` — Disability Rights (Section 504 / ADA)
- `elder_abuse_prevention` — Elder Abuse Prevention (Elder Justice Act)
- `guardianship_surrogate_decisionmaking` — Guardianship & Surrogate Decision-Making
- `immigrant_undocumented_patient_protections` — Immigrant & Undocumented Patient Protections
- `nursing_home_reform_act` — Nursing Home Reform Act (OBRA 1987)

### Pharmacy & Controlled Substances (`pharmacy_drugs`) — `healthcare:pharmacy`

10 keys:

- `340b_drug_pricing_program` — 340B Drug Pricing Program (42 U.S.C. § 256b)
- `dea_registration_controlled_substances` — DEA Registration & Controlled Substances (21 CFR 1301–1321)
- `drug_diversion_prevention` — Drug Diversion Prevention
- `drug_supply_chain_security_act` — Drug Supply Chain Security Act (DSCSA)
- `fda_rems_programs` — FDA REMS Programs
- `medication_error_reporting` — Medication Error Reporting
- `pharmaceutical_waste_disposal` — Pharmaceutical Waste Disposal
- `prescription_drug_monitoring_programs` — Prescription Drug Monitoring Programs (PDMPs)
- `state_pharmacy_practice_acts` — State Pharmacy Practice Acts
- `usp_compounding_standards` — USP Compounding Standards (<795>, <797>, <800>)

### Quality Reporting (`quality_reporting`) — `healthcare`

12 keys:

- `advanced_apms` — Advanced APMs
- `cms_star_ratings` — CMS Star Ratings
- `hac_reduction_program` — HAC Reduction Program
- `hedis_measures` — HEDIS Measures
- `home_health_quality_reporting` — Home Health Quality Reporting
- `hospital_iqr_program` — Hospital IQR Program
- `hospital_oqr_program` — Hospital OQR Program
- `hospital_readmissions_reduction_program` — Hospital Readmissions Reduction Program
- `hospital_vbp_program` — Hospital VBP Program
- `mips_qpp` — MIPS / QPP
- `snf_quality_reporting_program` — SNF Quality Reporting Program
- `state_quality_reporting_mandates` — State Quality Reporting Mandates

### Records Retention (`records_retention`) — `healthcare`

7 keys:

- `baa_requirements` — BAA Requirements
- `hipaa_documentation_requirements` — HIPAA Documentation Requirements
- `legal_hold_litigation_preservation` — Legal Hold & Litigation Preservation
- `medical_records_content_standards` — Medical Records Content Standards
- `medical_records_retention` — Medical Records Retention
- `patient_access_to_records` — Patient Access to Records (HIPAA Right of Access)
- `state_medical_records_laws` — State Medical Records Laws

### Reproductive & Behavioral Health (`reproductive_behavioral`) — `healthcare:behavioral_health`

10 keys:

- `42_cfr_part_2_reproductive_behavioral` — 42 CFR Part 2 (SUD Records — Detailed)
- `confidentiality_of_minor_health_records` — Confidentiality of Minor Health Records
- `conscience_religious_exemption_laws` — Conscience & Religious Exemption Laws
- `hivaids_testing_disclosure_laws` — HIV/AIDS Testing & Disclosure Laws
- `postdobbs_state_abortion_laws` — Post-Dobbs State Abortion Laws
- `state_mental_health_commitment_laws` — State Mental Health Commitment Laws
- `state_reproductive_health_privacy_laws` — State Reproductive Health Privacy Laws
- `state_sud_treatment_regulations` — State SUD Treatment Regulations
- `title_x_family_planning` — Title X Family Planning
- `transgender_healthcare_regulations` — Transgender Healthcare Regulations

### Tax-Exempt Compliance (`tax_exempt`) — `healthcare:nonprofit`

5 keys:

- `irc_501_for_charitable_hospitals` — IRC §501(r) for Charitable Hospitals
- `irs_form_990_schedule_h` — IRS Form 990 Schedule H
- `state_community_benefit_requirements` — State Community Benefit Requirements
- `state_property_tax_exemptions` — State Property Tax Exemptions
- `ubit` — UBIT (Unrelated Business Income Tax)

### Telehealth & Digital Health (`telehealth`) — `healthcare:telehealth`

10 keys:

- `aiml_in_clinical_decision_support` — AI/ML in Clinical Decision Support
- `fda_digital_health_samd` — FDA Digital Health / SaMD
- `interstate_medical_licensure_compact` — Interstate Medical Licensure Compact (IMLC)
- `medicare_telehealth_coverage` — Medicare Telehealth Coverage (§1834(m))
- `nurse_licensure_compact` — Nurse Licensure Compact (NLC)
- `psypact` — PSYPACT
- `remote_patient_monitoring` — Remote Patient Monitoring
- `ryan_haight_act` — Ryan Haight Act (Online Controlled Substance Prescribing)
- `state_telehealth_parity_laws` — State Telehealth Parity Laws
- `state_telehealth_practice_standards` — State Telehealth Practice Standards

### Transplant & Organ Procurement (`transplant_organ`) — `healthcare:transplant`

5 keys:

- `cms_cops_for_transplant_centers` — CMS CoPs for Transplant Centers (42 CFR 482.68–104)
- `national_organ_transplant_act` — National Organ Transplant Act (NOTA)
- `opo_conditions_for_coverage` — OPO Conditions for Coverage
- `optnunos_policies_bylaws` — OPTN/UNOS Policies & Bylaws
- `tissue_banking` — Tissue Banking (FDA 21 CFR Parts 1270, 1271)

