# Compliance Coverage Gap Analysis — Federal + CA Labor

_Ground-truth audit (dev DB + code), 2026-07-11._

## Context

Goal for the compliance/jurisdictional tool: **scope the entirety of the federal + California labor obligations a business is responsible for, keep it current as laws change or new ones pass, and let a business map its roster to that catalog and be "always protected."** The 5 admin "Compliance Data" surfaces (Compliance Mgmt, Jurisdictions, Compliance Library, Scope Studio, WC Rate Data — Payer Data out of scope) are meant to account for all of this.

**Verdict: the engine is built and correct; the data is a partial research-accreted set (federal labor is a stub), there is no enumerated definition of "done," the update loop is dormant and can't discover new law on its own, and a new city/industry can't enter the pipeline without a code change.**

### Admin persona this must serve
> "A coffee shop in San Diego is joining. I need everything for San Diego. I assume federal + state are done — now I need San Diego."
> Workflow: **scope → codify → generate policies (agent = Gemini + our eval tools) → store authority source + tag → review in Compliance Library.**

Two false assumptions in that quote, both surfaced below: (1) "federal + state are done" — federal labor is 5 rows; (2) "add San Diego" — no admin path to ingest a new city's authority; it's a code change.

---

## Pillar 1 — Coverage ("scope the entirety of federal + CA labor")

### Have
- Jurisdiction tree + inheritance: city→county→state→federal recursive CTE (`compliance_service.py:8530`).
- **CA state labor: 64 rows** — solid (leave 8, pay_frequency 6, meal_breaks 6, overtime 6, minor_work 5, scheduling 5, safety 5, min_wage 4, anti_discrim 4, final_pay 3, sick_leave 2, WC 1).
- CA local: 1,003 rows across 16 CA cities/counties.
- 28 labor categories enumerated (`compliance_registry.py:7298` `LABOR_CATEGORIES`); 495 `regulation_key_definitions` (+ severity via `rkdsev01`).
- Authority text ingested: 527 federal items (OSHA 1910/1904, FMLA 825, FLSA, RCRA×3) + 30 CA (labor-code, title-8, title-16) with `body_text`.

### Don't have
| Gap | Sev | Detail |
|---|---|---|
| **Federal labor catalog** | 🔴 | **5 labor rows.** Zero FMLA, EEO/Title VII, ADA, ADEA, workers-comp, WARN, I-9/E-Verify, ERISA, NLRA, USERRA, COBRA, equal-pay. The 60 federal rows are mostly healthcare. |
| **Enumerated master-list = definition of "done"** | 🔴 | "Entirety" is undefined in code. Expected set is emergent from research — only 12/28 labor categories have expected keys (88 keys); 16 categories structurally empty. Only auditable list = 12-key core checklist (`industry_keysets.py:89`). |
| Completeness never scored vs fed/CA-state | 🔴 | 0 eval results for federal, 3 for CA-state. Closest proxy (LA, inherits both) = **42–46% complete**, `focused_keys_complete=false`, 539 open critical `missing_key`. |
| Federal classification backlog | 🟡 | 193/527 federal items ingested-but-unclassified (all 3 RCRA indexes). |
| Codification depth | 🟡 | 364 classifications → **27 codifications** (12 fed + 15 CA). Classified-but-uncodified = known-applicable, no value. |
| CA jurisdiction hygiene | 🟡 | Dupe/misspelled jurisdictions (`los anageles`, `ca`, `san diego` vs `_county_san diego`) split data. |

---

## Pillar 2 — Freshness ("update regularly, catch changes AND new laws")

### Have (all built, all dormant)
- Change-detection: `previous_value`/`last_changed_at`/`change_status` + per-location `compliance_requirement_history` + alerts.
- Drift detection: eCFR re-ingest diffs → `authority_index_drift` → flags catalog rows `needs_review` (`codify.py:419`).
- `legislation_watch`: Gemini-grounded RSS scan (CA DIR, NY DOL, WA L&I) → proactive alerts.
- `structured_data_fetch`: DOL/UCB/NCSL CSV/HTML → cache.
- Scheduler framework: `scheduler_settings` + hourly `@worker_ready` re-dispatch.

