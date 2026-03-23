# Plan: First-Class Regulation Key Coverage System

## Context

Every regulation key should be treated like a stock ticker or street name — a uniquely important, indispensable data point. If Apple disappeared from the NASDAQ or the 405 disappeared from a map, you'd notice instantly. Our policy system needs the same property: if any policy is missing, stale, unfetched, or incomplete, it must be immediately and obviously apparent.

Today the system tracks coverage at the **category level** but not at the **key level**. Three structural gaps make missing keys silent:

1. **99 labor keys have no metadata** — `get_missing_regulations()` silently drops them
2. **5 oncology categories have 0 expected keys** — no keys defined at all
3. **No key-level UI** — admin heatmap operates at category granularity only

---

## Current Schema: How It Works Today

### The Data Model (6 interconnected tables)

```
┌─────────────────────┐     ┌───────────────────────────────────────────────┐
│   jurisdictions      │────▶│       jurisdiction_requirements                │
│                      │     │  (the core policy record)                     │
│ • city, state, county│     │                                               │
│ • last_verified_at   │     │  IDENTITY                                     │
│ • requirement_count  │     │  • id (UUID)                                  │
│ • UNIQUE(city,state) │     │  • jurisdiction_id → jurisdictions             │
└─────────────────────┘     │  • requirement_key (category:reg_key)          │
                             │  • canonical_key (state_city_cat_key, UNIQUE)  │
                             │  • category_id → compliance_categories         │
                             │  • category (slug: "minimum_wage")             │
                             │                                               │
                             │  CONTENT                                      │
                             │  • title, description, summary                │
                             │  • current_value ("$16.50/hr")                │
                             │  • numeric_value (16.50)                      │
                             │  • full_text_reference (statute text)         │
                             │  • statute_citation ("N.C.G.S. § 95-25.3")   │
                             │                                               │
                             │  JURISDICTION SCOPE                           │
                             │  • jurisdiction_level (state/city)            │
                             │  • jurisdiction_name ("North Carolina")       │
                             │  • rate_type (for min wage: general/tipped)   │
                             │                                               │
                             │  SOURCE & TRUST                               │
                             │  • source_url, source_name                   │
                             │  • source_tier (tier_1_government /           │
                             │    tier_2_official_secondary /                │
                             │    tier_3_aggregator)                         │
                             │  • fetch_hash (content hash for change detect)│
                             │                                               │
                             │  DATES                                        │
                             │  • effective_date (when law takes effect)     │
                             │  • expiration_date                            │
                             │  • last_verified_at (when we last checked)    │
                             │  • last_changed_at (when value last changed)  │
                             │  • created_at (when we first captured it)     │
                             │  • updated_at (last DB write)                 │
                             │  • previous_value (value before last change)  │
                             │                                               │
                             │  LIFECYCLE                                    │
                             │  • status (active / archived / superseded)    │
                             │  • superseded_by_id → self-reference          │
                             │                                               │
                             │  APPLICABILITY                                │
                             │  • applicable_entity_types (JSONB)            │
                             │  • applicable_industries (TEXT[])             │
                             │  • trigger_conditions (JSONB)                 │
                             │  • requires_written_policy (bool)             │
                             │                                               │
                             │  META                                         │
                             │  • metadata (JSONB — extensible)              │
                             │  • is_bookmarked (for admin review)           │
                             │  • sort_order                                 │
                             └───────────────────────────────────────────────┘
                                  │             │              │
                    ┌─────────────┘   ┌─────────┘    ┌─────────┘
                    ▼                 ▼               ▼
         ┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
         │ policy_change_log│ │ compliance_  │ │ verification_    │
         │                  │ │ embeddings   │ │ outcomes         │
         │ • field_changed  │ │              │ │                  │
         │ • old_value      │ │ • embedding  │ │ • predicted_     │
         │ • new_value      │ │   vector(768)│ │   confidence     │
         │ • change_source  │ │ • content    │ │ • actual_is_     │
         │ • change_reason  │ │ • metadata   │ │   change         │
         │ • changed_at     │ └──────────────┘ │ • reviewed_by    │
         └──────────────────┘                  │ • admin_notes    │
                                               └──────────────────┘
```

