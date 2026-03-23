# Plan: First-Class Regulation Key System

## Context

Every regulation key should be treated like a stock ticker or street name — uniquely important, indispensable, auditable. If any policy is missing, stale, unfetched, or incomplete, it must be immediately and obviously apparent.

This is a **data model upgrade**, not a visibility upgrade. Key definitions must live in the database (not Python code), carry full metadata, enforce staleness SLAs, and scale to new domains (biotech, dental, manufacturing) without code deploys.

---

## Current Schema: How It Works Today

### The Data Model

```
┌─────────────────────┐     ┌───────────────────────────────────────────────┐
│   jurisdictions      │────▶│       jurisdiction_requirements                │
│                      │     │  (the core policy record)                     │
│ • city, state, county│     │                                               │
│ • last_verified_at   │     │  IDENTITY                                     │
│ • requirement_count  │     │  • id (UUID)                                  │
│ • UNIQUE(city,state) │     │  • jurisdiction_id → jurisdictions             │
└─────────────────────┘     │  • requirement_key (composite: "cat:reg_key")  │
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
| `jurisdiction_sources` | Source reputation per domain per jurisdiction (success_count, accurate_count, Laplace smoothing) |
| `structured_data_sources` | Tier 1 API source registry (DOL, BLS, etc.) with fetch schedules and parser configs |
| `jurisdiction_legislation` | Upcoming/proposed legislation per jurisdiction |
| `compliance_requirement_history` | Point-in-time snapshots of requirement values |

### Current Registry (Python-only, `compliance_registry.py`)

| Construct | Count | Problem |
|-----------|-------|---------|
| `REGULATIONS` (RegulationDef) | 229 | Full metadata but only for healthcare/medical |
| `_LABOR_REGULATION_KEYS` | 99 keys | **Bare strings** — no name, no variance, no enforcing agency |
| Oncology keys | **0** | Not defined at all |
| **Total** | **328** | Only 229 have metadata; adding keys requires code deploy |

### What's Wrong

1. **Keys are code, not data** — adding a key requires a PR and deploy
2. **No audit trail** on the registry — no record of when/why a key was added
3. **99 labor keys are second-class** — `get_missing_regulations()` silently drops them
4. **5 oncology categories have 0 keys** — completely undefined
5. **`requirement_key` is a composite string** — parsed via string split, fragile
6. **No staleness SLA** — visibility into staleness but no enforcement thresholds
7. **No bidirectional integrity** — orphaned DB records aren't detected
8. **Static weights** — a radiation key shouldn't weigh the same for a dental office as for an oncology center
9. **No key dependencies** — related keys (state_min_wage + tipped_min_wage + overtime) aren't linked

---

## Phase 1: `regulation_key_definitions` Table

**Keys become data, not code.** CRUD via admin UI, audit trail built-in, no deploys to add keys.

### New table

```sql
CREATE TABLE regulation_key_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- IDENTITY
    key VARCHAR(100) NOT NULL,
    category_slug VARCHAR(50) NOT NULL,
    category_id UUID NOT NULL REFERENCES compliance_categories(id),
    -- NOTE: "domain" removed — regulatory_domain is already captured by
    -- compliance_categories.group (labor/healthcare/oncology/medical_compliance)
    -- and industry scope is captured by applicable_industries TEXT[].
    -- A single "domain" column conflates regulatory domain with industry vertical
    -- (e.g., OSHA spans healthcare AND manufacturing). Use the category's group
    -- for regulatory partitioning and applicable_industries for vertical filtering.
    UNIQUE(category_slug, key),

    -- DISPLAY
    name VARCHAR(200) NOT NULL,
    description TEXT,

    -- ENFORCEMENT
    enforcing_agency VARCHAR(200),
    authority_source_urls TEXT[],

    -- VARIANCE & WEIGHT
    state_variance VARCHAR(20) NOT NULL DEFAULT 'Moderate',
    base_weight NUMERIC(3,1) NOT NULL DEFAULT 1.0,

    -- APPLICABILITY SCOPE
    applies_to_levels TEXT[] DEFAULT '{state,city}',
    min_employee_threshold INTEGER,
    applicable_entity_types TEXT[],
    applicable_industries TEXT[],

    -- STALENESS SLA
    update_frequency VARCHAR(100),
    staleness_warning_days INTEGER DEFAULT 90,
    staleness_critical_days INTEGER DEFAULT 180,
    staleness_expired_days INTEGER DEFAULT 365,

    -- DEPENDENCIES
    -- key_group is a flat VARCHAR for now. When biotech clients need specific
    -- key combinations to constitute a valid compliance posture, promote to a
    -- key_groups table with min_required_count and completeness_threshold.
    -- See "Future: key_groups table" section below.
    key_group VARCHAR(100),

    -- AUDIT
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    notes TEXT
);

