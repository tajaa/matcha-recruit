# International Jurisdiction Support Plan

## Context

The compliance system currently only handles US jurisdictions. The `jurisdictions` table requires a 2-letter US state code, all compliance categories use US-specific regulation keys (FMLA, OSHA, etc.), and the scripts/skills validate against a hardcoded `US_STATE_CODES` set. The user needs to support international cities like Singapore, London, and Mexico City for clients like Giti Tire (manufacturing).

This plan adds international support incrementally — preserving all existing US functionality while enabling international jurisdiction creation and compliance research.

---

## Phase 1: Database Schema (Alembic Migration)

**New migration file**: `server/alembic/versions/zn1o2p3q4r5s_add_international_support.py`

### 1A. Extend Postgres ENUM `jurisdiction_level_enum`
The `jurisdictions.level` column uses a Postgres ENUM type (not VARCHAR). Must add new values:
```sql
ALTER TYPE jurisdiction_level_enum ADD VALUE IF NOT EXISTS 'national';
ALTER TYPE jurisdiction_level_enum ADD VALUE IF NOT EXISTS 'province';
ALTER TYPE jurisdiction_level_enum ADD VALUE IF NOT EXISTS 'region';
```
**Note**: `ALTER TYPE ADD VALUE` cannot run inside a transaction in Postgres — the migration must use `op.execute()` outside the transaction or set `autocommit=True`.

### 1B. `jurisdictions` table
- Add `country_code VARCHAR(2) NOT NULL DEFAULT 'US'` (ISO 3166-1 alpha-2)
- Widen `state VARCHAR(2)` → `state VARCHAR(10)` (Mexico uses "CDMX", etc.)
- Make `state` nullable (city-states like Singapore have no subdivision)
- Drop `UNIQUE(city, state)` → Add `UNIQUE(city, state, country_code)`
- Add index on `country_code`

### 1C. `business_locations` table
- Add `country_code VARCHAR(2) NOT NULL DEFAULT 'US'`
- Widen `state VARCHAR(2) NOT NULL` → `state VARCHAR(10)` and make nullable
- Make `zipcode` nullable (`VARCHAR(10) NOT NULL` → `VARCHAR(10)`) — international addresses may not have zip codes

### 1D. `structured_data_cache` table
- Add `country_code VARCHAR(2) NOT NULL DEFAULT 'US'`
- Widen `state VARCHAR(2) NOT NULL` → `state VARCHAR(10)` and make nullable

### 1E. `jurisdiction_reference` table (if exists)
- Add `country_code`, widen `state`, update unique constraint

All use `DEFAULT 'US'` — zero impact on existing data.

### 1F. Update `database.py` init_db()
- Update CREATE TABLE statements to include `country_code` with defaults
- Update backfill queries to pass `'US'`

**Files**: `server/alembic/versions/` (new), `server/app/database.py`

---

## Phase 2: Models & Registry

### 2A. Extend `JurisdictionLevel` enum
**File**: `server/app/core/models/compliance.py`

Add `national` and `province` as first-class levels (not aliased to "federal"):
```
national    # Country-level law (international)
province    # Subnational division (international)
region      # UK constituent countries, etc.
```

Update `JURISDICTION_PRIORITY` in `server/app/core/services/compliance_service.py`:
```python
{"city": 1, "county": 2, "state": 3, "province": 3, "region": 3, "federal": 4, "national": 4}
```

### 2B. Add manufacturing categories
**File**: `server/app/core/compliance_registry.py`

New group `"manufacturing"` with 6 categories:
- `environmental_permits` — Environmental Permits & Emissions
- `chemical_safety` — Chemical Safety & Hazardous Materials
- `import_export` — Import/Export & Trade Compliance
- `product_safety` — Product Safety & Quality Standards
- `machinery_safety` — Machinery & Equipment Safety
- `noise_vibration` — Noise & Vibration Limits

Add `MANUFACTURING_CATEGORIES` frozenset.

### 2C. Add international regulation keys to `regulation_key_definitions`

**NOTE**: As of the First-Class Regulation Key System (March 2026), key definitions live in the `regulation_key_definitions` **database table**, not in Python code. International keys are added via:

1. **Alembic seed migration** — INSERT rows into `regulation_key_definitions` for international keys
2. **Admin CRUD** — new keys can be added at runtime without code deploys

International keys to seed:

**Universal international labor keys** (apply to all non-US jurisdictions):
- `national_minimum_wage`, `sectoral_minimum_wage` — key_group: `intl_wage_rates`
- `annual_leave_entitlement`, `statutory_maternity_leave`, `statutory_paternity_leave` — key_group: `intl_leave_programs`
- `statutory_sick_leave`, `statutory_notice_period_employer`, `statutory_notice_period_employee` — key_group: `intl_termination`
- `severance_pay`, `redundancy_pay`, `probation_period` — key_group: `intl_termination`
- `social_insurance_employer`, `social_insurance_employee` — key_group: `intl_social_insurance`
- `thirteenth_month_pay`, `mandatory_bonus` — key_group: `intl_compensation`

