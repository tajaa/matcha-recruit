# Compliance Architecture Audit — 2026-07-16

_Verdict on an external multi-jurisdiction architecture proposal, the gaps that
audit exposed in our own system, and the sequenced plan to close them._

Companion docs: `CODIFICATION_SYSTEM.md` (the pipeline this audits),
`COMPLIANCE_GAP_ANALYSIS.md` (data-coverage audit), `EVAL_SYSTEM.md` (measurement),
`ONE_COMPLIANCE_SYSTEM.md`, `VERTICAL_COVERAGE_PLAN.md`.

Every claim below was verified against the live dev DB (`matcha-postgres:5432`)
and current code on 2026-07-16. Nothing is inferred from schema names — see
Finding 7 for why that distinction matters here.

---

## 1. Verdict

An external design proposal ("Multi-Jurisdiction Compliance System — Architecture")
was evaluated against our system. **Our architecture is ahead of it on every axis
the proposal names.** All eight of its "architectural must-haves" are already
built, several better than proposed. It is not a better design than what we have.

**But it works as an audit checklist, and it exposed a real pattern: our schema
describes a more advanced system than our data supports.** The gap is not
architecture — it is population and closed loops. The audit also surfaced three
defects the proposal never contemplates, two of which are actively losing data.

### Scorecard vs. the proposal's must-haves

| Proposal's must-have | Us | Evidence |
|---|---|---|
| Bitemporal model ("can't be retrofitted") | **AHEAD** — we retrofitted it 2026-07-15 | `jurisdiction_requirement_versions` (1,984 rows) fed by DB trigger `trg_capture_requirement_version`. The proposal relies on app discipline ("never UPDATE a row"); a trigger can't be skipped by a forgotten write path — which is exactly why it exists (`jrver01:8-11` lists four paths the old app-side log silently missed). |
| Immutable audit + provenance snapshots | **PARTIAL** | Version log yes. Frozen snapshots: 5 rows / 1781. See Finding 4. |
| AI/verified separation, read path can't reach | **AHEAD** | Proposal wants a `trust_state` column. We have `status='pending'`→`'active'` enforced as a **WHERE clause** (`compliance_service.py:1511`), the codified trio, **and** a read-time gate (PR #44) the proposal has no analogue for. Verified: 0 pending rows reach any tenant. |
| Deterministic runtime read path | **AHEAD** | Not "Gemini is off because a flag says so" but structurally unreachable: tenants get `project_location_from_catalog`, a different function with no path to Gemini (`compliance.py:229-241`). Caveat: `/compliance/ask` is tenant-reachable by design (user-initiated, RAG-grounded, 10/hr). |
| Structured applicability predicates | **AHEAD in engine, starved of data** | Proposal offers JSONB `@>` containment and names its own ceiling: *"ranges (`employees >= 15`) and negation need a rules engine."* We already have that rules engine — `evaluate_trigger_conditions` (`compliance_service.py:9471`) does `and/or/not` + `eq/neq/gt/gte/lt/lte/in/contains/exists`, and **fails closed** on unknown ops. The proposal never addresses fail-open, which is the actual liability question (ours failed open once and served the PSM standard to a bakery). See Finding 6. |
| Jurisdiction as resolvable hierarchy | **AHEAD** | `jurisdictions.parent_id` + recursive-CTE chain walk; cells are chain nodes owning exactly one level. The proposal calls this "consistently underestimated" — it's where we invested most. |
| Async work off the request path | **YES** | Celery. |
| Explicit "unknown" coverage state | **AHEAD** | Proposal has one `unchecked`. We have five: `pending/in_progress/covered/empty/failed`. `empty` (looked, found nothing — never retry) vs `failed` (retry) is a distinction it cannot express; its absence is what made us re-research empty cells forever. |

Not in the proposal at all: the **read-time codified gate**, the **compliance evals
suite**, and **two** independent content stores (statute body text + source-page
snapshot) where it designs one.

### What's worth taking from it

