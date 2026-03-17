# Compliance Database Schema Redesign
## Hierarchical Jurisdiction Precedence with Full Policy Granularity

**Date:** 2026-03-17
**Status:** Spec finalized, pending implementation

---

## Context

We're building a healthcare compliance intelligence platform where the database is the single source of truth for every regulation a facility is subject to. A medical clinic, hospital, or SNF onboards and immediately sees every regulation they're subject to — federal, state, and local — organized by domain, with clear visual hierarchy showing which policy governs and why, backed by legal citations and plain-English reasoning.

The current schema has flat category abstractions, duplicated federal data, no explainability, and no ORM. This redesign introduces:

- Hierarchical jurisdiction precedence (federal → state → county → city → special_district)
- Granular per-policy rows with canonical keys, fetch hashes, and change tracking
- A `compliance_categories` table replacing 45 hardcoded Python entries
- Precedence rules with structured reasoning replacing flat boolean preemption
- SQLAlchemy ORM models as schema source of truth
- A resolution query (recursive CTE) that returns the full jurisdiction stack with governing logic

**10 changes. 7 ORM models. 5 migrations. 13 new files. 7 modified files.**

---

## Current State

| Component | Status |
|-----------|--------|
| ORM | None — raw SQL via asyncpg |
| SQLAlchemy | NOT a dependency (alembic imports it internally but it's not in requirements.txt) |
| Alembic | 118 migrations, all raw SQL via `op.execute()`. `target_metadata = None` |
| Tables | 125 total, created in `database.py init_db()` + migrations |
| Categories | 45 hardcoded in `server/app/core/compliance_registry.py` as Python dataclasses |
| Hierarchy | city → county → state via `parent_id`. No federal row. |
| Preemption | `state_preemption_rules` table: flat `allows_local_override` boolean |
| Employee location | `work_state VARCHAR(2)` — single value, no multi-jurisdiction |
| Policy granularity | Category-level abstractions, not per-policy rows |
| Explainability | None — filters applied silently in code |

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

8 PostgreSQL ENUM types:

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

**Critical:** The `include_name` filter means autogenerate only manages tables with ORM models. All 125 legacy tables are invisible to Alembic autogenerate.

### 1f. Dual engine strategy

SQLAlchemy is used ONLY for schema definition + migration generation. All runtime queries stay on the existing asyncpg pool in `database.py`. No SQLAlchemy Session at runtime. No ORM query layer.

---

## Phase 2: ORM Model Definitions (7 models)

### 2a. `Jurisdiction` (modified) — `server/app/orm/jurisdiction.py`

Existing columns mirrored exactly + new `level` column:

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | gen_random_uuid() |
| city | VARCHAR(100) NOT NULL | |
| state | VARCHAR(2) NOT NULL | |
| county | VARCHAR(100) | nullable |
| **level** | **JurisdictionLevel enum** | **NEW. NOT NULL DEFAULT 'city'** |
| parent_id | UUID FK self | ON DELETE SET NULL |
| last_verified_at | TIMESTAMP | nullable |
| requirement_count | INTEGER DEFAULT 0 | |
| legislation_count | INTEGER DEFAULT 0 | |
| created_at, updated_at | TIMESTAMP | |

Constraints: UNIQUE(city, state). Indexes: level, parent_id, state.
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
| lower_jurisdiction_id | UUID FK jurisdictions NOT NULL | the jurisdiction that may override |
| precedence_type | PrecedenceType enum NOT NULL | floor/ceiling/supersede/additive |
| trigger_condition | JSONB | nullable — structured boolean expression evaluated against facility attributes |
| reasoning_text | TEXT | human-readable: "California CMIA provides broader protections than HIPAA..." |
| legal_citation | VARCHAR(500) | statute reference: "Cal. Civ. Code §56.10" |
| effective_date | DATE | nullable |
| sunset_date | DATE | nullable — for expiring rules |
| last_verified_at | TIMESTAMP | nullable |
| status | PrecedenceRuleStatus enum DEFAULT 'active' | |
| created_at, updated_at | TIMESTAMP | |

Constraints: UNIQUE(category_id, higher_jurisdiction_id, lower_jurisdiction_id).
Indexes: category_id, status, lower_jurisdiction_id.

**Precedence types explained:**
- `floor` — higher sets minimum, lower can be stricter (e.g., CA min wage > federal)
- `ceiling` — higher sets maximum, lower cannot exceed (e.g., TX preempts local min wage)
- `supersede` — lower completely replaces higher in this context
- `additive` — both apply simultaneously, no conflict

**Wildcard convention:** When `lower_jurisdiction_id = higher_jurisdiction_id`, the rule applies to ALL children of that jurisdiction.

### 2d. `JurisdictionRequirement` (modified) — `server/app/orm/requirement.py`

All existing columns mirrored exactly + new columns:

| New Column | Type | Notes |
|------------|------|-------|
| **canonical_key** | VARCHAR(255) UNIQUE | idempotency key: `ca_san_diego_minimum_wage_iwo_2024` |
| **category_id** | UUID FK compliance_categories | nullable during migration |
| **summary** | TEXT | plain-English description of what the policy requires |
| **full_text_reference** | TEXT | URL or document path to authoritative source text |
| **statute_citation** | VARCHAR(500) | formal legal citation: "San Diego Municipal Code §39.0101" |
| **fetch_hash** | VARCHAR(64) | SHA-256 of fetched content — skip update if hash matches |
| **status** | RequirementStatus enum DEFAULT 'active' | active/pending/repealed/superseded/under_review |
| **superseded_by_id** | UUID FK self | nullable — when a policy is replaced, point to new row |
| **applicable_entity_types** | JSONB | clinic, hospital, SNF, ambulatory_surgery_center, etc. |
| **trigger_conditions** | JSONB | structured conditions for when this policy applies to a specific facility |
| **metadata** | JSONB | overflow for policy-specific attributes |

**source_tier migration:** Existing INTEGER column (1/2/3) → SourceTier enum (tier_1_government/tier_2_official_secondary/tier_3_aggregator). Requires column rename + type swap.

Indexes: canonical_key, category_id, status, source_tier (added to existing jurisdiction_id, rate_type indexes).

### 2e. `PolicyChangeLog` (new) — `server/app/orm/requirement.py`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| requirement_id | UUID FK jurisdiction_requirements NOT NULL | ON DELETE CASCADE |
| field_changed | VARCHAR(100) NOT NULL | which field changed |
| old_value | TEXT | nullable |
| new_value | TEXT | nullable |
| changed_at | TIMESTAMP DEFAULT NOW() | |
| change_source | ChangeSource enum NOT NULL | ai_fetch/manual_review/legislative_update/system_migration |
| change_reason | TEXT | nullable — why this changed |

Indexes: requirement_id, changed_at.

Every mutation to jurisdiction_requirements writes a change log entry. Nothing changes silently.

### 2f. `ComplianceRequirement` (modified) — `server/app/orm/compliance.py`

All existing columns mirrored + 2 new explainability columns:

| New Column | Type | Notes |
|------------|------|-------|
| **governing_jurisdiction_level** | VARCHAR(20) | nullable — which level's policy governs for this category |
| **governing_precedence_rule_id** | UUID FK precedence_rules | nullable — which rule determined governance |

When sync logic copies from jurisdiction_requirements into compliance_requirements for a location, it evaluates precedence_rules and writes which rule determined governance. The frontend reads this to render the hierarchy with reasoning.

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
**RLS required** — policy via join to employees.org_id.

### 2h. `BusinessLocation` (schema-only mirror) — `server/app/orm/location.py`

Read-only ORM model mirroring the existing `business_locations` table so other models can declare FK relationships to it. No new columns added.

---

## Phase 3: Alembic Migrations (5 sequential)

All migrations use `op.execute()` with raw SQL (consistent with existing pattern) but are generated from the ORM model diffs as a starting point, then manually adjusted.

### Migration 1: Create ENUMs + compliance_categories

1. Create all 8 PostgreSQL ENUM types
2. CREATE TABLE `compliance_categories`
3. Seed 45 rows from `CATEGORIES` in `compliance_registry.py`

### Migration 2: Modify jurisdictions

1. ADD COLUMN `level jurisdiction_level_enum NOT NULL DEFAULT 'city'`
2. UPDATE existing state rows: `SET level = 'state' WHERE city = '' AND state != 'US'`
3. UPDATE county rows: `SET level = 'county' WHERE city LIKE '_county_%'`
4. INSERT federal row: `city='', state='US', level='federal'`
5. Link state rows → federal: `UPDATE jurisdictions SET parent_id = <federal_id> WHERE level = 'state' AND parent_id IS NULL`
6. Add index on `level`

### Migration 3: Create precedence_rules + migrate preemption data

1. CREATE TABLE `precedence_rules`
2. Migrate from `state_preemption_rules`:
   - `allows_local_override = true` → `precedence_type = 'floor'`
   - `allows_local_override = false` → `precedence_type = 'ceiling'`
   - `higher_jurisdiction_id` = state jurisdiction
   - `lower_jurisdiction_id` = same as higher (wildcard: applies to all children)
   - `category_id` = lookup from compliance_categories by slug
3. Do NOT drop `state_preemption_rules` — keep for backward compat during transition

### Migration 4: Modify jurisdiction_requirements + create policy_change_log

1. Add new columns: canonical_key, category_id, summary, full_text_reference, statute_citation, fetch_hash, status, superseded_by_id, applicable_entity_types, trigger_conditions, metadata
2. Migrate source_tier: INTEGER → source_tier_enum (add new column, backfill, drop old, rename)
3. Backfill category_id from compliance_categories via slug match on category column
4. Backfill canonical_key from existing requirement_key + jurisdiction context
5. CREATE TABLE `policy_change_log`
6. Add indexes: canonical_key, category_id, status

### Migration 5: Modify compliance_requirements + create employee_jurisdictions

1. Add governing_jurisdiction_level, governing_precedence_rule_id to compliance_requirements
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
    SELECT id, city, state, level, parent_id, 0 AS depth
    FROM jurisdictions WHERE id = $1
    UNION ALL
    SELECT j.id, j.city, j.state, j.level, j.parent_id, jc.depth + 1
    FROM jurisdictions j JOIN jurisdiction_chain jc ON j.id = jc.parent_id
),
chain_requirements AS (
    SELECT jr.*, jc.level AS jur_level, jc.depth
    FROM jurisdiction_requirements jr
    JOIN jurisdiction_chain jc ON jr.jurisdiction_id = jc.id
    WHERE jr.status = 'active'
),
chain_precedence AS (
    SELECT pr.*, cc.slug AS category_slug
    FROM precedence_rules pr
    JOIN compliance_categories cc ON pr.category_id = cc.id
    WHERE pr.status = 'active'
      AND pr.higher_jurisdiction_id IN (SELECT id FROM jurisdiction_chain)
      AND (pr.lower_jurisdiction_id IN (SELECT id FROM jurisdiction_chain)
           OR pr.lower_jurisdiction_id = pr.higher_jurisdiction_id)
)
SELECT cr.*, cp.id AS rule_id, cp.precedence_type,
       cp.reasoning_text, cp.legal_citation, cp.trigger_condition
