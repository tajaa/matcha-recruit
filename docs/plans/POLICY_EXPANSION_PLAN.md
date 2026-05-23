4# Policy Registry Expansion Plan

Current state: 7 groups, 59 categories, 483 keys, 396 seeded to DB.
Target state: 10+ groups, ~80 categories, ~750+ keys, full penalty/risk metadata, international frameworks, dependency graph.

---

## Tier 1: New Key Definitions & Categories

Pure data work — define in `compliance_registry.py`, seed to `regulation_key_definitions` and `compliance_categories`. No schema changes.

### 1.1 FDA Pre/Post-Market Lifecycle (NEW CATEGORY: `fda_lifecycle`)

**Group**: `life_sciences`
**Why**: Any company developing drugs, biologics, or combination products needs to track the full FDA submission-to-post-market pipeline. Current registry covers GMP and clinical trials but nothing on the approval and surveillance side.

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| `nda_bla_submission` | NDA/BLA Submission Requirements | FDA / CDER / CBER | Low/None |
| `anda_generic_pathway` | ANDA Generic Drug Pathway (Hatch-Waxman) | FDA / CDER | Low/None |
| `fda_breakthrough_accelerated` | Breakthrough / Fast Track / Accelerated Approval | FDA | Low/None |
| `fda_priority_review` | Priority Review & Voucher Programs | FDA | Low/None |
| `post_market_surveillance_faers` | Post-Market Surveillance (FAERS / MedWatch) | FDA | Low/None |
| `pharmacovigilance_safety_reporting` | Pharmacovigilance & Safety Reporting (ICSRs, PSURs) | FDA / EMA | Low/None |
| `rems_lifecycle` | REMS (Risk Evaluation & Mitigation Strategies) | FDA | Low/None |
| `fda_483_observations` | FDA 483 Observations & CAPA Management | FDA | Low/None |
| `product_labeling_pi_medication_guide` | Product Labeling (PI, Medication Guides, Black Box) | FDA | Low/None |
| `pediatric_study_requirements` | Pediatric Study Requirements (PREA / BPCA) | FDA | Low/None |
| `orphan_drug_exclusivity` | Orphan Drug Designation & Exclusivity | FDA | Low/None |
| `patent_exclusivity_orange_book` | Patent/Exclusivity Listings (Orange Book / Purple Book) | FDA | Low/None |

### 1.2 Medical Device Lifecycle (EXPAND `medical_devices`)

**Why**: Current `medical_devices` has 7 keys focused on reporting/tracking. Missing the entire pre-market classification and design control lifecycle.

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| `510k_pma_de_novo` | 510(k) / PMA / De Novo Classification Pathways | FDA / CDRH | Low/None |
| `design_controls_21cfr820` | Design Controls (21 CFR 820 Subpart C) | FDA | Low/None |
| `device_master_record` | Device Master Record (DMR) & Device History Record (DHR) | FDA | Low/None |
| `unique_device_identification` | Unique Device Identification (UDI) System | FDA | Low/None |
| `device_establishment_registration` | Device Establishment Registration & Listing | FDA | Low/None |
| `software_as_medical_device` | Software as a Medical Device (SaMD) — IEC 62304 | FDA / IEC | Low/None |
| `cybersecurity_medical_devices` | Cybersecurity for Medical Devices (FDA Guidance + PATCH Act) | FDA | Low/None |
| `human_factors_usability` | Human Factors / Usability Engineering (IEC 62366) | FDA | Low/None |

### 1.3 Quality Management Systems (NEW CATEGORY: `quality_systems`)