Only two ideas we genuinely lack: **peer benchmarking** ("40 similar dental offices
carry requirement R, this one doesn't" — we have expected-keyset gaps, never
population statistics) and **applying snapshot discipline to legislation** (bill
tables have no version history, no snapshot, and a model-emitted `confidence` as
their only trust signal — while requirements got all three).

---

## 2. Scope: what is codification, what is general catalog

Per `CODIFICATION_SYSTEM.md`, the pipeline is:

```
INGEST ─▶ CLASSIFY ─▶ CONFIRM ─▶ KEY ─▶ RESEARCH ─▶ CODIFY ─▶ (RECONCILE / DRIFT)
```

…and the business reads its obligations from one table, `jurisdiction_requirements`.
That boundary splits this audit's findings cleanly, and the split matters because
codification — not the catalog at large — is the product's value claim:

**Codification system** (the `scope_registry` pipeline):
- **A4** — `authority_index_items.body_text` is **0/59**. The RESEARCH stage grounds
  its value on body text; the column is empty, so that stage isn't grounding on
  statute bodies at all.
- **A1** — the 29 codified rows are the asset; **27 have no frozen source**.
- **B2** — `change_status` is the DRIFT stage's *output*. `propagate_drift_to_requirements`
  writes `needs_review` into a column whose readers can't match it.
- **E1** — hash-based drift feeds that same DRIFT stage.

**General catalog + its projection to tenants** (not codification):
- **A2** (tier-1 snapshots), **A5** (legislation snapshots), **B1** (the projection
  history CASCADE), **C** (world time on the read path), **D** (change notification),
  **G** (applicability vocabulary).

Both matter. But if forced to one, the codification core is A4 + A1 + B2 + E1.

---

## 3. Findings

Ranked by exposure. Codification-core items marked **[C]**.

### 1. Catalog changes reach tenants silently, and late
The proposal's "fan-out on promotion" is what we most lack.
- **No event-driven fan-out.** A changed catalog row reaches a tenant by a 7-day
  **pull** (`compliance_checks.py:63-80`). The targeted push on approve
  (`admin.py:9885-9893`) only reaches companies that **filed a coverage request**;
  everyone else waits for their poll.
- **Throughput ceiling**: dispatcher is `LIMIT 2` per cycle, worker restarts every
  15 min → **~192 locations/day**, fleet-size-bound, not 7-day-bound.
- **And when it lands, nobody is told.** `_sync_requirements_to_location` computes
  `changes_to_verify` (`:3629-3637`) and returns it — then `project_location_from_catalog`
  **discards it** (`:3835-3839`). `alert_type="change"` exists only on admin-only
  paths (`:6224`, `:9017`). Minimum wage goes $16.00 → $16.50, the row updates under
  the customer, `policy_change_log` records it, and the customer is never notified.

### 2. Drift is a proxy, not a measurement **[C, in part]**
Three monitoring loops exist; **none compares a stored requirement's value to its
live source.**
- `legislation_watch` — RSS discovery only; never reads `jurisdiction_requirements`.
  Alerts every location in the state regardless of category. The loop is open: the
  alert and the stale requirement it contradicts coexist.
- `authority_ingest` drift **[C]** — diffs eCFR **citation lists and heading strings**
  (`authority_ingest.py:230-300`). A regulator that changes a wage rate without
  editing the section heading produces **zero signal**. `authority_index_drift` has
  0 rows; the path has never fired.
- `structured_data_fetch` — 4 sources, **all minimum-wage**, 3 of 4 aggregators
  (Berkeley/EPI/NCSL), writing **cache only**, read solely by admin research.

### 3. `compliance_requirement_history` CASCADE destroys the history it saves
Live defect. The prune path snapshots, then deletes (`compliance_service.py:3741-3744`):
```python
await _snapshot_to_history(conn, stale, location_id)
await conn.execute("DELETE FROM compliance_requirements WHERE id = $1", stale_id)
```
But the history FK is (verified on dev):
```
compliance_requirement_history_requirement_id_fkey
  FOREIGN KEY (requirement_id) REFERENCES compliance_requirements(id) ON DELETE CASCADE
```
The DELETE cascades and erases the row just written **plus all prior history** for
it. Live state is consistent: 675 history rows, **0 orphaned survivors**.

