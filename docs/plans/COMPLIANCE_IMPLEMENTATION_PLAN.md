# Compliance System Implementation Plan

> Three-phase implementation plan for completing the international compliance architecture. Each phase is independently deployable — no phase depends on a later phase being complete.

---

## Phase 1: Schema Foundation

**Goal**: Lock down the static contract — ORM models, enums, migration, key definitions. After this phase, all three data pipelines (Claude Code, API fetches, Gemini) write into a fully documented, validated schema.

**Estimated scope**: 10 files created/modified, 1 migration

### 1.1 ORM Models for Orphan Tables

Create `server/app/orm/key_definition.py` with three models matching existing DB tables:

| Model | Table | Columns |
|-------|-------|---------|
| `RegulationKeyDefinition` | `regulation_key_definitions` | 23 cols: id, key, category_slug, category_id, name, description, enforcing_agency, authority_source_urls, state_variance, base_weight, applies_to_levels, min_employee_threshold, applicable_entity_types, applicable_industries, **applicable_countries** (new), update_frequency, staleness_warning/critical/expired_days, key_group, created_by, notes, timestamps |
| `RegulationKeyDefinitionHistory` | `regulation_key_definition_history` | 8 cols: id, key_definition_id, field_changed, old_value, new_value, changed_at, changed_by, change_reason |
| `RepositoryAlert` | `repository_alerts` | 17 cols: id, alert_type, severity, jurisdiction_id, key_definition_id, requirement_id, category, regulation_key, message, days_overdue, status, timestamps, acknowledged/resolved tracking |

### 1.2 Enum Updates

Modify `server/app/orm/enums.py` — add values that exist in DB but not in Python:

```
JurisdictionLevel += national, province, region
```

### 1.3 ORM Exports + Column Fix

- `server/app/orm/__init__.py` — export 3 new models
- `server/app/orm/requirement.py` — widen `current_value` from `String(100)` to `String(500)`

### 1.4 Migration

Single migration `server/alembic/versions/s4t5u6v7w8x9_international_key_definitions.py`:

| Step | What |
|------|------|
| 1a | `ALTER TABLE regulation_key_definitions ADD COLUMN applicable_countries TEXT[]` |
| 1b | Update `applies_to_levels` to include `'national'` for all existing 353 keys |
| 1c | Seed ~50 new international key definitions (9 universal + 29 MX + 4 GB + 2 SG) |
| 1d | Create 3 national jurisdiction rows (UK, Mexico, Singapore) |
| 1e | Link existing city jurisdictions (London, Mexico City, Singapore) to national parents |
| 1f | Create precedence rules (UK: supersede all; Mexico: supersede labor + additive anti_discrimination) |
| 1g | `ALTER TABLE jurisdiction_requirements ALTER COLUMN current_value TYPE VARCHAR(500)` |
| 1h | Fix 13 miscategorized London requirements (overtime, leave, anti_discrimination) |
| 1i | Backfill `key_definition_id` for all requirements (direct match) |

### 1.5 Registry Update

Modify `server/app/core/compliance_registry.py`:
- Add `_INTERNATIONAL_REGULATION_KEYS` dict (~50 keys across 20 categories)
- Merge into `EXPECTED_REGULATION_KEYS`
- Add `_KEY_COUNTRY_SCOPE` dict mapping `(category, key)` → applicable countries

### Phase 1 Files

| File | Action |
|------|--------|
| `server/app/orm/key_definition.py` | **NEW** |
| `server/app/orm/enums.py` | **MODIFY** |
| `server/app/orm/__init__.py` | **MODIFY** |
| `server/app/orm/requirement.py` | **MODIFY** |
| `server/alembic/versions/s4t5u6v7w8x9_...py` | **NEW** |
| `server/app/core/compliance_registry.py` | **MODIFY** |

### Phase 1 Verification

```bash
# Run migration
cd server && alembic upgrade head

# Verify key definitions
psql: SELECT count(*) FROM regulation_key_definitions  -- expect ~400+

# Verify hierarchy
psql: SELECT city, country_code, level, parent_id IS NOT NULL
      FROM jurisdictions WHERE country_code IN ('GB','MX','SG')

# Verify precedence
psql: SELECT j.display_name, cc.slug, pr.precedence_type
      FROM precedence_rules pr JOIN jurisdictions j ON ...
      WHERE j.country_code IN ('GB','MX')

# Verify London fix
psql: SELECT category, regulation_key FROM jurisdiction_requirements jr
      JOIN jurisdictions j ON j.id = jr.jurisdiction_id
      WHERE j.city = 'London' AND jr.regulation_key = 'daily_weekly_overtime'
      -- should show category = 'overtime', not 'minimum_wage'
```

---

## Phase 2: Runtime Safety

**Goal**: Make the compliance service, gap detection, and ingest pipeline country-aware. After this phase, international jurisdictions work correctly end-to-end without producing false positives or cross-country data leaks.

**Estimated scope**: 4 files modified

### 2.1 CTE Country Safety

Modify `server/app/core/services/compliance_service.py` — `resolve_jurisdiction_stack()` (~line 8107):

- Add `country_code` to SELECT columns in the recursive CTE
- Add `WHERE j.country_code = jc.country_code` to the recursive join
- Prevents hierarchy walks from crossing country boundaries

### 2.2 Country-Aware Gap Detection

Modify `server/app/core/compliance_registry.py` — `get_missing_regulations()` (~line 4565):

