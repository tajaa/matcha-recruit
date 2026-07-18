# Matcha ONE Compliance System — Gap Synthesis Review

_Synthesis of 50 adversarially-verified gap findings across 8 lanes (scope-registry-engine, runtime-read-path, eval-measurement, gap-surfaces, scope-studio-ui-api, data-coverage, freshness-workers-drift, cross-cutting). Every gap is tied to file:line evidence. Goal frame: "the most comprehensive labor-law intelligence repository + compliance system."_

> **Revision 2 (2026-07-13).** Every finding below was re-verified against the code at HEAD **and against the live dev database** (a verbatim prod clone). The DB pass changed the picture: two sub-claims were **refuted**, several were **overstated**, and three new findings — one Critical — were surfaced that the code-only pass missed. Corrections are marked **[R2]** inline. The headline theses (engine never authoritative, codify mints no values, corpus is thin) all survived and are, if anything, understated.

---

## Executive Summary

The ONE compliance system is **architecturally complete on paper but early and largely inert in practice.** Three things are simultaneously true:

1. **The new codification engine is built end-to-end but nowhere authoritative.** Every real onboarding still runs the legacy Gemini `expand_scope→map_to_bank` category-grab; `resolve_scope` output is only logged to `scope_shadow_log` and discarded. The "ONE definition of scope" is aspirational.
2. **The engine cannot actually grow the Library.** `codify.py` mints **zero** `jurisdiction_requirements` rows (it only stamps citations onto rows the legacy research pipeline already wrote); the sole value-minter is a single admin SSE button; every scheduled/freshness task is seeded **DISABLED**.
3. **Data coverage is two jurisdictions and two industries wide.** The **codified** corpus is federal + California only (the *served* catalog is far broader — 2,618 rows over 94 jurisdictions — but it is legacy runtime-research output, not codified/scoped); 2 of ~17 industries have a core checklist; **[R2]** 1 of **14** advertised clinical specialties is codified (the other 13 are aliases that collapse into the `healthcare` node — only `ophthalmology` is a real taxonomy node); **[R2]** **54 curated golden facts** across 6 US jurisdictions, all `claude-research`-authored and **none human-verified** (zero carry a `verified_by`).

The measurement layer that should make this thinness visible is itself dormant (evals never auto-run) and structurally biased (unfounded completeness denominator, federal criticals dropped from the gate, scope has no subscore). **The codification investment is real and correct where tested — but stranded behind an un-flipped cutover, an un-built operator UI, and a corpus two jurisdictions wide.** The highest-leverage work is not more architecture.

**[R2] The engine is not merely shadow — it has never been bootstrapped.** See the live-DB block below.

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

**[R2] Coverage funnel — retracted.** The "~334 enumerated → ~11 keyed → ~5 codified" figures came from the worked example in the (stale) `CODIFICATION_SYSTEM.md`, not from data; the original phrasing "verified against data" was wrong. The registry tables are **empty**, so no funnel exists to measure. (`seed.py` declares 19 explicit keyed citations plus a 27-entry baseline loop — the *intended* keyed set, none of it ingested.)

### [R2] Live-DB ground truth (dev = verbatim prod clone, 2026-07-13)

| Query | Result |
|---|---|
| `authority_indexes` / `authority_item_classifications` / `scope_codifications` / `scope_shadow_log` | **0 / 0 / 0 / 0 rows** |
| `compliance_eval_runs` | **0** — the eval system has never once run |
| `jurisdiction_requirements` where `research_source='gemini_grounded'` | **0** (737 ungrounded `gemini`, 1,880 with no provenance at all) |
| rows carrying a `statute_citation` | **62 of 2,618** (2.4%) |
| `source_url_status` | **`unchecked` on all 2,618** — the liveness stamp has never fired |
| `scheduler_settings` enabled | only `broker_risk_alerts` |
| catalog spread | 2,618 active rows / 103 jurisdictions (1,612 city · 623 state · 337 county · 46 federal) |

