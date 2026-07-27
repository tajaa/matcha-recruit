# The Compliance System — how law gets in, and how it gets served

_A read-only walkthrough of `server/`: how the platform acquires policy/regulatory
and jurisdictional information, codifies it, and serves it to a tenant. Written
2026-07-27 against `main` @ `57a6d2c`. No code changes accompany this document._

**The one fact to hold onto:** there are **two generations** of this pipeline
sharing one catalog table. Generation 1 (Gemini runtime research) serves
essentially every tenant today. Generation 2 (the authority-anchored scope
registry) is architecturally complete, correct where exercised, and **one
coordinate wide** — federal + California, additive-only. Reading the code without
knowing which generation you're in is the main way to get lost.

---

## 1. The spine

```
                 ┌─────────────────────────────────────────┐
   research  ───▶│      jurisdiction_requirements          │───▶  compliance_requirements
   pipelines     │  THE catalog. Jurisdiction-scoped,      │      per-tenant, per-location
                 │  NOT tenant-scoped.                     │      projection (a snapshot)
                 └─────────────────────────────────────────┘
```

The catalog being jurisdiction-scoped is the entire economic argument: research a
`(jurisdiction × category)` cell once, and the second dental office in Los Angeles
triggers **zero** Gemini calls. `compliance_requirements` is each location's copy,
written by projection.

**Row identity** is `(jurisdiction_id, requirement_key)` where `requirement_key` =
`<category>:<regulation_key>`, computed by `_compute_key_parts`
(`core/services/compliance_service/_catalog_writes.py:828`).

> **Sharp edge.** `minimum_wage` derives its write identity from **`rate_type`**,
> not `regulation_key` — `_compute_key_parts` ignores the key entirely for that
> category. This is why NY's downstate exempt threshold needed a *new rate_type*
> (`exempt_salary_regional`) to exist as its own row, and why `VALID_RATE_TYPES`
> is duplicated in `gemini_compliance.py` and `_normalize.py` with a test pinning
> the two copies together. Their drift **is** the bug: a producer emitting a
> rate_type outside the set flattens to `general` and overwrites the state's
> general minimum wage row with a salary-threshold figure.

### Supporting tables

| Table | Role |
|---|---|
| `jurisdictions` | The node tree: federal → state → county → city. County nodes store their name in `city` under a `_county_<name>` sentinel. |
| `compliance_categories` | Category vocabulary (DB). Drifts from the code registry — see §7. |
| `regulation_key_definitions` (RKD) | 490 rows; the key vocabulary + applicability hints. |
| `jurisdiction_vertical_coverage` | The industry-research ledger (§6). |
| `authority_indexes` / `_index_items` / `authority_item_classifications` | The scope registry corpus (§4). |
| `scope_codifications` | Stored scope↔catalog linkage with provenance. |
| `scope_strata` / `scope_resolutions` / `scope_shadow_log` | Derived scope, its cache, and the shadow diff. |
| `state_preemption_rules` | Per-category "may a locality exceed this?" |
| `compliance_eval_runs` / `_results` | Measurement (§8). |

---

## 2. Generation 1 — runtime research (the live path)

`core/services/compliance_service/_run.py:122 run_compliance_check_stream` is an
SSE generator, and is what actually runs when a tenant clicks "Run check" or an
onboarding build sweeps its locations. It's a **4-tier cascade, cheapest first**:

| Tier | Source | Reality |
|---|---|---|
| **1** | Authoritative structured feeds — `core/services/structured_data/` | **`minimum_wage` only.** All 4 sources declare `categories=["minimum_wage"]`. |
| **2** | The catalog, if fresh (`_is_jurisdiction_fresh`, threshold = `location.auto_check_interval_days`) | Free. Gaps filled from county/state parents via `_fill_missing_categories_from_parents`. |
| **2.5** | County→state reuse for cities with no local ordinance | Gated on `_lookup_has_local_ordinance`. |
| **3** | **Gemini + Google Search** (`core/services/gemini_compliance.py`) | Only fires on staleness or a coverage gap. |
| **4** | Triggered research off `facility_attributes` | FQHC, Medi-Cal, entity-type-specific obligations. |

Tier 2 → 3 escalation is driven by `_missing_required_categories`, which the
generator **shadows with a local closure** when the caller passes a narrowed
`categories` list (Matcha-X onboarding passes `MATCHA_X_LITE_CATEGORIES`, 9
categories instead of the full labor sweep). With `categories=None` the behaviour
is byte-for-byte the old full check.