-- Change tracking for key definitions themselves.
-- If someone changes staleness_critical_days from 180 to 60, we need a record
-- since these thresholds directly affect compliance officer alerts.
CREATE TABLE regulation_key_definition_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_definition_id UUID NOT NULL REFERENCES regulation_key_definitions(id) ON DELETE CASCADE,
    field_changed VARCHAR(100) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at TIMESTAMP DEFAULT NOW(),
    changed_by UUID REFERENCES users(id),
    change_reason TEXT
);
CREATE INDEX idx_rkdh_key_def ON regulation_key_definition_history(key_definition_id, changed_at);
```

### History write mechanism

History rows are written by **application-level logic in the admin CRUD endpoint**, not a Postgres trigger. Rationale:
- We need `changed_by` (the admin user UUID) which isn't available in a trigger context
- We need `change_reason` which comes from the request payload
- The admin update endpoint diffs old vs new values, writes one `regulation_key_definition_history` row per changed field, then performs the UPDATE — same pattern as `policy_change_log` writes in `compliance_service.py`

### Read cache invalidation

The Python registry (`compliance_registry.py`) becomes a read cache loaded from `regulation_key_definitions` at startup. Invalidation strategy:
- **In-memory cache with TTL**: 5-minute TTL via `functools.lru_cache` with timestamp check. Acceptable staleness for key definitions (they change rarely).
- **Immediate invalidation on admin write**: The admin CRUD endpoint calls `invalidate_key_definition_cache()` after any insert/update/delete, clearing the in-memory cache so the next read reloads from DB.
- **No cross-process signaling needed**: Each uvicorn worker reloads within 5 minutes. For immediate consistency after admin changes, the admin endpoint returns fresh data directly from the DB write response.

This avoids "works in dev but not prod" since workers don't need Redis pub/sub or webhooks — the TTL handles it.

### Seed migration

Migrate all 229 `RegulationDef` entries + 99 `_LABOR_REGULATION_KEYS` + ~25 new oncology keys. Python registry becomes a **read cache** loaded from DB at startup.

### Key groups

```
wage_rates:        state_minimum_wage, tipped_minimum_wage, exempt_salary_threshold,
                   healthcare_minimum_wage, fast_food_minimum_wage
leave_programs:    state_family_leave, state_paid_family_leave, pregnancy_disability_leave,
                   state_disability_insurance
overtime_rules:    daily_weekly_overtime, double_time, seventh_day_overtime,
                   mandatory_overtime_restrictions
radiation_safety:  state_radiation_control_programs, radiation_oncology_safety_team,
                   radioactive_materials_license
```

Gap analysis: "wage_rates group is 40% complete — partial coverage is unreliable."

---

## Phase 2: Split `requirement_key` Into Two Indexed Columns

```sql
-- Step 1: Add columns
ALTER TABLE jurisdiction_requirements
    ADD COLUMN IF NOT EXISTS regulation_key VARCHAR(100);
ALTER TABLE jurisdiction_requirements
    ADD COLUMN IF NOT EXISTS key_definition_id UUID REFERENCES regulation_key_definitions(id);

-- Step 2: Backfill regulation_key from existing composite requirement_key
UPDATE jurisdiction_requirements
SET regulation_key = CASE
    WHEN position(':' in requirement_key) > 0
    THEN substring(requirement_key from position(':' in requirement_key) + 1)
    ELSE requirement_key
END
WHERE regulation_key IS NULL;

-- Step 3: Verification — assert row counts match before and after
-- (migration should fail if any rows lost or duplicated)
DO $$
DECLARE
    total_before INTEGER;
    total_after INTEGER;
BEGIN
    SELECT count(*) INTO total_before FROM jurisdiction_requirements;
    SELECT count(*) INTO total_after FROM jurisdiction_requirements WHERE regulation_key IS NOT NULL;
    IF total_before != total_after THEN
        RAISE EXCEPTION 'Backfill mismatch: % rows total but only % got regulation_key',
            total_before, total_after;
    END IF;
