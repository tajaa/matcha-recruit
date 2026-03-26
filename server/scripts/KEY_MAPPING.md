# Research Key → Canonical Key Mapping

These research keys from `*_healthcare_gaps.md` files map to **existing** canonical keys in `EXPECTED_REGULATION_KEYS`. The ingestion script should remap `regulation_key` to the canonical key before inserting.

---

## telehealth

| Research Key | States | Canonical Key | Rationale |
|---|---|---|---|
| `az_telehealth_definition` | AZ | `state_telehealth_practice_standards` | Defines telehealth practice scope — that's what practice standards covers |
| `az_telehealth_insurance_parity` | AZ | `state_telehealth_parity_laws` | Insurance coverage parity |
| `az_telehealth_interstate_registration` | AZ | `interstate_medical_licensure_compact` | Interstate provider registration |
| `ca_telehealth_ab_744_payment_parity` | CA | `state_telehealth_parity_laws` | Commercial payment parity |
| `ca_telehealth_bpc_2290_5` | CA | `state_telehealth_practice_standards` | Informed consent is a core practice standard |
| `ca_telehealth_licensure_requirement` | CA | `state_telehealth_practice_standards` | Licensure requirement for telehealth practice |
| `ca_telehealth_sb_184_medi_cal_parity` | CA | `state_telehealth_parity_laws` | Medi-Cal payment parity |
| `co_telehealth_parity_crs_10_16_123` | CO | `state_telehealth_parity_laws` | Payment parity |
| `co_telehealth_oos_registration_sb_24_141` | CO | `interstate_medical_licensure_compact` | Out-of-state provider registration |
| `co_telehealth_medicaid_10_ccr_2505_10_8095` | CO | `state_telehealth_parity_laws` | Medicaid telehealth reimbursement parity |
| `hi_telehealth_practice` | HI | `state_telehealth_practice_standards` | Practice standards |
| `hi_telehealth_insurance_parity` | HI | `state_telehealth_parity_laws` | Insurance parity |
| `hi_telehealth_audio_only` | HI | `state_telehealth_parity_laws` | Audio-only modality coverage rules |
| `hi_telehealth_controlled_substances` | HI | `ryan_haight_act` | In-person requirement for controlled substances |
| `id_telehealth_virtual_care_access_act` | ID | `state_telehealth_practice_standards` | Comprehensive practice framework |
| `id_telehealth_prescribing_restrictions` | ID | `state_telehealth_practice_standards` | Prescribing is a practice standard |
| `id_telehealth_informed_consent` | ID | `state_telehealth_practice_standards` | Consent is a practice standard |
| `id_telehealth_continuity_of_care` | ID | `state_telehealth_practice_standards` | Continuity is a practice standard |
| `id_telehealth_interstate_mental_health` | ID | `psypact` | Interstate mental health telehealth |
| `nv_telehealth_licensure` | NV | `state_telehealth_practice_standards` | Licensure requirement |
| `nv_telehealth_payment_parity` | NV | `state_telehealth_parity_laws` | Payment parity |
| `nv_telehealth_patient_relationship` | NV | `state_telehealth_practice_standards` | Patient relationship establishment |
| `or_telehealth_payment_parity` | OR | `state_telehealth_parity_laws` | Payment parity |
| `or_telemedicine_cross_state_license` | OR | `interstate_medical_licensure_compact` | Cross-state licensure |
| `ut_telehealth_scope_prescribing` | UT | `state_telehealth_practice_standards` | Scope and prescribing standards |
| `ut_telehealth_coverage_parity` | UT | `state_telehealth_parity_laws` | Coverage parity |
| `wa_telehealth_audio_only_coverage` | WA | `state_telehealth_parity_laws` | Audio-only coverage mandate |

## cybersecurity