### Two flags that mean different things

- `allow_live_research=False` — no *per-company* Tier-3 research.
- `allow_repository_refresh=False` — **no Gemini at all**, full stop; a pure
  projection from whatever the catalog already holds.

The second exists because the first was leaky: the shared-jurisdiction gap-fill
branch ran regardless, so a "read-only" caller could still spend money. The
tenant-facing route passes both False. Also gated on `allow_repository_refresh`:
the healthcare **facility-inference** call (`service.infer_facility_profile`),
which auto-populates `facility_attributes.entity_type` — it's a Gemini call too.

### The research prompt

`gemini_compliance.py:458 _build_category_prompt` — one prompt per category,
batched. It mandates:

- a **primary** legal source on an official government site (`_SOURCE_MANDATE`)
- a stable snake_case `regulation_key`, seeded with the known keys for that
  category from `EXPECTED_REGULATION_KEYS`
- `statute_citation`, `penalties`, `implementation_steps`, `requires_written_policy`
- `no_rule_applies` — an explicit model flag. The prompt asks for a placeholder
  row rather than an empty list, because downstream an empty category reads as a
  **failed** research call. These get filtered out of the tenant's view later.
- `is_federal` mode: the default prompt asks for rules "beyond the federal
  baseline" and returns a null row when there aren't any — degenerate when the
  target *is* the federal baseline, so federal mode drops the escape hatch.

Model output is coerced and validated by `_coerce_requirement_shape` /
`_validate_requirement`, with `CORRECTION_HINTS` fed back on retry.

### Scoping — what gets researched at all

Still `core/services/onboarding_scope_ai.py`:

- `expand_scope(basics, locations)` — **one** Gemini call, JSON-strict, returns
  category slugs + certifications + licenses + applicable jurisdictions.
- `map_to_bank(ai_scope, conn)` — pure SQL, grabs **every catalog row in those
  categories** for those jurisdictions. Returns `{existing, missing, ambiguous}`.

This is per-session, uncached, uncited, and **category-granular** — the thing the
scope registry was built to replace. It is still the authoritative writer of
company scope (see §5).

### The write — read this function before touching anything

`_catalog_writes.py:236 _upsert_requirements_additive`. One long upsert carrying
a lot of hard-won behaviour:

- **`applicable_industries` UNIONS on conflict.** Tagging a generic labor row with
  a vertical tag hides it from every other tenant in that jurisdiction —
  poisoning the shared catalog. Only a specialization pass's own output is tagged.
- **`repealed` is frozen.** `WHERE status <> 'repealed'` — an admin's explicit
  "this value is wrong" verdict survives only as an audit trail, and re-research
  must not silently resurrect it.
- **Grounding verdicts move status both ways.** `grounded is False` ⇒
  `under_review` (quarantine); `True` ⇒ promote a quarantined row back to
  `active`. Without the promote half, `under_review` was terminal *and* the key
  stayed on the research worklist — re-burning Gemini every cycle, forever.
  `None` (the legacy ungrounded-by-design paths) never touches status.
- **Penalties deep-merge.** `jsonb ||` is shallow, so a new penalties block would
  wholesale-replace an old one and drop keys the new block omits (e.g. a
  skill-written `source_url` a grounded re-research never sets).
- **Category drift is parked, not dropped.** An unseeded category lands on the
  `uncategorized` sentinel (never an arbitrary `LIMIT 1` row — that was the bug),
  and the upsert **forward-repairs** the `category_id` once the seed migration
  lands. 10 registry categories had no seed row, four of them in the default
  research sweep — every result in those categories was silently vanishing.
- `statute_citation` from the model goes into `metadata.research_citation`. The
  **column** stays reconcile-owned (§5).

---

## 3. Where else law comes from

Not everything is Gemini:

- **`core/services/government_apis/`** — eCFR, Federal Register, Congress.gov,
  OpenStates, CMS, via an `orchestrator`. Feeds Tier 1 and the authority ingest.
- **`.claude/skills/fill-gaps-*`** — the Claude-Code research skills
  (`fill-gaps-labor`, `-healthcare`, `-penalties`, `research-jurisdiction`, …).
  These write catalog rows directly with real `source_url` + `verified_date`, and
  they are why the penalty deep-merge above matters: an ungrounded recall pass
  must not clobber a skill-written penalty block.