### Don't have
| Gap | Sev | Detail |
|---|---|---|
| **Loop is OFF** | 🔴 | Every compliance-refresh scheduler row `enabled=f`. `rss_feed_items=0`, `structured_data_cache=0`, `authority_index_drift=0` — never run. |
| **No net-new discovery path** | 🔴 | Nothing automated INSERTs a catalog row for a new law. legislation_watch → alerts only; codify drift → flags only; scheduled checks `allow_live_research=False`. New CA law stays invisible until a human runs `fill-gaps-*`. |
| No global changelog | 🟡 | "Rule X changed on date Y" exists only per-tenant (empty). No catalog-level version audit. |
| Watch sources thin | 🟡 | 3 RSS feeds; no Federal Register, no CA-Leg bill tracker, no municipal sources. |
| Ingest not scheduled | 🟡 | Authority indexes = one manual populate; sync task exists but disabled. |

---

## Pillar 3 — Roster mapping ("business maps roster to compliance")

### Have
- Roster → jurisdictions: `collect_roster_jurisdictions` → work locations → auto-create `business_locations` → check.
- Full geographic stack fed+state+county+city, precedence/preemption resolved.
- Industry filter: `applicable_industries` ∩ company tags (`_filter_requirements_for_company`).
- Conditional engine capable of attribute/entity_type/and-or-not incl. gte-headcount (`evaluate_trigger_conditions:8431`).

### Don't have
| Gap | Sev | Detail |
|---|---|---|
| **Headcount gating unwired for tenants** | 🔴 | `employee_count` never written to `facility_attributes`; 0/2,737 rows carry headcount triggers. FMLA-50-class obligations can't be represented → over-coverage now, silent under-coverage if authored conditionally. Works only in Scope Studio preview (`scope_registry.py:313`). |
| Untagged-industry leakage | 🟡 | 82% rows untagged → industry-specific rows served to everyone; mirror: mis-tagged row silently dropped. |
| Uncodified-applicable invisible to tenant | 🟡 | Scope-registry "applies, no value yet" queue is admin-only; tenant sees green. |
| Hierarchical vs flat views disagree | 🟡 | hierarchical read skips industry filter (`:8810`). |
| Blank work_state silently skipped | 🟡 | employees w/o work_state excluded from scope scan (`roster_jurisdictions.py:46`). |

---

## Pillar 4 — Admin on-ramp (the coffee-shop-in-SD workflow)

### Have
- Full curation pipeline **once authority text exists**: classify (disposition/industry/conditions/sub-jurisdiction tag) → confirm → key → grounded research (Gemini as locator, citation-gated) → codify → review in Compliance Library. Proven on federal this session.
- Eval guardrails: 6 suites incl. scope + grounding tier-1/2a (golden) /2b (LLM verifier) + readiness gate.

### Don't have
| Gap | Sev | Detail |
|---|---|---|
| **No local (city/county) authority ingest** | 🔴 | Source registry hardcoded (`authority_sources.py`: 6 eCFR + 4 curated). Adding San Diego municipal code = code change, no admin path. Step 1 of the persona workflow can't start. |
| **No coffee-shop / food-service industry keyset** | 🔴 | Core checklists = manufacturing + healthcare only. "Everything for a food-service tenant" is unmeasurable. |
| No baseline-assurance view | 🔴 | "I assume federal+state are done" is unverifiable in-app (and false). No per-jurisdiction "coverage X/Y ✓" against a real master-list. |
| No SD golden fixture | 🟡 | golden = federal/CA/LA/SF/NYC. SD unverified. |
| Evals scheduled off | 🟡 | `compliance_evals` scheduler row disabled — QA runs only on manual click. |

---

## Bottom line + dependency order