| Research Key | States | Canonical Key | Rationale |
|---|---|---|---|
| `ca_cybersecurity_sb_446_breach_notification` | CA | `state_data_breach_notification_laws` | Breach notification deadline |
| `ca_cybersecurity_cmia_civil_code_56` | CA | `state_cybersecurity_requirements` | State medical info confidentiality law |
| `ca_cybersecurity_ccpa_audit_requirements` | CA | `state_cybersecurity_requirements` | State privacy/cybersecurity audit requirement |
| `co_breach_notification_crs_6_1_716` | CO | `state_data_breach_notification_laws` | Breach notification |
| `co_privacy_act_crs_6_1_1301` | CO | `state_cybersecurity_requirements` | State privacy act with health data protections |
| `or_breach_notification_ocipa` | OR | `state_data_breach_notification_laws` | Breach notification |
| `or_consumer_privacy_act_health_data` | OR | `state_cybersecurity_requirements` | State consumer privacy act |
| `ut_breach_notification_13_44` | UT | `state_data_breach_notification_laws` | Breach notification |
| `ut_ucpa_sensitive_health_data` | UT | `state_cybersecurity_requirements` | State consumer privacy act |
| `wa_breach_notification_health_data` | WA | `state_data_breach_notification_laws` | Breach notification |
| `wa_mhmda_geofencing_enforcement` | WA | `state_cybersecurity_requirements` | My Health My Data Act enforcement provision |
| `nv_consumer_health_data_privacy` | NV | `state_cybersecurity_requirements` | Consumer health data privacy act |
| `nv_sb220_data_sale_optout` | NV | `state_cybersecurity_requirements` | Data sale opt-out — state privacy requirement |
| `hi_insurance_data_security` | HI | `state_cybersecurity_requirements` | Insurance data security law |
| `id_personal_information_definition` | ID | `state_data_breach_notification_laws` | Expands PI definition for breach notification |
| `az_data_breach_penalties` | AZ | `state_data_breach_notification_laws` | Enforcement/penalties for breach notification |
| `texas_medical_records_privacy_act` | TX | `state_cybersecurity_requirements` | State medical records privacy |
| `texas_sb_1188_ehr_storage` | TX | `state_cybersecurity_requirements` | EHR storage security |

## language_access

| Research Key | States | Canonical Key | Rationale |
|---|---|---|---|
| `ca_language_access_hsc_1259` | CA | `state_language_access_laws` | Hospital interpreter requirements |
| `ca_language_access_dymally_alatorre_gov_7290` | CA | `state_language_access_laws` | Bilingual services act |
| `ca_language_access_sb_1078_office` | CA | `state_language_access_laws` | State office of language access |
| `co_language_access_facility_licensure_6_ccr_1011_1` | CO | `state_language_access_laws` | Facility licensure tied to language services |
| `co_language_access_assessment_hb_25_1153` | CO | `state_language_access_laws` | Statewide language access assessment |
| `co_language_access_workers_comp_interpreter` | CO | `state_language_access_laws` | Workers' comp interpreter reimbursement |
| `hi_language_access_law` | HI | `state_language_access_laws` | State language access law |
| `hi_sign_language_healthcare` | HI | `state_language_access_laws` | Sign language interpreter requirements |
| `id_sign_language_interpreter_license` | ID | `state_language_access_laws` | Sign language interpreter licensure |
| `nv_healthcare_language_access` | NV | `state_language_access_laws` | Healthcare language assistance |
| `or_healthcare_interpreter_certification` | OR | `state_language_access_laws` | Interpreter certification |
| `or_interpretation_service_company` | OR | `state_language_access_laws` | Interpretation service registry |
| `ut_medical_language_interpreter_act` | UT | `state_language_access_laws` | Interpreter certification act |
| `wa_healthcare_interpreter_certification` | WA | `state_language_access_laws` | Interpreter certification |
| `wa_medicaid_interpreter_services` | WA | `state_language_access_laws` | Medicaid interpreter services |
| `az_ahcccs_language_access` | AZ | `state_language_access_laws` | Medicaid language access plan |
| `az_sign_language_interpreter_licensure` | AZ | `state_language_access_laws` | Sign language interpreter licensure |

## emerging_regulatory