- **`legislation_watch`** — Gemini-grounded legislation deltas. Note it is a
  **dead end**: it only writes `compliance_alerts`. A new law becomes a tenant
  nudge, never a codified obligation.

---

## 4. Generation 2 — the scope registry (`core/services/scope_registry/`)

This inverts the question. Instead of asking a model "what applies here?", it
**enumerates a real published authority** and classifies each item.

```
authority_indexes                12 today
  ↓ authority_ingest.py            7 eCFR parts: 29 CFR 1910, 1904, 825, 1903
authority_index_items                              40 CFR 260, 261, 262
  ↓ body_fetch.py (statute TEXT)  + us-flsa, us-labor-baseline (curated)
  ↓ classify.py (Gemini, subpart  + ca-labor-code, ca-title-8, ca-title-16
    level; sections inherit)
authority_item_classifications   ◀── THE PRIMITIVE. Exactly one disposition:
  ↓ human confirm                    universal_in_domain | category_specific
scope_strata (derived, never                            | conditional | excluded
  hand-edited; recompute_strata)
  ↓ resolve.py resolve_scope       ← pure SQL + evaluate_trigger_conditions.
codified keys  +  UNCODIFIED         NO AI AT READ TIME, EVER.
                 FETCH QUEUE
  ↓ research_loop.run_research_cycle
grounded research → reconcile → citation stamps
```

### The completeness argument

You cannot prove completeness against "all law." You **can** against an
enumerable index: coverage is `classified / enumerated`, and a gap is a specific
uncovered citation. `unclassified_count` **is** the remaining scoping work.

eCFR indexes are `enumerable=true` — "every section of 29 CFR 1910 is classified
or excluded with a reason" is mechanically checkable. The CA slices are
`enumerable=false` and labeled *"curated, not exhaustive"* in the UI. There,
`unclassified_count == 0` means the curated list is fully classified, **never**
that all CA law is scoped. Do not let the two read alike.

`unclassified` = *has no **confirmed** classification*. **Three** code paths write
that column (`classify`, `strata.recompute_strata`, `authority_ingest._recount`)
and a fix that touched only one silently self-reverted on the first admin
confirm. The test asserts the filter lives in the JOIN's `ON` clause — in the
`WHERE` it inverts the count to 0 — and fails if any writer drifts.

### Dispositions need both `applies_to` and `excludes`

Modeling only `applies_to` forces you to enumerate every included category for a
rule like lockout/tagout, which covers all of general industry. So
classifications carry both, and inherit the index's domain.

The canonical worked example, and the reason flat per-industry keysets can't
express this:

> An LA **warehouse** *is* general industry, so `29 CFR 1910.147` (lockout/tagout
> — conveyors, dock levelers, balers) genuinely applies. What it does **not** get
> is `1910.119` PSM (conditional on chemical quantities) or `anti_dumping_duties`
> (conditional on importing). What a **manufacturer** does not get is CA AB 701
> (warehouse quotas, NAICS 493).

`classify.py:validate_proposal` is the write-time gate: category slugs must exist
in the taxonomy, a cited `regulation_key` must exist in the RKD (else stored NULL
with a **warning** — the item is applicable-but-uncodified, i.e. the fetch queue;
keys are never invented), `entity_condition` must be a shape
`evaluate_trigger_conditions` accepts, and `excluded` requires a reason.

Gemini pre-classifies at **subpart** level (cutting 29 CFR 1910 from 204
decisions to 23) and lands `provisional`. Every engine read filters `confirmed`.
A human confirms; that is the work, and there's no shortcut that keeps the word
*definitively* honest.

### Grounded research (`grounded.py` + `body_fetch.py`)