- **Engine: built** — classify→key→grounded-research→codify→eval works and is guarded.
- **Data: federal labor is a stub; no master-list defines "done."**
- **Automation: dormant + can't discover new law by itself.**
- **On-ramp: new city/industry can't enter without code changes.**

Closing order (each stacks on the prior):
1. **Master-list + baseline eval** — enumerate federal + CA-state labor obligations; run completeness against those jurisdictions directly. _Defines "done" and makes "federal+state are ready" a checkable claim._
2. **Federal labor fill** — push the missing federal obligations through the existing scope pipeline to codified rows.
3. **Local-ingest path + industry keysets** — admin-authorable city/county authority source + a food-service (and generic-employer) core keyset. _Unblocks "add San Diego" and per-tenant-type assurance._
4. **Freshness loop on** — enable scheduler rows; wire legislation_watch / ingest-drift to _propose catalog rows_ (net-new discovery), not just alerts; global changelog.
5. **Roster-gating fixes** — headcount attribute wiring, untagged-industry, uncodified-visibility, view consistency.

_Part I above is the audit. Part II below is the implementation blueprint for closing it, in dependency order._

---
---

# Part II — Implementation Blueprint

Conventions that apply to every step:
- **Migrations are author-only** — write to `server/alembic/versions/`, user applies via `./scripts/migrate-dev.sh` → `./scripts/migrate-prod.sh`. Current head: `groundver01`. The four blueprint migrations are authored **sequentially chained** — `baseline01 → authsrc01 → discover01 → chglog01` — to keep a single alembic head regardless of which step lands first.
- **asyncpg pool has no JSONB codec** — every new JSONB read goes through `scope_registry/resolve.py:parse_jsonb`.
- **Gemini is a locator, never a source** — any path that creates/updates a catalog VALUE goes through the grounded corpus + citation gate (`scope_registry/grounded.py`), then the grounding eval verifies it. No auto-insert of values from recall or from feed summaries.
- **Evals are read-only over the catalog** — eval-owned state gets its own tables (precedent: `compliance_eval_grounding_verdicts`).
- Tests: pure logic in `server/tests/compliance_evals/` / `tests/scope_registry/` (no DB, no AI — mirror `test_grounding.py`); DB-touching checks via scratch scripts run manually.

---

## Step 1 — Master-list + baseline eval ("define done, then measure it")

**Goal:** an enumerated, citation-backed list of every federal + CA-state labor obligation, and an eval that scores those two jurisdictions against it directly. Turns "I assume federal+state are done" into a dashboard number.

### 1.1 Why the current eval can't do this
- `runner.py:108` `_resolve_jurisdiction_ids` — default subject set is `WHERE level NOT IN ('federal','national')`. Federal is *structurally excluded* from eval runs unless passed explicitly.
- Even passed explicitly, `completeness.evaluate_pair` scores against industry keysets built from `EXPECTED_REGULATION_KEYS` — which mixes state-level keys (`state_minimum_wage`, `local_minimum_wage`) into the expectation. A federal subject would be "missing" keys that don't exist at the federal level. Expectation must be **level-aware**.

### 1.2 The master-list module
New file `server/app/core/services/compliance_evals/baseline_masterlist.py` (pure, no DB/AI — same contract as `industry_keysets.py`):

```python
@dataclass(frozen=True)
class BaselineObligation:
    key: str              # regulation key (must exist in the key vocabulary, see 1.3)
    category: str         # one of LABOR_CATEGORIES | SUPPLEMENTARY_CATEGORIES
    citation: str         # "29 U.S.C. § 207", "29 CFR § 825.100", "Cal. Lab. Code § 226.7"
    authority_url: str    # primary source (ecfr.gov / uscode.house.gov / leginfo)
    applies_note: str = ""  # threshold note, e.g. "50+ employees within 75 mi (FMLA)"

FEDERAL_LABOR_MASTERLIST: List[BaselineObligation]   # target ~60–90 entries
CA_STATE_LABOR_MASTERLIST: List[BaselineObligation]  # target ~70–100 entries

def masterlist_keys(entries) -> Dict[str, FrozenSet[str]]  # category → keys, evaluate-ready
```