**Group**: `manufacturing`
**Why**: ISO certifications are contractual requirements for most healthcare customers and required for market access in many countries.

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| `iso_13485_medical_devices` | ISO 13485 — Medical Device QMS | Notified Bodies / Registrars | Low/None |
| `iso_9001_general_qms` | ISO 9001 — General Quality Management System | Registrars | Low/None |
| `iso_15189_clinical_labs` | ISO 15189 — Clinical Laboratory QMS | Accreditation Bodies | Low/None |
| `iso_14001_environmental` | ISO 14001 — Environmental Management System | Registrars | Low/None |
| `iso_45001_ohs` | ISO 45001 — Occupational Health & Safety | Registrars | Low/None |
| `iso_27001_information_security` | ISO 27001 — Information Security Management | Registrars | Low/None |
| `clia_lab_certification` | CLIA Laboratory Certification | CMS / CDC | Moderate |
| `cap_accreditation` | CAP (College of American Pathologists) Accreditation | CAP | Low/None |
| `joint_commission_accreditation` | Joint Commission Accreditation (TJC) | The Joint Commission | Low/None |

### 1.4 Cybersecurity & Data Protection (EXPAND `cybersecurity`)

**Why**: Current 9 keys are heavily HIPAA-focused. Missing broader frameworks that healthcare orgs also face.

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| `nist_csf_implementation` | NIST Cybersecurity Framework Implementation | NIST (voluntary) | Low/None |
| `soc2_type2_compliance` | SOC 2 Type II Compliance | AICPA / Auditors | Low/None |
| `gdpr_health_data` | GDPR — Health Data Processing (EU patients) | EU DPAs | Low/None |
| `fda_device_cybersecurity_guidance` | FDA Pre/Post-Market Cybersecurity Guidance (Devices) | FDA | Low/None |
| `patch_act_medical_devices` | PATCH Act — Medical Device Cybersecurity | FDA / Congress | Low/None |
| `state_consumer_privacy_acts` | State Consumer Privacy Acts (CCPA, CPA, CTDPA, etc.) | State AGs | High |
| `incident_response_plan` | Cybersecurity Incident Response Plan Requirements | Multiple | Moderate |
| `third_party_risk_management` | Third-Party / Vendor Risk Management | Multiple | Moderate |

### 1.5 Reimbursement & Value-Based Care (NEW CATEGORY: `reimbursement_vbc`)

**Group**: `healthcare`
**Why**: Any provider organization needs to track CMS quality programs, payment models, and reporting obligations that directly affect revenue.

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| `macra_mips_reporting` | MACRA / MIPS Quality Reporting | CMS | Low/None |
| `apm_participation` | Alternative Payment Model (APM) Participation | CMS | Low/None |
| `bundled_payment_compliance` | Bundled Payment Program Compliance (BPCI-A) | CMS | Low/None |
| `cms_star_ratings` | CMS Star Ratings Compliance (MA/Part D) | CMS | Low/None |
| `hedis_quality_measures` | HEDIS Quality Measures Compliance | NCQA | Low/None |
| `value_based_contract_requirements` | Value-Based Contract Requirements | CMS / Payers | Moderate |
| `drg_coding_compliance` | DRG/CPT Coding Compliance & Auditing | CMS / OIG | Low/None |
| `price_transparency_rule` | Hospital Price Transparency Rule | CMS | Low/None |
| `no_surprises_act` | No Surprises Act Compliance | CMS / State DOIs | Moderate |
| `good_faith_estimates` | Good Faith Estimates (Uninsured/Self-Pay) | CMS | Low/None |

### 1.6 Environmental Health & Safety Depth (EXPAND `environmental_safety` + `environmental_compliance`)

**Why**: Current keys are thin. Missing major EPA programs that carry significant penalties.

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| `tsca_toxic_substances` | TSCA — Toxic Substances Control Act | EPA | Moderate |
| `cercla_superfund_liability` | CERCLA / Superfund Liability | EPA | Moderate |
| `clean_air_act_title_v` | Clean Air Act Title V Permitting | EPA / State | High |
| `epa_risk_management_program` | EPA Risk Management Program (RMP) — 40 CFR 68 | EPA | Moderate |
| `epcra_tri_reporting` | EPCRA / TRI (Toxics Release Inventory) Reporting | EPA | Moderate |
| `rcra_hazardous_waste` | RCRA Hazardous Waste Management | EPA / State | High |
| `clean_water_act_npdes` | Clean Water Act / NPDES Permitting | EPA / State | High |
| `spcc_oil_spill_prevention` | SPCC — Oil Spill Prevention, Control, Countermeasure | EPA | Low/None |

