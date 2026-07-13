# Matcha ONE Compliance System — Gap Synthesis Review

_Synthesis of 50 adversarially-verified gap findings across 8 lanes (scope-registry-engine, runtime-read-path, eval-measurement, gap-surfaces, scope-studio-ui-api, data-coverage, freshness-workers-drift, cross-cutting). Every gap is tied to file:line evidence. Goal frame: "the most comprehensive labor-law intelligence repository + compliance system."_

---

## Executive Summary

The ONE compliance system is **architecturally complete on paper but early and largely inert in practice.** Three things are simultaneously true:

1. **The new codification engine is built end-to-end but nowhere authoritative.** Every real onboarding still runs the legacy Gemini `expand_scope→map_to_bank` category-grab; `resolve_scope` output is only logged to `scope_shadow_log` and discarded. The "ONE definition of scope" is aspirational.
2. **The engine cannot actually grow the Library.** `codify.py` mints **zero** `jurisdiction_requirements` rows (it only stamps citations onto rows the legacy research pipeline already wrote); the sole value-minter is a single admin SSE button; every scheduled/freshness task is seeded **DISABLED**.
3. **Data coverage is two jurisdictions and two industries wide.** Federal + California only; 2 of ~17 industries have a core checklist; 1 of 20+ healthcare sub-verticals is codified; **54 human-verified golden facts** across 6 US jurisdictions, all still `claude-research`-authored and self-declared unverified.

The measurement layer that should make this thinness visible is itself dormant (evals never auto-run) and structurally biased (unfounded completeness denominator, federal criticals dropped from the gate, scope has no subscore). **The codification investment is real and correct where tested — but stranded behind an un-flipped cutover, an un-built operator UI, and a corpus two jurisdictions wide.** The highest-leverage work is not more architecture.

---

## State-of-the-Pipeline Snapshot

| Stage | Built? | Wired to runtime? | Auto-runs? | Notes |
|---|---|---|---|---|
| INGEST | ✅ | Curl/CLI only | Scheduler seeded **off** | No UI button (`ScopeStudio.tsx`) |
| CLASSIFY | ✅ | Curl only | Only via admin route | Writes `provisional` |
| CONFIRM | ✅ (endpoints) | ❌ no UI caller | — | Engine reads `confirmed`-only → reads ~nothing |
| KEY | ✅ (endpoint) | ❌ no editor | — | Unkeyed items permanently stalled |
| RESEARCH (fetch-queue) | ✅ | 1 admin button | ❌ no worker | Only value-minter |
| CODIFY | ✅ | side-effect of research | ❌ | **Mints 0 rows** — citation-stamp only |
| RECONCILE/DRIFT | ✅ (code-complete) | drift UI-wired | ❌ (needs 2 ingests + enabled sync) | Detector produces 0 flags by default |
| resolve_scope (read) | ✅ | **SHADOW only** | — | Logged + discarded; no cutover path |
| Evals | ✅ (7 suites) | read-path reads stored runs | ❌ seeded disabled | Only completeness computed live |

