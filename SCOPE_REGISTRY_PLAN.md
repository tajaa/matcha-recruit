# Scope Registry — authority-anchored (jurisdiction × business-category) scoping

**Goal.** Determine, *definitively and before fetching any values*, which regulations a business is
liable for — by business category (ophthalmology, manufacturing, shipping…) in a specific city.
Federal×ALL and State×ALL layers are static across all US / all in-state employers and are scoped
once. Category-specific layers are scoped once per (category × jurisdiction), committed, and reused:
the second LA warehouse to sign up triggers **zero** new scoping work.

Scoping is upstream of everything. Its output is the authoritative worklist of what to fetch and
codify. Only once we can say *"these are the 230 obligations, each citing a real published
authority"* does it become meaningful to go fetch their values.

> Companion doc: `EVAL_SYSTEM.md` — the eval suites that *verify* the catalog. This document is
> about the layer above them: deciding what belongs in the catalog in the first place.

---

## 1. Why this exists — the current state

### Scoping today is an LLM naming category slugs

`onboarding_scope_ai.expand_scope` (`core/services/onboarding_scope_ai.py:307`) makes **one Gemini
call per onboarding session** that returns a list of `compliance_categories` slugs. `map_to_bank`
(`:571`) then grabs **every `jurisdiction_requirements` row in those categories** for the company's
jurisdictions, and `admin_onboarding.py:219` projects the result into `compliance_requirements`.

That is: per-session, uncached, uncited, unconfirmed, and category-granular. Nothing is reusable —
the second LA manufacturer pays for a fresh Gemini call and may get a different answer. Nothing is
citable — no authority says *why* a category is in scope.

### Seven industry vocabularies that do not agree

| Vocabulary | Location |
|---|---|
| `_INDUSTRY_ALIASES` canonical outputs | `compliance_service.py:90` |
| `industry_compliance_profiles.name` | migration `indprofrestore01` |
| `compliance_categories.industry_tag` | `compliance_registry.py` |
| admin FE `INDUSTRIES` | `IndustryRequirements.tsx:33` |
| signup `INDUSTRY_OPTIONS` | `client/src/data/industryConstants.ts` |
| `GUIDED_INDUSTRY_PLAYBOOK` keys | `handbook_service.py:290` |
| `HEALTHCARE_SPECIALTIES` | `industryConstants.ts` |

Two live bugs follow directly:

- **`/admin/industry-requirements` returns an empty matrix for manufacturing.** The endpoint
  (`admin.py:8549`) never calls `_resolve_industry`; it does `name ILIKE $1` against the raw FE
  value. `construction_manufacturing`, `restaurant_hospitality`, and `tech_professional` match
  nothing. (`fast_food` "works" only because `_` is a SQL `LIKE` wildcard that happens to match the
  space in `Fast Food`.)
- **`_INDUSTRY_ALIASES["warehouse"] = "manufacturing"`.** A warehouse is scoped as a factory, so
  CA **AB 701** (warehouse quota law, NAICS 493) can never be scoped for it. `logistics`,
  `distribution center`, `fulfillment center`, and `transportation` resolve to `""` — no industry
  at all.

### The eval system's denominator is unfounded

`compliance_evals/` verifies the catalog against `EXPECTED_REGULATION_KEYS` plus registry *category
groups*. Because `MANUFACTURING_CATEGORIES` is a taxonomy artifact rather than a legal fact, the
eval currently demands `anti_dumping_duties`, `conflict_minerals_dodd_frank`, and `works_council`
(an EU concept) of a twelve-person LA machine shop. The numerator is measured; the denominator is
asserted. This registry replaces the denominator.

### Dormant machinery already in the repo

- `regulation_key_definitions` (490 rows) has exactly the right applicability columns —
  `applicable_industries`, `min_employee_threshold`, `applicable_entity_types`, `applies_to_levels`,
  `authority_source_urls`. **All empty. Nothing reads them.** (`orm/key_definition.py:8`:
  *"Schema-only — not runtime queries."*)