The contrast is the tell — `jurisdiction_requirement_versions` has **0 foreign keys**,
deliberately (`jrver01:55`: *"versions must survive the requirement's delete"*).
Same codebase, opposite decisions. Same defect at `:3518-3522`.

Prune is also driven by `new_requirement_keys`, so an under-emitting run silently
deletes live tenant rows; the ad-hoc guards at `:3552-3558` and `:3703` are evidence
the failure mode is known and being patched case-by-case rather than structurally.

### 4. "Codified" isn't yet provable — both content stores are empty **[C]**
The promise is *without a doubt*. Today codified means a citation string and a live
link, not frozen text:
- `requirement_source_snapshots`: **5 / 1781**, all `context='approve'`.
- `authority_index_items.body_text`: **0 / 59** — `statbody01` shipped the fetchers;
  nothing calls them. Per `CODIFICATION_SYSTEM.md` this is the RESEARCH stage's
  grounding input.
- **27 of our 29 codified rows have neither.**

`snapshot_source()` already exists — best-effort, hash-deduped, supports
`approve|codify|research|verify`. Only two contexts call it; nothing backfills.

### 5. World time is stored but never read
`effective_date` (1271/1781), `expiration_date` (6) are stored and carried through
the upsert — but only `handbook_service.py:1464` filters on them. The Requirements
tab does not. Live today:

> **Colorado EEO-1 Demographic Reporting**, `effective_date = 2027-07-01`, is
> projected to a tenant right now as a current obligation, unmarked.

One row, small blast radius — but the mechanism is wrong and grows with
forward-looking research. The proposal's proactive framing ("compliant today, X
takes effect March 1") is product value we're leaving on the table;
`upcoming_legislation` does it on a separate axis the catalog ignores.

### 6. The predicate engine is better than the proposal's, and starved
- Only **1 of 5** `_filter_requirements_for_company` call sites runs the trigger pass
  (`_project_chain_to_location:1588`); `:5072`, `:5200`, `:6026`, `:6544` don't.
- `trigger_conditions` populated on **135/1781**. Curated `TRIGGER_PROFILES` use
  exactly two attribute keys (`entity_type`, `payer_contracts`) — both healthcare.
- `facility_attributes` is free-form JSONB with **no vocabulary and no validation**.
- So **"employers with ≥15 employees" cannot be expressed today** — the evaluator
  would handle it; there is no attribute, no data, no write path.
- Industry matching itself is a Python set-intersection post-fetch, with a
  substring-marker fallback including a literal `" sb 525"` check (`:180`).

### 7. Dead columns make the design look better than it is
`fetch_hash` (0 writers), `structured_source_id` (0), `superseded_by_id` (0),
`status='superseded'` (unreachable outside a dedupe migration), `min_employee_threshold`
(0 readers). Anyone auditing our schema — including a future us — overcounts what
is live. This audit had to verify every column against data for exactly this reason.

### 8. `change_status` carries literal quotes — drift counters read 0 **[C]**
Stored values are `'new'` (5 chars, quotes included) and `'unchanged'` (11). Every
comparison in `admin.py` is unquoted. Proven on dev:
```
changed_count | new_count | needs_review | new_if_unquoted | unchanged_if_unquoted
            0 |         0 |            0 |            1348 |                   433
```
`admin.py:5139-5140` report 0/0 where truth is 1348/433; the `needs_review` filter
(`:4283`, `:4305`) can never match; index `idx_jr_needs_review` is permanently empty.
The ORM (`server_default="new"`) and migration `t5u6v7w8x9y0` are both **correct** —
the live column default is `'''new'''::character varying`, so something ALTERed it.
Find the writer before fixing the data.

### 9. Genuinely absent
- **Peer benchmarking** — we have expected-keyset gaps (per-jurisdiction facts),
  never population statistics. `peer_rows` (`:6994`) is a false friend: same
  company's other locations.
