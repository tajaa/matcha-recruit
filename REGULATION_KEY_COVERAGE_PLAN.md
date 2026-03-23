# Plan: First-Class Regulation Key Coverage System

## Context

Every regulation key (328 across 40 categories) should be treated like a stock ticker or street name — a uniquely important, indispensable data point. Today the system tracks coverage at the **category level** ("does this jurisdiction have any minimum_wage data?") but not at the **key level** ("does it have state_minimum_wage, tipped_minimum_wage, AND exempt_salary_threshold?"). Three structural gaps make missing keys silent:

1. **99 labor keys have no metadata** — `get_missing_regulations()` filters through `REGULATION_MAP` (229 healthcare entries only), silently dropping all labor gaps
2. **5 oncology categories have 0 expected keys** — despite having `ComplianceCategoryDef` entries, they define no regulation keys at all
3. **No key-level UI** — admin heatmap and gap panel operate at category granularity only

---

## Phase 1: Make All Keys First-Class in the Registry

**File:** `server/app/core/compliance_registry.py`

### 1a. Add lightweight `RegulationKeyDef` dataclass (~line 39)

```python
@dataclass(frozen=True)
class RegulationKeyDef:
    key: str
    category: str
    name: str               # "State Minimum Wage"
    state_variance: str     # "High" | "Moderate" | "Low/None"
    weight: float = 1.0     # 1.0 default, 1.5 for High variance
```

This is intentionally lighter than `RegulationDef` — no description, enforcing_agency, authority_sources. Labor/oncology keys don't need that metadata; they just need to be named, weighted, and countable.

### 1b. Convert `_LABOR_REGULATION_KEYS` from `frozenset[str]` to `list[RegulationKeyDef]`

Replace the current 99 bare string keys with named defs. Example:

```python
_LABOR_KEY_DEFS: Dict[str, List[RegulationKeyDef]] = {
    "minimum_wage": [
        RegulationKeyDef("state_minimum_wage", "minimum_wage", "State Minimum Wage", "High", 1.5),
        RegulationKeyDef("tipped_minimum_wage", "minimum_wage", "Tipped Minimum Wage", "High", 1.5),
        RegulationKeyDef("exempt_salary_threshold", "minimum_wage", "Exempt Salary Threshold", "Moderate", 1.0),
        # ... all 10
    ],
    # ... all 15 labor/supplementary categories
}
```

### 1c. Add oncology key definitions (~25-30 keys across 5 categories)

These categories currently have ZERO expected keys. Define them based on our research data (Charlotte, etc.):

- `radiation_safety`: ~6 keys (state_radiation_control_programs, radiation_safety_officer, linear_accelerator_qa, brachytherapy_safety, radiation_oncology_safety_team, radioactive_materials_license)
- `chemotherapy_handling`: ~5 keys (usp_compounding_standards, closed_system_transfer, hazardous_drug_assessment, spill_management, hazardous_waste_disposal)
- `tumor_registry`: ~4 keys (cancer_registry_reporting, reporting_timelines, electronic_reporting_format, registry_data_quality)
- `oncology_clinical_trials`: ~5 keys (clinical_trial_coverage_mandates, right_to_try, protocol_deviation_reporting, adverse_event_reporting, investigational_drug_access)
- `oncology_patient_rights`: ~5 keys (patient_rights_declarations, hospice_palliative_care, advance_directives, fertility_preservation_counseling, cancer_treatment_consent)

### 1d. Build unified lookup structures

```python
# All keys as RegulationKeyDef (from RegulationDef + labor + oncology)
ALL_KEY_DEFS: Dict[str, RegulationKeyDef] = {}
# ... populated from REGULATION_MAP (mapped to RegulationKeyDef) + _LABOR_KEY_DEFS + _ONCOLOGY_KEY_DEFS

KEY_DEFS_BY_CATEGORY: Dict[str, List[RegulationKeyDef]] = {}
# ... every category -> its full key list

# Keep EXPECTED_REGULATION_KEYS backward-compatible (still frozenset[str])
EXPECTED_REGULATION_KEYS: Dict[str, FrozenSet[str]] = {
    cat: frozenset(kd.key for kd in defs)
    for cat, defs in KEY_DEFS_BY_CATEGORY.items()
}
```

### 1e. Fix `get_missing_regulations()` (line 3779)