| Research Key | States | Canonical Key | Rationale |
|---|---|---|---|
| `az_ai_healthcare_claims_review` | AZ | `ai_algorithmic_decisionmaking` | AI in claims decision-making |
| `ca_emerging_regulatory_ab_489_ai_healthcare` | CA | `ai_algorithmic_decisionmaking` | AI deceptive representations in healthcare |
| `ca_emerging_regulatory_ccpa_admt` | CA | `ai_algorithmic_decisionmaking` | Automated decision-making technology |
| `co_ai_act_sb_24_205` | CO | `ai_algorithmic_decisionmaking` | Comprehensive AI act — algorithmic decision-making |
| `nv_ai_healthcare_disclosure` | NV | `ai_algorithmic_decisionmaking` | Generative AI disclosure in medical comms |
| `nv_ai_mental_health_prohibition` | NV | `ai_algorithmic_decisionmaking` | AI prohibition in mental health — algorithmic decision |
| `ut_ai_policy_act_healthcare_disclosure` | UT | `ai_algorithmic_decisionmaking` | AI disclosure for healthcare occupations |
| `wa_ai_task_force_healthcare_prior_auth` | WA | `ai_algorithmic_decisionmaking` | AI in prior authorization decisions |
| `id_ai_innovation_protection` | ID | `ai_algorithmic_decisionmaking` | AI regulation limitations (deregulatory) |

## health_it

| Research Key | States | Canonical Key | Rationale |
|---|---|---|---|
| `az_hie_opt_out_requirements` | AZ | `state_hie_requirements` | HIE opt-out/privacy |
| `az_hie_interoperability_standards` | AZ | `state_hie_requirements` | HIE interoperability standards |
| `ca_health_it_ab_133_dxf` | CA | `state_hie_requirements` | Statewide data exchange framework |
| `ca_health_it_ab_352_sensitive_services` | CA | `state_hie_requirements` | HIE privacy for sensitive services |
| `co_hie_opt_out_consent_corhio` | CO | `state_hie_requirements` | HIE opt-out consent |
| `hi_health_data_exchange_framework` | HI | `state_hie_requirements` | State health data exchange |
| `hi_hie_designation` | HI | `state_hie_requirements` | State-designated HIE |
| `id_health_data_exchange_participation` | ID | `state_hie_requirements` | HIE governance and participation |
| `nv_hie_opt_in_consent` | NV | `state_hie_requirements` | HIE opt-in consent |
| `or_hitoc_hie_governance` | OR | `state_hie_requirements` | HIE governance council |
| `ut_chie_medicaid_enrollment` | UT | `state_hie_requirements` | Mandatory Medicaid HIE enrollment |
| `wa_my_health_my_data_act` | WA | `state_hie_requirements` | Consumer health data regulation |
| `co_pdmp_mandatory_check_ehr_integration` | CO | `eprescribing_for_controlled_substances` | PDMP mandatory check with EHR integration |
| `wa_pmp_ehr_integration_mandate` | WA | `eprescribing_for_controlled_substances` | PMP EHR integration mandate |
| `texas_ehr_data_localization_and_ai` | TX | `state_hie_requirements` | EHR data localization |
| `tx_ehr_data_localization_and_security` | TX | `state_hie_requirements` | EHR data localization (duplicate) |

## marketing_comms

| Research Key | States | Canonical Key | Rationale |
|---|---|---|---|
| `az_medical_advertising_rules` | AZ | `state_consumer_protection_deceptive_practices` | Medical advertising regulations |
| `az_health_insurance_advertising` | AZ | `state_consumer_protection_deceptive_practices` | Insurance advertising standards |
| `ca_marketing_comms_bpc_651` | CA | `state_consumer_protection_deceptive_practices` | False/misleading claims in healthcare advertising |
| `ca_marketing_comms_hsc_119402` | CA | `state_consumer_protection_deceptive_practices` | Drug marketing compliance program |
| `co_medical_advertising_crs_12_240_121_rule_290` | CO | `state_consumer_protection_deceptive_practices` | Medical advertising regulation |
| `co_pharma_marketing_hb_19_1131` | CO | `state_consumer_protection_deceptive_practices` | Pharma marketing transparency |
| `hi_false_advertising_drugs_devices` | HI | `state_consumer_protection_deceptive_practices` | False advertising of drugs |
| `hi_deceptive_trade_practices` | HI | `state_consumer_protection_deceptive_practices` | Deceptive trade practices act |
| `id_physician_advertising_discipline` | ID | `state_consumer_protection_deceptive_practices` | Unethical advertising discipline |
| `nv_healthcare_advertising_disclosure` | NV | `state_consumer_protection_deceptive_practices` | Advertising licensure disclosure |
| `or_medical_advertising_false_claims` | OR | `state_consumer_protection_deceptive_practices` | False medical advertising |
| `or_insurance_marketing_restrictions` | OR | `state_consumer_protection_deceptive_practices` | Insurance marketing restrictions |
| `ut_cosmetic_medical_advertising` | UT | `state_consumer_protection_deceptive_practices` | Truth in advertising for cosmetic procedures |
| `wa_controlled_substance_advertising_ban` | WA | `state_consumer_protection_deceptive_practices` | Controlled substance advertising prohibition |
| `wa_health_plan_marketing_antidiscrimination` | WA | `state_consumer_protection_deceptive_practices` | Health plan marketing anti-discrimination |
| `ny_healthcare_advertising` | NY | `state_consumer_protection_deceptive_practices` | Healthcare advertising |
| `texas_healthcare_advertising_rules` | TX | `state_consumer_protection_deceptive_practices` | Healthcare advertising |
| `tx_medical_advertising_rules` | TX | `state_consumer_protection_deceptive_practices` | Medical board advertising rules |

