# Facility Inference + Triggered Research Pipeline

## Overview

Healthcare companies in Matcha get automatic facility profiling and payer-specific compliance requirements. When a healthcare company runs a compliance check on a location, the system:

1. **Infers** the facility type and payer contracts from the company name (via Gemini)
2. **Activates** trigger profiles based on the inferred attributes
3. **Researches** payer/entity-specific requirements (Medi-Cal, Medicare, FQHC, CAH)
4. **Caches** triggered requirements at the jurisdiction level for reuse by all future companies

This runs inside the existing compliance check SSE stream — no separate endpoints needed.

---

## Architecture

```
Compliance Check (SSE stream)
│
├── Facility Inference (before Tier 1)
│   └── Gemini classifies company → entity_type + payer_contracts
│       → stored on business_locations.facility_attributes
│
├── Tier 1: Structured data (minimum_wage from authoritative sources)
├── Tier 2: Jurisdiction repository (cached requirements)
├── Tier 3: Gemini research (base requirements, admin-only)
│
└── Tier 4: Triggered Research (after Tier 3)
    ├── get_activated_profiles(facility_attributes)
    │   → matches against TRIGGER_PROFILES registry
    ├── For each activated profile:
    │   ├── Check jurisdiction_requirements cache
    │   │   (applicable_entity_types @> '["medi_cal"]')
    │   ├── If cached → load and append
    │   └── If not → Gemini researches → upsert to jurisdiction_requirements
    └── Gap detection → admin alerts for missing specialty categories
```

## How It Works

### Step 1: Facility Inference

Runs once per location, at the start of compliance checks. Skips if `entity_type` is already set.

**Trigger condition:** `canonical_industry == "healthcare"` and no existing `entity_type`

**What it does:**
- Calls `GeminiComplianceService.infer_facility_profile()` with company name, industry, healthcare specialties, city, state
- Gemini returns: `entity_type`, `likely_payer_contracts`, `confidence`, `reasoning`
- Only persists if `confidence >= 0.5`
- Merges into existing `facility_attributes` (doesn't overwrite)
- Reloads the location object so Tier 4 sees the new attributes immediately

**Entity types:** `hospital`, `fqhc`, `critical_access_hospital`, `clinic`, `nursing_facility`, `pharmacy`, `behavioral_health`, `ambulatory_surgery_center`, `home_health`, `hospice`, `dialysis_center`, `lab`, `dental`, `other`

**Payer contracts:** `medicare`, `medi_cal` (CA only), `medicaid_other` (non-CA), `commercial`, `tricare`

**SSE event:**
```json
{"type": "facility_inference", "message": "Detected: hospital"}
```

### Step 2: Trigger Profile Activation

Defined in `server/app/core/compliance_registry.py` as `TRIGGER_PROFILES`:

| Profile | Key | Matches On | Categories Researched |
|---------|-----|-----------|----------------------|
| Federally Qualified Health Center | `fqhc` | `entity_type == "fqhc"` | billing_integrity, clinical_safety, healthcare_workforce, quality_reporting, payer_relations |
| Medi-Cal Participation | `medi_cal` | `"medi_cal" in payer_contracts` | billing_integrity, payer_relations, quality_reporting |
| Medicare Participation | `medicare` | `"medicare" in payer_contracts` | billing_integrity, payer_relations, quality_reporting |
| Critical Access Hospital | `critical_access_hospital` | `entity_type == "critical_access_hospital"` | billing_integrity, clinical_safety, emergency_preparedness |

`get_activated_profiles(facility_attributes)` checks each profile against the location's attributes and returns all that match. A hospital accepting both Medicare and Medi-Cal activates both profiles.

### Step 3: Triggered Research

For each activated profile, the system:

1. **Checks the cache** — queries `jurisdiction_requirements` for rows where `applicable_entity_types @> '["profile_key"]'`
2. **If cached** — loads existing rows and appends to results (no Gemini call)
3. **If not cached** — calls `GeminiComplianceService.research_triggered_requirements()`:
   - Builds targeted prompts per category using the profile's `research_instruction`
   - Instructs Gemini to return only requirements SPECIFIC to the trigger (not baseline rules)
   - Tags every returned requirement with `trigger_conditions` and `applicable_entity_types`
   - Upserts to `jurisdiction_requirements` with `category_id` resolved from `compliance_categories`

**SSE events:**
```json
{"type": "trigger_research", "message": "Researching Medi-Cal Participation-specific requirements..."}
{"type": "trigger_research", "message": "Researching Medicare Participation-specific requirements..."}
```

### Step 4: Gap Detection

After triggered research, the system checks if any activated profile's applicable categories are missing from the results. If so, it creates a `missing_specialty` alert for admin review (deduplicated — won't re-alert).

---

## DB Schema

### `business_locations.facility_attributes` (JSONB)