- **Legislation is the unprotected flank** — no version history, no snapshot,
  model-emitted `confidence` as sole trust signal. Bill text is exactly what changes
  between reads.
- **Special districts** — modeled (`authority_type`, enum value) but
  `_LEVELS_OWNED_BY` (`vertical_coverage.py:71-77`) lists only
  federal/national/state/county/city, so they're silently dropped from every chain.
- **Coverage axes ≠ applicability axes** — the ledger tracks jurisdiction × industry
  × category; trigger-conditional obligations are orthogonal to all three, so a cell
  can read `covered` while every trigger-gated obligation in it is unresearched.

---

## 4. Plan

**This round: A + B + C + E1 + G.** D is its own PR after. E2 and peer benchmarking
deferred with reasons stated below.

### A. Make codified provable — Findings 4, 9
1. **[C]** Admin-triggered backfill over the **29 codified rows** first (27 need one),
   via existing `snapshot_source(conn, id, url, "verify", client=shared)` — one shared
   `httpx.AsyncClient`, best-effort, already idempotent on the content-hash unique.
2. Extend to `status='active' AND source_tier='tier_1_government'` (332 rows).
3. Wire the `research` context into the routed research upsert — snapshot at birth,
   not only at approve. Also fix the Compliance Pilot commit path, which currently
   ignores `snap_targets` (`research_review.py:36-38`, `:116-117`).
4. **[C]** Find why `statbody01`'s body fetchers are never called; populate
   `authority_index_items.body_text` (0/59). This is the RESEARCH stage's grounding
   input — investigate before writing code.
5. **Legislation snapshots**: point the same `snapshot_source` pattern at
   `jurisdiction_legislation` / `upcoming_legislation` source URLs (new context or a
   sibling table keyed on legislation id — decide at implementation). Optional second
   migration: extend the `jrver01`-style version trigger to the legislation tables.

### B. Fix the live defects — Findings 3, 8, 7
1. Migration: drop the `compliance_requirement_history` FK (match the `jrver01:55`
   precedent) or `ON DELETE SET NULL`. Already-lost history is unrecoverable, so
   sooner = less loss. Same defect at `compliance_service.py:3518-3522`.
2. **[C]** Migration: `btrim(change_status, '''')` + fix the column default
   (`'''new'''` → `'new'`) + **find the writer that quoted them first**.
3. Fold dead-column cleanup into the same migration — it's nearly free here:
   `superseded_by_id` (redundant now the versions table exists), `min_employee_threshold`
   (stays dead even after G, which puts `employee_count` in `facility_attributes`),
   `structured_source_id`. **Keep `fetch_hash`** — E1 revives it.

### C. Read world time — Finding 5
Add `AND (effective_date IS NULL OR effective_date <= CURRENT_DATE)` +
`(expiration_date IS NULL OR expiration_date >= CURRENT_DATE)` to the projection,
and surface future-effective rows as a distinct "takes effect {date}" lane rather
than hiding them — the proactive framing is the product value. Follow
`handbook_service.py:1464`, which already does the expiry half.