Federal content to enumerate (the curation work — every entry individually cited, per the `curated_ca.py` rule "no invented law; unverified until a human checks the URL"):
FLSA (min wage 29 USC 206, OT 207, child labor 212, recordkeeping 211/516, exempt 29 CFR 541, tip credit 203(m), PUMP Act 218d) · FMLA (29 CFR 825) · Title VII / PDA / PWFA (42 USC 2000e; 29 CFR 1604/1636) · ADA Title I (42 USC 12112) · ADEA (29 USC 623) · EPA equal pay (29 USC 206(d)) · GINA · OSHA (general duty 29 USC 654, recordkeeping 29 CFR 1904, posting) · WARN (29 USC 2102) · I-9/IRCA (8 USC 1324a; 8 CFR 274a) · ERISA (29 USC 1021 disclosures) · COBRA (29 USC 1161) · NLRA §7/§8 (29 USC 157/158) · USERRA (38 USC 4301) · FCRA background checks (15 USC 1681b) · EEO-1 reporting (29 CFR 1602) · federal contractor-only rows EXCLUDED (EO 11246, SCA/DBA) — out of scope for the general-employer baseline, note them in the module docstring.
CA list: mirror from the existing 64 CA rows + close known gaps (SB 553 WVPP, POBR-adjacent excluded, PAGA notice, Cal-WARN 25-employee delta, CFRA 5-employee delta vs FMLA, SB 1343 training, pay-data reporting SB 1162, fast-food council AB 1228 as industry-scoped).

### 1.3 Key vocabulary + RKD seeding
- Every masterlist `key` must exist in `compliance_registry._LABOR_REGULATION_KEYS` (Gemini dedup vocabulary) — add missing keys there (e.g. `leave: fmla` exists; `warn_act: federal_warn_notice`, `i9_everify: form_i9_verification`, `erisa_benefits: spd_disclosure`, `nlra_organizing: protected_concerted_activity`… will be new). Pure test: every masterlist key ∈ EXPECTED_REGULATION_KEYS[category] (same enforcement pattern as CORE_LABOR_KEYS).
- Migration `baseline01` (parent `groundver01`): seed `regulation_key_definitions` rows for masterlist keys not yet in RKD (INSERT ... ON CONFLICT DO NOTHING; severity from `compliance_registry.resolve_severity`; citation + authority_source_urls from the masterlist entry). Exact precedent: `oshakeys01_osha_machine_safety_keys.py`.
- **Known side effect (expected, not a regression):** adding ~40 federal keys to `_LABOR_REGULATION_KEYS` widens the *full* completeness expectation for every jurisdiction — all city completeness scores will **drop** when Step 1 lands and recover as Step 2 fills federal (cities inherit the federal rows via the chain union). Land Step 1 with this stated in the PR.

### 1.4 The baseline suite
New file `server/app/core/services/compliance_evals/baseline.py`:
- `run_baseline(conn) -> {results, findings, totals}` — for each of (federal, CA-state):
  - resolve jurisdiction id (reuse `golden._resolve_jurisdiction_id` with level='federal' / state='CA');
  - fetch that jurisdiction's OWN catalog rows (not the chain union — the point is "does the base layer itself exist"), index by `category:normalize_key(...)` (reuse `golden._rows_for`);
  - diff against `masterlist_keys(...)`; each miss → finding `baseline_missing_key`, **severity critical**, `expected={citation, authority_url}`;
  - score = present/expected per jurisdiction (reuse `scoring._pct` shape; add `baseline_score` to `scoring.py`).