- `company_compliance_scope` — a per-company pointer manifest, **dead** (backfilled into
  `compliance_requirements`; nothing reads it).
- `evaluate_trigger_conditions` (`compliance_service.py:8368`) — a live, deterministic, recursive
  entity-condition evaluator. Reusable verbatim.
- `government_apis/ecfr.py` — already fetches the official eCFR structure API.

---

## 2. The completeness argument

You cannot prove completeness against *all law*. That set is open-ended, and any system claiming
"we got everything" is lying.

You **can** prove completeness against an **enumerable authority index**. Coverage becomes
`classified_items / enumerated_items`, and a gap is a specific uncovered citation.

**Live-verified against the official eCFR API (issue date 2026-07-06):**

| Part | Domain | Sections |
|---|---|---|
| 29 CFR 1910 | General industry | 204 (23 subparts) |
| 29 CFR 1926 | Construction | 304 |
| 29 CFR 1928 | Agriculture | 8 |

`1910.147` (lockout/tagout) and `1910.119` (PSM) both appear in the enumeration. So for federal,
*"every section of 29 CFR 1910 is classified or excluded with a reason"* is a **checkable
statement**.

**OSHA already partitions by industry at the part level.** That is a large simplification: the
*index* carries an applicability domain (1910 → general industry; 1926 → construction), and most
sections within it are universal-in-domain. Classification is a delta, not a from-scratch judgment.

**California and Los Angeles are not machine-enumerable.** Title 8, the Labor Code, Title 16
(professional licensing boards — where ophthalmology's obligations actually live), and the LAMC have
no open, exhaustive API. Their indexes are **curated**, marked `enumerable = false`, and labeled in
the UI as *"curated, not exhaustive."* There, `unclassified_count = 0` means *"the curated list is
fully classified"* — never *"all CA law is scoped."* This ceiling is honest and must not be papered
over.

---

## 3. Architecture — classification-first

**The primitive act is classifying an enumerated authority item.** Strata are *derived* from
classifications, never hand-authored. Every item in an index gets exactly one disposition:

```
INDEX  ecfr-29-1910   domain: general_industry   (excludes: construction, agriculture, maritime)

  1910.147  lockout/tagout        → universal_in_domain
  1910.119  process safety mgmt   → conditional      cond: chemical_qty > threshold
  1910.1030 bloodborne pathogens  → category_specific  applies_to: [healthcare, tattoo, lab]
  1910.1    purpose and scope     → excluded         reason: definitional, no obligation

INDEX  ca-labor-code   domain: all_ca_employers   (curated, enumerable=false)

  §§ 2100-2112  AB 701 quotas     → category_specific  applies_to: [warehousing]
  § 6401.9      SB 553 WVPP       → universal_in_domain
```

This inversion buys three things directly:

1. **Soundness.** Every scope entry cites a real enumerated item. Nothing is invented.
2. **Completeness.** `unclassified_count` *is* the remaining scoping work. Zero means scoping for
   that index is closed. That is the "definitively scoped" claim, and it is mechanically checkable.
3. **The fetch worklist falls out for free.** `items classified applicable to (category ×
   jurisdiction) AND having no codified requirement` is exactly what must be fetched next. Scope
   drives fetch; fetch never precedes scope. An applicable item with **no `regulation_key` yet** is
   representable — the key is minted at codify time — so scoping is never blocked by gaps in our own
   catalog.

### Disposition needs both `applies_to` and `excludes`

Modeling only `applies_to` forces you to enumerate every included category for a rule like
lockout/tagout, which applies across all of general industry. The classification therefore carries
`applies_to_categories` **and** `excludes_categories`, and inherits the index's domain.

### A correction this model forced

An earlier sketch of this design claimed a warehouse should get "AB 701 in, the manufacturing pack
out." **That is wrong, and the classification model is what surfaces it.** A warehouse *is* general
industry, so `29 CFR 1910.147` (lockout/tagout — conveyors, dock levelers, balers) genuinely applies
to it. What a warehouse does *not* get is `1910.119` PSM (conditional on chemical quantities) or
`anti_dumping_duties` (conditional on importing). What a *manufacturer* does not get is AB 701.

Flat per-industry keysets cannot express this. Classification against the authority's own structure
can, and it is why the current `industry_keysets.py` demands EU works-council rules of a machine
shop.

### Business categories are hierarchical

Not a flat eight-industry list. `healthcare → medical_offices → ophthalmology`. A category inherits
every ancestor's strata and adds its own. NAICS carries most of the structure (ophthalmology ≈
621111 physicians / 621320 optometrists; warehousing = 493; shipping/transportation = 48–49;
manufacturing = 31–33; construction = 23). Resolution walks the ancestry chain.