The anti-hallucination half. `body_fetch` pulls actual statute text (eCFR
full-text XML per part; generic best-effort `.gov` HTML with bs4 extraction for
everything else — that's what makes "new states plug in" work without new code).
`build_grounded_corpus` renders it as numbered excerpts; the prompt's grounding
rules **override prior knowledge** and require `cited_sources: ["S1", …]`.

Then, in `_specialization.py:research_specialization_for_jurisdiction`:

- `validate_requirement_citations` → cited a real corpus id ⇒
  `research_source='gemini_grounded'`; otherwise `'gemini'` +
  `metadata.grounding='ungrounded'`.
- `validate_penalty_citations` runs **independently** (penalty text usually lives
  in a different section), and an ungrounded penalty block is **dropped**, not
  persisted from recall.
- A req that *was given* statute text and still failed to cite it lands
  `status='under_review'`. Narrower than "any ungrounded row" on purpose, so the
  legacy ungrounded-by-design paths are untouched.

`_load_jurisdiction_requirements` (`_jurisdictions.py:388`) is the single choke
point every tenant-sync and gap-detection read goes through, and it excludes
`under_review` **and** `repealed` — so a quarantined row reads as a *gap to
re-research*, never as served coverage.

---

## 5. Codify — the step the name refers to (`scope_registry/codify.py`)

**"Codified" is a trio**, and there is exactly one predicate for it
(`codify.py:24 codified_sql`):

```sql
statute_citation IS NOT NULL AND citation_verified_at IS NOT NULL
                             AND citation_item_id IS NOT NULL
```

All three, because `reconcile_codifications` writes all three together and
nothing else writes any of them. `citation_item_id` is `ON DELETE SET NULL`, so
deleting the backing authority item must drop the row **out** of codified and
back into the backlog rather than leaving a phantom asset. `is_codified_row`
(`_hierarchy.py:73`) is the Python mirror, kept next to the SQL so they can't
drift — the studio meter and the quality audit had already disagreed once.

### `match_codifications` — the pure core, and its three guards

Key-equality join between confirmed classifications and catalog rows. Every guard
is a bug that shipped and wrote false legal citations to customers:

1. **country guard** — registry keys are a *global* vocabulary
   (`national_minimum_wage` is as true of the UK as the US), so key equality
   alone stamped the US FLSA cite `29 U.S.C. § 206` onto **UK National Living
   Wage** and Mexico's **ZLFN border-zone wage**. "Federal law applies
   everywhere" means everywhere *in the United States*.
2. **state guard** — a state-scoped authority binds only its own state's rows.
   Without it `Cal. Lab. Code § 510` bound the **federal** overtime row.
3. **category guard** — the same key can live under two categories
   (`exempt_salary_threshold` under both minimum_wage and overtime).

### `build_citation_stamps` — direct vs. baseline

The subtlest logic in the system, and the one worth understanding before you touch
anything here. Given links, split by **jurisdictional relation**:

- **direct** → goes in the `statute_citation` **column**. The authority *is* this
  row's operative law. Two ways to qualify: **same level** (a CA code section on a
  CA row), or **higher level whose value the row restates verbatim** — TX's
  `$684/week` exempt threshold *is* the FLSA figure, so `29 CFR § 541.600`
  genuinely is its citation.
- **baseline** → goes in `metadata.jurisdictional_basis` as a *floor* relation.
  The authority sits above and the row sets its **own** value.

| Jurisdiction | Value | Correct treatment |
|---|---|---|
| Texas | `$684.00/week` | **direct** — it *is* the FLSA figure |
| California | `$70,304/year` | **baseline** — that's CA law; the federal reg says $684 |
| New York | `$1,275/week` | **baseline** — NY law |

All 51 federal→non-federal stamps originally had the CA/NY shape: telling a
customer their $70,304 California obligation came from a federal reg that says
$684. Surfaced to the customer as a **floor chip** instead, so the fix *gained*
signal rather than just deleting citations.

Restatement test: `numeric_value` first, then normalized text, against the
authority-level row. Three rules hold it together:

- **No basis codified ⇒ baseline, never a guessed stamp.** A wrong citation is
  worse than none.
- **A demote only clears an existing stamp on a `verified` mismatch.** Absent
  basis is not evidence of divergence — otherwise quarantining *one* federal row
  would strip correct citations off every state row that restates it.
- **The floor is keyed `(regulation_key, level, country, state)`** (`_basis_key`),
  and `national` normalizes to `federal` on **both** sides of the lookup. Keyed
  on `(key, level)` alone, a UK row became "the federal floor" every US state was
  tested against; one level down, all 50 states shared one bucket.

`select_primary_citation` picks the one that lands in the column: level match →
regulation over statute (the regulation carries the operative *value*; 29 U.S.C.
213 only authorizes the exemption) → deepest hierarchy → lexicographic.

### What codify does NOT do