This is the load-bearing correction to the whole review. The scope registry is not "shadow-only" — **it has never been populated**, so `populate_scope_registry.py` (the CLI the empty state points at) was never run, no classification was ever confirmed, no citation was ever reconciled, and the grounded research path has never minted a single catalog row. Every "reads ~empty set unless the CLI was run" hedge below resolves to: *it wasn't*. The served catalog is entirely the legacy ungrounded pipeline's output.

---

## Themed Gap Sections

### 1. Data coverage is two jurisdictions and two industries wide _(CRITICAL — the raw comprehensiveness bottleneck)_

The codified corpus the whole pipeline feeds is **US-federal + California only**. Everything else is served by legacy runtime-research rows, not the new codified/scoped corpus. Industry breadth is taxonomic, not substantive.

- `authority_sources.py:51-127` — exactly 11 authority indexes (6 federal eCFR + `us-flsa`/`us-labor-baseline` + `ca-labor-code`/`ca-title-8`/`ca-title-16`). `all_index_slugs()` returns only these.
- `resolve.py:205-210` — any non-CA state hits the documented degrade path _"no state jurisdiction row — coverage degrades to federal only."_ `baseline_masterlist.py:233-238` `BASELINE_JURISDICTIONS=('federal','ca')`.
- `curated_ca.py:230-261` — exactly **5** optometry/opticianry rows codified; `seed.py:112-116` maps them to `ophthalmology`. **[R2]** The taxonomy (`categories.py:109-144`) advertises **14** clinical specialties as `exact_aliases` (oncology, cardiology, behavioral_health, telehealth, …) — not "20+" — and they all `resolve_category` back to the `healthcare` **parent**; `ophthalmology` (`:137-146`) is the only one that is a real node, and the only one with codified authority. Still the biggest "promised but empty" gap for the healthcare book, but the promise is narrower than first stated.
- `industry_keysets.py:101-139` — `CORE_INDUSTRY_KEYSETS` has only `manufacturing` + `healthcare`; `INDUSTRY_CATEGORY_SETS:49-58` gives hospitality/retail/technology/`fast food` an **empty frozenset** (no industry-specific expectation at all). `runner.py:433-435` raises for `depth='core'` on the other ~15 slugs.
- `baseline_masterlist.py:60-157` — all 27 federal marquee obligations (Title VII, ADA, ADEA, WARN, I-9, COBRA, ERISA, NLRA, USERRA, FCRA, EEO-1, GINA, PWFA) exist as **scope rows only**; `codify.py` creates no value, so they are pointers without a codified obligation until a research row exists. _(Bodies ARE fetchable via `body_fetch.py:143-159` govinfo/USC path — the gap is codified value, not missing ingest.)_
- All 54 golden facts carry `curated_by='claude-research'` and **none** carries a `verified_by` — even the ground-truth corpus is unverified. **[R2]** For the curated modules the framing was wrong: `curated_ca.py:9-15` / `curated_us.py:15-18` state the doctrine in *docstrings*, but `curated_by` / `verified` **are not columns** (`scoperg01:106-141` has neither). There is nothing to set to `verified=true` — the rows are unverified because **no verification mechanism exists**, which is worse than the original claim.
- **Warehouse→AB701 flagship still fails end-to-end** — but **[R2] not for the reason given.** The tag half is confirmed: warehousing has `legacy_industry=None` (`categories.py:194`) → `_get_company_industry_tags` returns `set()` → `_filter_requirements_for_company` hits `elif not company_tags: continue` (`compliance_service.py:2789-2790`) and drops **every** industry-tagged row (generic/untagged rows still pass). The AB701 half is **REFUTED**: the quota rows (`curated_ca.py:138-176`) are **not** in `scope_codifications` and there is no `verified` column (`codify02:29-42`). They are seeded with `_category(["warehousing"])` and **no `regulation_key`** (`seed.py:98-103`), and `codify.py:288` (`if not r["regulation_key"]: unkeyed.append(...)`) routes keyless rows to the fetch-queue forever. **AB701 can never be codified as written** — a strictly worse failure than "sitting in a dormant table."
- **[R2]** Phase-E domains: `data_privacy`, `food_safety`, and DOT/FMCSA have **zero** footprint anywhere (confirmed). But **construction and financial_services DO exist as seeded taxonomy** (`categories.py:175-185`, `:229-234`; `scoperg01:87,98-99`) — what they lack is a category group, core keyset, and authority index. "Zero taxonomy in any migration" was wrong for those two.