### Resolution

A **stratum** is a reusable coordinate `(level, jurisdiction, category|ALL, entity_condition|base)`
→ the derived set of classified items (and their keys, where codified). A company's scope is the
union of the strata its coordinates and category ancestry select.

```
Manufacturer, LA, 40 employees, uses solvents
  federal×ALL ∪ federal×general_industry ∪ CA×ALL ∪ CA×manufacturing ∪ LAcounty×ALL ∪ LAcity×ALL
  ∪ conditional: headcount ≥ 50 → FMLA (NOT selected: 40 employees)
  ∪ conditional: chemical_qty > TQ → PSM 1910.119 (selected)
  anti_dumping_duties: conditional on imports_goods — not selected

Warehouse, LA (NAICS 493110)
  same universal + general_industry layers (so 1910.147 IS in scope)
  swaps CA×manufacturing → CA×warehousing  ⇒ AB 701 in
  PSM and anti-dumping not selected

Ophthalmology practice, LA (NAICS 621111)
  universal + healthcare + medical_offices + ophthalmology chain
  + CA Title 16 board items; zero machine-safety pack

Second identical business → identical stratum set → zero AI calls.
```

Resolution is **pure SQL plus the existing deterministic `evaluate_trigger_conditions`**. No AI at
read time, ever. AI pre-classifies at authoring time; a human confirms; unconfirmed classifications
are `provisional` and count toward no resolved scope — the same confirm-before-verdict invariant
`limit_adequacy` already enforces.

### Classification burden, priced honestly

The 72 seeded CFR `(title, part)` pairs run to thousands of sections. Mitigations, in order of
leverage: the **index domain** disposes of whole parts at once (1926 is construction, full stop);
**subpart-level classification with section inheritance** cuts 1910 from 204 decisions to 23
(Subpart O = machine guarding → industrial); AI pre-classifies and a human confirms per subpart,
with per-section override and a full audit trail. Roughly a 10× reduction in confirmations. There is
no shortcut beyond this that keeps the word *definitively* honest.

---

## 4. Schema — migration `scoperg01`

`down_revision = 'jureval01'`. Raw-SQL `IF NOT EXISTS` (the `jureval01` pattern). **Not auto-applied
— the user runs `./scripts/migrate-dev.sh`.**

- **`business_categories`** — the one canonical taxonomy every legacy vocabulary maps *into*.
  `slug PK, label, parent_slug FK(self), naics_codes TEXT[], aliases TEXT[]`.
  Seeds `warehousing` (493), `construction` (23), `transportation` (48–49) as first-class and
  distinct from `manufacturing` (31–33); `healthcare → medical_offices → ophthalmology`.
- **`authority_indexes`** — `slug UNIQUE, name, level, jurisdiction_id FK, source_type
  ('ecfr'|'federal_register'|'curated'), source_ref JSONB, domain_categories TEXT[],
  domain_excludes TEXT[], enumerable BOOL, item_count, unclassified_count, last_ingested_at`.
- **`authority_index_items`** — `authority_index_id FK CASCADE, citation, heading, hierarchy JSONB
  {title,part,subpart,section}, parent_item_id FK (subpart → section), source_url, amendment_date,
  UNIQUE(index_id, citation)`.