**It mints zero `jurisdiction_requirements` rows.** `codify.py` contains no
`INSERT INTO jurisdiction_requirements`. It stamps citations onto rows the
research pipeline already wrote, and records the linkage in `scope_codifications`.
An unmatched `regulation_key` lands in `unmatched_keys` and never becomes a value.

The only value-minters are `research_specialization_for_jurisdiction` (admin SSE
button + the Compliance Pilot action layer) and the headless
`research_loop.run_research_cycle`.

### The loop that closes it

`research_loop.py:166 run_research_cycle`:

```
chain_uncodified → group_research_units (severity-ordered) → prefetch_bodies
                 → run_research_units (GROUNDED) → reconcile_codifications
                 → chain_uncodified (after)
```

Capped at `MAX_UNITS_PER_CYCLE = 5`, chain `[{"state": "CA", "city": None}]`, and
it **guards its own cadence off `scheduler_settings.last_run_at`**
(`MIN_RESEARCH_INTERVAL_DAYS = 6`) because the worker container restarts hourly
and this makes live Gemini calls.

`corpus_for_jurisdiction` is deliberately **not** built on `chain_uncodified` —
that function's `labor_only=True` default drops the `licensed_professions` index a
specialty pass is precisely about, and it returns only the *uncodified* worklist,
so a section's text would vanish from the corpus the moment its key codified. Both
made specialty grounding a silent no-op.

### Cutover — how much of this is authoritative

`cutover.py:24`:

```python
CUTOVER_ALLOWLIST = {("CA", None)}
```

**Additive only** — engine-definitive codified keys are *unioned* into the bank
projection alongside the category-grab; a coordinate the engine misses still gets
whatever `expand_scope` found. Gated company-wide: only when **every** location
resolves `coverage_source == "engine"`. Any failure returns `[]`, a safe no-op.

A **code constant, not an admin toggle**, on purpose: the `scope_shadow_log`
agreement rate is the evidence that justifies widening it, and a self-serve
toggle would let someone flip it before that evidence exists.

`shadow.py` runs `resolve_scope` alongside `expand_scope` on onboarding finalize
and records the diff. `expand_scope → map_to_bank` remains the sole authoritative
writer of company scope everywhere else.

---

## 6. The vertical ledger (`core/services/vertical_coverage.py`)

Auto-scopes **any** US industry, not just the ones hand-authored into
`compliance_registry/`. A tenant *triggers* a fill; the result is shared.

```
resolve_vertical  (sub-specialty → healthcare entity_type → THE INDUSTRY ITSELF:
                   a hotel's vertical is `hospitality`)
  → ensure_specialty   (industry_specialties.discover + confirm if no categories yet)
  → missing_cells      (ledger diff)
  → fill               (research_specialization_for_jurisdiction, one call per cell)
```

**The ledger is the point.** `jurisdiction_vertical_coverage` is keyed
`(jurisdiction_id, industry_tag, category)` — *not* per tenant or location — so
federal research runs once nationally, state once per state, and the second
dental office in a city makes **zero** Gemini calls.

Invariants, each a silent bug that shipped:

- **`empty` ≠ `failed`.** "Researched, genuinely nothing" is a distinct terminal
  status from "retry me." The coverage check this replaced (`skip_existing` — "are
  there rows already?") structurally cannot express that, so empty cells were
  re-researched forever.
- **`backfill_ledger` runs first.** A cold ledger over a seeded vertical
  (healthcare = 17 categories, 300+ rows) re-researches the whole thing on the
  next tenant's onboarding.
- **A cell is a CHAIN NODE × category and owns exactly ONE level.** Cells come
  from `expand_to_chains` (federal→state→county→city), never the tenant's leaf.
  Keyed on the leaf, federal law is re-researched once per city and a California
  row LA paid for is unreadable by SF. `only_levels` keeps only rows stamped with
  the cell's own level — otherwise the city, county, state and federal passes each
  volunteer California's amalgam rule under a *different title*, and no
  deterministic dedupe can collapse them. `route_by_level=True` files each row on
  the jurisdiction its stamped level belongs to (researching a city hands back
  federal obligations; filing them on the city is the misparenting `jparent01`
  exists to undo).
- **The category vocabulary is the DB, not a constant.** `refresh_dynamic_categories(conn)`
  unions `compliance_categories` in. Without it, a runtime-discovered category read
  as "invalid", the requested list emptied, and the research call **fell back to
  `DEFAULT_RESEARCH_CATEGORIES`** — returning wage law that the specialty path then
  force-tagged `healthcare:dental` (153 rows of it).
- **A top-level industry's tag is bare.** `industry_tag()` collapses `(x, x)` → `x`,
  because `hospitality:hospitality` matches no company and would hide every row
  from the tenant who paid to research it.
- **Never blanket-tag.** See the UNION note in §2.

> `route_by_level` defaults to **False**, which is known debt: the admin
> specialization flow and the scope-registry research paths still write
> leaf-misparented rows. Flipping the default needs those three flows re-verified
> (their `skip_existing` checks read per-jurisdiction state that routing
> relocates). See the TODO at `_specialization.py:206`.

**Three triggers:** the Matcha-X onboarding build (step 3c); the tenant "Run
check" via `include_vertical_fill=True`, **opt-in by design** (the stream has 5
callers; an unconditional fill would fire 3× per Matcha-X build and add silent
Gemini spend to the admin white-glove flows); and the `vertical_coverage_sweep`
Celery task (seeded **disabled**, one sweep/day via an atomic `last_run_at`
claim).