### 1.7 Supply Chain & Procurement Compliance (NEW CATEGORY: `supply_chain`)

**Group**: `manufacturing`
**Why**: Any manufacturer or large health system has supply chain compliance obligations around conflict minerals, chemical content, and forced labor prevention.

| Key | Name | Enforcing Agency | State Variance |
|-----|------|-----------------|----------------|
| `conflict_minerals_dodd_frank` | Conflict Minerals (Dodd-Frank §1502 / SEC) | SEC | Low/None |
| `reach_regulation` | REACH Chemical Registration (EU) | ECHA | Low/None |
| `rohs_directive` | RoHS Directive (Restriction of Hazardous Substances) | EU Member States | Low/None |
| `uyghur_forced_labor_prevention` | Uyghur Forced Labor Prevention Act (UFLPA) | CBP / DHS | Low/None |
| `supplier_qualification_audit` | Supplier Qualification & Audit Requirements | FDA / ISO | Moderate |
| `track_trace_serialization` | Track & Trace / Serialization (DSCSA integration) | FDA | Low/None |
| `gpp_green_procurement` | Green Procurement / Environmentally Preferable Purchasing | EPA / GSA | Low/None |
| `antibribery_fcpa_uk_bribery` | Anti-Bribery (FCPA / UK Bribery Act) | DOJ / SFO | Low/None |

**Tier 1 Total: ~65 new keys across 3 new categories + 3 expanded categories**

---

## Tier 2: International Regulatory Frameworks

New key definitions with `applicable_countries` scoping. Some need new categories.

### 2.1 EU Medical Device / IVD Regulation (NEW CATEGORY: `eu_mdr_ivdr`)

**Group**: `medical_compliance`
**applicable_countries**: `['EU']` (or individual member states)

| Key | Name | Enforcing Agency |
|-----|------|-----------------|
| `eu_mdr_classification` | EU MDR Device Classification (Class I/IIa/IIb/III) | Notified Bodies |
| `eu_mdr_conformity_assessment` | EU MDR Conformity Assessment Procedures | Notified Bodies |
| `ce_marking_requirements` | CE Marking Requirements (Medical Devices) | EU Commission |
| `eu_ivdr_classification` | EU IVDR IVD Classification (A/B/C/D) | Notified Bodies |
| `eudamed_registration` | EUDAMED Database Registration | EU Commission |
| `eu_mdr_post_market_surveillance` | EU MDR Post-Market Surveillance (PMS/PMCF) | Competent Authorities |
| `eu_mdr_clinical_evaluation` | EU MDR Clinical Evaluation & Investigation | Notified Bodies |
| `eu_authorized_representative` | EU Authorized Representative Requirements | EU Commission |

### 2.2 International Drug Regulatory (EXPAND `fda_lifecycle` with country variants)

| Key | applicable_countries | Name | Agency |
|-----|---------------------|------|--------|
| `ema_marketing_authorization` | `['EU']` | EMA Marketing Authorization (Centralised/Decentralised) | EMA |
| `health_canada_drug_submission` | `['CA']` | Health Canada Drug Submission (NDS/ANDS) | Health Canada |
| `pmda_drug_approval` | `['JP']` | PMDA Drug Approval Process | PMDA (Japan) |
| `nmpa_drug_registration` | `['CN']` | NMPA Drug Registration | NMPA (China) |
| `tga_drug_registration` | `['AU']` | TGA Drug Registration | TGA (Australia) |
| `anvisa_drug_registration` | `['BR']` | ANVISA Drug Registration | ANVISA (Brazil) |
| `ich_ctd_format` | NULL (universal) | ICH CTD (Common Technical Document) Format | ICH |
| `ich_gcp_e6r2` | NULL (universal) | ICH GCP E6(R2) Good Clinical Practice | ICH |
| `ich_stability_testing` | NULL (universal) | ICH Q1 Stability Testing Guidelines | ICH |
| `ich_impurities` | NULL (universal) | ICH Q3 Impurities Guidelines | ICH |