Current (broken for labor/oncology):
```python
def get_missing_regulations(category, existing_keys) -> List[RegulationDef]:
    expected = EXPECTED_REGULATION_KEYS.get(category, frozenset())
    missing_keys = expected - existing_keys
    return [REGULATION_MAP[k] for k in sorted(missing_keys) if k in REGULATION_MAP]  # ← silently skips labor
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

Implementation:
1. Query `jurisdiction_requirements` grouped by `category` + extracted regulation_key (split `requirement_key` on `:`)
2. Cross-reference against `KEY_DEFS_BY_CATEGORY` to identify present vs missing
3. Compute weighted coverage score: `sum(weight for present) / sum(weight for all) * 100`

Response shape:
```json
{
  "summary": {
    "total_expected_keys": 328,
    "total_present_keys": 245,
    "key_coverage_pct": 74.7,
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
      "status": "present",
      "jurisdiction_count": 42,
      "best_tier": 3
    }]
  }]
}
```

### 2b. Enhance `data-overview` summary

Add `key_coverage_pct` and `weighted_coverage_score` to the existing summary object. Small addition — one extra SQL query counting distinct regulation keys per jurisdiction vs expected.

### 2c. Enhance `coverage-matrix` cells

Add `keys_present` and `keys_expected` to each cell alongside existing `req_count`, `best_tier`, `avg_completeness`. This lets the heatmap show `7/10` instead of just a count.

---

## Phase 3: Update TypeScript Generation

**File:** `scripts/generate_compliance_ts.py` (or equivalent TS generation script)

- Export `ALL_REGULATION_KEYS_BY_CATEGORY` covering all 328 keys (currently only 229 healthcare)
- Export `REGULATION_KEY_NAMES: Record<string, string>` for all keys
- Export `REGULATION_KEY_WEIGHTS: Record<string, number>` for weighted scoring
- Add TS types for `KeyCoverageResponse`

**File:** `client/src/api/compliance.ts`

- Add `fetchKeyCoverage()` API function
- Add TypeScript interfaces for the response

---

## Phase 4: Key-Level UI in Admin Dashboard

**Files:** `client/src/components/admin/jurisdiction/`

### 4a. `KeyCoverageDrawer.tsx` (new)

Opens when admin clicks a heatmap cell. Shows:
- Progress bar: "7 of 10 keys present (70%)"
- List of all expected keys for that category, each with:
  - Green checkmark (present) or red X with "DATA NEEDED" badge (missing)
  - Weight badge (1.5x for high-variance keys)
  - Tier indicator for present keys

### 4b. Update `CoverageHeatmap.tsx`

- Change cell display from `req_count` to fraction: `7/10` (keys present / expected)
- Keep existing color logic but base it on key coverage % instead of field completeness
- Add `onClick` to open `KeyCoverageDrawer`

### 4c. Update `GapIntelligencePanel.tsx`

- Surface key-level gaps: "Charlotte, NC — Minimum Wage — Missing: tipped_minimum_wage, healthcare_minimum_wage"
- Weight-adjusted priority: missing `state_minimum_wage` (weight 1.5) scores higher than `youth_minimum_wage` (weight 1.0)

### 4d. `KeyCoverageOverview.tsx` (new, optional)

New tab in JurisdictionData showing all 328 keys as rows (grouped by category), with columns for jurisdiction coverage count, coverage %, weighted score. Like a Bloomberg terminal board — searchable, filterable, color-coded by coverage level.

---

## Implementation Order

```
Phase 1 (Registry)  →  Phase 2 (API)  →  Phase 3 (TS Gen)  →  Phase 4 (UI)
     ↑ no deps          needs Phase 1      needs Phase 2        needs Phase 2+3
```

Phases 1-3 can be done in one session. Phase 4 depends on API + types being ready.

## No DB Schema Changes

The existing `jurisdiction_requirements.requirement_key` column stores `category:regulation_key`. We extract the regulation_key portion via string split. No new tables or columns needed.

## Verification

1. **Registry**: `python -c "from app.core.compliance_registry import KEY_DEFS_BY_CATEGORY, ALL_KEY_DEFS; print(f'{len(ALL_KEY_DEFS)} total keys across {len(KEY_DEFS_BY_CATEGORY)} categories')"` — should show ~355 keys across 40 categories
2. **API**: `curl localhost:8001/api/admin/jurisdictions/key-coverage?jurisdiction_id=<charlotte_id>` — should show per-category key coverage with present/missing status
3. **UI**: Navigate to `/admin/jurisdiction-data`, verify heatmap cells show `n/m` fractions, click a cell to see key-level drawer
4. **Gap detection**: `get_missing_regulations("minimum_wage", {"state_minimum_wage"})` should return 9 missing `RegulationKeyDef` objects (not silently return empty)