---

## 7. The tenant read path

`_hierarchy.py:173 _project_chain_to_location`:

```
chain union → normalize categories → industry filter → FACILITY TRIGGERS → preemption
```

- **`_load_chain_requirements`** walks the jurisdiction chain.
- **`_filter_requirements_for_company`** — untagged rows always pass; tagged rows
  need a set intersection with the company's tags. A company with **no** industry
  tags gets *every* industry-specific row dropped. (This is why `warehousing`
  having `legacy_industry=None` broke the AB 701 flagship end-to-end.)
- **Facility triggers** — `evaluate_trigger_conditions` against
  `location.facility_attributes`. This pass is what keeps "exhaustive" from
  becoming "everything": nothing in the tenant read path ever evaluated them, so a
  dental practice was being served hospital and opioid-clinic obligations.
- **`_filter_with_preemption`** + `determine_governing_requirement` resolve
  federal→state→local precedence. Keep this boundary clean: **scope answers
  *whether* an obligation applies; preemption answers *which level wins*.**

Two failure modes worth knowing:

- `_eval_condition` **fails closed** on an unrecognized node. A plausible Gemini
  typo (`op` where it meant `operator`) returned `True`, silently turning a
  *conditional* obligation into a universal one and serving the PSM standard to
  every warehouse. `jurisdiction_requirements.trigger_conditions` are written by
  research with **no write-time shape gate** (unlike scope-registry
  classifications, which `validate_proposal` rejects) — read-time now fails
  closed, but a malformed trigger still persists silently. **Still open.**
- An unreadable `trigger_conditions` value (garbage string, not dict) is treated
  as unconditional and logged. `isinstance(dict)`, not truthiness — one bad
  catalog row would otherwise take down the projection for every tenant whose
  chain contains it.

### The codified-only kill switch

`codified_gate_sql` (`_hierarchy.py:87`) appends `AND <trio>` to every
tenant-facing read of requirement **content**, when the `tenant_codified_only`
platform setting is on. The alias is the joined **catalog** row, not the
projection: codification is a property of the law we researched once, not of each
tenant's copy. `get_tenant_codified_only` **fails closed to `True`** — a DB hiccup
reading a display policy must not open the gate.

### Propagation

The onboarding projection is a **one-time snapshot**; the tenant Compliance tab
reads `compliance_requirements`, not the live catalog. There is **no automatic
propagation** — refresh is the manual "Run check" button, and that endpoint lives
on the full-`compliance` router, so **`compliance_lite` (Matcha-X) tenants have no
refresh path at all.**

---

## 8. Measurement (`core/services/compliance_evals/`)

**Read-only over the catalog — never writes to it.** Seven suites:

| Suite | What it measures |
|---|---|
| `completeness` | Per jurisdiction × industry, against `industry_keysets.expected_keys` |
| `authority` | Citation liveness + primary-source domain classification |
| `tagging` | Key/category integrity + the structural `applicable_industries` check (an untagged industry-specific row is served to *every* tenant) |
| `golden` | Hand-verified facts in `fixtures/golden/*.json`, effective-date windowed |
| `baseline` | Federal + CA-state against the enumerated labor master-list |
| `scope` | `unclassified_authority_item`, `provisional_classification`, `scope_without_value`, `ungated_conditional` |
| `grounding` | Value-provenance verification (tier-2b verifier off by default) |