- Add `country_code: str = "US"` parameter
- Filter `EXPECTED_REGULATION_KEYS` by `_KEY_COUNTRY_SCOPE` when country != US
- Update all callers to pass `country_code`

### 2.3 Country-Filtered Context

Modify `server/scripts/jurisdiction_context.py` (~line 77):

- When `country_code != 'US'`, query `regulation_key_definitions` filtered by `applicable_countries`
- Return only country-relevant expected keys (not US tipped_minimum_wage for UK jurisdictions)

### 2.4 Ingest Key Linking Validation

Modify `server/scripts/ingest_research_md.py` (~line 269):

- Add JOIN to `jurisdictions` in the `key_definition_id` backfill query
- Add `WHERE (rkd.applicable_countries IS NULL OR j.country_code = ANY(rkd.applicable_countries))`
- Prevents linking country-restricted key definitions to wrong jurisdictions

### Phase 2 Files

| File | Action |
|------|--------|
| `server/app/core/services/compliance_service.py` | **MODIFY** — CTE safety |
| `server/app/core/compliance_registry.py` | **MODIFY** — gap detection |
| `server/scripts/jurisdiction_context.py` | **MODIFY** — context filtering |
| `server/scripts/ingest_research_md.py` | **MODIFY** — link validation |

### Phase 2 Verification

```bash
# CTE safety — London should only return GB jurisdictions
./venv/bin/python -c "
# resolve_jurisdiction_stack(london_id) should return 2 rows:
# London (city) + UK (national), both GB
"

# Gap detection — MX should not see US-only keys
./venv/bin/python -c "
from app.core.compliance_registry import get_missing_regulations
missing = get_missing_regulations('minimum_wage', set(), 'MX')
# Should include national_minimum_wage, NOT tipped_minimum_wage
"

# Context — MX jurisdiction_context should show MX keys
./venv/bin/python scripts/jurisdiction_context.py 'Mexico City' CDMX --country MX
# expected_regulation_keys should include aguinaldo, PTU, not US keys

# Ingest dry-run
./venv/bin/python scripts/ingest_research_md.py scripts/mexico_city_mx_research.md \
    --city "Mexico City" --state CDMX --country MX --dry-run
# All keys should map to key_definition_id
```

---

## Phase 3: Data Ingest + Jurisdiction Linking

**Goal**: Populate the system with researched compliance data and ensure new jurisdictions auto-link to their national parent. After this phase, Mexico City, NYC life sciences, and Boston life sciences data is live.

**Estimated scope**: 1 file modified, 3 ingest runs

### 3.1 Auto-Link Parent for International Jurisdictions

Modify `server/scripts/create_jurisdiction.py`:

- When `country_code != 'US'`, look up national-level jurisdiction for that country
- Auto-set `parent_id` on the new city jurisdiction
- Avoids manual parent linking for future international jurisdictions

### 3.2 Ingest Research Data

Run ingest for the three completed research files:

```bash
# Mexico City — 58 requirements (labor + healthcare + oncology)
./venv/bin/python scripts/ingest_research_md.py scripts/mexico_city_mx_research.md \
    --city "Mexico City" --state CDMX --country MX

# NYC life sciences — 11 requirements
./venv/bin/python scripts/ingest_research_md.py scripts/new_york_city_ny_life_sciences_research.md \
    --city "New York City" --state NY

# Boston life sciences — 8 requirements
./venv/bin/python scripts/ingest_research_md.py scripts/boston_ma_life_sciences_research.md \
    --city Boston --state MA
```

### Phase 3 Files

| File | Action |
|------|--------|
| `server/scripts/create_jurisdiction.py` | **MODIFY** — auto parent linking |

### Phase 3 Verification

```bash
# Verify ingest counts
psql: SELECT j.city, j.country_code, count(jr.id)
      FROM jurisdiction_requirements jr
      JOIN jurisdictions j ON j.id = jr.jurisdiction_id
      WHERE j.city IN ('Mexico City', 'New York City', 'Boston')
      GROUP BY j.city, j.country_code
# Mexico City: 58, NYC: existing + 11, Boston: existing + 8

# Verify key_definition_id linkage for new data
psql: SELECT count(*), count(key_definition_id)
      FROM jurisdiction_requirements jr
      JOIN jurisdictions j ON j.id = jr.jurisdiction_id
      WHERE j.city = 'Mexico City'
# Both counts should be 58 (all linked)

# Test auto parent linking
./venv/bin/python scripts/create_jurisdiction.py "Guadalajara" "JAL" --country MX
# Should auto-link to Mexico national parent
```

---

## Summary

| Phase | Goal | Files | Deployable independently? |
|-------|------|-------|--------------------------|
| **1** | Schema foundation — ORM, migration, key definitions | 6 | Yes |
| **2** | Runtime safety — country-aware queries and gap detection | 4 | Yes (requires Phase 1) |
| **3** | Data ingest — populate MX/NYC/Boston + auto-linking | 1 + 3 ingests | Yes (requires Phase 1+2) |

**Total**: 11 files, 1 migration, 3 data ingests

## Deferred Work (not in scope)

- US key normalization: 1,668 legacy descriptive keys → 353 canonical keys
- Admin cherry-pick endpoint: `POST /admin/locations/{location_id}/requirements/add`
- Admin coverage dashboard: filter by `country_code`
- `_filter_with_preemption()`: guard for non-US country_code
- ORM models for remaining 21 compliance tables (prioritized in architecture doc)