**Coverage funnel (doc's worked example, verified against data):** ~334 federal sections enumerated → ~11 keyed → ~5 codified, out of a ~27 federal + ~23 CA master-list. **The corpus is federal + CA, full stop.**

---

## Themed Gap Sections

### 1. Data coverage is two jurisdictions and two industries wide _(CRITICAL — the raw comprehensiveness bottleneck)_

The codified corpus the whole pipeline feeds is **US-federal + California only**. Everything else is served by legacy runtime-research rows, not the new codified/scoped corpus. Industry breadth is taxonomic, not substantive.

- `authority_sources.py:51-127` — exactly 11 authority indexes (6 federal eCFR + `us-flsa`/`us-labor-baseline` + `ca-labor-code`/`ca-title-8`/`ca-title-16`). `all_index_slugs()` returns only these.
- `resolve.py:205-210` — any non-CA state hits the documented degrade path _"no state jurisdiction row — coverage degrades to federal only."_ `baseline_masterlist.py:233-238` `BASELINE_JURISDICTIONS=('federal','ca')`.
- `curated_ca.py:230-261` — exactly **5** optometry/opticianry rows codified; `seed.py:112-116` maps them to `ophthalmology`. Taxonomy (`categories.py:109-144`) advertises **20+** clinical verticals (dental, nursing, pharmacy, oncology…). Single biggest "promised but empty" gap for the healthcare book.
- `industry_keysets.py:101-139` — `CORE_INDUSTRY_KEYSETS` has only `manufacturing` + `healthcare`; `INDUSTRY_CATEGORY_SETS:49-58` gives hospitality/retail/technology/`fast food` an **empty frozenset** (no industry-specific expectation at all). `runner.py:433-435` raises for `depth='core'` on the other ~15 slugs.
- `baseline_masterlist.py:60-157` — all 27 federal marquee obligations (Title VII, ADA, ADEA, WARN, I-9, COBRA, ERISA, NLRA, USERRA, FCRA, EEO-1, GINA, PWFA) exist as **scope rows only**; `codify.py` creates no value, so they are pointers without a codified obligation until a research row exists. _(Bodies ARE fetchable via `body_fetch.py:143-159` govinfo/USC path — the gap is codified value, not missing ingest.)_
- All 54 golden facts + curated federal/CA rows carry `curated_by='claude-research'` with **no `verified=true`** (`curated_ca.py:9-15`, `curated_us.py:15-18`) — even the ground-truth corpus is unverified.
- **Warehouse→AB701 flagship still fails end-to-end:** warehousing has `legacy_industry=None` (`categories.py:194`) → empty tags → `_filter_requirements_for_company` drops **all** industry-tagged rows (`compliance_service.py:2789-2790`); AB701 quota data lives only in the dormant `scope_codifications` tables (`curated_ca.py:138-174`, `verified=False`), never reaching the served catalog.
- Phase-E domains (data_privacy, food_safety, construction, DOT, financial) have **zero** taxonomy in any migration — non-labor/non-healthcare businesses have no domain to be scored against.

**Fill:** Author authority indexes + baseline master-lists + ≥10 golden facts per jurisdiction for NY/TX/IL/WA/FL + NYC/Chicago/Seattle/SF (mirror the CA slice). Curate ≤30-key core keysets for restaurant/hospitality, retail, construction, warehousing, tech. Codify the marquee federal statutes + top clinical boards (nursing/dental/pharmacy) starting in CA. Give warehousing a non-null `legacy_industry` or teach the tag filter the new slugs. Stand up Phase-E domain migrations + the E1 coverage-manifest so un-modeled domains fail loud. _(Partly tracked: `COMPLIANCE_REMEDIATION_PLAN` Phase-E, `COMPLIANCE_GAP_ANALYSIS.md:239`.)_

### 2. The registry is never authoritative — the shadow→cutover promise never shipped _(CRITICAL)_

`resolve_scope` was to ship SHADOW-first then take over. It is **permanently shadow**: `expand_scope→map_to_bank` is the sole writer of company scope, and there is **no cutover mechanism in code**.

- Authoritative population: `_write_compliance_scope_rows(existing_items=resolved.get('existing'))` at `admin_onboarding.py:1417-1423`, fed by `ai_expand_scope→map_to_bank` (`:1154/1241`).
- `resolve_scope`'s only runtime callers are non-authoritative: admin preview GET (`scope_registry.py:309-315`), the discarded `record_shadow` diff (`shadow.py:58-113`, docstring _"expand_scope stays authoritative"_), and the gap-dashboard overlay that _"never overwrites"_ the bank arrays (`admin_onboarding.py:1706-1728`).
- `scope_shadow_log` has exactly one reader — the admin diff route (`scope_registry.py:485-507`). No code promotes `only_in_resolve` into any tenant's scope. Grep for any cutover/flag/promotion switch = nothing.
- The actionable "Research a gap" list is always the category-grab; the engine's grounded worklist is shape-incompatible (`gap_surfaces.py:11-19`) and surfaces only as a coverage badge.
- **The confidence surface to justify cutover is invisible:** `scope_shadow_log` is written every finalize but consumed by **no UI** (grep client/src = 0 hits) — the shadow phase can never end.
- Shadow is admin-only + untested on real data: `record_shadow` wired at one callsite (`admin_onboarding.py:1522-1529`); self-serve Compliance/Lite/X (`matcha_x_onboarding.py`) never call it; `test_shadow.py` exercises only pure set math.

**Fill:** Feature-flagged per-jurisdiction/industry "registry-authoritative" gate in `finalize` consuming `resolve_company_scope` where proven (federal+CA first), falling back to `expand_scope` elsewhere. Render `/shadow-log` in Scope Studio with an agreement-rate rollup as the go/no-go signal. Wire `record_shadow` into the self-serve build path. Add an engine-sourced "Research a gap" worklist. _(Tracked: `SCOPE_REGISTRY_PLAN.md` commit 5/6 — the deferred step.)_

### 3. The codification engine cannot grow the Library _(CRITICAL)_

CODIFY is **enrichment-only** and **dormant**, and ungrounded model-recall values persist under the "codified" join.

- `codify.py` has **0** `INSERT INTO jurisdiction_requirements`. `reconcile_codifications` upserts `scope_codifications` linkage (`:668-684`) + stamps citations onto **existing** rows (`:696-708`); an unmatched `regulation_key` lands in `unmatched_keys` and never becomes a value.
- Sole value-minter: `research_specialization_for_jurisdiction` via `POST /fetch-queue/research` (`scope_registry.py:351-469`), whose **only** caller is one Scope Studio button (`ScopeStudio.tsx:875-876`). No worker calls research or reconcile — growth is manual per-chain clicks.
- `scope_registry_authority` scheduler seeded `enabled=false` (`scoperg01:250-260`); dormant in prod.
- **Grounding gate persists ungrounded VALUES:** `compliance_service.py:9216-9234` upserts both grounded and ungrounded reqs (only penalties nulled); `validate_requirement_citations` (`grounded.py:98-104`) never removes a req — a hallucinated value can be codified and string-joined as "codified" (`grounded.py:91-94` concedes it's _"not a value-provenance guarantee"_).
- New (`'new'`) citations on re-ingest are auto-stamped propagated with no path back to classify (`codify.py:411-413,451-460`); ingest never dispatches classify.
- Specialty derive→research still writes via the **legacy ungrounded** pipeline (`ScopeStudio.tsx` `researchTargetGap` → `/admin/specialization-research/run` → `research_specialization_for_jurisdiction` WITHOUT `grounded_corpus`, `admin.py:7801-7809` → `metadata.grounding='ungrounded'`).

**Fill:** Give codify a CREATE path. Add a scheduler-gated headless `fetch_queue → research → reconcile` task. Quarantine ungrounded values (`status='provisional'` / review queue) so the codified join can't serve them; add an ungrounded-value eval metric. Auto-dispatch classify on `'new'` drift. Route specialty-gap research through the grounded path.

### 4. The engine layer is structurally dark — all-or-nothing gates _(CRITICAL)_

Even where data exists, the grounded verdict can never render because the covering **federal** index (shared across every chain) is far from fully classified.

- `registry_expected_keys` (`completeness.py:151-157`) returns `None` if ANY covering index has `unclassified_count>0`; federal (`jurisdiction_id IS NULL`) is unconditionally covering → `None` everywhere → `expectation_source='registry_groups'` (the unfounded `industry_keysets` denominator) for every cell (`:236-241`).
- `gap_surfaces.py:128-134/282-285` collapses `coverage_source` to `'bank'` unless engine is definitive for ALL coords; `GapDashboard.tsx:340-357` renders the grounded badge only when `coverageSource==='engine'` → **entire overlay is dead weight** until federal reaches 0 unclassified (~5 of ~334 today).
- **No confirm/override UI:** classify writes `provisional` (`classify.py:517,529`); confirm/override endpoints exist (`scope_registry.py:253-281`) but grep client/src = **0 callers**; every engine read filters `confirmed` (`resolve.py:389`, `codify.py:245/562`, `strata.py:58`, `labor_scope.py:235`, `completeness.py:191-202`) → reads ~empty set unless the `populate_scope_registry.py` CLI was run.
- **No KEY editor:** `PUT /items/{id}/classification` exists (`scope_registry.py:263-281`, comment _"there is no FE editor to re-supply it"_) but is unwired — unkeyed items permanently stalled.
- **Front half un-driveable from UI:** grep client/src = 8 scope-registry call sites, all read/RESEARCH/DRIFT; ingest/classify/seed/confirm/strata/reconcile are curl-only; empty state says run `server/scripts/populate_scope_registry.py` (`ScopeStudio.tsx:978`).
- RECONCILE, strata view, GET fetch-queue worklist defined (`scope_registry.py:284/325/337`) but never surfaced.

**Fill:** Loosen the gate to **per-category/per-key** definitiveness (or a partial-verdict honesty banner). Build an Authority/Codification tab over the existing endpoints: index list + funnel bars, a `classified=false` confirm/override queue, a KEY-assignment drawer, a strata inspector, a Reconcile button.

### 5. The measurement layer is dormant and structurally biased _(HIGH)_

- `compliance_evals` scheduler seeded `enabled=false` (`jureval01:118-130`); no celery-beat → every non-completeness subscore empty unless an admin clicks Run (`runner.py:385-478`). 2,724 rows / 105 jurisdictions have no accuracy/authority/freshness/tag measurement on any cadence.
- **Golden caps ~99 of 105 jurisdictions at DEGRADED:** 54 facts / 6 jurisdictions; `MIN_GOLDEN_FACTS_READY=10` (`scoring.py:19`) + accuracy does **not** inherit the chain (`golden.py:_rows_for` filters `jurisdiction_id=$1`) → LA(6)/SF(4)/NYC(4) and every fixture-less jurisdiction (all international) can never be READY.
- scope + grounding excluded from the scheduled sweep (`compliance_evals.py:83-89`); scope is findings-only, no subscore (`scope.py:59-60`); grounding tier-2b verifier off by default (`config.py:180`).
- **Federal scope criticals never gate readiness:** `runner.py:286-288` drops `jid=None`; `_resolve_jurisdiction_ids` excludes federal (`:112-114`) → a jurisdiction reads READY over a 95%-uncodified federal baseline.
- Scope registry has **no 0–100 subscore** (`scoring.py:40-55` `Subscores` lacks a scope field).
- Penalty coverage, preemption correctness, and jurisdiction breadth measured by **no** suite (enumerated every `finding_type`); a wholly-absent state yields no cell/finding.
- Completeness's registry repoint is dead until an index is fully hand-classified (`completeness.py:132-134`) — the unfounded denominator gates the 90% readiness threshold.

**Fill:** Flip the evals scheduler on + heartbeat alert. Make golden inheritance-aware + a fact-authoring pipeline (≥10/jurisdiction). Add scope+grounding to the sweep; give scope a subscore; fold federal criticals into the gate. Add penalty/breadth/preemption suites. Relax the `unclassified_count=0` gate to a per-key floor; surface `expectation_source` in the UI.

### 6. The freshness / keep-current loop is dormant and broken at its seams _(HIGH)_

- All freshness schedulers seeded `enabled=false` (`legislation_watch`, `pattern_recognition`, `structured_data_fetch`, `scope_registry_authority`, `compliance_evals`, `handbook_freshness`, `risk_assessment` — `database.py:588-598` + migrations); no celery-beat → nothing runs out of the box, undocumented as a go-live step.
- **legislation_watch is a dead-end:** only persists `INSERT INTO compliance_alerts` (`legislation_watch.py:223-245`); grep for `scope_*`/`jurisdiction_requirements`/`needs_review` = 0 — a new law becomes a tenant nudge, never a codified obligation.
- RSS feeds cover **3 states** (CA/NY/WA) + **no federal** (`database.py:3716-3723`) — most laws never detected.
- Tier-1 structured data is **minimum_wage-only** (all 4 sources `categories=['minimum_wage']`, `k1l2m3n4o5p6:121-175`).
- `source_url_status` is a **write-time snapshot** (`_validate_source_urls` 3 callers, all writes); no liveness re-sweep.
- Drift→needs_review is code-complete + UI-wired but fires only from the disabled re-ingest, needs 2 ingests for a baseline (`authority_ingest.py:221-222`), and has no ingest UI button → **0 flags by default**.
- Onboarding projection is a **one-time snapshot** (`admin_onboarding.py:1417`); reads `r.*` from `compliance_requirements` not the live catalog (`compliance_service.py:6121-6144`) → repriced/new rows never reach onboarded tenants until a location re-add or the disabled `compliance_checks` runs.

**Fill:** Per-task default-on-at-go-live + checklist + admin banner. Bridge `legislation_watch` into the codification review path. Seed a 50-state + federal feed catalog + admin CRUD. Add structured sources for sick-leave/scheduling/overtime. Add a URL-liveness sweep. Seed baseline ingests to arm drift. Add an event fan-out re-syncing companies on catalog change. _(Tracked: `COMPLIANCE_GAP_ANALYSIS.md:239`, Phase-E6.)_

### 7. Correctness bugs in the live read path + dead weight _(MEDIUM)_

- **Arbitrary `category_id` fallback:** `compliance_service.py:1700-1703` COALESCEs an unmatched slug to `(SELECT id FROM compliance_categories LIMIT 1)` — no ORDER BY, and `$19` is the RAW category string (`:1800`). `map_to_bank` keys tenant projection purely on `category_id` (`onboarding_scope_ai.py:596-600,711`) → mis-served to wrong companies, invisible under its true category.
- **Codified citations absent from the flat surface:** `codify.py:699-701` stamps `statute_citation`, but `get_location_requirements` selects only `source_url_status` (`compliance_service.py:6121-6128`) and `RequirementResponse` (`models/compliance.py:232-254`) has no citation field → only visible in `view=hierarchical`. The codification payoff is invisible/unauditable to the customer.
- **Second gap engine over the same catalog:** `handbook_gap_analyzer` → `handbook_service._fetch_state_requirements` (raw state-filter, no `_filter_requirements_for_company`, no `applicable_industries`, no scope-engine symbol) computes its own coverage math that can disagree with `resolve_scope`.
- **Decorative cache:** `resolve.py:221-236` only sets `cache_state`, recomputes either way; `stratum_ids` hardcoded `'{}'` (`:361`); freshness key checks `scope_strata.refreshed_at` while the read path selects `authority_item_classifications` — a latent invalidation trap.
- **Dead table:** `company_compliance_scope` nothing reads, yet `onboarding_scope_ai.py:580` docstring still points at it.

**Fill:** Drop the LIMIT-1 fallback (NULL + eval flag on miss). Add `statute_citation`/`citation_verified_at` to `RequirementResponse`. Route handbook `_fetch_state_requirements` through the shared applicability filter. Implement or remove the cache. Fix the docstring + drop the dead table.

### 8. The engine's core read path has zero end-to-end test coverage _(HIGH)_

- `test_resolve_semantics.py` imports only pure helpers and asserts §9 cases against hand-built `_row()` dicts through `classification_matches` — never through `resolve_scope`'s SQL. Grep server/tests for `resolve_scope` = 0.
- The confirmed-classification join, provisional count, key-precise catalog join, codified/uncodified split, and cache round-trip (`resolve.py:241-369`) have **zero** coverage.
- The only DB test (`test_gap_surfaces_integration.py`) is `skipif`-gated and calls `gap_surfaces`, not `resolve_scope` — the §9 acceptance (LA warehouse → AB701 + 1910.147, excludes 1910.119 PSM) is never verified through the real read path.

**Fill:** A DB-backed fixture test (rolled-back txn) seeding a tiny federal + CA index (universal 1910.147, warehousing AB701, conditional 1910.119) that calls `resolve_scope(...)` and asserts the §9 codified set — plus a data-driven `record_shadow` diff test.

---

## Fill Next (Prioritized)

1. **Author data for the next 5 states + top cities** (authority indexes + baselines + ≥10 golden facts each). The raw comprehensiveness bottleneck — corpus is federal+CA only.
2. **Give `codify.py` a CREATE path + a headless research→reconcile loop.** The engine mints zero rows and only grows via one manual button.
3. **Ship the shadow→authoritative cutover for federal+CA** behind a per-coordinate gate, using `scope_shadow_log` agreement as the signal.
4. **Loosen the all-or-nothing engine gate to per-category/per-key** (or a partial-verdict banner) so the grounded engine renders before federal is 100% classified.
5. **Build the Scope Studio cockpit** (Confirm/Override + KEY queue, Ingest/Classify buttons, strata, Reconcile, shadow-log dashboard). Backend done; only UI missing.
6. **Flip evals on + make golden inheritance-aware + add a scope subscore + gate on federal criticals.** Measurement is dormant and biased.
7. **Curate core keysets for the top 5 industries by employer count + codify marquee federal statutes + top clinical boards.**
8. **Fix live-path correctness bugs** (`category_id` fallback, missing `statute_citation` on the flat surface) **+ add the `resolve_scope` §9 acceptance test.**

---

## All Gaps by Lane & Severity

| Lane | Gap | Type | Sev |
|---|---|---|---|
| data-coverage | Codified registry = federal + CA only; 48 states/all cities/all intl absent | DATA | Critical |
| data-coverage | 27 federal marquee statutes are scope-only skeletons (no codified value) | STRUCT/DATA | Critical |
| runtime | Warehouse resolves to empty industry → AB701 still unreachable | DATA/STRUCT | High |
| data-coverage | Core checklist for only 2 of ~17 industries | DATA | High |
| data-coverage | 20+ healthcare verticals in taxonomy, 1 codified (eye care) | DATA | High |
| data-coverage | Golden corpus = 54 facts / 6 jurisdictions, all unverified | DATA/MEAS | High |
| gap-surfaces | Remediation Phase-E domains (privacy/food/construction/DOT) un-modeled | DATA | High |
| freshness | RSS feeds cover 3 states + no federal | DATA | High |
| freshness | Tier-1 structured data = minimum_wage only | DATA | Medium |
| scope-engine | resolve_scope never runtime-authoritative (×5 findings, deduped) | STRUCT | High |
| runtime | Codified corpus not consumed by onboarding | STRUCT | High/Med |
| scope-engine | CODIFY mints no catalog values (enrichment-only) | STRUCT | High |
| runtime | Codify enrichment-only AND scheduler dormant | STRUCT | High |
| scope-engine | Grounding gate persists ungrounded VALUES | STRUCT/CORRECT | High |
| scope-studio | Specialty derive→research uses legacy ungrounded pipeline | STRUCT | Medium |
| gap-surfaces | Engine overlay structurally dark (all-or-nothing federal gate) | STRUCT | Critical |
| eval | Completeness denominator still unfounded (registry repoint dead) | STRUCT/MEAS | Critical |
| gap-surfaces / studio | No confirm/override UI — classifications stuck provisional | STRUCT | Critical |
| scope-studio | KEY step has no editor — unkeyed items stalled | STRUCT | High |
| gap-surfaces / studio | INGEST/CLASSIFY/CONFIRM front half un-driveable from UI | STRUCT | High |
| gap-surfaces | No codification funnel cockpit | UX | High |
| scope-studio | RECONCILE/strata/GET fetch-queue orphaned (no UI) | STRUCT | Medium |
| eval | Evals never auto-run (scheduler disabled, no beat) | MEAS | High |
| eval | Golden caps ~99/105 jurisdictions at DEGRADED (no inheritance) | MEAS | Critical |
| eval | scope + grounding excluded from sweep; federal criticals dropped | MEAS | High |
| cross-cutting | Federal scope criticals (jid=NULL) don't gate readiness | MEAS | High |
| cross-cutting | Scope suite has no 0–100 subscore | MEAS | Medium |
| eval | Penalty/preemption/breadth unmeasured by any suite | MEAS | Medium |
| eval | Core checklist + industry expectation gaps (4 of 8 empty) | MEAS/DATA | High |
| freshness | All keep-current schedulers seeded disabled | STRUCT/FRESH | High |
| freshness | legislation_watch → tenant alert dead-end, no Library bridge | STRUCT | High |
| freshness | Drift detector dormant (needs baseline + enabled sync) | STRUCT/FRESH | Medium |
| scope-engine | New citations on re-ingest → no reclassify loop | STRUCT | Medium |
| runtime | Projection snapshot staleness (no catalog→tenant fan-out) | FRESH | Medium |
| freshness | Source-URL liveness captured at write-time only | FRESH | Medium |
| gap-surfaces / studio | scope_shadow_log written but surfaced in no UI (×2) | MEAS | Medium |
| cross-cutting | Shadow untested + admin-only (self-serve unshadowed) | STRUCT/TEST | Medium |
| runtime | category_id arbitrary fallback mis-tags served rows | CORRECT | Medium |
| runtime | Verified citations absent from flat tenant requirements list | CORRECT/UX | Medium |
| gap-surfaces | handbook_gap_analyzer = parallel disconnected gap engine | STRUCT | Medium |
| scope-engine / cross | scope_resolutions cache is a no-op + mis-wired invalidation (×2) | TECH-DEBT | Medium |
| scope-engine | company_compliance_scope dead table + stale docstring | TECH-DEBT | Low |
| cross-cutting | resolve_scope SQL read path (§9 acceptance) untested | TEST | High |

**Legend:** DATA = data-coverage gap · STRUCT = structural/implementation (pipeline not wired, disconnect, dead code) · MEAS = measurement blind-spot · FRESH = freshness/staleness · CORRECT = correctness bug · TEST = test coverage · UX = missing surface · TECH-DEBT = dead weight.

**Already tracked in remediation docs:** the shadow→authoritative cutover (`SCOPE_REGISTRY_PLAN` commit 5/6), Phase-E domain expansion + E6 diff-schedulers + E1 coverage-manifest (`COMPLIANCE_REMEDIATION_PLAN`), federal-register + more-states feeds (`COMPLIANCE_GAP_ANALYSIS.md:239`), and the completeness registry-repoint (`SCOPE_REGISTRY_PLAN §10`). **Newly surfaced by this review:** the codify-mints-no-values reality, the arbitrary `category_id` correctness bug, missing citations on the flat surface, golden non-inheritance capping READY, federal criticals dropped from the gate, the decorative cache's mis-wired invalidation, and the total absence of an end-to-end `resolve_scope` SQL test.
