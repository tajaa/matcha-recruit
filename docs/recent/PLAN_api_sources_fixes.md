# Fix API Sources Tab — 3 Improvements

## Context
The new "API Sources" tab on the Jurisdiction Data admin page queries `jurisdiction_requirements` by `metadata->>'research_source'`. This must align with the existing tiered policy system:
- **`source_tier`** (DB enum column): `tier_1_government` / `tier_2_official_secondary` / `tier_3_aggregator` — displayed in PolicyBrowserTab TierBadge and Data Quality tab
- **`research_source`** (metadata JSONB): `official_api` / `gemini` / `claude_skill` / `structured` / `manual` — displayed in the new API Sources tab cards
- These are complementary: source_tier = confidence level, research_source = provenance/origin
- Both are admin-only — business users in Compliance.tsx / ComplianceRequirementsTab.tsx never see either field
- IR and ER Copilot consume company `policies` table, not `jurisdiction_requirements` — no impact there

---

## 1. Add functional index on `metadata->>'research_source'`

**Why:** All 3 queries in the API Sources endpoint filter/group on this JSONB key with no index. The existing `ix_jurisdiction_requirements_source_tier` index covers the enum column but not the JSONB path.

**File:** New Alembic migration `server/alembic/versions/zs7t8u9v0w1x_add_research_source_index.py`
- `revision = "zs7t8u9v0w1x"`, `down_revision = "zr6s7t8u9v0w"`
- upgrade: `CREATE INDEX IF NOT EXISTS ix_jr_research_source ON jurisdiction_requirements ((metadata->>'research_source'))`
- downgrade: `DROP INDEX IF EXISTS ix_jr_research_source`

**Note:** DDL on production DB — needs user approval before `alembic upgrade head`.

---

## 2. Tag all `_upsert_requirements_additive` calls with `research_source`

**Why:** Only `federal_sources.py` passes `research_source="official_api"`. All Gemini and MD-import calls leave it unset → rows appear as "Untagged" in the API Sources tab, even though they have correct `source_tier` values.

### A. Service calls (compliance_service.py)

Add `research_source=` parameter to these existing calls:

| Line | Context | Tag | Rationale |
|------|---------|-----|-----------|
| 1425 | `_upsert_jurisdiction_requirements_routed` (MD-to-DB importer) | `"structured"` | Tier-2 curated data from markdown repository |
| 1666 | `_research_healthcare_requirements_for_jurisdiction` | `"gemini"` | Gemini AI research |
| ~1755 | Healthcare trigger profiles | `"gemini"` | Gemini AI research |
| ~1863 | Oncology research | `"gemini"` | Gemini AI research |
| ~2009 | Medical compliance research | `"gemini"` | Gemini AI research |
| ~2106 | State-level caching | `"gemini"` | Gemini AI research |
| ~4562, ~7071 | Trigger profile research | `"gemini"` | Gemini AI research |
| ~7505 | Repository refresh | `"gemini"` | Gemini AI research |
| ~8304 | Specialization research | `"gemini"` | Gemini AI research |

Each change is a single keyword argument addition, e.g.:
```python
await _upsert_requirements_additive(conn, jurisdiction_id, reqs, research_source="gemini")
```

### B. Backfill existing rows (scripts/backfill_research_source.py)

Add a second UPDATE to tag Gemini-sourced rows that are currently untagged:
```sql
UPDATE jurisdiction_requirements
SET metadata = COALESCE(metadata, '{}'::jsonb) || '{"research_source": "gemini"}'::jsonb
WHERE source_tier = 'tier_3_aggregator'
  AND (metadata IS NULL OR metadata->>'research_source' IS NULL)
  AND source_name NOT LIKE 'Federal Register%'
  AND source_name != 'CMS Provider Data'
  AND source_name != 'Congress.gov'
```

This uses the existing `source_tier` as a heuristic — tier_3 rows that aren't from known official APIs are Gemini-researched. This is safe because:
- Tier 1/2 rows come from structured data sources (already have proper attribution)
- Tier 3 is the default for all Gemini-researched data

---

## 3. Fix ORDER BY for recent entries

**Why:** Query sorts by `jr.created_at DESC` but the frontend "Updated" column shows `updated_at ?? created_at`. Recently-updated old entries won't surface.

**File:** `server/app/core/routes/admin.py` line 3515

Change:
```sql
ORDER BY jr.created_at DESC
```
To:
```sql
ORDER BY COALESCE(jr.updated_at, jr.created_at) DESC
```

---

## Files to modify

1. `server/alembic/versions/zs7t8u9v0w1x_add_research_source_index.py` — **new file** (Alembic migration)
2. `server/app/core/services/compliance_service.py` — add `research_source=` kwarg to ~10 calls
3. `server/app/core/routes/admin.py` — fix ORDER BY on line 3515
4. `scripts/backfill_research_source.py` — add second UPDATE for Gemini rows

## Verification

1. Run `alembic upgrade head` (after user approval) to create the index
2. Run `python scripts/backfill_research_source.py` to tag existing rows
3. Start server, open admin Jurisdiction Data → API Sources tab
4. Confirm: source cards show proper counts for "Official APIs", "Gemini AI", "Structured Data" instead of a large "Untagged" bucket
5. Confirm: recent entries table sorts by most recently updated
6. Confirm: PolicyBrowserTab still shows correct TierBadge colors (unchanged — source_tier is a separate column)
7. Confirm: Compliance page for business users is unaffected (doesn't read metadata.research_source)