- **`authority_item_classifications`** — *the primitive.* `item_id FK CASCADE UNIQUE, disposition
  ('universal_in_domain'|'category_specific'|'conditional'|'excluded'), applies_to_categories
  TEXT[], excludes_categories TEXT[], entity_condition JSONB (`evaluate_trigger_conditions` shape),
  excluded_reason, regulation_key (NULLABLE — null means applicable-but-not-yet-codified, i.e. the
  fetch queue), key_definition_id FK, inherits_from_item_id FK, status
  ('provisional'|'confirmed'), proposed_by ('gemini'|'seed'|'admin'), confirmed_by/at`.
  **Items with no classification row are `unclassified` — the definitive remaining-work counter.**
- **`scope_strata`** — *derived, materialized, never hand-edited.* `level, jurisdiction_id FK
  (NULL iff federal), category_slug (NULL = ALL), entity_condition JSONB (NULL = base), label,
  status, coverage_pct, item_count, key_count, refreshed_at`. Unique coordinate index via
  `COALESCE(...) + md5(entity_condition::text)`. Rebuilt by `recompute_strata()`.
- **`scope_resolutions`** — cache. `coordinate_hash UNIQUE, stratum_ids UUID[], key_count,
  uncodified_count, provisional_count, computed_at`. This is what proves "second warehouse = zero
  work."
- **`scope_shadow_log`** — `session_id, company_id, resolve_keys TEXT[], expand_keys TEXT[],
  only_in_resolve TEXT[], only_in_expand TEXT[], unmodeled_coordinates JSONB, created_at`.
- Seeds a `scheduler_settings` row `scope_registry_authority`, **disabled** (the hourly worker
  restart must never sweep .gov unattended).

`regulation_key_definitions`' existing empty applicability columns get **populated as derivation
hints** from confirmed classifications — no parallel columns are added.

---

## 5. Backend — `server/app/core/services/scope_registry/`

| File | Responsibility |
|---|---|
| `models.py` | Pydantic: `BusinessCategory`, `AuthorityIndex(Item)`, `ItemClassification`, `Stratum`, `ResolvedScope` |
| `categories.py` | Taxonomy seed; `resolve_category(raw)`, `ancestry(slug)`, `categories_for_naics(naics)`. `compliance_service._resolve_industry` becomes a thin shim delegating here — killing `warehouse → manufacturing` |
| `authority_ingest.py` | `ingest_ecfr_index(title, part)` reusing `government_apis/ecfr.py:_fetch_part_structure` / `_parse_structure` (one item per subpart **and** section, `parent_item_id` linked). `ingest_curated_index(slug, rows)` for CA/LAMC CSV. Idempotent upsert |
| `classify.py` | The authoring engine. Gemini singleton (google.genai + `google_search` grounding) pre-classifies **at subpart level**. Hard gates: `applies_to`/`excludes` values must exist in `business_categories`; a cited key must exist in RKD or be flagged uncodified. Lands `provisional`. `confirm_classification()` → triggers `recompute_strata()` |
| `seed.py` | Phase-1 provisional classifications from `industry_keysets.CORE_*` + RKD hints + known conditionals: FMLA (headcount ≥ 50), PSM (chemical > TQ), anti-dumping (imports_goods — **out of base manufacturing**), AB 701 (warehousing) |
| `resolve.py` | `resolve_scope(conn, company_id \| {naics\|category, jurisdiction_chain, facility_attributes})` |
| `strata.py` | `recompute_strata()`, coverage math, per-index `unclassified_count` |
| `shadow.py` | Runs `resolve_scope` alongside `expand_scope` on onboarding finalize, records the diff. `expand_scope` **stays authoritative** |

**`resolve_scope`:**
1. Category ancestry chain from `categories.py`.
2. One indexed SQL query for confirmed strata matching `(level, jurisdiction)` × `(ancestry ∪ ALL)`.
3. In-process `evaluate_trigger_conditions` filter for conditional strata (reuse
   `compliance_service.py:8368` verbatim — deterministic Python, not an LLM).
4. Union → codified keys + **uncodified applicable items** (the fetch queue), split
   confirmed/provisional; `unmodeled_coordinates` for any `(category × jurisdiction)` with no
   confirmed stratum.