**Country-specific keys** (scoped via `applicable_industries` or `applicable_entity_types`):
- `sg_cpf_contribution` — applies_to: Singapore only
- `mx_aguinaldo` — applies_to: Mexico only
- `gb_national_living_wage` — applies_to: UK only

**Manufacturing keys** (new category group):
- `environmental_impact_assessment`, `emissions_permits`, `waste_management_license` — key_group: `manufacturing_environmental`
- `hazardous_materials_handling`, `chemical_inventory_reporting` — key_group: `manufacturing_chemical`
- `import_license`, `export_controls`, `customs_compliance` — key_group: `manufacturing_trade`

Each key gets:
- `enforcing_agency` — the country's relevant ministry/agency
- `staleness_warning_days` — typically longer for international (180-365) since laws change less frequently in many jurisdictions
- `applicable_industries` — manufacturing keys scoped to `["manufacturing"]`
- `applies_to_levels` — `'{national,province}'` instead of `'{state,city}'`

The Python registry (`_LABOR_REGULATION_KEYS`, `_ONCOLOGY_REGULATION_KEYS`) remains as a **read cache** — it's loaded from the DB at startup. No Python code changes needed for new international keys.

The `key-coverage` API and `integrity-check` endpoint automatically pick up international keys since they query `regulation_key_definitions` directly. The `KeyCoverageDrawer` UI shows them alongside US keys with no changes needed.

### 2D. Update Gemini compliance service
**File**: `server/app/core/services/gemini_compliance.py`

- Add `"national"` and `"province"` to `VALID_JURISDICTION_LEVELS` (line 39)
- Stop aliasing `"national"` → `"federal"` in `_JURISDICTION_LEVEL_ALIASES` (line 57)
- Update `_build_category_prompt()` (line 374) to accept `country_code` param — when not US, change language from "state baseline" to "national law", remove US-specific references (FMLA, OSHA, tip credits)
- **Update JSON response schema** in `_build_category_prompt()` (line 404) — currently hardcodes `"jurisdiction_level": "state" | "county" | "city"`. Must add `"national" | "province"` for international
- Update `_coerce_requirement_shape()` to accept `"national"` and `"province"` without aliasing them away

### 2E. Update Pydantic models for international
**File**: `server/app/core/models/compliance.py`

- `LocationCreate.state` is currently `str` (required) → make `Optional[str]` for international
- `BusinessLocation.state` is `str` → make `Optional[str]`
- Add `country_code: str = "US"` to both `LocationCreate` and `BusinessLocation`

**Files**: `server/app/core/models/compliance.py`, `server/app/core/compliance_registry.py`, `server/app/core/services/compliance_service.py`, `server/app/core/services/gemini_compliance.py`

### Caveats discovered during review
- `jurisdiction_level` in `jurisdiction_requirements` and `structured_data_cache` is `VARCHAR(20)` (not the Postgres ENUM) — so those columns accept any string value. Only `jurisdictions.level` uses the ENUM.
- `business_locations.zipcode` is `NOT NULL` in the DB schema but `Optional[str]` in the Pydantic model — the migration must make the DB column nullable to match.
- `city` column in `jurisdictions` was already made nullable by a prior migration (to support state-level rows).

---

## Phase 3: Scripts

### 3A. Update `create_jurisdiction.py`
- Add `--country` argument (default: `US`)
- When US: validate state against `US_STATE_CODES` (unchanged behavior)
- When not US: accept state as freeform or empty (e.g., Singapore has none)
- Update INSERT to include `country_code`
- Update duplicate check: `WHERE LOWER(city) = LOWER($1) AND COALESCE(state, '') = COALESCE($2, '') AND country_code = $3`
- Display name: US → `"Houston, TX"`, international → `"Singapore, SG"` or `"London, ENG, GB"`

### 3B. Update `jurisdiction_context.py`
- Add `--country` argument
- Skip `state_preemption_rules` lookup for non-US (preemption is a US concept)
- Skip `has_local_ordinance` for non-US
- Include `country_code` in output JSON
- For non-US, include manufacturing categories in groups if `--categories manufacturing`

### 3C. Update `bootstrap_jurisdiction.py`
- Add `--country` argument, same validation logic as create_jurisdiction.py
- Add `--categories manufacturing` option
- Pass country context to Gemini research prompts

**Files**: `server/scripts/create_jurisdiction.py`, `server/scripts/jurisdiction_context.py`, `server/scripts/bootstrap_jurisdiction.py`

---

## Phase 4: New Skill — `/research-jurisdiction-intl`

**File**: `.claude/commands/research-jurisdiction-intl.md`

Separate skill from the US version because research approach differs fundamentally:
- **US**: "What state/city-specific laws go BEYOND federal baseline?"
- **International**: "What are the employment/manufacturing laws in {country}? What local variations exist for {city}?"

### Skill flow:
1. Parse city + country (+ optional state/region) from `$ARGUMENTS`
2. Create jurisdiction via `create_jurisdiction.py --country XX`
3. Get context via `jurisdiction_context.py --country XX`
4. Research using country-specific search queries:
   - `"{country} employment law minimum wage {year}"`
   - `"{country} statutory annual leave entitlement"`
   - `"{country} termination notice period severance"`
   - `"{country} manufacturing environmental compliance"`
   - `"{country} {city} local employment regulations"`