**Fill:** Author authority indexes + baseline master-lists + ≥10 golden facts per jurisdiction for NY/TX/IL/WA/FL + NYC/Chicago/Seattle/SF (mirror the CA slice). Curate ≤30-key core keysets for restaurant/hospitality, retail, construction, warehousing, tech. Codify the marquee federal statutes + top clinical boards (nursing/dental/pharmacy) starting in CA. Give warehousing a non-null `legacy_industry` or teach the tag filter the new slugs. Stand up Phase-E domain migrations + the E1 coverage-manifest so un-modeled domains fail loud. _(Partly tracked: `COMPLIANCE_REMEDIATION_PLAN` Phase-E, `COMPLIANCE_GAP_ANALYSIS.md:239`.)_

### 2. The registry is never authoritative — the shadow→cutover promise never shipped _(CRITICAL)_

`resolve_scope` was to ship SHADOW-first then take over. It is **permanently shadow**: `expand_scope→map_to_bank` is the sole writer of company scope, and there is **no cutover mechanism in code**.

- Authoritative population: `_write_compliance_scope_rows(existing_items=resolved.get('existing'))` at `admin_onboarding.py:1417-1423`, fed by `ai_expand_scope→map_to_bank` (`:1154/1241`). **[R2]** There is a **second** authoritative writer: the employee-sync enrichment path (`admin_onboarding.py:661-697`) runs its own `ai_expand_scope→map_to_bank→_write_compliance_scope_rows(..., source="employee_sync")` — same registry-free pipeline, so the conclusion is unchanged, but "the" writer undercounts by one.
- `resolve_scope`'s only runtime callers are non-authoritative: admin preview GET (`scope_registry.py:309-315`), the discarded `record_shadow` diff (`shadow.py:58-113`, docstring _"expand_scope stays authoritative"_), and the gap-dashboard overlay that _"never overwrites"_ the bank arrays (`admin_onboarding.py:1706-1728`).
- `scope_shadow_log` has exactly one reader — the admin diff route (`scope_registry.py:485-507`). No code promotes `only_in_resolve` into any tenant's scope. Grep for any cutover/flag/promotion switch = nothing.
- The actionable "Research a gap" list is always the category-grab; the engine's grounded worklist is shape-incompatible (`gap_surfaces.py:11-19`) and surfaces only as a coverage badge.
- **The confidence surface to justify cutover is invisible:** `scope_shadow_log` is written every finalize but consumed by **no UI** (grep client/src = 0 hits) — the shadow phase can never end.
- Shadow is admin-only + untested on real data: `record_shadow` wired at one callsite (`admin_onboarding.py:1522-1529`); self-serve Compliance/Lite/X (`matcha_x_onboarding.py`) never call it; `test_shadow.py` exercises only pure set math.

**Fill:** Feature-flagged per-jurisdiction/industry "registry-authoritative" gate in `finalize` consuming `resolve_company_scope` where proven (federal+CA first), falling back to `expand_scope` elsewhere. Render `/shadow-log` in Scope Studio with an agreement-rate rollup as the go/no-go signal. Wire `record_shadow` into the self-serve build path. Add an engine-sourced "Research a gap" worklist. _(Tracked: `SCOPE_REGISTRY_PLAN.md` commit 5/6 — the deferred step.)_

### 3. The codification engine cannot grow the Library _(CRITICAL)_

CODIFY is **enrichment-only** and **dormant**, and ungrounded model-recall values persist under the "codified" join.