The catalog join is **key-precise** — `WHERE jurisdiction_id = ANY(chain) AND regulation_key =
ANY(resolved)` — not the category-grab that `map_to_bank` does today.

---

## 6. API — `server/app/core/routes/scope_registry.py` (all `require_admin`)

- `GET  /admin/scope-registry/authority` — indexes, `unclassified_count`, coverage, `enumerable` badge
- `POST /admin/scope-registry/authority/{slug}/ingest` — Celery; SSE via `publish_task_progress` on `admin:scope_registry`
- `GET  /admin/scope-registry/authority/{slug}/items?classified=false` — **the definitive remaining-work list**
- `POST /admin/scope-registry/authority/{slug}/classify` — Gemini pre-classification (Celery)
- `POST /admin/scope-registry/classifications/confirm` — batch confirm → recompute strata
- `PUT  /admin/scope-registry/items/{id}/classification` — manual override
- `GET  /admin/scope-registry/strata` (+ `/{id}`) — read-only view of the materialization
- `GET  /admin/scope-registry/resolve?category=ophthalmology&state=CA&city=Los%20Angeles&headcount=40`
  — live preview: strata matched, codified keys with citations, uncodified items, counts, unmodeled coordinates
- `GET  /admin/scope-registry/fetch-queue?category=&state=` — applicable-classified items with no codified requirement; the direct input to the research pipeline
- `GET  /admin/scope-registry/shadow-log` — diff review surface

**Celery** (`workers/tasks/scope_registry.py`): `ingest_authority_index`, `classify_authority_index`.
Network/long, `time_limit`, progress/complete/error publishes. `@worker_ready` dispatch gated on the
disabled scheduler row, with the `jureval01` self-throttle (the worker restarts hourly).

---

## 7. Eval integration