END $$;

-- Step 4: Backfill key_definition_id by linking to regulation_key_definitions
-- This MUST happen in the same migration as the column add — otherwise Phase 3's
-- integrity check will report thousands of false "orphans" that are just unlinked.
UPDATE jurisdiction_requirements jr
SET key_definition_id = rkd.id
FROM regulation_key_definitions rkd
WHERE jr.category = rkd.category_slug
  AND jr.regulation_key = rkd.key
  AND jr.key_definition_id IS NULL;

-- Step 5: Indexes
CREATE INDEX idx_jr_regulation_key ON jurisdiction_requirements(regulation_key);
CREATE INDEX idx_jr_category_regulation_key ON jurisdiction_requirements(category, regulation_key);
CREATE INDEX idx_jr_key_definition_id ON jurisdiction_requirements(key_definition_id);
```

Old composite `requirement_key` stays for backward compat but is no longer parsed at runtime. Rows where `key_definition_id IS NULL` after backfill are genuine orphans (Gemini-invented keys that don't match any definition).

### Rollback plan

If seed migration has bad data or backfill has edge cases:
- `regulation_key_definitions` → `DROP TABLE` (clean, no downstream deps yet)
- `regulation_key` column → `ALTER TABLE DROP COLUMN` (derived data, re-derivable)
- `key_definition_id` column → `ALTER TABLE DROP COLUMN` (soft FK, nullable)

All three changes are independently reversible. The backfill is non-destructive (adds columns, doesn't modify existing data).

---

## Phase 3: Bidirectional Integrity Checks

### Registry → DB: "What's missing?"

Query `regulation_key_definitions` LEFT JOIN `jurisdiction_requirements` — return keys where jr.id IS NULL. Respect applicability scope (skip keys where jurisdiction doesn't match `applies_to_levels`, `applicable_entity_types`, `applicable_industries`).

### DB → Registry: "What's orphaned?"

Query `jurisdiction_requirements` LEFT JOIN `regulation_key_definitions` — return rows where rkd.id IS NULL. These are records tracking something the system can't classify.

### Endpoint: `GET /admin/jurisdictions/integrity-check`

```json
{
  "missing_keys": [...],
  "orphaned_records": [...],
  "stale_keys": [...],
  "partial_groups": [...],
  "total_defined_keys": 355,
  "total_db_records": 4200,
  "integrity_score": 94.2
}
```

---

## Phase 4: Staleness SLAs with Enforcement

### Per-key thresholds (from `regulation_key_definitions`)

| Level | Field | Default | Action |
|-------|-------|---------|--------|
| Warning | `staleness_warning_days` | 90 | Yellow badge in UI |
| Critical | `staleness_critical_days` | 180 | Red badge + admin notification |
| Expired | `staleness_expired_days` | 365 | Data flagged unreliable, compliance officer alerted |

### Non-default examples

| Key | Warning | Critical | Why |
|-----|---------|----------|-----|
| `state_minimum_wage` | 30 | 60 | Changes annually Jan 1 |
| `nurse_staffing_ratios` | 180 | 365 | Changes rarely |
| `state_radiation_control_programs` | 365 | 730 | NRC reviews every 4 years |

### Enforcement: Celery periodic task (weekly)

### Alert destination: `repository_alerts` (new table)

The existing `compliance_alerts` table is **company-scoped** — requires `location_id` + `company_id` NOT NULL. It's for alerting a business that their compliance posture changed. Staleness alerts are **system-level** — they're about the jurisdiction data repository itself, not any company's posture.

```sql
CREATE TABLE repository_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- What
    alert_type VARCHAR(30) NOT NULL,         -- 'stale_warning' | 'stale_critical' | 'stale_expired' | 'missing_data'
    severity VARCHAR(20) NOT NULL,           -- 'warning' | 'critical' | 'expired' | 'missing'
    -- Where
    jurisdiction_id UUID REFERENCES jurisdictions(id) ON DELETE CASCADE,
    key_definition_id UUID REFERENCES regulation_key_definitions(id) ON DELETE CASCADE,
    requirement_id UUID REFERENCES jurisdiction_requirements(id) ON DELETE SET NULL,
    -- Context
    category VARCHAR(50),
    regulation_key VARCHAR(100),
    message TEXT NOT NULL,                    -- "state_minimum_wage for Charlotte, NC is 45 days past verification"
    days_overdue INTEGER,                    -- How far past the threshold
    -- Lifecycle
    status VARCHAR(20) NOT NULL DEFAULT 'open',  -- 'open' | 'acknowledged' | 'resolved'
    created_at TIMESTAMP DEFAULT NOW(),
    acknowledged_at TIMESTAMP,
    acknowledged_by UUID REFERENCES users(id),
    resolved_at TIMESTAMP,
    resolved_by UUID REFERENCES users(id),
    resolution_note TEXT
);
CREATE INDEX idx_repo_alerts_status ON repository_alerts(status);
CREATE INDEX idx_repo_alerts_jurisdiction ON repository_alerts(jurisdiction_id);
CREATE INDEX idx_repo_alerts_severity ON repository_alerts(severity);
-- Prevent duplicate open alerts for the same key+jurisdiction
CREATE UNIQUE INDEX idx_repo_alerts_dedup
    ON repository_alerts(jurisdiction_id, key_definition_id, alert_type)
    WHERE status = 'open';