```json
{
  "entity_type": "hospital",
  "payer_contracts": ["medicare", "medi_cal", "commercial", "tricare"]
}
```

Set by facility inference. Can also be set manually via `PATCH /api/compliance/locations/{id}/facility-attributes`.

### `jurisdiction_requirements` columns for triggered data

| Column | Type | Purpose |
|--------|------|---------|
| `trigger_conditions` | JSONB | The trigger condition that produced this requirement (e.g., `{"type": "entity_type", "value": "fqhc"}`) |
| `applicable_entity_types` | JSONB | Array of profile keys this applies to (e.g., `["medi_cal"]`) |
| `category_id` | UUID FK | Links to `compliance_categories` for hierarchical queries |

Triggered requirements are stored on the **jurisdiction** (not the company), so they're reused by any future company in the same city/state.

### `compliance_requirements` (company-level)

Synced from `jurisdiction_requirements` during the compliance check. The `_sync_requirements_to_location` function copies both base and triggered requirements to the company's location.

---

## Example: UCSF Medical Center Test Run

**Setup:**
- Company: "UCSF Medical Center", industry: healthcare, specialties: internal_medicine, surgery, emergency_medicine, pediatrics
- Location: San Francisco, CA

**SSE stream output:**
```
facility_inference  → Detected: hospital
fallback            → Using cached data (SF already has base requirements)
trigger_research    → Researching Medi-Cal Participation-specific requirements...
trigger_research    → Researching Medicare Participation-specific requirements...
completed           → 42 total (20 base + 22 triggered)
```

**Result breakdown:**
- 20 base San Francisco requirements (minimum_wage, sick_leave, scheduling, etc.)
- 10 Medi-Cal specific (provider enrollment, TAR compliance, MCAS reporting, CalAIM ECM, etc.)
- 12 Medicare specific (60-day overpayment rule, MIPS reporting, CoPs QAPI, IQR program, etc.)

**Second run:** Triggered requirements load from cache — no Gemini calls.

---

## Bugs Fixed During Testing (2026-03-18)

### 1. `display_name` NOT NULL on jurisdictions

The `_get_or_create_jurisdiction` function didn't include `display_name` or `level` in its INSERT statements, but migration `zm1n2o3p4q5r_02` made `display_name` NOT NULL. Fixed all 6 INSERT sites across `compliance_service.py`, `admin.py`, `database.py`, and `leave_eligibility_service.py`.

### 2. State jurisdiction lookup — NULL vs empty string

State jurisdictions use `city = ''` (empty string) by convention, but some pre-migration rows have `city = NULL`. The unique index uses `COALESCE(city, '')` so both map to the same value, but `WHERE city = ''` doesn't match NULL. Fixed to `WHERE COALESCE(city, '') = ''`.

### 3. `new_count` referenced before assignment

The `except` block in `run_compliance_check_stream` referenced `new_count`, `updated_count`, `alert_count` before they were assigned (they're set after `_sync_requirements_to_location`). Initialized all three to `0` at function scope.

### 4. JSONB `applicable_entity_types` serialization

asyncpg requires JSONB values to be passed as `json.dumps()` strings, but the code passed Python lists directly. Added `json.dumps()` for both `applicable_entity_types` and `trigger_conditions`.

### 5. `category_id` NOT NULL on jurisdiction_requirements

Migration `zo3p4q5r6s7t_04` added `category_id` as NOT NULL with a backfill, but the upsert functions didn't include it. Fixed by resolving `category_id` inline via subquery: `(SELECT id FROM compliance_categories WHERE slug = $19 LIMIT 1)`. Uses a separate `$19` parameter (duplicate of `$3` category) because asyncpg can't deduce types when the same parameter is used in two different column contexts.

---

## Key Files

| File | What |
|------|------|
| `server/app/core/services/compliance_service.py` | Facility inference block (~line 3900), Tier 4 triggered research (~line 4355), upsert functions |
| `server/app/core/services/gemini_compliance.py` | `infer_facility_profile()`, `research_triggered_requirements()`, prompt builders |
| `server/app/core/compliance_registry.py` | `TRIGGER_PROFILES`, `TriggerProfileDef`, `get_activated_profiles()` |
| `server/app/core/models/compliance.py` | `BusinessLocation.facility_attributes` field, `FacilityAttributesUpdate` model |
| `server/app/core/routes/compliance.py` | SSE stream endpoint, facility-attributes PATCH/GET endpoints |

## Design Decisions

- **Inference runs once** — `entity_type` is checked before inference; once set, it never reruns
- **Confidence threshold 0.5** — prevents garbage classifications from persisting
- **Jurisdiction-level caching** — triggered requirements stored on the jurisdiction, not the company, so research is shared across all companies in the same location
- **Additive upsert** — `_upsert_requirements_additive` never deletes existing rows; only adds or updates
- **Profile-aware gap detection** — alerts only fire for missing categories relevant to activated profiles, not all healthcare categories