- Wire into `runner.py`: `ALL_SUITES += ("baseline",)`, dispatch block (pure+DB, not network), totals `baseline_*`. `EvalSuite` Literal in `models/compliance_evals.py` += "baseline". **Important:** baseline passes its own explicit jurisdiction ids — do NOT rely on `_resolve_jurisdiction_ids` (which excludes federal). Scorecard rows persist with `industry = NULL` (the industry-agnostic convention authority/tagging already use). Default `EvalRunRequest.suites` stays as-is; the admin "Run evals" suite picker adds "baseline" so it runs when explicitly selected.
- Endpoint `GET /admin/jurisdictions/evals/baseline-checklist` (mirror the existing `core-checklist` endpoint in `admin.py`): per-entry present/missing with citation — the admin's "federal: 71/88 ✓" view.
- FE: Evals tab in `JurisdictionData.tsx` renders the new suite row + checklist (same pattern as core-checklist).

### 1.5 Verification
- Pure: masterlist keys all in vocabulary; `masterlist_keys` shape; miss-diff logic with fake rows.
- Live (scratch script, dev): `run_baseline` → expect federal ≈ 5–10% present (that IS the finding), CA-state materially higher. Checklist endpoint renders every entry with citation.

### 1.6 Wire baseline into the /admin Gap Analysis system
The gap-analysis surfaces (GapAnalysisHome/GapDashboard/GapOverview → `admin_onboarding.py`) already read the scope-registry engine — `gap_surfaces.resolve_company_scope` (`admin_onboarding.py:1715`) and `resolve_chain_category_coverage` (`admin.py:8853`) — so **Steps 2–3 enrich the gap dashboard automatically** (denser classifications/codifications = better engine verdicts, no wiring needed). But the baseline verdict would land only in the Compliance Library evals tab, while the persona *starts* at Gap Analysis. Add:
- `gap_surfaces.baseline_readiness_for_chain(conn, jurisdiction_ids)` — latest baseline present/expected per base-layer jurisdiction (federal + each state in the company's chain), reading `compliance_eval_results` for the baseline suite.
- Surface as a **base-layer readiness banner** on the company Gap Analysis dashboard: "Federal labor baseline: 71/88 · CA state: 62/74 — base layers this company inherits." Additive per the module's design rule (never replaces the bank arrays the FE actions consume).
- (Step 4 tie-in, optional/defer: pending `catalog_change_proposals` for the company's jurisdictions on the same dashboard.)

---

## Step 2 — Federal labor fill (data through the existing pipeline)

**Goal:** drive the Step-1 federal misses to codified `jurisdiction_requirements` rows using the scope pipeline (never bulk-insert values by hand — the pipeline is what stamps authority + grounding).

### 2.1 Authority sources first
The pipeline can only ground on ingested text. Extend `scope_registry/authority_sources.py`:
- **eCFR live parts (cheap — fetcher already handles any title/part):** add `FederalPart` entries for 29 CFR 541 (exempt tests), 29 CFR 1602 (EEO-1), 29 CFR 1604 (sex discrimination), 8 CFR 274a (I-9), 29 CFR 2520 (ERISA reporting/disclosure — EBSA; not 4022=PBGC or 2560=claims procedure), 20 CFR 1002 (USERRA).
- **USC-based statutes (no eCFR part):** new `curated_us.py` mirroring `curated_ca.py` (`CuratedRow` shape: citation/heading/hierarchy/source_url → uscode.house.gov), new `CuratedIndexSpec` entries: `us-title-vii`, `us-ada`, `us-adea`, `us-warn`, `us-nlra`, `us-cobra-erisa`, `us-userra`, `us-fcra`. Follow the curated_ca verification doctrine: `curated_by='claude-research'`, `verified=False`, unverified until human opens URL.
- Ingest each (admin "sync" button or `sync_all_authority_indexes` scratch call — writes `authority_indexes`/`authority_index_items`).

### 2.2 Pipeline run per index (repeat of this week's federal workflow)
1. `classify_authority_index` (Gemini, provisional) → admin confirm in Scope Studio. Classification carries disposition + `entity_condition` for thresholds (FMLA `{"type":"attribute","key":"employee_count","operator":"gte","value":50}` — author these NOW; Step 5 makes tenants honor them).
2. Key the confirmed classifications to the Step-1 RKD keys (Scope Studio keying UI; Gemini under-keys deliberately — expect manual keying like the OSHA batch).
3. Fetch-queue grounded research (`POST /fetch-queue/research`) — Gemini extracts values from `body_text`, citation-gated, writes `jurisdiction_requirements` rows w/ `metadata.grounding='grounded'`.
4. Codify (`chain_uncodified` → codify) — links classification↔row into `scope_codifications`.
5. Evals close the loop: baseline score rises; grounding suite (tier-1 + golden + optional tier-2b) verifies every new grounded row; add 5–10 federal facts to `fixtures/golden/us_federal.json` for the highest-stakes values (FMLA 50/12-week, WARN 60-day/100, OT 1.5×/40, EEO-1 100).

### 2.3 Verification
- `run_baseline` federal score trends toward ~100 with every batch; every miss remaining has a reason.
- Grounding eval: 0 `value_not_in_text` / `grounded_but_wrong` on the new rows.
- Tenant smoke: hierarchical view for a CA location now shows federal leave/anti-discrimination/WARN categories.

---

## Step 3 — Local-jurisdiction ingest + industry keysets (the "add San Diego" on-ramp)

**Goal:** an admin adds a city/county authority source and a tenant-type checklist without shipping code.

### 3.1 DB-backed curated authority sources
Today `ingest_curated_index` reads only in-code `CURATED_ROWS[slug]`. Make curated rows data:
- Migration `authsrc01`: table `authority_source_rows` (`id`, `index_slug` text, `citation` text, `heading` text, `hierarchy` jsonb, `source_url` text, `sort_order` int, `curated_by` text, `verified` bool default false, `created_at`, UNIQUE(index_slug, citation)) + table `authority_index_specs` (`slug` PK, `name`, `level`, `jurisdiction_spec` jsonb — same fields `CuratedIndexSpec` carries) so an index itself is admin-creatable.
- `authority_sources.py`: **keep the code registry sync** — `curated_index_by_slug`/`all_index_slugs` have 4 sync callsites (`core/routes/scope_registry.py:62/166/236`, `authority_ingest.py:436`) and must not go async. The DB-defined specs are an **async fallback in the route/ingest layer**: when a slug isn't in the code registry, the (already-async) route/ingest code queries `authority_index_specs` before 404ing. `ingest_curated_index` reads `CURATED_ROWS.get(slug)` first, falls back to `SELECT ... FROM authority_source_rows WHERE index_slug=$1 ORDER BY sort_order`. Code entries win on slug collision.
- Routes (`core/routes/scope_registry.py`, `require_admin`): CRUD for specs + rows (`POST/PUT/DELETE /scope-registry/indexes`, `/indexes/{slug}/rows`), plus reuse the existing ingest trigger. `_JSONB_FIELDS` += hierarchy/jurisdiction_spec.
- FE (ScopeStudio.tsx): "New index" modal (slug/name/level/jurisdiction picker) + curated-row editor (citation/heading/url) + Ingest button. After ingest, rows appear in the existing classify→key→research→codify flow untouched.
- `body_fetch.py`: curated rows have `source_url` but no body — the existing body-fetch step (used for CA leginfo pages) must accept municipal-code URLs; keep the fetch generic (GET + readability strip), degrade to stub. **Fetch risk:** municode/amlegal hosts are JS-rendered SPAs — plain GET yields stubs. Mitigation: prefer server-rendered .gov ordinance pages (e.g. San Diego's own municipal-code site) when curating `source_url`s; stub-degradation remains the honest fallback — values then can't ground and land ungrounded/unresearched, **visible** in the grounding eval (`corpus_stub`) rather than silently wrong.

### 3.2 Industry keysets for the persona
`industry_keysets.py`:
- Add `"food_service"` to `INDUSTRY_CATEGORY_SETS` (base categories only — like hospitality) and to `INDUSTRY_PROFILE_NAMES` → "Restaurant / Hospitality" or "Fast Food".
- Add `CORE_INDUSTRY_KEYSETS["food_service"]`: ≤15 keys, nationally applicable rule holds (food-handler/permit keys are state-specific → they belong in the CA masterlist / catalog, NOT the national core set; core = tip pooling/tip credit, minor work permits, scheduling_reporting, harassment training, plus the labor core). Membership rules at `industry_keysets.py:75-99` apply verbatim; every key must exist in EXPECTED_REGULATION_KEYS (add to `_LABOR_REGULATION_KEYS` where new).
- Golden fixture `us_ca_san_diego.json`: 5+ hand-verified facts (SD minimum wage + earned-sick-leave ordinance values from sandiego.gov).
- Jurisdiction hygiene (one-time data fix, scripted + user-approved): merge/rename `los anageles`→`los angeles`, resolve `ca` stub, verify `san diego` vs `_county_san diego` split rows.

### 3.3 Verification
- Admin end-to-end in dev: create `sd-municipal-code` index via UI → add 5 curated rows → ingest → classify → confirm → key → grounded research → codify → SD rows visible in Compliance Library with grounded citations; grounding eval green.
- Completeness for (san diego × food_service) returns a scored cell.

---

## Step 4 — Freshness loop (catch changes AND net-new law)

**Goal:** scheduled change-detection live, plus a *human-gated* discovery funnel that turns watch-signals into catalog rows.

### 4.1 Turn on what exists (ops + hardening, minimal code)
- `scheduler_settings`: enable `structured_data_fetch`, `compliance_checks` (bump `max_per_cycle`), `legislation_watch`, `scope_registry_authority` (weekly eCFR re-ingest → drift), `compliance_evals`, `deadline_escalation`. User-approved UPDATEs (prod = live DB rules apply).
- Seed `rss_feed_sources`: Federal Register API (`https://www.federalregister.gov/api/v1/documents.json?conditions[agencies][]=wage-and-hour-division...` — DOL/EEOC/OSHA/NLRB agencies), CA leginfo/DIR "what's new". Keep the 0.3 relevance threshold.

### 4.2 Discovery funnel (the net-new path) — migration `discover01`
Table `catalog_change_proposals`:
```sql
id uuid PK, source varchar(30)            -- 'legislation_watch' | 'authority_drift' | 'admin'
jurisdiction_id uuid NULL, category text, proposed_key text NULL,
title text, summary text, source_url text,
payload jsonb,                            -- raw feed item / drift record
status varchar(12) DEFAULT 'pending'      -- pending|accepted|rejected|duplicate
  CHECK (...), resolved_by uuid NULL, resolved_at timestamptz,
created_at timestamptz DEFAULT now()
-- dedupe: Postgres forbids expressions in UNIQUE constraints — use a unique INDEX
-- (exact precedent: jureval01's COALESCE(industry,'') index):
-- CREATE UNIQUE INDEX uq_catalog_change_proposals
--   ON catalog_change_proposals (source, source_url, COALESCE(proposed_key,''));
```
- `legislation_watch.create_proactive_alerts` additionally INSERTs a proposal per qualifying item (alerts stay — tenant-facing; proposals are admin-facing).
- `codify.propagate_drift_to_requirements`: drift on items with NO codified row → proposal (`source='authority_drift'`) instead of the current silent nothing.
- Admin review surface (Compliance Library new tab, routes in `admin.py`): list pending → **Accept** dispatches the existing grounded research for that (jurisdiction, category) targeting the proposed key (reuse the fetch-queue research entry point) → row lands citation-gated; **Reject/duplicate** closes it. **No auto-insert, ever** — acceptance is the human gate; grounding eval audits the output.

### 4.3 Global changelog — migration `chglog01`
Table `jurisdiction_requirement_changes` (`requirement_id`, `changed_at`, `change_kind` created|value_changed|expired|superseded, `old_value` text, `new_value` text, `source` text, `metadata` jsonb). Write from the ONE upsert chokepoint `compliance_service._upsert_requirements_additive` (+ admin manual-edit route): compare `current_value` before/after, insert on delta. Surface: Compliance Library "Changelog" panel + per-requirement history drawer. This is the tenant-independent "rule X changed on date Y" record; per-tenant `compliance_requirement_history` stays as-is.

### 4.4 Verification
- Force one watch cycle in dev → proposals appear; accept one → grounded row lands with citations; changelog row recorded; grounding eval green on it.
- Re-ingest an eCFR part after upstream text change → drift → `needs_review` on codified rows + proposal for uncodified.

---

## Step 5 — Roster-mapping correctness (serve it right)

**Goal:** what the tenant sees = exactly what applies.

### 5.1 Headcount gating (FMLA-50 class)
- Compute active headcount where requirements are read: in `get_location_requirements` + `get_hierarchical_requirements`, build `attrs = {**facility_attributes, "employee_count": n}` with `n = SELECT count(*) FROM employees WHERE org_id=$1 AND termination_date IS NULL` (company-wide; per-worksite refinement later). (`employees.org_id` carries the company id directly — existing queries bind `company_id` to it, e.g. `employees/crud.py` `WHERE e.org_id = $1`; no resolution step.) Pass into `evaluate_trigger_conditions` at `determine_governing_requirement` (`compliance_service.py:8658/8684`). Read-time derivation — nothing stored, no staleness.
- Trigger authoring: Step-2 classifications already carry `entity_condition` thresholds; codify/research must copy them onto the catalog rows' `trigger_conditions` (today research writes NULL). One data backfill for existing FMLA/WARN/COBRA/EEO-1 rows.
- **UX rule:** a threshold-excluded requirement renders as "not applicable at your size (applies at ≥50)" — visible-but-gated, never silently dropped (audit trail for "why don't I see FMLA?").
- Pure tests: 30-person CA employer excludes FMLA-50, includes CFRA-5; 60-person includes both.

### 5.2 View consistency
`get_hierarchical_requirements` (`:8810`) must apply `_filter_requirements_for_company` exactly as the flat view does (`:6136`). One call + tests that both views agree for the same location.

### 5.3 Untagged-industry hygiene
Backfill sweep using `industry_keysets` (the tagging suite's structural check already identifies untagged industry-specific rows — 49 open critical `industry_tag_missing`): script proposes `applicable_industries` per finding, admin approves, UPDATE. Then flip the tagging-suite finding to block readiness (already critical).

### 5.4 Known-applicable-but-uncodified visibility
Tenant compliance page: banner "N obligations identified for your jurisdictions are pending research" — count from the same `fetch_queue` the admin sees (read-only endpoint, feature-gated with `compliance`). Kills the "green while known-incomplete" failure mode.

### 5.5 Roster edge
`collect_roster_jurisdictions`: surface `skipped_no_work_state` count in the drift alert + admin dashboard, so blank `work_state` employees are a visible data-quality task, not silence.

### 5.6 Verification
- Pure trigger tests (5.1); both-views-agree test (5.2).
- Dev tenant smoke: 30-person coffee-shop company in San Diego → sees SD+CA+federal stack, FMLA shown as below-threshold, pending-research banner counts match admin fetch queue.

---

## Sequencing & sizing

| Step | Depends on | Size | Nature |
|---|---|---|---|
| 1. Master-list + baseline eval | — | M (curation-heavy) | new module + suite + 1 migration |
| 2. Federal fill | 1 (keys) | L (pipeline runs + curated_us) | data via existing pipeline |
| 3. Local ingest + keysets | — (parallel w/ 2) | M | 1 migration + CRUD + FE |
| 4. Freshness | 2–3 useful first | M | 2 migrations + funnel + ops |
| 5. Roster fixes | 2 (thresholds authored) | S–M | read-path changes + backfills |

Steps 1+3 are independent — can run in parallel. Step 2 is the long pole (curation + classify/key/confirm cycles). Nothing here changes tenant behavior until Step 5 (Steps 1–4 are admin/data-side), so it ships incrementally without product risk.