### Supporting Tables

| Table | Purpose |
|-------|---------|
| `compliance_categories` | Canonical category definitions (40 entries: slug, name, domain, group, sort_order) |
| `jurisdiction_sources` | Source reputation per domain per jurisdiction (success_count, accurate_count, inaccurate_count, Laplace smoothing) |
| `structured_data_sources` | Tier 1 API source registry (DOL, BLS, etc.) with fetch schedules and parser configs |
| `jurisdiction_legislation` | Upcoming/proposed legislation per jurisdiction (for forward-looking alerts) |
| `compliance_requirement_history` | Point-in-time snapshots of requirement values |

### The Registry (Python, `compliance_registry.py`)

| Construct | Count | What It Contains |
|-----------|-------|-----------------|
| `CATEGORIES` | 40 | `ComplianceCategoryDef` — key, label, group, research_mode, industry_tag |
| `REGULATIONS` | 229 | `RegulationDef` — key, category, name, description, enforcing_agency, state_variance, update_frequency, authority_sources |
| `_LABOR_REGULATION_KEYS` | 99 keys | **Bare strings only** — no name, no variance, no weight |
| Oncology keys | **0** | Not defined at all |
| **Total expected keys** | **328** | But only 229 have full metadata |

### What's Tracked vs What's Missing

| Attribute | Currently Stored? | Where? |
|-----------|:-:|--------|
| Policy content (title, description, value) | Yes | `jurisdiction_requirements` |
| Source URL and name | Yes | `jurisdiction_requirements` |
| Source tier (gov/secondary/aggregator) | Yes | `jurisdiction_requirements.source_tier` |
| Statute citation | Yes | `jurisdiction_requirements.statute_citation` |
| Effective date | Yes | `jurisdiction_requirements.effective_date` |
| When we first captured it | Yes | `jurisdiction_requirements.created_at` |
| When we last verified it | Yes | `jurisdiction_requirements.last_verified_at` |
| When the value last changed | Yes | `jurisdiction_requirements.last_changed_at` |
| Previous value | Yes | `jurisdiction_requirements.previous_value` |
| Content hash for change detection | Yes | `jurisdiction_requirements.fetch_hash` |
| Change history (field-level) | Yes | `policy_change_log` |
| Vector embedding for RAG | Yes | `compliance_embeddings` |
| Verification outcomes | Yes | `verification_outcomes` |
| **Which keys are EXPECTED per category** | Partial | Registry only — labor keys are bare strings, oncology has none |
| **Which keys are MISSING per jurisdiction** | Broken | `get_missing_regulations()` silently skips labor/oncology |
| **Key-level coverage scores** | No | Only category-level coverage exists |
| **Human-readable names for all keys** | No | Only 229/328 have names |
| **Variance/weight per key** | No | Only 229/328 have state_variance |
| **Per-key staleness alerting** | No | Only per-jurisdiction staleness |

---

## The Goal: Each Policy as a Unique System

Every one of our ~355 regulation keys should carry enough metadata to answer any compliance officer's question:

- **What is this policy?** → name, description, category, group
- **Where did we get this data?** → source_url, source_name, source_tier, statute_citation
- **When was it enacted?** → effective_date, expiration_date
- **When did we first capture it?** → created_at
- **When did we last check it?** → last_verified_at
- **When did the value last change?** → last_changed_at, previous_value
- **Is it current?** → status (active/archived/superseded), superseded_by_id
- **How much does it vary by jurisdiction?** → state_variance, weight
- **Which jurisdictions have it?** → jurisdiction_count, coverage_pct
- **Which jurisdictions are missing it?** → immediately visible gap
- **What changed and when?** → policy_change_log history
- **How confident are we?** → source_tier, verification_outcomes, fetch_hash

The DB schema already captures most of this per-record. The gap is in the **registry** (where keys are defined) and the **surface** (where gaps are shown).

---

## Phase 1: Make All Keys First-Class in the Registry

**File:** `server/app/core/compliance_registry.py`