- `codify.py` has **0** `INSERT INTO jurisdiction_requirements`. `reconcile_codifications` upserts `scope_codifications` linkage (`:668-684`) + stamps citations onto **existing** rows (`:696-708`); an unmatched `regulation_key` lands in `unmatched_keys` and never becomes a value.
- Sole value-minter: `research_specialization_for_jurisdiction` via `POST /fetch-queue/research` (`scope_registry.py:351-469`), whose **only** caller is one Scope Studio button (`ScopeStudio.tsx:875-876`). **[R2]** That is true of the *endpoint*, but the underlying function has a **second** route caller — the legacy ungrounded path at `admin.py:7801` (see the bullet below) — so "sole value-minter, one caller" describes the grounded fetch-queue only. No worker calls research or reconcile — growth is manual per-chain clicks. (The worker isn't fully inert, though: `workers/tasks/scope_registry.py:75` calls `propagate_drift_to_requirements` after every ingest, which does write to `jurisdiction_requirements` — but only a `needs_review` stamp, never a value.)
- `scope_registry_authority` scheduler seeded `enabled=false` (`scoperg01:250-260`); dormant in prod.
- **Grounding gate persists ungrounded VALUES:** `compliance_service.py:9216-9234` upserts both grounded and ungrounded reqs (only penalties nulled); `validate_requirement_citations` (`grounded.py:98-104`) never removes a req — a hallucinated value can be codified and string-joined as "codified" (`grounded.py:91-94` concedes it's _"not a value-provenance guarantee"_).
- New (`'new'`) citations on re-ingest are auto-stamped propagated with no path back to classify (`codify.py:411-413,451-460`); ingest never dispatches classify. **[R2]** The load-bearing stamp is actually `codify.py:528-535` — inside the transaction, it stamps `propagated_at = NOW()` for **every** unpropagated row (amended/removed just processed, plus any `'new'` rows), which is what drains a `'new'` citation off the worklist without ever routing it to classify.
- Specialty derive→research still writes via the **legacy ungrounded** pipeline (`ScopeStudio.tsx` `researchTargetGap` → `/admin/specialization-research/run` → `research_specialization_for_jurisdiction` WITHOUT `grounded_corpus`, `admin.py:7801-7809`). **[R2]** The path is confirmed, but `metadata.grounding='ungrounded'` is **not actually written** — `_upsert_requirements_additive` only sets the `grounding` key conditionally (`compliance_service.py:1665-1666`, `if req.get("grounding"): ...`), and the legacy path never sets it. So these rows land with **no `grounding` key at all** — indistinguishable from pre-grounding-era rows on that field, and only separable via `metadata.research_source='gemini'` vs `'gemini_grounded'`. A silent gap, worse than a mislabeled one.

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

- `compliance_evals` scheduler seeded `enabled=false` (`jureval01:118-130`); no celery-beat → every non-completeness subscore empty unless an admin clicks Run. **[R2]** Run path corrected: `runner.py:385-478` is `onboarding_readiness` (merges *stored* results), not the executor — the actual eval run is `run_evals` (`runner.py:169-374`), triggered from `POST /jurisdictions/evals/run` (`admin.py:5194-5240`). **[R2]** "2,724 rows / 105 jurisdictions" corrected against the live dev DB (verbatim prod clone): **2,618 rows / 103 jurisdictions** — none have accuracy/authority/freshness/tag measurement on any cadence, confirmed also by `compliance_eval_runs` = **0**.
- **Golden caps ~99 of 105 jurisdictions at DEGRADED:** 54 facts / 6 jurisdictions; `MIN_GOLDEN_FACTS_READY=10` (`scoring.py:19`) + accuracy does **not** inherit the chain (`golden.py:_rows_for` filters `jurisdiction_id=$1`) → LA(6)/SF(4)/NYC(4) and every fixture-less jurisdiction (all international) can never be READY.
- scope + grounding excluded from the scheduled sweep (`compliance_evals.py:83-89`); scope is findings-only, no subscore (`scope.py:59-60`); grounding tier-2b verifier off by default (`config.py:180`).
- **Federal scope criticals never gate readiness:** `runner.py:286-288` drops `jid=None`; `_resolve_jurisdiction_ids` excludes federal (`:112-114`) → a jurisdiction reads READY over a 95%-uncodified federal baseline.
- Scope registry has **no 0–100 subscore** (`scoring.py:40-55` `Subscores` lacks a scope field).
- Penalty coverage, preemption correctness, and jurisdiction breadth measured by **no** suite (enumerated every `finding_type`); a wholly-absent state yields no cell/finding.
- Completeness's registry repoint is dead until an index is fully hand-classified (**[R2]** real gate is `completeness.py:146-157`, not `:132-134`, which is docstring prose) — the unfounded denominator gates the 90% readiness threshold. **[R2]** The gate is global, not per-jurisdiction: the `covering` query pulls in **every** `jurisdiction_id IS NULL` (federal) index for **any** chain, so one unclassified item in an unrelated federal index (e.g. RCRA hazardous-waste, `ecfr-40-260`) disables the registry denominator for every jurisdiction in the system, not just its own coordinate.

**Fill:** Flip the evals scheduler on + heartbeat alert. Make golden inheritance-aware + a fact-authoring pipeline (≥10/jurisdiction). Add scope+grounding to the sweep; give scope a subscore; fold federal criticals into the gate. Add penalty/breadth/preemption suites. Relax the `unclassified_count=0` gate to a per-key floor; surface `expectation_source` in the UI.

### 6. The freshness / keep-current loop is dormant and broken at its seams _(HIGH)_

- All freshness schedulers seeded `enabled=false` (`legislation_watch`, `pattern_recognition`, `structured_data_fetch`, `scope_registry_authority`, `compliance_evals`, `handbook_freshness`, `risk_assessment`); no celery-beat → nothing runs out of the box, undocumented as a go-live step. **[R2]** Seed location corrected: `database.py:588-598` covers only `handbook_freshness`+`risk_assessment`; the bulk seed is `database.py:3650-3660` + `3925-3975` plus 5 migrations. **[R2]** Confirmed independently against live `scheduler_settings`: **every row is `false` except `broker_risk_alerts`** (not a freshness task).
- **legislation_watch is a dead-end:** only persists `INSERT INTO compliance_alerts` (**[R2]** correct file is `core/services/legislation_watch.py:223-245` — the file under `workers/tasks/` of the same name is a 46-line Celery wrapper with no line 223); grep for `scope_*`/`jurisdiction_requirements`/`needs_review` = 0 — a new law becomes a tenant nudge, never a codified obligation.
- RSS feeds cover **3 states** (CA/NY/WA) + **no federal** (`database.py:3717-3723`) — most laws never detected.
- Tier-1 structured data is **minimum_wage-only** (all 4 sources `categories=['minimum_wage']`, `k1l2m3n4o5p6:121-175`).
- `source_url_status` is a **write-time snapshot** (`_validate_source_urls` 3 callers, all writes); no liveness re-sweep. **[R2]** Confirmed live: all 2,618 catalog rows read `source_url_status='unchecked'` — the stamp has never fired even once.
- Drift→needs_review is code-complete + UI-wired but fires only from the disabled re-ingest, needs 2 ingests for a baseline (**[R2]** guard is `authority_ingest.py:225-226`; `:221-223` is the docstring), and has no ingest **UI button** → **0 flags by default**. (A manual API trigger exists — `POST /admin/scope-registry/authority/{slug}/ingest`, `scope_registry.py:59-68` — just no frontend caller.)
- Onboarding projection is a **one-time snapshot** (`admin_onboarding.py:1417`); reads `r.*` from `compliance_requirements` not the live catalog (`compliance_service.py:6121-6144`) → catalog changes don't auto-propagate. **[R2]** Overstated as "never reach… until a location re-add or the disabled `compliance_checks` runs": a tenant-facing **"Run check" button** re-syncs on demand (`Compliance.tsx:220` → `POST /compliance/locations/{id}/check` → `_sync_requirements_to_location`, repository-only for clients). Correct framing: there is no *automatic* propagation — refresh is manual-only — and that manual endpoint lives on the full-`compliance` router, so **`compliance_lite` (Matcha-X) tenants have no refresh path at all**.

**Fill:** Per-task default-on-at-go-live + checklist + admin banner. Bridge `legislation_watch` into the codification review path. Seed a 50-state + federal feed catalog + admin CRUD. Add structured sources for sick-leave/scheduling/overtime. Add a URL-liveness sweep. Seed baseline ingests to arm drift. Add an event fan-out re-syncing companies on catalog change. _(Tracked: `COMPLIANCE_GAP_ANALYSIS.md:239`, Phase-E6.)_

### 7. Correctness bugs in the live read path + dead weight _(MEDIUM)_

- **Arbitrary `category_id` fallback:** `compliance_service.py:1699-1703` COALESCEs an unmatched slug to `(SELECT id FROM compliance_categories LIMIT 1)` — no ORDER BY. **[R2]** `$19` is the **normalized/aliased** slug (`_normalize_category`, applied at `:1651-1654`), not raw text — but it is still unvalidated against `compliance_categories.slug`, and that table is a hand-seeded migration artifact independent of the code registry (`CATEGORY_KEYS`); the two have drifted before, repeatedly — see `baseline01:5,11` and `mfgcat01:1,9`, both migrations backfilling categories the registry already assumed existed. So this is not defensive dead code; it's live whenever a registry key ships ahead of its seed migration. **[R2]** The identical fallback also exists at `compliance_service.py:2624-2628` (`_upsert_jurisdiction_requirements`) — the report only caught one of two. `map_to_bank` keys tenant projection purely on `category_id` (`onboarding_scope_ai.py:596-600,711`) → mis-served to wrong companies, invisible under its true category. **[R2]** Blast radius is wider than stated: the hierarchical precedence join is also keyed on `category_id` (`compliance_service.py:8607`), so a mis-COALESCEd row gets the wrong preemption treatment too.
- **Codified citations absent from the flat surface:** `codify.py:696-706` stamps `statute_citation` (report's `:699-701` is just the `SET` line), but `get_location_requirements` selects only `source_url_status` (`compliance_service.py:6121-6128`) and `RequirementResponse` (`models/compliance.py:232-255`) has no citation field → only visible in `view=hierarchical`. The codification payoff is invisible/unauditable to the customer.
- **Second gap engine over the same catalog:** `handbook_gap_analyzer` → `handbook_service._fetch_state_requirements` (raw state-filter, no `_filter_requirements_for_company`, no `applicable_industries`, no scope-engine symbol) computes its own coverage math that can disagree with `resolve_scope`. **[R2]** The call chain has a middle hop the report skipped: `routes/handbook_gap_analyzer.py` doesn't call `handbook_service` directly — it hands off to `handbook_audit_service.py:275,283`, which calls `_fetch_state_requirements`. The same function also feeds handbook generation and Handbook Pilot — wider blast radius than one analyzer.
- **Decorative cache:** `resolve.py:221-236` only sets `cache_state`, recomputes either way; `stratum_ids` hardcoded `'{}'` (`:361`); freshness key checks `scope_strata.refreshed_at` while the read path selects `authority_item_classifications` — a latent invalidation trap.
- **Dead table:** `company_compliance_scope` nothing reads, yet `onboarding_scope_ai.py:580` docstring still points at it.

**Fill:** Drop the LIMIT-1 fallback at both sites (**[R2]** `category_id` is `NOT NULL` on `jurisdiction_requirements` — the fix is skip-row + warn + backfill any `CATEGORY_KEYS` missing from `compliance_categories`, not "NULL it"). Add `statute_citation`/`citation_verified_at` to `RequirementResponse`. Route handbook `_fetch_state_requirements` through the shared applicability filter. Implement or remove the cache. Fix the docstring + drop the dead table.

### 8. The engine's core read path has zero end-to-end test coverage _(HIGH)_

- `test_resolve_semantics.py` imports only pure helpers and asserts §9 cases against hand-built `_row()` dicts through `classification_matches` — never through `resolve_scope`'s SQL. **[R2]** Grep server/tests for `resolve_scope` = **1** hit, not 0 (a docstring mention in that file's module comment) — no test *calls* it, so the conclusion is unchanged, but "0 hits" was factually wrong.
- The confirmed-classification join, provisional count, key-precise catalog join, codified/uncodified split, and cache round-trip (`resolve.py:241-369`) have **zero** coverage.
- **[R2] REFUTED as written:** the report says the only DB test "calls `gap_surfaces`, not `resolve_scope`." It does call `resolve_scope` — `gap_surfaces.resolve_company_scope` invokes it directly (`gap_surfaces.py:250`). The residual, correct claim: `test_gap_surfaces_integration.py` is **double** `skipif`-gated (`RUN_DB_GAP_TESTS`, plus a second per-test gate on `GAP_TEST_COMPANY_ID`) and asserts only shape invariants (`codified + to_codify == expected`, `0 ≤ coverage_pct ≤ 100`) against whatever dev data happens to exist — the §9 acceptance (LA warehouse → AB701 + 1910.147, excludes 1910.119 PSM) is asserted **nowhere**, through `resolve_scope` or otherwise.

**Fill:** A DB-backed fixture test (rolled-back txn) seeding a tiny federal + CA index (universal 1910.147, warehousing AB701, conditional 1910.119) that calls `resolve_scope(...)` and asserts the §9 codified set — plus a data-driven `record_shadow` diff test.

### [R2] 9. Findings missed by the original pass

Surfaced by the revision-2 code + live-DB re-verification, not in the original 50.
**[R3]** adds one more, found by *running* the pipeline rather than reading it —
worth noting on its own: the code-only pass, the live-DB pass, the eval suites
and the typecheck all missed it, and it was writing wrong data to a
customer-visible field.

- **[R2-CRITICAL] `unclassified_count` counts absence-of-any-row, not absence-of-confirmation — the one place the system reads falsely CONFIDENT instead of falsely dark.** `classify.py:306-319`'s `_refresh_unclassified_count` is `LEFT JOIN authority_item_classifications c ... WHERE c.id IS NULL` — it goes to zero the moment every item has *any* classification row, including `status='provisional'`. But `registry_expected_keys` (`completeness.py:161-175`) filters `c.status='confirmed'` for the actual denominator. So: run `--classify` (Gemini) without ever running `--confirm`, and `unclassified_count` reads 0 → the completeness gate opens (`:156`) → the expected-keys query then silently returns a **shrunken confirmed-only set** as if it were the full registry → completeness reads inflated. Every other gap in this doc fails toward the engine going dark (conservative); this one fails toward the score lying high. Today it's latent (registry is empty — see the live-DB block), but it will fire as soon as anyone runs `--classify` without a UI to `--confirm` afterward (§4's own finding), which is the default trajectory of "just bootstrap it."
- **[R2-HIGH] The idempotency/anti-polymorphy half of the codification work is unaudited — and it left unresolved collisions.** Commit `b694559` ("anti-polymorphy — one obligation, one tag, one active row") is the other half of this system's design goal (one code ↔ one obligation, values swappable without forking the tag) and this review never touches it. Its own commit message reports **10 key collisions preserved for curation, untouched** — two genuinely different obligations sharing one `regulation_key` (Cal-COBRA vs Federal COBRA, Statutory Sick Leave vs Maternity Leave, MIPS vs Adverse Event Reporting, plus an NY exempt-downstate-tier collision) — because a blind supersede would have deleted live obligations. `dedup_jurisdiction_requirements.py` is a manual CLI, run once on dev, never on prod. The `duplicate_active_obligation` eval finding (`tagging.py`) exists to catch this class but the eval suite has **never run** (`compliance_eval_runs` = 0), so nothing has ever scored it.
- **[R3-HIGH] `reconcile` stamped US federal citations onto FOREIGN catalog rows.** `match_codifications` (`codify.py`) guarded on state but not country, and its own docstring justified this as "federal law applies everywhere" — but *everywhere* means everywhere **in the United States**. Registry keys are a global vocabulary (`national_minimum_wage` is as true of the UK as of the US), so key-equality alone bound `29 U.S.C. § 206` (FLSA) to **"UK National Living Wage"**, Mexico's **ZLFN Border Zone Minimum Wage**, and France/Singapore working-hours rows — citing a statute that has no force in those countries, on the customer-visible surface. The state guard could never catch it: those rows have no state. **Neither the code-only review nor the eval suites saw this** — it is invisible until you actually run a reconcile and read the output. Found by driving the pipeline end-to-end (ingest → seed → confirm → reconcile) against dev; 6 bogus stamps were written, then cleared, and a country guard added.
- **[R2-MEDIUM] Composite score can read healthy while readiness gates DEGRADED — an asymmetry the review's own "unmeasured is null, never 100" framing obscures.** `composite_score` (`scoring.py:190-195`) averages **only measured** subscores, so a jurisdiction with no golden facts (accuracy unmeasured) doesn't get dragged down on the headline number — it just fails the separate readiness *gate* (§5's golden-caps-DEGRADED finding). The two signals can diverge: composite ~90, readiness DEGRADED, for the same jurisdiction. Relatedly, federal golden results are computed every run but never persisted — `runner.py:297`'s persist loop iterates `jur_ids`, and `_resolve_jurisdiction_ids` (`:112-114`) excludes federal — so the 13 US-federal golden facts produce findings but no stored score at all.

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
| data-coverage | 14 healthcare specialty aliases in taxonomy, 1 real node codified (eye care) — **[R2]** corrected from "20+" | DATA | High |
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
| **[R3]** scope-engine | `reconcile` stamped US federal citations onto UK/MX/FR/SG rows (no country guard) | CORRECT | **High** |
| **[R2]** eval | `unclassified_count` counts absence-of-any-row not absence-of-confirmation → completeness can read inflated | CORRECT/MEAS | **Critical** |
| **[R2]** data-coverage | 10 key collisions preserved for curation, unresolved (idempotency/anti-polymorphy half unaudited) | DATA/STRUCT | High |
| **[R2]** eval | Composite score averages only measured subscores → can read healthy while readiness gate is DEGRADED; federal golden never persisted | MEAS | Medium |

**Legend:** DATA = data-coverage gap · STRUCT = structural/implementation (pipeline not wired, disconnect, dead code) · MEAS = measurement blind-spot · FRESH = freshness/staleness · CORRECT = correctness bug · TEST = test coverage · UX = missing surface · TECH-DEBT = dead weight.

**Already tracked in remediation docs:** the shadow→authoritative cutover (`SCOPE_REGISTRY_PLAN` commit 5/6), Phase-E domain expansion + E6 diff-schedulers + E1 coverage-manifest (`COMPLIANCE_REMEDIATION_PLAN`), federal-register + more-states feeds (`COMPLIANCE_GAP_ANALYSIS.md:239`), and the completeness registry-repoint (`SCOPE_REGISTRY_PLAN §10`). **Newly surfaced by this review:** the codify-mints-no-values reality, the arbitrary `category_id` correctness bug, missing citations on the flat surface, golden non-inheritance capping READY, federal criticals dropped from the gate, the decorative cache's mis-wired invalidation, and the total absence of an end-to-end `resolve_scope` SQL test. **[R2] Newly surfaced by the revision-2 re-verification:** the registry has never been bootstrapped at all (not merely shadow — every registry table is 0 rows in the prod clone), the `unclassified_count` soundness hole that inflates rather than darkens the score, the 10 unresolved obligation-key collisions from the anti-polymorphy commit, and the composite/readiness scoring asymmetry. **[R2] Refuted on re-verification:** AB701 is not a dormant-but-present `scope_codifications` row — it was seeded with no `regulation_key` and can never be codified as written; the DB integration test does transitively call `resolve_scope` (via `gap_surfaces.resolve_company_scope`), it just never asserts the §9 acceptance.