```

**Stale data detection:**
1. Join `jurisdiction_requirements` with `regulation_key_definitions`
2. Compute `days_since_verified = NOW() - last_verified_at`
3. Compare against per-key thresholds
4. Warning → upsert `repository_alerts` row (dedup index prevents duplicates)
5. Critical → same, with severity escalation if warning already exists
6. Expired → same, mark requirement metadata as unreliable

**Never-verified / zero-data detection:**
A key seeded in `regulation_key_definitions` with zero matching `jurisdiction_requirements` rows for a jurisdiction where it should apply is **worse than stale** — it's an acknowledged gap with zero data. The task must also:
7. Query `regulation_key_definitions` LEFT JOIN `jurisdiction_requirements` for each active jurisdiction
8. Filter by applicability scope (`applies_to_levels`, `applicable_industries`, `applicable_entity_types`)
9. Keys with zero matches → upsert `repository_alerts` with alert_type `missing_data`
10. Surface these as "NO DATA" in the UI — more urgent than any staleness level

**Auto-resolution:** When the Celery task runs and a previously-alerting key is now verified/present, it sets `status = 'resolved'` and `resolved_at = NOW()` on the open alert.

**Scaling note:** The never-verified check is a cross-product (~355 keys × N jurisdictions). At current scale (~50 jurisdictions) this is trivial. As we scale to 500+ jurisdictions and 500+ keys:
- **Smart join strategy**: Only check jurisdictions that have *some* requirements in a category but are missing specific keys (not the full cross-product). This filters out jurisdictions with zero data entirely (those are already known gaps).
- **Materialized view**: If the weekly query exceeds 5s, materialize `jurisdiction_key_coverage` as a view refreshed by the Celery task, storing (jurisdiction_id, key_definition_id, status, days_stale).
- **For now**: The naive LEFT JOIN is fine. Add `EXPLAIN ANALYZE` monitoring to the Celery task so we see when it starts to slow down.

---

## Phase 5: Contextual Weights

`base_weight` provides the default. Actual weight depends on context:

```python
def resolve_weight(key_def, company_profile) -> float:
    """Compute contextual weight. Uses additive adjustments with a floor
    to avoid extreme ratios that distort mixed-use facility scores."""
    weight = key_def.base_weight
    adjustment = 0.0

    if key_def.applicable_industries:
        if company_profile.industry in key_def.applicable_industries:
            adjustment += 0.5   # Directly relevant
        else:
            adjustment -= 0.5   # Not this company's vertical

    if key_def.applicable_entity_types:
        if company_profile.entity_type in key_def.applicable_entity_types:
            adjustment += 0.5
        else:
            adjustment -= 0.5

    # Floor at 0.2 × base_weight — even irrelevant keys have SOME baseline value
    # (a dental office should still know radiation regs exist, just not prioritize them)
    return max(weight + adjustment, weight * 0.2)
```

- Oncology center + radiation key: base 1.5 + 0.5 + 0.5 = **2.5**
- Dental office + radiation key: base 1.5 - 0.5 - 0.5 = **0.5** (floor = 0.3, so 0.5)
- Mixed-use facility: adjustments partially cancel, scores stay reasonable
- Max ratio between best/worst: ~5:1 (not 25:1 with multiplicative stacking)
- Admin/global view: uses `base_weight` for universal index

---

## Phase 6: Key-Level Coverage API

`GET /admin/jurisdictions/key-coverage`

Response includes per-key: status, enforcing_agency, staleness_level, key_group, current_value, days_since_verified. Per-category: partial_groups showing incomplete co-required sets.

---

## Phase 7: TypeScript Generation & UI

TS generation queries `regulation_key_definitions` table (not Python constants). Admin UI: heatmap cells show `n/m` fractions, click opens drawer with enforcing agency, staleness badge, group completeness. New KeyCoverageOverview tab: Bloomberg-terminal style.

---

## Implementation Order

```
Phase 1 (DB table + seed)  →  Phase 2 (split columns)  →  Phase 3 (integrity)
                                                                    ↓