### E1. Drift phase-1 — hash-based change detection **[C]** — Finding 2
Depends on A; blocked on B2 (writing `needs_review` into a column whose readers
can't match it is useless). Scheduled worker, `scheduler_settings` row seeded
**disabled** per convention: re-fetch snapshotted source URLs, compare `content_hash`;
changed hash → `change_status='needs_review'` + a `metadata.drift` breadcrumb reusing
the exact shape the authority-drift propagator writes, so the existing admin
resolution endpoint (`admin.py:5994-6038`) works unchanged. **Revives `fetch_hash`**
(stamp the last-checked hash on the catalog row). No LLM; no spend beyond fetches.

### G. Trigger vocabulary — Finding 6 groundwork
Define a validated key vocabulary for `business_locations.facility_attributes`
(start: `employee_count` int, plus the two live keys `entity_type` / `payer_contracts`,
plus a small curated set). Enforce at the write path
(`routes/compliance.py:1356-1379 update_facility_attributes`) — reject unknown keys
and wrong types, mirroring how scope-registry `validate_proposal` gates classification
shapes. Deliverables: vocabulary constant + validator + tests + short doc.

Does **not** widen the trigger pass to the other 4 read paths yet — that only becomes
meaningful once triggers are populated against this vocabulary, and widening a pass
over 135/1781 rows against an unvalidated attribute bag would change tenant results
based on garbage.

### D. Close the notification loop — Finding 1 — next PR
Stop discarding `changes_to_verify` in `project_location_from_catalog`; emit
`alert_type="change"` on the tenant path. Then real fan-out on catalog change instead
of the 7-day pull, and raise the `LIMIT 2` dispatcher ceiling.

### Deferred, with reasons
- **E2 — value-level drift**: extract the value from changed page prose and
  semantically compare to stored `current_value`. A Gemini pass per changed row;
  needs design + spend controls. E1 delivers the deterministic half first.
- **Peer benchmarking**: pre-customer. Cohort size is N≈1 — we cannot benchmark one
  dental office against itself. Real idea; no data to run it on.
- **Widening the trigger pass**: genuine dependency on G, see above.
- **Special districts in the chain walk** (Finding 9): schema supports them, the
  walk drops them. Scoped separately.

---

## 5. Verification

- **A**: re-run `codified_without_snapshot` → 29 → ~0 (dead URLs record `http_status`
  and stay auditable misses, so ~0 not 0). Legislation: every row with a URL gains a
  snapshot or an auditable miss.
- **B**: `new_count` at `admin.py:5140` must return 1348, not 0. For the FK: a
  rehearsed prune must leave the history row standing.
- **C**: the Colorado EEO-1 row leaves the live list and appears in the upcoming lane;
  `projected_but_not_yet_law` → 0.
- **E1**: hand-edit one snapshot's stored hash on dev, run the worker → the row flips
  to `needs_review` with a breadcrumb the existing admin endpoint can clear. Unchanged
  pages write nothing (hash dedupe).
- **G**: posting an unknown key or wrong-typed value to `update_facility_attributes`
  422s; the two live keys keep working; validator unit tests are DB-free.
- Tests: `server/tests/compliance/`, `server/tests/scope_registry/`. The `change_status`
  normalization and the world-time predicate are DB-free unit tests.
- **Prod**: no DDL without explicit approval; `compliedrem01` is still dev-only. Every
  migration follows `server/CLAUDE.md` rules — set-based, real `downgrade()`, committed
  before applying, rehearsed via `MIGRATE_REHEARSAL=1`.

## Appendix — queries used

```sql
-- Finding 4: codified rows lacking frozen evidence
WITH codified AS (
  SELECT id FROM jurisdiction_requirements
  WHERE statute_citation IS NOT NULL
    AND citation_verified_at IS NOT NULL
    AND citation_item_id IS NOT NULL
)
SELECT (SELECT count(*) FROM codified) AS codified_rows,
       (SELECT count(*) FROM codified c
          WHERE NOT EXISTS (SELECT 1 FROM requirement_source_snapshots s
                            WHERE s.requirement_id = c.id)) AS codified_without_snapshot;

-- Finding 5: projected to tenants but not yet law (or expired)
SELECT count(*) FILTER (WHERE jr.effective_date > CURRENT_DATE)  AS projected_but_not_yet_law,
       count(*) FILTER (WHERE jr.expiration_date < CURRENT_DATE) AS projected_but_expired
FROM compliance_requirements cr
JOIN jurisdiction_requirements jr ON jr.id = cr.jurisdiction_requirement_id;

-- Finding 8: the dead counters
SELECT count(*) FILTER (WHERE change_status = 'new')                  AS new_count,
       count(*) FILTER (WHERE btrim(change_status, '''') = 'new')     AS new_if_unquoted
FROM jurisdiction_requirements;

-- Finding 3: history rows that outlived their requirement (expect 0 = cascade fired)
SELECT count(*) FILTER (
  WHERE NOT EXISTS (SELECT 1 FROM compliance_requirements cr WHERE cr.id = h.requirement_id)
) AS orphaned_survivors
FROM compliance_requirement_history h;
```
