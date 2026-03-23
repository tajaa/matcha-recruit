# Compliance Database Schema Redesign
## Hierarchical Jurisdiction Precedence with Full Policy Granularity

**Date:** 2026-03-17
**Status:** Implementation Plan — ready for execution

---

## Context

We're building a healthcare compliance intelligence platform where the database is the single source of truth for every regulation a facility is subject to. The current schema has flat category abstractions, duplicated federal data, no explainability, and no ORM. This redesign introduces:

- Hierarchical jurisdiction precedence (federal → state → county → city → special_district)
- Granular per-policy rows with canonical keys, fetch hashes, and change tracking
- A `compliance_categories` table replacing 45 hardcoded Python entries
- Precedence rules with structured reasoning replacing flat boolean preemption
- SQLAlchemy ORM models as schema source of truth
- A resolution query (recursive CTE) that returns the full jurisdiction stack with governing logic

**10 changes total.** SQLAlchemy is NOT currently a dependency. All 125 existing tables use raw SQL via asyncpg. Alembic has `target_metadata = None`.

---

## Phase 1: SQLAlchemy Infrastructure

### 1a. Add dependency

**File:** `server/requirements.txt` — add `sqlalchemy[asyncio]>=2.0.25`

### 1b. Create ORM package

**New directory:** `server/app/orm/` (NOT `server/app/models/` — that's the deprecated Pydantic re-export shim)

```
server/app/orm/
    __init__.py          # Exports Base, all models
    base.py              # DeclarativeBase, naming conventions, TimestampMixin
    enums.py             # All PostgreSQL ENUM types
    jurisdiction.py      # Jurisdiction, ComplianceCategory, PrecedenceRule
    requirement.py       # JurisdictionRequirement, PolicyChangeLog
    compliance.py        # ComplianceRequirement (per-location)
    employee.py          # EmployeeJurisdiction
    location.py          # BusinessLocation (schema-only mirror for FK refs)
```

### 1c. `server/app/orm/base.py`

```python
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime, func
from datetime import datetime

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
```

### 1d. `server/app/orm/enums.py`

9 PostgreSQL ENUM types:

| Enum | Values |
|------|--------|
| `JurisdictionLevel` | federal, state, county, city, special_district |
| `PrecedenceType` | floor, ceiling, supersede, additive |
| `PrecedenceRuleStatus` | active, pending_review, repealed |
| `RequirementStatus` | active, pending, repealed, superseded, under_review |
| `SourceTier` | tier_1_government, tier_2_official_secondary, tier_3_aggregator |
| `ChangeSource` | ai_fetch, manual_review, legislative_update, system_migration |
| `EmployeeJurisdictionRelType` | licensed_in, works_at, telehealth_coverage, historical |
| `CategoryDomain` | labor, privacy, clinical, billing, licensing, safety, reporting, emergency, corporate_integrity |
| `GovernanceSource` | precedence_rule, default_local, not_evaluated |

### 1e. Modify `server/alembic/env.py`

```python
# Replace: target_metadata = None
from app.orm import Base
target_metadata = Base.metadata

# Add include_name filter to prevent dropping unmodeled legacy tables
def include_name(name, type_, parent_names):
    if type_ == "table":
        return name in target_metadata.tables
    return True

# In do_run_migrations:
def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()
```

**Critical:** The `include_name` filter means autogenerate only manages tables with ORM models. All 125 legacy tables are invisible.

### 1f. Dual engine strategy

SQLAlchemy is used ONLY for schema definition + migration generation. All runtime queries stay on the existing asyncpg pool in `database.py`. No SQLAlchemy Session at runtime.

---

## Phase 2: ORM Model Definitions (7 models)

### 2a. `Jurisdiction` (modified) — `server/app/orm/jurisdiction.py`

Existing columns mirrored exactly + new `level` column:

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | gen_random_uuid() |
| city | VARCHAR(100) | **nullable** — NULL for federal and state rows. Only populated for city/county/special_district. Eliminates empty-string convention. |
| state | VARCHAR(2) NOT NULL | 'US' for federal row |
| county | VARCHAR(100) | nullable |
| display_name | VARCHAR(200) NOT NULL | **NEW.** Human-readable: "Federal", "California", "San Francisco, CA", "Miami-Dade County, FL". Computed on insert/update. Every query that needs a label reads this instead of concatenating city/state. |
| **level** | **JurisdictionLevel enum** | **NEW. NOT NULL DEFAULT 'city'** |
| parent_id | UUID FK self | ON DELETE SET NULL |
| last_verified_at | TIMESTAMP | nullable |
| requirement_count | INTEGER DEFAULT 0 | |
| legislation_count | INTEGER DEFAULT 0 | |
| created_at, updated_at | TIMESTAMP | |

Constraints: UNIQUE(city, state) — PostgreSQL treats NULLs as distinct in unique constraints, so federal (NULL, 'US') and each state (NULL, 'CA') are unique. Partial unique index `CREATE UNIQUE INDEX uq_jurisdictions_state_level ON jurisdictions (state) WHERE city IS NULL AND level IN ('federal', 'state')` prevents duplicate state-level rows.
Indexes: level, parent_id, state.
Relationships: parent (self), children (self), requirements.

### 2b. `ComplianceCategory` (new) — `server/app/orm/jurisdiction.py`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| slug | VARCHAR(60) UNIQUE NOT NULL | e.g. "minimum_wage", "hipaa_privacy" |
| name | VARCHAR(255) NOT NULL | human-readable |
| description | TEXT | nullable |
| parent_category_id | UUID FK self | nullable, for subcategories |
| domain | CategoryDomain enum NOT NULL | labor, privacy, clinical, etc. |
| group | VARCHAR(30) NOT NULL | preserves existing group (labor/healthcare/oncology/etc.) |
| industry_tag | VARCHAR(60) | nullable |
| research_mode | VARCHAR(30) DEFAULT 'default_sweep' | |
| docx_section | INTEGER | nullable |
| sort_order | INTEGER DEFAULT 0 | |
| created_at, updated_at | TIMESTAMP | |

Indexes: domain, group.

**Domain mapping from existing groups:**
- labor, supplementary → `labor`
- healthcare → per-category: hipaa_privacy→`privacy`, billing_integrity→`billing`, clinical_safety→`clinical`, healthcare_workforce→`clinical`, corporate_integrity→`corporate_integrity`, research_consent→`clinical`, state_licensing→`licensing`, emergency_preparedness→`emergency`
- oncology → `safety`
- medical_compliance → per-category (cybersecurity→`safety`, quality_reporting→`reporting`, pharmacy_drugs→`clinical`, telehealth→`clinical`, environmental_safety→`safety`, etc.)

### 2c. `PrecedenceRule` (new) — `server/app/orm/jurisdiction.py`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| category_id | UUID FK compliance_categories NOT NULL | |
| higher_jurisdiction_id | UUID FK jurisdictions NOT NULL | the jurisdiction that sets the baseline |
| lower_jurisdiction_id | UUID FK jurisdictions | **nullable** — specific child jurisdiction, or NULL when `applies_to_all_children = true` |
| applies_to_all_children | BOOLEAN NOT NULL DEFAULT false | when true, rule applies to every descendant of higher_jurisdiction_id; lower_jurisdiction_id must be NULL |
| precedence_type | PrecedenceType enum NOT NULL | floor/ceiling/supersede/additive |
| trigger_condition | JSONB | nullable — structured boolean expression |
| reasoning_text | TEXT | human-readable explanation |
| legal_citation | VARCHAR(500) | e.g. "Cal. Civ. Code §56.10" |
| effective_date | DATE | nullable |
| sunset_date | DATE | nullable |
| last_verified_at | TIMESTAMP | nullable |
| status | PrecedenceRuleStatus enum DEFAULT 'active' | |
| created_at, updated_at | TIMESTAMP | |

Constraints: UNIQUE(category_id, higher_jurisdiction_id, lower_jurisdiction_id) where lower_jurisdiction_id IS NOT NULL. CHECK: `(applies_to_all_children = true AND lower_jurisdiction_id IS NULL) OR (applies_to_all_children = false AND lower_jurisdiction_id IS NOT NULL)`.
Indexes: category_id, status, lower_jurisdiction_id, **higher_jurisdiction_id**.

**No wildcard convention.** Instead, `applies_to_all_children = true` with `lower_jurisdiction_id = NULL` explicitly means "this rule governs between higher_jurisdiction and every jurisdiction beneath it in the tree." Specific pair rules (both IDs set, `applies_to_all_children = false`) take priority over blanket rules during resolution.

### 2d. `JurisdictionRequirement` (modified) — `server/app/orm/requirement.py`

All existing columns mirrored + new columns:

| New Column | Type | Notes |
|------------|------|-------|
| **canonical_key** | VARCHAR(255) UNIQUE | idempotency key: `ca_san_diego_minimum_wage_iwo_2024` |
| **category_id** | UUID FK compliance_categories | nullable initially, **ALTER to NOT NULL after backfill in Migration 4** |
| **summary** | TEXT | plain-English description |
| **full_text_reference** | TEXT | URL/path to authoritative source |
| **statute_citation** | VARCHAR(500) | formal legal citation |
| **fetch_hash** | VARCHAR(64) | SHA-256 of **normalized** fetched content. Normalization: strip leading/trailing whitespace, collapse internal whitespace runs to single space, normalize Unicode to NFC, strip HTML tags if HTML source, lowercase. This prevents phantom changes from whitespace/encoding drift between fetches flooding policy_change_log. Hash is computed by a shared `normalize_and_hash(raw_content: str) -> str` utility. |
| **status** | RequirementStatus enum DEFAULT 'active' | active/pending/repealed/superseded/under_review |
| **superseded_by_id** | UUID FK self | nullable |
| **applicable_entity_types** | JSONB | clinic, hospital, SNF, etc. |
| **trigger_conditions** | JSONB | when this policy applies to a facility |
| **metadata** | JSONB | overflow |

**source_tier migration:** INTEGER (1/2/3) → SourceTier enum (tier_1_government/tier_2_official_secondary/tier_3_aggregator). Requires column swap.

Indexes: canonical_key, category_id, status, source_tier (added to existing jurisdiction_id, rate_type indexes).

### 2e. `PolicyChangeLog` (new) — `server/app/orm/requirement.py`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| requirement_id | UUID FK jurisdiction_requirements NOT NULL | ON DELETE CASCADE |
| field_changed | VARCHAR(100) NOT NULL | |
| old_value | TEXT | nullable |
| new_value | TEXT | nullable |
| changed_at | TIMESTAMP DEFAULT NOW() | |
| change_source | ChangeSource enum NOT NULL | ai_fetch/manual_review/legislative_update/system_migration |
| change_reason | TEXT | nullable |

Indexes: requirement_id, changed_at.

### 2f. `ComplianceRequirement` (modified) — `server/app/orm/compliance.py`

All existing columns mirrored + 2 new explainability columns:

| New Column | Type | Notes |
|------------|------|-------|
| **governing_jurisdiction_level** | VARCHAR(20) | nullable — which level's policy governs for this category |
| **governing_precedence_rule_id** | UUID FK precedence_rules | nullable — which rule determined governance |
| **governance_source** | VARCHAR(20) NOT NULL DEFAULT 'not_evaluated' | enum: `precedence_rule` (rule matched), `default_local` (no rule, most-local wins), `not_evaluated` (sync hasn't run yet). Disambiguates NULL rule_id: `default_local` + NULL rule_id means "we checked, no rule applies, local governs." `not_evaluated` + NULL means "sync hasn't populated this yet." |

### 2g. `EmployeeJurisdiction` (new) — `server/app/orm/employee.py`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| employee_id | UUID FK employees NOT NULL | ON DELETE CASCADE |
| jurisdiction_id | UUID FK jurisdictions NOT NULL | ON DELETE CASCADE |
| relationship_type | EmployeeJurisdictionRelType enum NOT NULL | licensed_in/works_at/telehealth_coverage/historical |
| effective_date | DATE | nullable |
| end_date | DATE | nullable |
| created_at | TIMESTAMP | |

Constraints: UNIQUE(employee_id, jurisdiction_id, relationship_type).
Indexes: employee_id, jurisdiction_id, relationship_type.

**RLS policy** (exact SQL):
```sql
ALTER TABLE employee_jurisdictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_jurisdictions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON employee_jurisdictions
    USING (
        employee_id IN (
            SELECT id FROM employees
            WHERE org_id::text = current_setting('app.current_tenant_id', true)
        )
        OR current_setting('app.is_admin', true) = 'true'
    );
```
This matches the existing RLS pattern in `e72bfad5eca9_add_row_level_security.py`. The subquery is acceptable here because `employee_id` is indexed and the employees table has an index on `org_id`. The admin bypass clause mirrors other tenant isolation policies.

### 2h. `BusinessLocation` (schema-only mirror) — `server/app/orm/location.py`

Read-only ORM model mirroring the existing `business_locations` table so other models can declare FK relationships to it. No new columns.

---

## Phase 3: Alembic Migrations (5 sequential)

All migrations use `op.execute()` with raw SQL (consistent with existing pattern) but are generated from the ORM model diffs as a starting point, then manually adjusted.

### Migration 1: Create ENUMs + compliance_categories

1. Create all 8 PostgreSQL ENUM types
2. CREATE TABLE `compliance_categories`
3. Seed 45 rows from `CATEGORIES` in `compliance_registry.py`

### Migration 2: Modify jurisdictions

1. ADD COLUMN `level jurisdiction_level_enum NOT NULL DEFAULT 'city'`
2. ADD COLUMN `display_name VARCHAR(200)`
3. ALTER COLUMN `city` DROP NOT NULL — make nullable
4. UPDATE existing state rows: `SET level = 'state', city = NULL WHERE city = '' AND state != 'US'`
5. UPDATE county rows: `SET level = 'county' WHERE city LIKE '_county_%'`
6. INSERT federal row: `city=NULL, state='US', level='federal', display_name='Federal'`
7. Link state rows → federal: `UPDATE jurisdictions SET parent_id = <federal_id> WHERE level = 'state' AND parent_id IS NULL`
8. Backfill display_name for all rows:
   - federal: `'Federal'`
   - state: state full name from lookup (e.g., `'California'`)
   - county: `'{county}, {state}'` (e.g., `'Miami-Dade County, FL'`)
   - city: `'{city}, {state}'` (e.g., `'San Francisco, CA'`)
9. ALTER `display_name` SET NOT NULL after backfill
10. Add index on `level`
11. Add partial unique index: `CREATE UNIQUE INDEX uq_jurisdictions_state_level ON jurisdictions (state) WHERE city IS NULL AND level IN ('federal', 'state')`
12. Drop old UNIQUE(city, state) constraint, add new one that handles NULLs: `CREATE UNIQUE INDEX uq_jurisdictions_city_state ON jurisdictions (COALESCE(city, ''), state)`

### Migration 3: Create precedence_rules + migrate preemption data

1. CREATE TABLE `precedence_rules`
2. Migrate from `state_preemption_rules`:
   - `allows_local_override = true` → `precedence_type = 'floor'`
   - `allows_local_override = false` → `precedence_type = 'ceiling'`
   - `higher_jurisdiction_id` = state jurisdiction for that state
   - `lower_jurisdiction_id` = **NULL** (blanket rule)
   - `applies_to_all_children` = **true** (applies to every city/county under the state)
   - `category_id` = lookup from compliance_categories by slug
3. Do NOT drop `state_preemption_rules` yet — keep for backward compat

### Migration 4: Modify jurisdiction_requirements + create policy_change_log

1. Add new columns: canonical_key, category_id, summary, full_text_reference, statute_citation, fetch_hash, status, superseded_by_id, applicable_entity_types, trigger_conditions, metadata
2. Migrate source_tier: INTEGER → source_tier_enum (add new column, backfill, drop old, rename)
3. Backfill category_id from compliance_categories via slug match on category column
4. **ALTER category_id to NOT NULL** — after backfill, no row should be orphaned. Any rows with unknown category get a fallback "uncategorized" category or are flagged for review. The string `category` column remains for backward compat but `category_id` is the canonical FK going forward.
5. Backfill canonical_key from existing requirement_key + jurisdiction context
6. CREATE TABLE `policy_change_log`
7. Add indexes: canonical_key, category_id, status

### Migration 5: Modify compliance_requirements + create employee_jurisdictions

1. Add governing_jurisdiction_level, governing_precedence_rule_id, governance_source (enum, NOT NULL DEFAULT 'not_evaluated') to compliance_requirements
2. CREATE TABLE `employee_jurisdictions`
3. Migrate work_state data: INSERT into employee_jurisdictions with relationship_type='works_at'
4. Migrate work_location_id data: INSERT city-level jurisdiction links
5. Add RLS policy on employee_jurisdictions
6. Add deprecation comment on employees.work_state (do NOT drop)

---

## Phase 4: Service Layer — Resolution Query

### 4a. New function: `resolve_jurisdiction_stack()`

**File:** `server/app/core/services/compliance_service.py`

Recursive CTE that, given a `jurisdiction_id`:
1. Walks `parent_id` up to federal (depth 0 = leaf, depth N = federal)
2. Joins `jurisdiction_requirements` at each level (WHERE status = 'active')
3. LEFT JOINs `precedence_rules` (WHERE status = 'active' AND higher/lower jurisdiction in chain)
4. Returns all rows ordered by category + depth

```sql
WITH RECURSIVE jurisdiction_chain AS (
    -- Walk parent_id from leaf up to federal
    SELECT id, city, state, level, parent_id, 0 AS depth
    FROM jurisdictions WHERE id = $1
    UNION ALL
    SELECT j.id, j.city, j.state, j.level, j.parent_id, jc.depth + 1
    FROM jurisdictions j JOIN jurisdiction_chain jc ON j.id = jc.parent_id
),
chain_requirements AS (
    SELECT jr.*, jr.category_id AS req_category_id, jc.level AS jur_level, jc.depth
    FROM jurisdiction_requirements jr
    JOIN jurisdiction_chain jc ON jr.jurisdiction_id = jc.id
    WHERE jr.status = 'active'
),
chain_precedence AS (
    -- Match precedence rules: either specific pair or blanket (applies_to_all_children)
    SELECT pr.id AS rule_id, pr.category_id AS rule_category_id,
           pr.precedence_type, pr.reasoning_text, pr.legal_citation,
           pr.trigger_condition, pr.applies_to_all_children,
           pr.higher_jurisdiction_id, pr.lower_jurisdiction_id
    FROM precedence_rules pr
    WHERE pr.status = 'active'
      AND pr.higher_jurisdiction_id IN (SELECT id FROM jurisdiction_chain)
      AND (
          -- Specific pair: both higher and lower are in our chain
          (pr.applies_to_all_children = false
           AND pr.lower_jurisdiction_id IN (SELECT id FROM jurisdiction_chain))
          OR
          -- Blanket rule: applies to all descendants of higher
          (pr.applies_to_all_children = true)
      )
)
SELECT cr.*,
       cp.rule_id, cp.precedence_type,
       cp.reasoning_text, cp.legal_citation, cp.trigger_condition
FROM chain_requirements cr
LEFT JOIN chain_precedence cp
    ON cp.rule_category_id = cr.req_category_id  -- join on FK, not string
ORDER BY cr.category, cr.depth ASC
```

**Key fixes vs. original CTE:**
- Joins precedence on `category_id` FK (not string slug match)
- Blanket rules (`applies_to_all_children = true`) match via `higher_jurisdiction_id IN chain` — no self-referential lower_jurisdiction_id trick
- Specific pair rules require both higher and lower in the chain
- When both a blanket and specific rule match the same category, `determine_governing_requirement()` gives priority to the specific rule

### 4b. New function: `determine_governing_requirement()`

Python post-processing of CTE results per category:
- **floor**: highest value (most beneficial to employee)
- **ceiling**: higher jurisdiction's value
- **supersede**: lower jurisdiction completely replaces
- **additive**: all levels apply simultaneously
- **no rule**: default to most-local (lowest depth)

### 4c. Gradual migration

- `_filter_with_preemption()` (compliance_service.py:3137) stays working
- New resolution path runs in parallel, controlled by `?view=hierarchical` param
- All ~15 call sites of `_filter_with_preemption()` migrate incrementally

---

## Phase 5: API Changes

### 5a. New Pydantic response schemas

**File:** `server/app/core/models/compliance.py`

```python
class JurisdictionLevelRequirement(BaseModel):
    id: str
    jurisdiction_level: str
    jurisdiction_name: str
    title: str
    description: Optional[str] = None
    current_value: Optional[str] = None
    numeric_value: Optional[float] = None
    source_url: Optional[str] = None
    statute_citation: Optional[str] = None
    status: str = "active"
    canonical_key: Optional[str] = None

class PrecedenceInfo(BaseModel):
    precedence_type: str  # floor/ceiling/supersede/additive
    reasoning_text: Optional[str] = None
    legal_citation: Optional[str] = None
    trigger_condition: Optional[dict] = None

class CategoryComplianceStack(BaseModel):
    category: str
    category_label: str
    domain: Optional[str] = None
    governing_level: str
    governing_requirement: JurisdictionLevelRequirement
    precedence: Optional[PrecedenceInfo] = None
    all_levels: List[JurisdictionLevelRequirement]
    affected_employee_count: Optional[int] = None

class HierarchicalComplianceResponse(BaseModel):
    location_id: str
    location_name: str
    city: str
    state: str
    categories: List[CategoryComplianceStack]
    total_categories: int
    total_requirements: int
```

### 5b. Endpoint changes

**File:** `server/app/core/routes/compliance.py`

- `GET /locations/{id}/requirements` — add `?view=hierarchical` param. Default `flat` (backward compat). When `hierarchical`, returns `HierarchicalComplianceResponse`.
- **New:** `GET /compliance/categories` — returns all categories from DB table
- **New:** `GET /compliance/precedence-rules?state={state}` — returns precedence rules
- **New:** `GET /compliance/locations/{id}/jurisdiction-stack` — raw resolution for admin/debug

### 5c. Frontend types

**File:** `client/src/types/compliance.ts` — add TypeScript interfaces matching the Pydantic schemas above.

---

## File Manifest

### New files (13)

| File | Purpose |
|------|---------|
| `server/app/orm/__init__.py` | Package init, exports Base + all models |
| `server/app/orm/base.py` | DeclarativeBase, naming conventions, TimestampMixin |
| `server/app/orm/enums.py` | 8 PostgreSQL ENUM types |
| `server/app/orm/jurisdiction.py` | Jurisdiction, ComplianceCategory, PrecedenceRule models |
| `server/app/orm/requirement.py` | JurisdictionRequirement, PolicyChangeLog models |
| `server/app/orm/compliance.py` | ComplianceRequirement model |
| `server/app/orm/employee.py` | EmployeeJurisdiction model |
| `server/app/orm/location.py` | BusinessLocation model (schema-only FK reference) |
| `server/alembic/versions/XXXX_01_enums_and_categories.py` | Migration 1 |
| `server/alembic/versions/XXXX_02_jurisdictions_hierarchy.py` | Migration 2 |
| `server/alembic/versions/XXXX_03_precedence_rules.py` | Migration 3 |
| `server/alembic/versions/XXXX_04_jurisdiction_requirements_granular.py` | Migration 4 |
| `server/alembic/versions/XXXX_05_explainability_and_employee_junctions.py` | Migration 5 |

### Modified files (7)

| File | Changes |
|------|---------|
| `server/requirements.txt` | Add `sqlalchemy[asyncio]>=2.0.25` |
| `server/alembic/env.py` | Import Base.metadata, add include_name filter, enable compare_type |
| `server/app/core/models/compliance.py` | Add 4 new Pydantic response schemas, add `special_district` to JurisdictionLevel enum |
| `server/app/core/services/compliance_service.py` | Add `resolve_jurisdiction_stack()`, `determine_governing_requirement()`; modify `get_location_requirements()` for hierarchical view |
| `server/app/core/routes/compliance.py` | Add `view` param, 3 new endpoints |
| `server/app/core/compliance_registry.py` | Add `CATEGORY_DOMAIN_MAP` dict for seeding; keep existing CATEGORIES list |
| `client/src/types/compliance.ts` | Add hierarchical response interfaces |

### Not modified yet (backward compat, migrate later)

| File | Reason |
|------|--------|
| `server/app/core/routes/admin.py` | Admin jurisdiction endpoints unchanged; add precedence rule management later |
| `server/app/database.py` | asyncpg pool + init_db unchanged; ORM models live separately |
| `state_preemption_rules` table | Not dropped; kept for backward compat during transition |
| `employees.work_state` column | Not dropped; deprecated in code with comment |

---

## Verification

1. **ORM models compile:** `cd server && python3 -c "from app.orm import Base; print(sorted(Base.metadata.tables.keys()))"`
2. **Autogenerate preview:** `cd server && alembic revision --autogenerate --sql -m "test" | head -100` — verify only managed tables appear, no DROP TABLE for legacy tables
3. **Migration dry-run:** Run migrations 1-5 against a test DB (NOT production). Verify:
   - `SELECT COUNT(*) FROM compliance_categories` → 45
   - `SELECT * FROM jurisdictions WHERE level = 'federal'` → 1 row
   - `SELECT COUNT(*) FROM precedence_rules` → matches `state_preemption_rules` count
   - `SELECT COUNT(*) FROM jurisdiction_requirements WHERE canonical_key IS NOT NULL` → > 0
   - `SELECT COUNT(*) FROM employee_jurisdictions` → matches employees with work_state
4. **Resolution query:** Call `resolve_jurisdiction_stack(conn, <sf_jurisdiction_id>)` and verify it returns federal + CA state + SF city requirements with precedence rules
5. **API:** `GET /api/compliance/locations/{id}/requirements?view=hierarchical` returns `HierarchicalComplianceResponse`
6. **Backward compat:** `GET /api/compliance/locations/{id}/requirements` (no view param) returns existing flat `List[RequirementResponse]`

---

## Implementation Order

Execute phases sequentially:
1. **Phase 1** (infra) — requirements.txt, orm package, env.py
2. **Phase 2** (models) — all 7 ORM model files
3. **Phase 3** (migrations) — 5 migration files with data migration SQL
4. **Phase 4** (service) — resolution query + governing logic
5. **Phase 5** (API) — Pydantic schemas + endpoint changes

Each phase is independently testable. No phase depends on later phases being complete.

---

## Industry Extensibility (Future Verticals)

The schema is designed to expand beyond healthcare to dental, biotech, law firms, unions, and any regulated industry.

### What requires zero schema changes
- New categories = `INSERT` rows into `compliance_categories` (DB table, not hardcoded)
- `industry_tag` on categories routes by vertical (`biotech:gmp`, `dental:infection_control`, `legal:malpractice`)
- `applicable_entity_types` JSONB on requirements handles entity-level filtering (law firm vs clinic vs lab)
- `trigger_conditions` JSONB encodes any boolean expression against facility attributes
- The resolution CTE is industry-agnostic — runs against whatever categories exist for a jurisdiction

### What requires one migration per new domain
- Add new value to `CategoryDomain` enum (e.g., `financial`, `biotech`, `dental`, `legal`)
- Insert new `compliance_categories` rows with appropriate domain + group + industry_tag

### One structural generalization needed before going multi-industry
- `companies.healthcare_specialties` is too healthcare-specific — rename/replace with `industry_attributes JSONB` or a `company_industries` junction table
- This is the **only** structural change required; everything else is data

### Adding a new vertical in practice (e.g. dental)
1. Write ~8–15 new `ComplianceCategoryDef` entries in `compliance_registry.py`
2. Run migration to seed them into `compliance_categories` with `domain='dental'` + appropriate `industry_tag`
3. Write fetch/research logic for those categories
4. Jurisdiction hierarchy, precedence rules, and resolution query all work unchanged