5. Write markdown to `scripts/{city}_{country}_research.md`

### Category mapping for international:
| Category | International Research Focus |
|----------|------------------------------|
| `minimum_wage` | National/sectoral minimum wage, progressive wage models |
| `overtime` | OT rates (may differ from US 1.5x), max hours, rest day pay |
| `sick_leave` | Statutory sick leave (most countries mandate it unlike US) |
| `leave` | Annual leave, maternity/paternity, notice periods, severance, 13th month/bonus (critical internationally) |
| `meal_breaks` | Working time regulations, rest periods |
| `workers_comp` | Work injury insurance, social insurance contributions |
| `workplace_safety` | National safety authority, factory inspections |
| `anti_discrimination` | Protected characteristics (varies by country) |
| `environmental_permits` | (manufacturing) Environmental impact assessments |
| `import_export` | (manufacturing) Trade compliance, customs |

### Output format:
Same as US skill — `regulation_key`, `jurisdiction_level` (using `national`/`province` instead of `federal`/`state`), `source_url`, etc.

**Files**: `.claude/commands/research-jurisdiction-intl.md`, `.claude/commands/README.md`

---

## Phase 5: Update Models & Routes (deferred)

Update `BusinessLocation`, `LocationCreate`, `HierarchicalComplianceResponse` in `server/app/core/models/compliance.py` to include optional `country_code` field. Update compliance routes to pass country context. This can be a follow-up PR after the foundation is solid.

---

## Implementation Sequence

| Step | What | Files | Risk |
|------|------|-------|------|
| 1 | Alembic migration (country_code + widen state + ENUM) | `alembic/versions/`, `database.py` | **Production DB** — needs user approval |
| 2 | Registry + models (manufacturing categories, intl keys, jurisdiction levels) | `compliance_registry.py`, `models/compliance.py`, `compliance_service.py` | Low — additive only |
| 3 | Gemini prompt updates (country awareness) | `gemini_compliance.py` | Low — only affects new research |
| 4 | Scripts (--country flag) | `create_jurisdiction.py`, `jurisdiction_context.py`, `bootstrap_jurisdiction.py` | Low — backward compatible |
| 5 | New skill (`/research-jurisdiction-intl`) | `.claude/commands/` | None — new file |

Steps 1-5 can ship as one PR. Step 1 requires explicit user approval before running the migration.

---

## Verification

1. **Existing US flow**: Run `/research-jurisdiction Houston TX` — should work identically
2. **New international flow**: Run `/research-jurisdiction-intl Singapore SG` — should create jurisdiction with `country_code='SG'`, research Singapore employment law
3. **DB check**: `SELECT city, state, country_code FROM jurisdictions` — existing rows should all have `country_code='US'`
4. **Manufacturing**: Run `/research-jurisdiction-intl --categories manufacturing "Mexico City" MX --state CDMX` — should include manufacturing categories
5. **Gemini pipeline**: Run `/bootstrap-jurisdiction --country SG Singapore` — should work with country-aware prompts
6. **Key definitions**: `SELECT count(*) FROM regulation_key_definitions WHERE applies_to_levels @> '{national}'` — should return international key count
7. **Integrity check**: `GET /admin/jurisdictions/integrity-check?jurisdiction_id=<singapore_id>` — should show international keys as expected, not US-only keys
8. **Key coverage**: `GET /admin/jurisdictions/key-coverage?jurisdiction_id=<singapore_id>` — should show intl_wage_rates, intl_leave_programs groups
9. **Staleness SLAs**: International keys should have longer thresholds (180-365 days warning) than US wage keys (30 days)

---

## Interaction with First-Class Regulation Key System

The international expansion builds directly on the `regulation_key_definitions` table (implemented March 2026). Key integration points:

| System Component | How International Uses It |
|-----------------|--------------------------|
| `regulation_key_definitions` | International keys seeded with `applies_to_levels = '{national,province}'` and country-specific `applicable_industries` |
| `key_group` | New groups: `intl_wage_rates`, `intl_leave_programs`, `intl_termination`, `intl_social_insurance`, `manufacturing_*` |
| `staleness_warning_days` | International defaults: 180 (vs 30-90 for US wage keys) — laws change less frequently in many jurisdictions |
| `resolve_weight()` | Manufacturing keys get high weight for manufacturing companies, low weight for healthcare — contextual scoring works automatically |
| `repository_alerts` | Staleness check covers international jurisdictions — `POST /admin/jurisdictions/run-staleness-check` works for all country codes |
| `KeyCoverageDrawer` | UI shows international keys alongside US keys with no changes — groups display as `intl_wage_rates 3/5` |
| `integrity-check` | Bidirectional check respects `applies_to_levels` — won't flag US-only keys as missing for Singapore |

No new tables needed — the existing `regulation_key_definitions` + `repository_alerts` infrastructure handles international keys as first-class citizens.