### 2.3 International Data Protection

| Key | applicable_countries | Name | Agency |
|-----|---------------------|------|--------|
| `gdpr_full` | `['EU']` | GDPR — Full Regulation | EU DPAs |
| `uk_gdpr` | `['GB']` | UK GDPR (post-Brexit) | ICO |
| `pipeda` | `['CA']` | PIPEDA — Personal Information Protection (Canada) | OPC |
| `lgpd` | `['BR']` | LGPD — Lei Geral de Protecao de Dados (Brazil) | ANPD |
| `pdpa_singapore` | `['SG']` | PDPA — Personal Data Protection Act (Singapore) | PDPC |
| `appi_japan` | `['JP']` | APPI — Act on Protection of Personal Information (Japan) | PPC |
| `pipl_china` | `['CN']` | PIPL — Personal Information Protection Law (China) | CAC |

**Tier 2 Total: ~25 new keys across 1 new category + international variants**

---

## Tier 3: Structural & Schema Upgrades

### 3.1 Penalty & Risk Fields

Add to `regulation_key_definitions` table:

```sql
ALTER TABLE regulation_key_definitions ADD COLUMN IF NOT EXISTS
    penalty_min DECIMAL(12,2),          -- e.g., 100.00
    penalty_max DECIMAL(12,2),          -- e.g., 50000.00
    penalty_unit VARCHAR(30),           -- 'per_day', 'per_violation', 'per_incident', 'per_record', 'aggregate'
    penalty_notes TEXT,                 -- "Up to $1.9M/year for willful neglect (HIPAA Tier 4)"
    enforcement_frequency VARCHAR(20),  -- 'active', 'moderate', 'rare', 'complaint_driven'
    risk_severity VARCHAR(20),          -- 'critical', 'high', 'moderate', 'low'
    criminal_liability BOOLEAN DEFAULT false;  -- can violations result in criminal charges?
```

Also add to ORM model `RegulationKeyDefinition` and `database.py` init_db.

**Impact**: Enables triage views — "these 5 policies carry $50K/day penalties, those 20 are warning-letter-level."

### 3.2 Entity-Type Filtering

The `applicable_entity_types` JSONB column already exists on both `regulation_key_definitions` and `jurisdiction_requirements`. Currently empty.

**Populate with a taxonomy:**
```
hospital_system, critical_access_hospital, ambulatory_surgery_center,
physician_practice, clinical_laboratory, pharmacy, ltc_snf,
home_health_agency, device_manufacturer, drug_manufacturer,
biologic_manufacturer, health_plan, pharmacy_benefit_manager,
clinical_research_org, health_it_vendor
```

Write a migration script to backfill `applicable_entity_types` on all 396+ key definitions based on the key's domain:
- `hipaa_*` keys → all entity types
- `fda_*` keys → manufacturers only
- `cms_*` quality keys → providers only
- `iso_*` keys → manufacturers + labs
- etc.

**Impact**: A 20-bed rural clinic sees only the keys that apply to it, not device manufacturing keys.

### 3.3 Pending Regulations Pipeline

The `jurisdiction_legislation` table already exists with fields for tracking pending bills:
- `current_status` (proposed, committee, passed_one_chamber, signed, effective)
- `expected_effective_date`
- `impact_summary`

**What's needed:**
- Link legislation to the key it will affect: add `target_key_definition_id UUID REFERENCES regulation_key_definitions(id)` to `jurisdiction_legislation`
- Frontend: show "Upcoming" badge on policy detail page when linked legislation exists
- Cron job or manual trigger to promote legislation → requirement when it becomes effective

**Impact**: Clients see "CA SB 446 takes effect Jan 2026 — will change your breach notification deadline from 60→30 days" before enforcement.

### 3.4 Cross-Reference Dependency Graph

New table:

```sql
CREATE TABLE key_dependencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_key_id UUID NOT NULL REFERENCES regulation_key_definitions(id),
    target_key_id UUID NOT NULL REFERENCES regulation_key_definitions(id),
    dependency_type VARCHAR(30) NOT NULL,  -- 'triggers', 'requires', 'supersedes', 'conflicts_with', 'informs'
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(source_key_id, target_key_id, dependency_type)
);
```

**Example edges:**
- `state_telehealth_parity_laws` **triggers** `state_telehealth_practice_standards`
- `hipaa_security_rule_cybersecurity` **requires** `incident_response_plan`
- `eu_mdr_classification` **requires** `ce_marking_requirements`
- `nda_bla_submission` **triggers** `post_market_surveillance_faers`

**Impact**: When a policy changes, the system knows which other policies might be affected.

### 3.5 Audit & Attestation Workflow

Add to `jurisdiction_requirements`:

```sql
ALTER TABLE jurisdiction_requirements ADD COLUMN IF NOT EXISTS
    compliance_status VARCHAR(20) DEFAULT 'not_assessed',  -- 'compliant', 'non_compliant', 'partial', 'not_assessed', 'exempt'
    assessed_at TIMESTAMP,
    assessed_by UUID REFERENCES users(id),
    next_assessment_due DATE,
    remediation_status VARCHAR(20),    -- 'not_needed', 'planned', 'in_progress', 'completed'
    remediation_notes TEXT;
```

**Impact**: Transform from "here's what the law says" to "here's whether you're compliant and what you need to do."

### 3.6 Sparse Metadata Backfill

Currently ~180 keys (labor + supplementary) have no `enforcing_agency`, `state_variance`, or `description` in the registry. Only healthcare/medical/oncology keys have full `RegulationDef` objects.

**Fix**: Create full `RegulationDef` entries for all labor/supplementary keys. This is research work — each key needs:
- Accurate enforcing agency (DOL, State DOL, IRS, etc.)
- State variance level (High/Moderate/Low)
- Description
- Authority source URLs

Can be done incrementally by category. Priority: `minimum_wage`, `overtime`, `leave` (most customer-facing).

---

## Implementation Order

| Phase | What | New Keys | Schema Changes | Effort |
|-------|------|----------|---------------|--------|
| **Phase 1** | Tier 1 keys + categories | ~65 | None | Medium — define + seed |
| **Phase 2** | Tier 3.1 penalty/risk fields | 0 | 7 columns on `regulation_key_definitions` | Small — migration + backfill |
| **Phase 3** | Tier 3.2 entity-type backfill | 0 | None (column exists) | Medium — research + populate |
| **Phase 4** | Tier 2 international keys | ~25 | None | Medium — define + seed |
| **Phase 5** | Tier 3.3 pending regs pipeline | 0 | 1 FK column on `jurisdiction_legislation` | Small |
| **Phase 6** | Tier 3.4 dependency graph | 0 | New `key_dependencies` table | Medium |
| **Phase 7** | Tier 3.5 audit/attestation | 0 | 6 columns on `jurisdiction_requirements` | Small — migration |
| **Phase 8** | Tier 3.6 metadata backfill | 0 | None | Large — research per key |

**Phase 1 is the highest-impact, lowest-risk starting point.** It immediately expands coverage from 483 → ~550 keys and opens new market segments (pharma, device manufacturers, larger health systems).

---

## Files Affected

| File | Phases |
|------|--------|
| `server/app/core/compliance_registry.py` | 1, 4, 8 |
| `server/alembic/versions/<new>.py` | 2, 5, 6, 7 |
| `server/app/orm/requirement.py` | 2, 7 |
| `server/app/orm/key_definition.py` | 2 |
| `server/app/database.py` | 2, 6, 7 |
| `POLICY_REGISTRY.md` | 1, 4 (regenerate) |
| `server/scripts/seed_key_definitions.py` | 1, 4 (or inline in migration) |
| `client/src/pages/admin/PolicyDetailPage.tsx` | 2, 5, 7 (display new fields) |
| `client/src/pages/admin/CategoryDetailPage.tsx` | 2 (display new fields) |