## tax_exempt

| Research Key | States | Canonical Key | Rationale |
|---|---|---|---|
| `ca_tax_exempt_sb_697_community_benefit` | CA | `state_community_benefit_requirements` | Community benefit plan requirements |
| `ca_tax_exempt_ab_204_reporting_penalties` | CA | `state_community_benefit_requirements` | Community benefit reporting/enforcement |
| `co_hospital_community_benefit_hb_19_1320` | CO | `state_community_benefit_requirements` | Community benefit accountability |
| `nv_nonprofit_hospital_community_benefit` | NV | `state_community_benefit_requirements` | Community benefit reporting |
| `or_hospital_community_benefit_hb3076` | OR | `state_community_benefit_requirements` | Community benefit reporting |
| `or_hospital_charity_care_sliding_scale` | OR | `state_community_benefit_requirements` | Charity care sliding scale |
| `id_hospital_property_tax_exemption_community_benefit` | ID | `state_property_tax_exemptions` | Property tax exemption with community benefit |
| `hi_nonprofit_hospital_tax_exemption` | HI | `state_property_tax_exemptions` | Hospital tax exemption |
| `az_qualifying_healthcare_org_exemption` | AZ | `state_property_tax_exemptions` | Healthcare org tax exemption |
| `ut_nonprofit_hospital_tax_exempt_charity_care` | UT | `state_property_tax_exemptions` | Hospital property tax exemption |
| `wa_charity_care_expanded_fpl_thresholds` | WA | `state_community_benefit_requirements` | Charity care FPL thresholds |

## transplant_organ

| Research Key | States | Canonical Key | Rationale |
|---|---|---|---|
| `az_revised_uniform_anatomical_gift_act` | AZ | `optnunos_policies_bylaws` | State UAGA adoption |
| `ca_transplant_organ_hsc_7150_uaga` | CA | `optnunos_policies_bylaws` | State UAGA adoption |
| `co_anatomical_gift_act_crs_15_19` | CO | `optnunos_policies_bylaws` | State UAGA adoption |
| `hi_anatomical_gift_act` | HI | `optnunos_policies_bylaws` | State UAGA adoption |
| `nv_anatomical_gift_act` | NV | `optnunos_policies_bylaws` | State UAGA adoption |
| `or_anatomical_gift_act` | OR | `optnunos_policies_bylaws` | State UAGA adoption |
| `ut_anatomical_gift_act` | UT | `optnunos_policies_bylaws` | State UAGA adoption |
| `wa_anatomical_gift_act` | WA | `optnunos_policies_bylaws` | State UAGA adoption |
| `ny_anatomical_gift_act` | NY | `optnunos_policies_bylaws` | State UAGA adoption |
| `tx_revised_uniform_anatomical_gift_act` | TX | `optnunos_policies_bylaws` | State UAGA adoption |
| `id_anatomical_gift_hospital_procurement` | ID | `opo_conditions_for_coverage` | Hospital-OPO procurement agreements |
| `az_donor_registry_requirements` | AZ | `optnunos_policies_bylaws` | Donor registry establishment |
| `id_donor_registry` | ID | `optnunos_policies_bylaws` | Donor registry |
| `ca_transplant_organ_dmv_registry_integration` | CA | `optnunos_policies_bylaws` | DMV donor registration |
| `wa_donor_registry_dol_integration` | WA | `optnunos_policies_bylaws` | DOL donor registry integration |