Rolls into an **onboarding-readiness gate** (`scoring.py`). **Unmeasured is
`null`, never 100** — the system fails dark, not high.

**Two depths.** `full` sweeps the registry (180 keys for manufacturing, 237 for
healthcare) — too many to hand-audit, so a wrong expectation would go unnoticed.
`core` is a curated **≤30-key must-have checklist**, and only `manufacturing` +
`healthcare` have one. Core keys must be nationally applicable (no
`healthcare_minimum_wage` — that's CA SB 525) and every miss is critical by
construction. Adding an industry means **curating a core set**, not widening a
category group.

Two catalog quirks the evals must reconcile, both live: minimum-wage rows are
keyed on **rate_type** not registry keys (`keys.normalize_key`), and
`get_missing_regulations` skips its country filter for the US — so it demands
Mexican keys (`finiquito`) of US employers, which `industry_keysets.expected_keys`
filters unconditionally instead.

The completeness **denominator** is the honest weak point:
`registry_expected_keys` returns `None` if *any* covering index has
`unclassified_count > 0`, and the federal indexes are unconditionally covering —
so one unclassified item in an unrelated federal index (say RCRA
`ecfr-40-260`) disables the registry denominator for **every** jurisdiction, and
the cell falls back to `industry_keysets` tagged
`expectation_source: 'registry_groups'`. The numerator is measured; that
denominator is asserted.

---

## 9. Admin surfaces

- **`/admin/studio`** (`client/src/pages/admin/studio/ComplianceStudio.tsx`) —
  the unified cockpit. Tabs: Authority, Coverage, Codified, Library, Pipeline,
  plus `StudioAssistant` / `pilot`. `AuthorityCockpit` +
  `AuthorityCockpit/ClassificationEditor` drive the registry.
- **`POST/GET /admin/scope-registry/*`** (`core/routes/admin_tools/scope_registry.py`,
  23 endpoints, all `require_admin`) — ingest, fetch-bodies, classify,
  propose-keys, seed, confirm, vocabulary, classification override, strata,
  resolve preview, fetch-queue, fetch-queue/research (SSE), under-review + decide,
  reconcile, drift + acknowledge, labor-scope, shadow-log.
- **Compliance Pilot** (`core/services/compliance_pilot.py`) — chat-driven library
  building. A turn may emit one structured **proposal** (research / check_sources
  over an industry × jurisdiction coordinate) which the admin confirms into a
  background run that drives the *existing* pipeline: research stages rows
  `initial_status='pending'`, and `research_review.approve_staged` activates +
  codifies them.

Two operational traps that have bitten:

- **`.delay()` onto a broker with no worker succeeds** — the task sits in Redis
  forever, so Ingest/Classify reported "running" and nothing happened. Now reports
  `worker_online` + a `queued_no_worker` status. (`dev-remote.sh` *does* run a
  worker — as a **process**, not a container, so a `docker ps` check misses it.)
- **`celery_app.control.ping` is synchronous broker I/O.** Called inline from an
  async route it froze the whole uvicorn process for the timeout. Now
  `asyncio.to_thread`.

---

## 10. Migrations worth knowing

| Revision | What |
|---|---|
| `scoperg01` | The registry: `business_categories`, `authority_indexes`, `_index_items`, `authority_item_classifications`, `scope_strata`, `scope_resolutions`, `scope_shadow_log` + the seeded-disabled `scope_registry_authority` scheduler row |
| `scoperg02` | `scope_registry_research` scheduler row (seeded disabled) |
| `statbody01` | `authority_index_items.body_text` — statute text, so compliance means being able to *read* the obligation |
| `codify01/02/03` | `regulation_key` backfill · `scope_codifications` · widen `source` to 64 (`VARCHAR(20)` with `'scheduled_research'` at 18 chars was a tripwire — overflow raises *inside* the reconcile transaction, rolling back every link and citation the run computed) |
| `jparent01` | Re-parented requirements to their stamped level. **The template for set-based prod migrations** — a TEMP table holds the plan, ~20 statements, four seconds |
| `rekey01/02` | Obligation-key collision resolution + identity-drift healing. A re-key leaving a stale composite re-opens the collision on the next research pass (`ON CONFLICT` matches nothing, a twin is minted) |
| `jureval01` | The eval system (scheduler row seeded disabled) |
| `vertcov01/02` | The vertical ledger + its sweep scheduler (seeded disabled) |

---

## 11. Where it actually stands — the honest read

**Generation 1 serves essentially every tenant.** `expand_scope → map_to_bank` is
still the authoritative writer of company scope. Cutover is `{("CA", None)}` and
additive-only.

**Everything scheduled is seeded disabled** — `scope_registry_authority`,
`scope_registry_research`, `compliance_evals`, `vertical_coverage_sweep`,
`legislation_watch`, `structured_data_fetch`, `pattern_recognition`. There is no
celery-beat; the hourly worker restart re-fires `@worker_ready`, which checks the
`scheduler_settings` row. **Flipping these on is an unwritten go-live step**, and
the research cycle makes live Gemini calls.

**Coverage is narrow.**

- Authority corpus: **federal + California only.** Any non-CA state hits the
  documented degrade path in `resolve.py` — *"no state jurisdiction row — coverage
  degrades to federal only."* `BASELINE_JURISDICTIONS = ('federal', 'ca')`.
- Tier-1 structured data: **`minimum_wage` only.**
- Legislation-watch RSS: **3 states (CA/NY/WA), no federal.**
- Core keysets: **`manufacturing` + `healthcare`.** hospitality / retail /
  technology / fast-food have an *empty frozenset* — no industry-specific
  expectation at all, and `runner.py` raises for `depth='core'` on the other ~15
  slugs.
- Clinical specialties: the taxonomy advertises 14 as `exact_aliases`, but they
  all `resolve_category` back to the `healthcare` **parent**. Only
  `ophthalmology` is a real node with codified authority (5 optometry/opticianry
  rows).
- Golden facts: ~54 across 6 US jurisdictions at the last audit, all
  `claude-research`-authored. There is **no verification mechanism** — `curated_by`
  / `verified` are stated in docstrings but are not columns.
- `MIN_GOLDEN_FACTS_READY = 10`, and accuracy does not inherit the chain — so
  LA(6) / SF(4) / NYC(4) and every fixture-less jurisdiction can never read READY.

### Known-open items

1. **`trigger_conditions` have no write-time shape gate.** Read-time fails closed;
   the malformed row still persists silently. The registry side validates at write
   (`validate_proposal`); the research side should too.
2. **`_resolve_regulation_key`'s Jaccard threshold can re-collide the maternity
   rows.** `{statutory, maternity, leave}` ∩ `{statutory, sick, leave}` = 2/4 =
   **exactly** the 0.5 acceptance threshold. Nothing stops a producer repeating the
   original mis-filing.
3. **The NY regional exempt threshold is invisible to the wage-violation
   checker** — it buckets on `rate_type='exempt_salary'` only, so an NYC exempt
   employee paid between the statewide and downstate figures reads as compliant.
   Needs per-region geo applicability (the regional row sits at the NY *state*
   node with nothing marking which counties it binds).
4. **`rekey01`/`rekey02` are dev-applied only** — they must run on prod before the
   next research pass, or prod re-mints the twins they removed.
5. **`legislation_watch` is a dead end** (§3) — no bridge into the codification
   review path.
6. **No URL-liveness re-sweep.** `source_url_status` is a write-time snapshot;
   `_validate_source_urls` has 3 callers, all writes.
7. **`compliance_lite` tenants have no refresh path** (§7).
8. **`route_by_level` default-False debt** (§6).

**The bottleneck is data authoring, not architecture** — authority indexes,
baseline master-lists, core keysets, and ≥10 golden facts per jurisdiction for
NY/TX/IL/WA/FL + NYC/Chicago/Seattle/SF, mirroring the CA slice. The codification
engine is correct where exercised; it is starved.

---

## 12. Reading order, if you're picking this up cold

1. `compliance_service/_run.py:122` — the live 4-tier cascade.
2. `_catalog_writes.py:236` — the write, and every invariant on it.
3. `_hierarchy.py:173` + `:716` — projection and preemption.
4. `scope_registry/codify.py:1-350` — the trio, the three guards, direct vs
   baseline.
5. `scope_registry/resolve.py` + `strata.py` — the read side, no AI.
6. `vertical_coverage.py` — the ledger and why it's keyed the way it is.
7. `compliance_evals/scoring.py` — what "ready" means.

The docstrings in this subsystem are unusually load-bearing: most of them record a
specific bug that shipped and the reason the current shape is what it is. Read them
before changing behaviour, not after.