### 1a. Add `RegulationKeyDef` dataclass (~line 39)

```python
@dataclass(frozen=True)
class RegulationKeyDef:
    key: str
    category: str
    name: str               # "State Minimum Wage"
    state_variance: str     # "High" | "Moderate" | "Low/None"
    weight: float = 1.0     # 1.0 default, 1.5 for High variance
```

Lighter than `RegulationDef` — no description, enforcing_agency, authority_sources. Those stay on `RegulationDef` for healthcare. Every key just needs to be named, weighted, and countable.

### 1b. Convert `_LABOR_REGULATION_KEYS` from `frozenset[str]` to `list[RegulationKeyDef]`

Replace the current 99 bare string keys with named defs:

```python
_LABOR_KEY_DEFS: Dict[str, List[RegulationKeyDef]] = {
    "minimum_wage": [
        RegulationKeyDef("state_minimum_wage", "minimum_wage", "State Minimum Wage", "High", 1.5),
        RegulationKeyDef("tipped_minimum_wage", "minimum_wage", "Tipped Minimum Wage", "High", 1.5),
        RegulationKeyDef("exempt_salary_threshold", "minimum_wage", "Exempt Salary Threshold", "Moderate", 1.0),
        # ... all 10
    ],
    # ... all 15 labor/supplementary categories (99 keys total)
}
```

### 1c. Add oncology key definitions (~25 keys across 5 categories)

Currently ZERO keys. Define based on our research (Charlotte NC, etc.):

- `radiation_safety`: ~6 keys (state_radiation_control_programs, radiation_safety_officer, linear_accelerator_qa, brachytherapy_safety, radiation_oncology_safety_team, radioactive_materials_license)
- `chemotherapy_handling`: ~5 keys (usp_compounding_standards, closed_system_transfer, hazardous_drug_assessment, spill_management, hazardous_waste_disposal)
- `tumor_registry`: ~4 keys (cancer_registry_reporting, reporting_timelines, electronic_reporting_format, registry_data_quality)
- `oncology_clinical_trials`: ~5 keys (clinical_trial_coverage_mandates, right_to_try, protocol_deviation_reporting, adverse_event_reporting, investigational_drug_access)
- `oncology_patient_rights`: ~5 keys (patient_rights_declarations, hospice_palliative_care, advance_directives, fertility_preservation_counseling, cancer_treatment_consent)

### 1d. Build unified lookup structures

```python
ALL_KEY_DEFS: Dict[str, RegulationKeyDef] = {}
# Populated from: REGULATION_MAP (→ RegulationKeyDef) + _LABOR_KEY_DEFS + _ONCOLOGY_KEY_DEFS

KEY_DEFS_BY_CATEGORY: Dict[str, List[RegulationKeyDef]] = {}
# Every category → its full key list

# Backward-compatible (still frozenset[str])
EXPECTED_REGULATION_KEYS: Dict[str, FrozenSet[str]] = {
    cat: frozenset(kd.key for kd in defs)
    for cat, defs in KEY_DEFS_BY_CATEGORY.items()
}
```

### 1e. Fix `get_missing_regulations()` (line 3779)

Current (broken — silently skips labor/oncology):
```python
return [REGULATION_MAP[k] for k in sorted(missing_keys) if k in REGULATION_MAP]
```

Fixed:
```python
def get_missing_regulations(category, existing_keys) -> List[RegulationKeyDef]:
    expected = KEY_DEFS_BY_CATEGORY.get(category, [])
    return [kd for kd in expected if kd.key not in existing_keys]
```

---

## Phase 2: Key-Level Coverage API

**File:** `server/app/core/routes/admin.py`

### 2a. New endpoint: `GET /admin/jurisdictions/key-coverage`

Query params: `jurisdiction_id`, `category`, `state`, `gaps_only` (all optional)

For each key, return everything a compliance officer needs at a glance:

```json
{
  "summary": {
    "total_expected_keys": 355,
    "total_present_keys": 245,
    "key_coverage_pct": 69.0,
    "weighted_coverage_score": 71.2,
    "categories_fully_covered": 18,
    "categories_with_gaps": 22
  },
  "by_category": [{
    "category": "minimum_wage",
    "group": "labor",
    "expected": 10,
    "present": 7,
    "coverage_pct": 70.0,
    "keys": [{
      "key": "state_minimum_wage",
      "name": "State Minimum Wage",
      "weight": 1.5,
      "state_variance": "High",
      "status": "present",
      "jurisdiction_count": 42,
      "best_tier": 3,
      "oldest_verification_days": 12,
      "newest_value": "$16.50/hr",
      "has_change_history": true
    }, {
      "key": "healthcare_minimum_wage",
      "name": "Healthcare Minimum Wage",
      "weight": 1.5,
      "state_variance": "High",
      "status": "missing",
      "jurisdiction_count": 0,
      "best_tier": 0,
      "oldest_verification_days": null,
      "newest_value": null,
      "has_change_history": false
    }]
  }]
}
```

### 2b. Enhance `data-overview` summary

Add `key_coverage_pct` and `weighted_coverage_score` to existing summary.

### 2c. Enhance `coverage-matrix` cells

Add `keys_present` and `keys_expected` per cell so heatmap can show `7/10` fractions.

---

## Phase 3: Update TypeScript Generation

**File:** `scripts/generate_compliance_ts.py`

- Export `ALL_REGULATION_KEYS_BY_CATEGORY` covering all ~355 keys (not just 229 healthcare)
- Export `REGULATION_KEY_NAMES: Record<string, string>` for all keys
- Export `REGULATION_KEY_WEIGHTS: Record<string, number>` for weighted scoring
- Add TS types for `KeyCoverageResponse`

**File:** `client/src/api/compliance.ts`

- Add `fetchKeyCoverage()` API function + TypeScript interfaces

---

## Phase 4: Key-Level UI in Admin Dashboard

**Files:** `client/src/components/admin/jurisdiction/`

### 4a. `KeyCoverageDrawer.tsx` (new)

Opens on heatmap cell click. Shows:
- Progress bar: "7 of 10 keys present (70%)"
- Each key: checkmark/X, name, weight badge, tier badge, last verified date, current value
- Missing keys highlighted red with "DATA NEEDED" badge
- Per-key: created_at, last_verified_at, last_changed_at, source_tier, source_url

### 4b. Update `CoverageHeatmap.tsx`

- Cells show `7/10` (keys present / expected) instead of bare `req_count`
- Color based on key coverage % instead of field completeness
- Click opens `KeyCoverageDrawer`

### 4c. Update `GapIntelligencePanel.tsx`

- Key-level gaps: "Charlotte, NC — Minimum Wage — Missing: tipped_minimum_wage, healthcare_minimum_wage"
- Weight-adjusted priority scoring

### 4d. `KeyCoverageOverview.tsx` (new)

All ~355 keys as rows grouped by category. Columns: jurisdiction coverage count, %, weighted score. Bloomberg-terminal style — searchable, filterable, color-coded.

---

## Implementation Order

```
Phase 1 (Registry)  →  Phase 2 (API)  →  Phase 3 (TS Gen)  →  Phase 4 (UI)
     no deps             needs Phase 1      needs Phase 2        needs 2+3
```

## No New DB Tables or Columns

The existing schema already stores everything we need per policy record. The gap is purely in the registry (key metadata) and the surface (coverage visibility). `requirement_key` stores `category:regulation_key` — we extract the key via string split and cross-reference against the enriched registry.

## Verification

1. **Registry**: `python -c "from app.core.compliance_registry import ALL_KEY_DEFS; print(len(ALL_KEY_DEFS))"` → ~355 keys
2. **Gap fix**: `get_missing_regulations("minimum_wage", {"state_minimum_wage"})` → returns 9 `RegulationKeyDef` objects (not empty)
3. **API**: `curl localhost:8001/api/admin/jurisdictions/key-coverage?jurisdiction_id=<charlotte_id>` → per-key coverage with dates and values
4. **UI**: Heatmap cells show `n/m`, click opens key drawer with full policy details
