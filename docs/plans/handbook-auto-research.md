# Handbook Auto-Research System

## Overview

When a hospitality handbook is created via template, the system automatically detects and fills missing jurisdiction topics before generation. This avoids 400 errors from incomplete jurisdiction data while keeping the research scoped and fast.

## Flow

### 1. Pre-flight Detection
**Where:** `HandbookService.create_handbook()` → pre-flight block

- Only triggers for `source_type="template"` and `STRICT_TEMPLATE_INDUSTRIES` (hospitality)
- Fetches existing `jurisdiction_requirements` for the handbook's scopes
- Calls `_find_missing_state_topics()` to compare against `MANDATORY_STATE_TOPICS`
- Example: PA has 7/8 mandatory topics, missing `scheduling_reporting`

### 2. Auto-Research (Gap Fill Only)
**Where:** `_auto_research_missing_handbook_topics()` in `handbook_service.py`

**Guard rails — will NOT research if:**
- State-level jurisdiction row doesn't exist in `jurisdictions` table (never been researched)
- Jurisdiction exists but has zero `jurisdiction_requirements` rows (empty, needs full admin refresh)

**When it proceeds:**
- Loads existing requirements as context
- Calls `_refresh_repository_missing_categories()` for just the missing categories
- Uses cached `jurisdiction_sources` so it's a single Gemini call, not a full discovery
- 90s timeout (enough for 1-3 missing topics with cached sources)

### 3. Persistence to Jurisdiction Repository
**Where:** `_refresh_repository_missing_categories()` → `_upsert_jurisdiction_requirements()` in `compliance_service.py`

- Merges new research with existing requirements
- Upserts to `jurisdiction_requirements` table (shared, not company-specific)
- This data is now available for ALL companies in that jurisdiction

### 4. Sync to Company Compliance
**Where:** `_auto_research_missing_handbook_topics()` → sync block after research

- After successful research, finds all active `business_locations` for the company in that state
- Joins through `jurisdictions` table to match by state
- Calls `_sync_requirements_to_location()` for each location
- Uses `create_alerts=False` (background gap-fill, not a material change alert)
- Updates `compliance_requirements` table (company-specific)

### 5. Handbook Generation
**Where:** Back in `create_handbook()` transaction

- Re-fetches `_fetch_state_requirements()` — picks up the newly persisted data
- `_build_template_sections()` now has full coverage
- `allow_fallback=auto_researched` is still set as safety net in case research partially failed

## Data Flow Diagram

```
Handbook creation request
    │
    ▼
Pre-flight: detect missing topics (e.g., PA missing scheduling_reporting)
    │
    ▼
Guard: PA jurisdiction exists AND has existing data? ── No ──▶ Skip (needs admin refresh)
    │ Yes
    ▼
Gemini research (1 call, cached sources, 90s timeout)
    │
    ▼
Persist to jurisdiction_requirements  ◀── shared across all companies
    │
    ▼
Sync to company's business_locations  ◀── company-specific compliance_requirements
    │
    ▼
Re-fetch jurisdiction data (now complete)
    │
    ▼
Generate handbook with full coverage
```

## Key Tables

| Table | Scope | Updated By |
|-------|-------|------------|
| `jurisdictions` | Shared | NOT created by auto-research (must pre-exist) |
| `jurisdiction_requirements` | Shared | Upserted after successful Gemini research |
| `jurisdiction_sources` | Shared | Used as cache for faster research; discovered on first full refresh |
| `compliance_requirements` | Per company/location | Synced from jurisdiction_requirements after research |

## What Triggers a Full Refresh vs Auto-Research

| Scenario | Action |
|----------|--------|
| PA has 7/8 topics, missing 1 | Auto-research fills the gap |
| New state with no jurisdiction row | Skipped — admin must run full jurisdiction research |
| Jurisdiction exists but 0 requirements | Skipped — admin must run full compliance refresh |
| Manual "sync compliance" button | Reads from jurisdiction_requirements, syncs to company locations |

## Historical Context

Before this fix:
- Auto-research would try to bootstrap brand-new jurisdictions from scratch
- Created empty jurisdiction rows then attempted full discovery + research
- Timed out at 30s, persisted nothing
- Set `allow_fallback=True` regardless of success/failure
- Handbooks were generated with missing policy gaps silently
