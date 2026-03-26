# Leftover Research Keys — Not Mapped to Existing Canonical Keys

These research keys don't have a clear match in the current `EXPECTED_REGULATION_KEYS` registry. Review each to decide: create a new canonical key, or drop it.

---

## emerging_regulatory

| Research Key | States | Title | Notes |
|---|---|---|---|
| `az_ai_oversight_committee` | AZ | Arizona AI Steering Committee for State Policy Framework | Governance/advisory body, not a binding regulation |
| `ca_emerging_regulatory_sb_942_ai_transparency` | CA | California AI Transparency Act — Watermarking and Disclosure | AI content watermarking — new concept, not covered by `ai_algorithmic_decisionmaking` |
| `ca_emerging_regulatory_sb_243_ai_chatbots` | CA | AI Companion Chatbot Safety Requirements | AI chatbot-specific safety rules |
| `or_ai_nurse_title_ban_hb2748` | OR | Prohibition on AI Use of Nursing Titles (HB 2748) | AI professional title protection — very specific |
| `or_ai_chatbot_regulation_sb1546` | OR | Consumer-Facing Interactive AI Regulation (SB 1546) | AI chatbot regulation with private right of action |
| `or_ag_ai_guidance_2024` | OR | Oregon Attorney General AI Guidance for Businesses | Guidance only, not law |
| `ut_mental_health_chatbot_regulation` | UT | AI Mental Health Chatbot Disclosure, Privacy, and Advertising Requirements | Mental health chatbot regulation |
| `wa_hb2155_nursing_ai_title_protection` | WA | Nursing Title Protection from AI Systems (HB 2155) | Same concept as OR HB 2748 — AI title protection |
| `wa_hb2225_ai_companion_regulation` | WA | AI Companion Chatbot Mental Health Regulation (HB 2225) | Same concept as CA SB 243, UT chatbot reg |

**Possible new canonical keys:**
- `ai_transparency_disclosure` — covers CA SB 942, AI watermarking/disclosure requirements
- `ai_chatbot_regulation` — covers CA SB 243, OR SB 1546, UT chatbot reg, WA HB 2225
- `ai_professional_title_protection` — covers OR HB 2748, WA HB 2155
- Drop `az_ai_oversight_committee` and `or_ag_ai_guidance_2024` (non-binding)

## health_it

| Research Key | States | Title | Notes |
|---|---|---|---|
| `tx_sensitive_test_result_delay` | TX | Texas 72-Hour Delay for Sensitive Test Results (S.B. 922) | Patient access delay for sensitive results — unique concept |

**Possible new canonical key:**
- `patient_result_access_delay` — or map to `state_hie_requirements` as a stretch

## marketing_comms

| Research Key | States | Title | Notes |
|---|---|---|---|
| `nv_geofencing_healthcare_prohibition` | NV | Geofencing Prohibition Near Healthcare Providers — SB 370 | Location-based marketing near healthcare facilities |
| `ny_healthcare_fee_splitting` | NY | NY Anti-Kickback and Fee-Splitting Laws | Fee-splitting/kickback — different from advertising |
| `texas_patient_solicitation_act` | TX | Texas Patient Solicitation Act | Patient solicitation — different from general advertising |
| `tx_patient_solicitation_act` | TX | Texas Patient Solicitation Act | Duplicate of above (two TX files) |
| `wa_anti_kickback_fee_splitting` | WA | WA Anti-Rebate and Fee-Splitting Laws | Same concept as NY fee-splitting |
| `wa_my_health_my_data_act` | WA | WA My Health My Data Act (MHMD) | This is really a privacy/cybersecurity law, not marketing |

**Possible new canonical keys:**
- `state_anti_kickback_fee_splitting` — covers NY and WA fee-splitting laws
- `state_patient_solicitation` — covers TX patient solicitation
- `geofencing_healthcare_prohibition` — covers NV (and WA MHMD has a geofencing component too)
- Move `wa_my_health_my_data_act` to cybersecurity → `state_cybersecurity_requirements`

## tax_exempt

| Research Key | States | Title | Notes |
|---|---|---|---|
| `hi_get_exemption_medical_services` | HI | General Excise Tax Exemption for Medical Services (SB 1035 / Act 2024) | Sales/excise tax exemption for medical services — different from property tax or community benefit |
| `ny_charitable_registration` | NY | NY Charitable Organization Registration | Charitable org registration — different from hospital tax exemption |

**Possible new canonical keys:**
- `state_healthcare_sales_tax_exemption` — covers HI GET exemption
- `state_charitable_registration` — covers NY charitable org registration

## transplant_organ

| Research Key | States | Title | Notes |
|---|---|---|---|
| `ca_transplant_organ_ab_1268_tax_return` | CA | Organ Donor Registration via State Tax Returns | Donor registration via tax filing — novel channel |
| `co_living_organ_donor_hb_24_1132` | CO | Support for Living Organ Donors Act (HB 24-1132) | Living donor employment protections + tax credits |
| `nv_organ_sale_prohibition` | NV | Prohibition on Sale of Human Organs — NRS 201.460 | Maps to `national_organ_transplant_act` (state equivalent)? |
| `ny_bone_marrow_donation_leave` | NY | NY Labor Law § 202-a (Bone Marrow Donation) | Leave law — could be under `leave` category instead |
| `or_organ_donation_marketing_restrictions` | OR | Advertising and Marketing Prohibitions Related to Human Remains (ORS 97.946) | Marketing restriction for organ donation |
| `ut_living_organ_donor_protections` | UT | Living Organ Donor Insurance Nondiscrimination and Tax Credits | Same concept as CO — living donor protections |

**Possible new canonical keys:**
- `living_organ_donor_protections` — covers CO HB 24-1132 and UT protections
- `state_donor_registration_channels` — covers CA tax return registration
- Map `nv_organ_sale_prohibition` → `national_organ_transplant_act` (state-level mirror)
- Move `ny_bone_marrow_donation_leave` → `leave` category as `bone_marrow_donor_leave`
- Map `or_organ_donation_marketing_restrictions` → marketing_comms or drop

## telehealth

| Research Key | States | Title | Notes |
|---|---|---|---|
| `or_telehealth_cultural_linguistic_sb822` | OR | Culturally and Linguistically Appropriate Telehealth Requirements (SB 822, 2025) | Telehealth + language access intersection — unique |

**Possible new canonical key:**
- `state_telehealth_cultural_linguistic` — or map to `state_language_access_laws`

---

## Summary

| Category | Leftover Count | Suggested New Keys |
|---|---|---|
| emerging_regulatory | 9 | 3 (ai_transparency_disclosure, ai_chatbot_regulation, ai_professional_title_protection) + drop 2 non-binding |
| health_it | 1 | 0-1 (stretch to state_hie_requirements or new) |
| marketing_comms | 6 | 2-3 (anti_kickback, patient_solicitation, geofencing) + reclassify 1 |
| tax_exempt | 2 | 1-2 (sales tax exemption, charitable registration) |
| transplant_organ | 6 | 1-2 (living_donor_protections, donor_registration_channels) + reclassify/remap 3 |
| telehealth | 1 | 0-1 (remap to language_access or new) |
| **Total** | **25** | **~8-12 new canonical keys needed** |