FROM chain_requirements cr
LEFT JOIN chain_precedence cp ON cp.category_slug = cr.category
ORDER BY cr.category, cr.depth ASC
```

This is a single composed query. Not ORM traversal.

### 4b. New function: `determine_governing_requirement()`

Python post-processing of CTE results, grouped by category:
- **floor**: take highest value (most beneficial to employee)
- **ceiling**: take higher jurisdiction's value
- **supersede**: lower jurisdiction completely replaces higher
- **additive**: all levels apply simultaneously, no conflict
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
    jurisdiction_level: str  # federal/state/county/city/special_district
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
- **New:** `GET /compliance/precedence-rules?state={state}` — returns precedence rules for a state
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
| `server/alembic/versions/XXXX_01_enums_and_categories.py` | Migration 1: ENUMs + compliance_categories |
| `server/alembic/versions/XXXX_02_jurisdictions_hierarchy.py` | Migration 2: federal jurisdiction + level column |
| `server/alembic/versions/XXXX_03_precedence_rules.py` | Migration 3: precedence_rules + preemption data migration |
| `server/alembic/versions/XXXX_04_jurisdiction_requirements_granular.py` | Migration 4: granular policy columns + policy_change_log |
| `server/alembic/versions/XXXX_05_explainability_and_employee_junctions.py` | Migration 5: explainability + employee_jurisdictions |

### Modified files (7)

| File | Changes |
|------|---------|
| `server/requirements.txt` | Add `sqlalchemy[asyncio]>=2.0.25` |
| `server/alembic/env.py` | Import Base.metadata, add include_name filter, enable compare_type |
| `server/app/core/models/compliance.py` | Add 4 new Pydantic response schemas, add `special_district` to JurisdictionLevel enum |
| `server/app/core/services/compliance_service.py` | Add `resolve_jurisdiction_stack()`, `determine_governing_requirement()`; modify `get_location_requirements()` for hierarchical view |
| `server/app/core/routes/compliance.py` | Add `view` param to requirements endpoint, add 3 new endpoints |
| `server/app/core/compliance_registry.py` | Add `CATEGORY_DOMAIN_MAP` dict for seeding; keep existing CATEGORIES list |
| `client/src/types/compliance.ts` | Add hierarchical response TypeScript interfaces |

### Not modified (backward compat, migrate later)

| File | Reason |
|------|--------|
| `server/app/core/routes/admin.py` | Admin jurisdiction endpoints unchanged; add precedence rule management later |
| `server/app/database.py` | asyncpg pool + init_db unchanged; ORM models live separately |
| `state_preemption_rules` table | Not dropped; kept for backward compat during transition |
| `employees.work_state` column | Not dropped; deprecated in code with comment |

---

## Verification

1. **ORM models compile:** `cd server && python3 -c "from app.orm import Base; print(sorted(Base.metadata.tables.keys()))"`
2. **Autogenerate preview:** `cd server && alembic revision --autogenerate --sql -m "test"` — verify only managed tables appear, no DROP TABLE for legacy tables
3. **Migration dry-run:** Run migrations 1-5 against a test DB (NOT production). Verify:
   - `SELECT COUNT(*) FROM compliance_categories` → 45
   - `SELECT * FROM jurisdictions WHERE level = 'federal'` → 1 row
   - `SELECT COUNT(*) FROM precedence_rules` → matches `state_preemption_rules` count
   - `SELECT COUNT(*) FROM jurisdiction_requirements WHERE canonical_key IS NOT NULL` → > 0
   - `SELECT COUNT(*) FROM employee_jurisdictions` → matches employees with work_state
4. **Resolution query:** Call `resolve_jurisdiction_stack(conn, <sf_jurisdiction_id>)` — returns federal + CA state + SF city requirements with precedence rules
5. **API endpoint:** `GET /api/compliance/locations/{id}/requirements?view=hierarchical` returns nested `HierarchicalComplianceResponse`
6. **Backward compat:** `GET /api/compliance/locations/{id}/requirements` (no view param) returns existing flat `List[RequirementResponse]`

---

## Implementation Order

Execute phases sequentially. Each is independently testable:

1. **Phase 1** — SQLAlchemy infrastructure: requirements.txt, orm package, env.py
2. **Phase 2** — ORM model definitions: all 7 model files
3. **Phase 3** — Alembic migrations: 5 migration files with data migration SQL
4. **Phase 4** — Service layer: resolution query + governing logic
5. **Phase 5** — API layer: Pydantic schemas + endpoint changes