- **New fifth suite** `compliance_evals/scope.py` (non-network, inline). Findings:
  `unclassified_authority_item` (critical if `enumerable`, warn if curated — the definitive-scope
  counter), `provisional_classification` (critical — counts toward no resolved scope),
  `scope_without_value` (critical — classified applicable, no catalog row: the fetch queue surfaced
  as findings), `ungated_conditional` (warn — a conditional classification whose gating attribute is
  absent from the company's locations; *under*-scoping made visible rather than silent).
- **`completeness.py`** — where a `(jurisdiction × category)` coordinate has confirmed strata,
  `expected` = resolved scope. Otherwise fall back to `industry_keysets`, tagging the cell
  `expectation_source: 'registry_groups'` so the unfounded denominator is at least labeled.
- **`industry_keysets.py`** demoted to a seed input and the human-auditable core checklist. It stops
  being a source of truth wherever strata exist.

---

## 8. Phasing

Phase 1 covers **federal + CA** and three categories chosen to exercise all three mechanisms:
**manufacturing** (industrial), **warehousing** (taxonomy-splitting — proves the AB 701 fix), and
**ophthalmology** (deep hierarchy + a curated licensing-board index).

| # | Commit |
|---|---|
| 1 | Matrix-page vocabulary fix — standalone, repairs a live bug |
| 2 | `scoperg01` migration + `categories.py` + `_resolve_industry` shim |
| 3 | Authority ingest — eCFR for 29 CFR 1910/1904/825 + 40 CFR 260-262; curated CA indexes (Labor Code incl. AB 701 §§ 2100-2112, Title 8 core, Title 16 board slice) |
| 4 | `classify.py` + `seed.py` + `recompute_strata` + `resolve.py` + endpoints (fetch-queue, resolve-preview) |
| 5 | `shadow.py` wired into `admin_onboarding` finalize + shadow-log endpoint |
| 6 | Eval `scope` suite + `completeness` repoint + `ScopeRegistry.tsx` |

### Standalone fix (commit 1)

`admin.py:8549 get_industry_requirements_matrix` — route the incoming industry through the canonical
resolver, match the profile and `industry_tag` on the canonical slug, and swap `IndustryRequirements.tsx`'s
`INDUSTRIES` values to canonical slugs. This stops the page returning an empty matrix for
manufacturing today. The page is rebuilt as the Scope Registry surface in commit 6; this just stops
it lying in the meantime.

### Frontend (commit 6)

`client/src/pages/admin/ScopeRegistry.tsx` + route + sidebar entry: authority-index table with
`unclassified_count` and an `enumerable` badge (curated indexes visibly labeled *"curated, not
exhaustive"*); the unclassified-items worklist with confirm/override actions; strata view;
resolve-preview widget (category + location + headcount → count, keys, citations, fetch queue); and
the shadow-log diff table.

---

## 9. Verification

1. **Unit tests** (`tests/scope_registry/`, no live-DB mutation): category ancestry and NAICS
   resolution (`621111` → ophthalmology chain; `493110` → warehousing, **not** manufacturing);
   alias round-trip for all seven legacy vocabularies; subpart → section inheritance and override;
   `applies_to` / `excludes` interaction with the index domain; conditional strata via
   `evaluate_trigger_conditions` fixtures; resolution dedup; uncodified-item surfacing;
   unmodeled-coordinate detection.
2. **eCFR ingest smoke** (live): 29 CFR 1910 → 23 subparts + 204 sections with parent links;
   `1910.147` and `1910.119` present; idempotent re-run; `unclassified_count` equals item count
   before any classification.
3. **The acceptance test.**
   - LA warehouse (NAICS 493110) → scope **contains** AB 701 **and** `1910.147` (general industry);
     **excludes** `1910.119` PSM (no chemicals) and `anti_dumping_duties` (no imports).
   - LA manufacturer (NAICS 332) → contains `lockout_tagout` citing `29 CFR 1910.147`; **excludes**
     AB 701.
   - LA ophthalmology practice (621111) → universal + healthcare chain + Title 16 board items; zero
     machine-safety pack.
   - Second identical business → `scope_resolutions` cache hit, **zero Gemini and zero network calls.**
   - **Definitive-scope check:** for a confirmed index, `unclassified_count == 0` ⇒ scope for its
     coordinates is closed, and `fetch-queue` lists exactly the applicable-but-uncodified items.
4. **Shadow:** one gap-analysis session end-to-end on dev; `scope_shadow_log` shows both key sets and
   the diff; `expand_scope`'s result in `compliance_requirements` is unchanged.
5. **Eval:** `scope` suite reports `unclassified_authority_item` findings (real and expected on day
   one); provisional classifications flagged until confirmed.
6. `pytest tests/compliance_evals tests/scope_registry -q`; `npx tsc --noEmit --incremental false`.
7. User applies `scoperg01`.

---

## 10. Honest limits

- **Federal completeness is provable.** eCFR is official and exhaustive; *"every item is classified
  or excluded with a reason"* is checkable. **CA and LA are curation-bounded.** There
  `unclassified_count = 0` means the curated list is fully classified — not that all CA law is
  scoped. The UI says so. Do not let the two read alike.
- **Classification volume is the real cost.** Index domains and subpart inheritance cut it roughly
  10×, but a human still confirms every subpart. That is the work. There is no shortcut that keeps
  *definitively* honest.
- **`companies.naics` is frequently absent or self-reported.** Resolution then degrades to alias
  mapping. A missing NAICS surfaces as an `unmodeled_coordinate`, never as a silent empty scope.
- **Scope answers *whether* an obligation applies; preemption answers *which level wins*.** The
  latter stays in `determine_governing_requirement`. Resolution dedups keys across levels. Keep this
  boundary clean or the count becomes ambiguous.
- **Conditional strata under-scope silently when an attribute is missing.** FMLA fires only if
  headcount is recorded. The `ungated_conditional` eval finding exists to make that visible — the
  same "silence is not a pass" principle the eval system already enforces.
- **Seed provenance.** `industry_keysets.py` was itself LLM-authored. Seeding from it imports its
  judgment, which is why seed rows land `provisional` and require confirmation. The seed accelerates
  authoring; it does not grant authority.
- **The taxonomy is open-ended.** Ophthalmology today, med-spas tomorrow. Adding a category is a
  taxonomy row plus classifying the deltas — not a schema change, and not a re-scope of ancestors.
