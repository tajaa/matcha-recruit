# Plan: Payer Policy Definitions System (Future)

## Context

The regulation_key_definitions pattern (implemented on `policy-system-3-23`) solved compliance data integrity: 353 canonical keys, staleness SLAs, gap detection, bidirectional integrity checks, contextual weights. The payer medical policies system has the same structural problems and should get the same treatment — but as a separate effort after the current branch merges.

## Current Payer Architecture

- **Table**: `payer_medical_policies` keyed by `(payer_name, policy_number)`
- **Sources**: CMS API (Medicare NCDs/LCDs), Gemini research (commercial payers), RAG embeddings
- **Delivery**: Matcha Work payer mode (vector search → context injection)
- **Staleness**: `last_reviewed` DATE with no enforcement thresholds
- **Gap detection**: None — gaps only surface when a user query returns no results
- **Integrity**: Optional `confidence` field, no validation, no audit table

## Patterns to Apply from Regulation Key System

### 1. `payer_policy_definitions` table

Canonical registry of expected payer+procedure combinations:
- `key`: e.g., `uhc:77066` (payer:CPT code)
- `payer_name`, `procedure_code`, `procedure_description`
- `expected_payers[]` — which payers should have a policy for this procedure
- `staleness_warning_days`, `staleness_critical_days` — CMS quarterly, commercial annually
- `policy_group` — e.g., "oncology_screening", "cardiac_imaging" (like key_group)
- `base_weight` — how important this procedure is for coverage scoring

### 2. Gap detection

"Which payers are missing coverage data for common oncology procedures?"
- Cross-product: `payer_policy_definitions` × active payers → identify missing policies
- Priority by procedure weight and payer importance

### 3. Staleness SLAs

- CMS policies: 90-day warning (quarterly update cycle)
- Commercial payers: 180-day warning (annual review cycle)
- Admin-triggered staleness check (same pattern as `POST /admin/jurisdictions/run-staleness-check`)
- Write to `repository_alerts` (same table, different `alert_type` prefix)

### 4. Integrity checks

- Missing policies: expected procedure+payer combinations not in DB
- Orphaned policies: DB rows that don't match any defined procedure
- Stale policies: past their per-definition SLA threshold
- Low-confidence policies: Gemini research with `confidence < 0.5`

### 5. Change audit

- `payer_policy_change_log` — same pattern as `policy_change_log`
- Track field-level changes on upsert (CMS ingest already detects changes but doesn't log them)

### 6. Admin UI

- "Payer Index" tab on a payer admin page (same pattern as Key Index)
- "Payer Integrity" tab (same pattern as Integrity tab)
- Per-payer drill-down showing which procedures are covered/missing

## Key Difference from Compliance

Compliance is **jurisdiction × category × key** (geographic).
Payer is **payer × procedure_code** (organizational).

They share the same *patterns* but not the same *tables*. Don't try to merge them — the domain semantics are too different.

## Files to Modify (when implemented)

- `server/alembic/versions/` — new migration for `payer_policy_definitions` + audit table
- `server/app/core/services/cms_coverage_api.py` — add change logging on ingest
- `server/app/core/services/payer_policy_research.py` — link to definitions, validate against expected schema
- `server/app/core/routes/admin.py` — payer integrity-check + staleness-check endpoints
- `client/src/components/admin/` — Payer Index + Payer Integrity tabs

## Trigger

Implement when: (a) payer mode is used by real clients, or (b) payer data quality becomes a support issue (users asking about procedures and getting stale/missing data).
