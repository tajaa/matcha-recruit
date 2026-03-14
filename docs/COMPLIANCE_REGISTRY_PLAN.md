# Compliance Category Registry — Single Source of Truth

## Context

We're building the most robust medical jurisdiction and compliance system in the country. The docx defines **25 categories / 229 specific regulations**, each with enforcing agency, state variance level, and authoritative sources. Currently these are scattered across 6+ files with no canonical registry, and completeness is probabilistic — we trust the LLM found everything because there's no predefined list of what should exist.

**The fix**: A three-level registry that codifies every regulation so completeness is **deterministic**:
- **25 categories** (regulatory domains)
- **229 regulations** (specific laws/rules within each category)
- **N jurisdiction rows** (per-jurisdiction instances of each regulation)

After a research run, we can query: "for jurisdiction X, which of the 229 regulations have rows and which don't?" — no LLM needed.

## Data Extracted from Docx

The 229 regulations break down as:

| # | Category | Regs | Our Key |
|---|----------|------|---------|
| 1 | Patient Privacy & Data Protection | 10 | `hipaa_privacy` |
| 2 | Billing, Coding & Financial Integrity | 13 | `billing_integrity` |
| 3 | Clinical Quality & Patient Safety | 17 | `clinical_safety` |
| 4 | Workforce, Credentialing & Employment | 17 | `healthcare_workforce` |
| 5 | Corporate Integrity & Compliance Programs | 9 | `corporate_integrity` |
| 6 | Health IT, Interoperability & Electronic Records | 10 | `health_it` |
| 7 | Quality Reporting & Value-Based Care | 12 | `quality_reporting` |
| 8 | Cybersecurity & Information Security | 9 | `cybersecurity` |
| 9 | Environmental, Facility & Physical Safety | 10 | `environmental_safety` |
| 10 | Emergency Preparedness & Disaster Response | 7 | `emergency_preparedness` |
| 11 | Research, Clinical Trials & Institutional Review | 9 | `research_consent` |
| 12 | Pharmacy, Drug Supply Chain & Controlled Substances | 10 | `pharmacy_drugs` |
| 13 | Payer Relations, Insurance & Managed Care | 9 | `payer_relations` |
| 14 | Reproductive, Behavioral & Sensitive Health Services | 10 | `reproductive_behavioral` |
| 15 | Pediatric & Vulnerable Population Protections | 8 | `pediatric_vulnerable` |
| 16 | Telehealth & Digital Health | 10 | `telehealth` |
| 17 | Medical Devices & Equipment | 7 | `medical_devices` |
| 18 | Transplantation & Organ Procurement | 5 | `transplant_organ` |
| 19 | Antitrust & Competition in Healthcare | 5 | `antitrust` |
| 20 | Tax-Exempt Status & Community Benefit | 5 | `tax_exempt` |
| 21 | Language Access, Civil Rights & Nondiscrimination | 6 | `language_access` |
| 22 | Records Management, Retention & Documentation | 7 | `records_retention` |
| 23 | Marketing, Advertising & Patient Communications | 7 | `marketing_comms` |
| 24 | Governance, Licensure & Organizational Structure | 7 | `state_licensing` |
| 25 | Emerging & Specialized Regulatory Areas | 10 | `emerging_regulatory` |

Full regulation data already extracted to `/tmp/compliance_regulations.json` (229 entries with name, description, enforcing agency, state variance, update frequency, authoritative sources).

## Architecture: Three-Level Hierarchy

```
ComplianceCategoryDef (25)          ← regulatory domain
  └─ RegulationDef (229)            ← specific law/rule (e.g. "HIPAA Privacy Rule")
       └─ jurisdiction_requirements  ← per-jurisdiction DB row (existing table)
```

### Level 1: Category (`ComplianceCategoryDef`)
```python
@dataclass(frozen=True)
class ComplianceCategoryDef:
    key: str              # "pharmacy_drugs"
    label: str            # "Pharmacy & Controlled Substances"
    short_label: str      # "Pharmacy"
    group: str            # "labor" | "healthcare" | "oncology" | "medical_compliance" | "supplementary"
    industry_tag: str     # "healthcare:pharmacy"
    research_mode: str    # "default_sweep" | "specialty" | "health_specs"
    docx_section: int | None
```

### Level 2: Regulation (`RegulationDef`)
```python
@dataclass(frozen=True)
class RegulationDef:
    key: str                  # "hipaa_privacy_rule" (snake_case, unique across all categories)
    category: str             # "hipaa_privacy" (links to ComplianceCategoryDef.key)
    name: str                 # "HIPAA Privacy Rule (45 CFR Part 160, 164 Subparts A & E)"
    description: str          # Full scope description from docx
    enforcing_agency: str     # "HHS OCR"
    state_variance: str       # "High" | "Moderate" | "Low/None"
    update_frequency: str     # "Every 2-5 yrs"
    authority_sources: tuple  # ({"domain": "hhs.gov/hipaa", "name": "HHS HIPAA"}, ...)
```

### Level 3: Jurisdiction Row (existing `jurisdiction_requirements` table)
No schema change. The existing `requirement_key` column already uniquely identifies rows per jurisdiction. After research, we match returned rows against the predefined `RegulationDef` keys to determine completeness.

## New File: `server/app/core/compliance_registry.py`

Single source of truth. Contains:

1. **`ComplianceCategoryDef` dataclass** + **`CATEGORIES`** list (25 medical + 12 labor + 3 supplementary = 40 entries)
2. **`RegulationDef` dataclass** + **`REGULATIONS`** list (229 entries, parsed from docx)
3. **`RESEARCH_PROMPTS`** dict — per-category Gemini research instructions (moved from gemini_compliance.py)
4. **`CATEGORY_ALIASES`** dict — merged superset (moved from gemini_compliance.py + compliance_service.py)
5. **Derived exports** — computed at module load:

| Export | Replaces | Purpose |
|--------|----------|---------|
| `CATEGORY_MAP` | (new) | `Dict[str, ComplianceCategoryDef]` |
| `CATEGORY_KEYS` | `VALID_CATEGORIES` | `frozenset` of all valid keys |
| `LABOR_CATEGORIES` | `REQUIRED_LABOR_CATEGORIES` | `frozenset` |
| `HEALTHCARE_CATEGORIES` | `HEALTHCARE_CATEGORIES` | `frozenset` |
| `ONCOLOGY_CATEGORIES` | `ONCOLOGY_CATEGORIES` | `frozenset` |
| `MEDICAL_COMPLIANCE_CATEGORIES` | `MEDICAL_COMPLIANCE_CATEGORIES` | `frozenset` |
| `SPECIALTY_CATEGORIES` | `_HEALTHCARE_ONLY_CATEGORIES` | healthcare + oncology |
| `DEFAULT_RESEARCH_CATEGORIES` | `DEFAULT_RESEARCH_CATEGORIES` | sorted list |
| `CATEGORY_LABELS` | 3 separate label dicts | `Dict[str, str]` |
| `CATEGORY_SHORT_LABELS` | `CAT_LABELS` | `Dict[str, str]` |
| `INDUSTRY_TAGS` | `MEDICAL_COMPLIANCE_INDUSTRY_TAGS` | `Dict[str, str]` |
| `CATEGORY_AUTHORITY_SOURCES` | jurisdiction_context.py | `Dict[str, list]` |
| `REGULATION_MAP` | (new) | `Dict[str, RegulationDef]` |
| `REGULATIONS_BY_CATEGORY` | (new) | `Dict[str, List[RegulationDef]]` |
| `EXPECTED_REGULATION_KEYS` | (new) | `Dict[str, FrozenSet[str]]` — per category |

6. **Completeness check helper**:
```python
def get_missing_regulations(category: str, existing_keys: Set[str]) -> List[RegulationDef]:
    """Return regulations in this category not yet present in DB."""
    expected = EXPECTED_REGULATION_KEYS.get(category, frozenset())
    missing_keys = expected - existing_keys
    return [REGULATION_MAP[k] for k in missing_keys if k in REGULATION_MAP]
```

## Frontend: Generated TypeScript

### `scripts/generate_compliance_ts.py`
Reads registry, generates `client/src/generated/complianceCategories.ts`:
- `CATEGORY_LABELS`, `CATEGORY_SHORT_LABELS`
- Category group sets
- `REGULATION_KEYS_BY_CATEGORY: Record<string, string[]>` — for completeness UI
- `REGULATION_NAMES: Record<string, string>` — for display

Generated file committed to git. Re-run when categories change.

## Bug Fixes Included

1. **`VALID_CATEGORIES` missing 17 medical compliance categories** — Gemini's `_normalize_category_value` rejects them
2. **`ComplianceCategory` enum missing 22 categories** (oncology + medical compliance)
3. **`COMPLIANCE_CATEGORY_LABELS` only has 12 of 40 labels** — healthcare/oncology/medical labels missing from client
4. **No completeness checking** — currently can't tell if a research run missed regulations

## Backend Consumer Updates (6 files)

### 1. `compliance_service.py`
- Remove 4 category sets + industry tags dict (lines 62-128)
- Re-export from registry for backward compat
- Add completeness check to research functions (log missing regulations after each run)

### 2. `gemini_compliance.py`
- Remove `VALID_CATEGORIES`, `_HEALTHCARE_ONLY_CATEGORIES`, `DEFAULT_RESEARCH_CATEGORIES`, `_CATEGORY_ALIASES`, `category_instructions`
- Import all from registry
- **Fixes the validation bug** for medical compliance categories

### 3. `jurisdiction_context.py`
- Remove `CATEGORY_AUTHORITY_SOURCES` dict
- Import from registry

### 4. `policy_draft_service.py`
- Derive industry-specific `POLICY_TYPES` from registry `policy_type` fields
- Keep generic policy types (PTO, anti_harassment, etc.) in this file

### 5. `models/compliance.py`
- Expand `ComplianceCategory` enum to all categories

### 6. `admin.py`
- No direct changes — imports from compliance_service re-exports

## Frontend Consumer Updates (3 files)

### 1. `api/compliance.ts`
- Replace `COMPLIANCE_CATEGORY_LABELS` with import from generated file, re-export

### 2. `pages/admin/JurisdictionData.tsx`
- Replace `CAT_LABELS`, `ALL_CATEGORIES`, 3 category sets with imports from generated file

### 3. `pages/admin/Jurisdictions.tsx`
- Replace `categoryLabel`, `medicalCategories` with imports from generated file

## Implementation Order

1. **Create `compliance_registry.py`** — all 25 categories, 229 regulations, prompts, aliases, sources
2. **Create `generate_compliance_ts.py`** and generate the .ts file
3. **Update backend consumers** (gemini → compliance_service → jurisdiction_context → policy_draft → models)
4. **Update frontend consumers** (compliance.ts → JurisdictionData → Jurisdictions)
5. **Remove dead inline definitions**

## Verification

1. `python3 -c "from app.core.compliance_registry import *; print(f'{len(CATEGORIES)} categories, {len(REGULATIONS)} regulations')"` → `40 categories, 229 regulations`
2. Syntax check all modified `.py` files
3. `cd client && npx tsc --noEmit`
4. `python3 scripts/generate_compliance_ts.py` runs clean
5. Start server → run jurisdiction check → categories still resolve
6. Verify `get_missing_regulations("pharmacy_drugs", set())` returns all 10 pharmacy regulations