Phase 4 (staleness SLAs)   →  Phase 5 (contextual weights)  →  Phase 6 (API)
                                                                    ↓
                                                              Phase 7 (TS + UI)
```

## Critical Files

- `server/app/core/compliance_registry.py` — convert to DB-backed read cache
- `server/app/core/routes/admin.py` — integrity-check + key-coverage endpoints
- `server/app/core/services/compliance_service.py` — `_compute_requirement_key()` uses new `regulation_key` column
- `server/app/database.py` — new table DDL
- `server/alembic/versions/` — migration for table + seed + column additions
- `scripts/generate_compliance_ts.py` — query DB instead of Python constants
- `client/src/components/admin/jurisdiction/` — heatmap, drawer, overview UI

## DB Schema Changes Summary

| Change | Type | Rollback |
|--------|------|----------|
| `regulation_key_definitions` | New table | `DROP TABLE` |
| `regulation_key_definition_history` | New table | `DROP TABLE` |
| `repository_alerts` | New table | `DROP TABLE` |
| `jurisdiction_requirements.regulation_key` | New column + backfill | `DROP COLUMN` (re-derivable) |
| `jurisdiction_requirements.key_definition_id` | New FK column + backfill | `DROP COLUMN` |
| Seed ~355 key definitions | Data migration | `TRUNCATE regulation_key_definitions` |

## Verification

1. `SELECT count(*) FROM regulation_key_definitions` → ~355 rows
2. `SELECT count(*) FROM jurisdiction_requirements WHERE key_definition_id IS NOT NULL` → majority linked (remainder are genuine orphans)
3. `SELECT count(*) FROM jurisdiction_requirements WHERE regulation_key IS NULL` → 0 (backfill complete)
4. `GET /admin/jurisdictions/integrity-check` → orphaned count matches unlinked rows, missing keys respect applicability scope
5. `SELECT * FROM regulation_key_definitions WHERE staleness_warning_days < 90` → min wage keys show 30-day threshold
6. `SELECT key_group, count(*) FROM regulation_key_definitions GROUP BY key_group` → wage_rates=5, leave_programs=4
7. Update a key definition's `staleness_critical_days` → row appears in `regulation_key_definition_history`
8. Staleness task detects never-verified keys (zero `jurisdiction_requirements` matches) as "missing" alerts
9. `resolve_weight()` for oncology center + radiation key → 2.5; dental office → 0.5 (max ratio ~5:1)
10. Missing key query returns results for labor AND oncology (not just healthcare)
11. UI: heatmap `n/m`, drawer shows enforcing agency + staleness + group completeness

---

## Future: `key_groups` Table

Not in scope for initial implementation, but documented here for when biotech/manufacturing clients need specific key combinations to constitute a valid compliance posture.

The flat `key_group VARCHAR(100)` gets you 90% of the value — group completeness is derived from `SELECT key_group, count(*) GROUP BY key_group`. But the threshold for "partial coverage is unreliable" lives in application logic with no admin visibility or per-group customization.

When needed, promote to:

```sql
CREATE TABLE key_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(100) NOT NULL UNIQUE,        -- "wage_rates"
    name VARCHAR(200) NOT NULL,               -- "Wage Rate Requirements"
    description TEXT,
    min_required_count INTEGER,               -- Minimum keys for "reliable" coverage
    completeness_threshold NUMERIC(3,2),      -- e.g., 0.80 = 80% of keys required
    applicable_industries TEXT[],             -- Which industries care about this group
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

Then `regulation_key_definitions.key_group` becomes a FK: `key_group_id UUID REFERENCES key_groups(id)`. Gap analysis changes from hardcoded thresholds to `WHERE present_count < kg.min_required_count`.

**Trigger**: When a client asks "what does it mean for us to be 60% covered on radiation safety — is that enough?" and the answer needs to vary by client.
