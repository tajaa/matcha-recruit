# Tenant-triggered vertical coverage: auto-scope any US industry, once, for everyone

> **STATUS: implemented 2026-07-14.** Migration `vertcov01`,
> `server/app/core/services/vertical_coverage.py`, and the vertical phase in
> `matcha_x_onboarding.py` `POST /build/stream`. Verified end-to-end on dev —
> see "Results" at the bottom. Two bugs found while verifying (a hardcoded
> category vocabulary and a top-level industry tag shape) are written up there;
> both were silent, and both would have shipped a catalog full of wage law
> mislabelled as dental.

## Context

The product promises to scope *any* US company. Driving a real LA dental office
through it end-to-end showed it only scopes verticals someone hand-fed it.

Today's committed fixes (`3eb777e`, `d13d095`, `6ee1700`, plus uncommitted
chain-projection + trigger-decode work) fixed **reachability**: the catalog was
63% misparented, the tenant projection synced one research pass instead of the
jurisdiction-chain union, and `trigger_conditions` was multi-encoded so it failed
open. An LA dental office now correctly sees LA minimum wage, CA overtime, OSHA
bloodborne pathogens, HIPAA.

It still sees **nothing dental**, for one structural reason:

**Coverage is remembered per jurisdiction, never per industry.**
`_is_jurisdiction_fresh` (compliance_service.py:1321) keys on
`jurisdictions.last_verified_at` alone. Once Los Angeles is verified — by
anybody, in any industry — every later company reads "fresh" and never triggers
research. The first tenant in a city freezes the catalog for everyone after.
Result: every industry-tagged row in the catalog is healthcare (309 `healthcare`
+ 10 hand-seeded sub-verticals); **zero** rows for retail, hospitality,
construction, manufacturing, and none for dental.

### The engine already exists — it is admin-manual and has no memory

Do not rebuild these. Reuse them:

- `industry_specialties.discover(parent_industry, name)` (industry_specialties.py:128)
  → Gemini derives the 5–15 categories a vertical needs beyond its parent's
  baseline, plus a reusable `research_context` paragraph. `confirm()` (:159)
  commits them to `compliance_categories` tagged `healthcare:dental`,
  transactionally and idempotently. The `industry_specialties` table already
  holds `oncology`, `pharmacy`, `behavioral_health`… and **no dental**.
- `research_specialization_for_jurisdiction(conn, jurisdiction_id, categories,
  industry_tag, industry_context=…)` (compliance_service.py:9575)
  → researches a (jurisdiction × industry × categories) slice, grounds it,
  force-tags `applicable_industries=[industry_tag]` (:9701), and upserts. Derives
  `is_federal` automatically, so federal/state/city slices all work.
- `corpus_for_jurisdiction` (scope_registry/research_loop.py:56) for grounding.
- An admin SSE endpoint (`routes/admin.py:7735 run_specialization_research`)
  already chains discover → confirm → research.

**What is missing is only two things:**
1. **Tenants cannot trigger it.** The onboarding build never calls any of it.
   Facility inference correctly detects `entity_type = "Dental Practice"` and the
   detection is dropped on the floor — nothing downstream consumes it.
2. **There is no coverage ledger.** `research_specialization_for_jurisdiction`
   infers coverage with `skip_existing` — "are there rows tagged `healthcare:dental`
   in this jurisdiction for this category?" (:9647). That cannot distinguish
   *never researched* from *researched, genuinely nothing to find*, and cannot
   record a failure. So empty cells are re-researched forever and the loop never
   converges.

The catalog is tenant-independent. A dental office in LA *triggers* a fill; the
result is shared, so every later dental office in that jurisdiction reads it
instantly with zero Gemini calls. That reuse is the entire point.

## Design

### 1. Migration `vertcov01` — the ledger

`jurisdiction_vertical_coverage`:
`(jurisdiction_id, industry_tag, category)` **UNIQUE**, plus `status`
(`pending` | `in_progress` | `covered` | `empty` | `failed`),
`requirements_written` INT, `error` TEXT, `requested_by_company_id`, timestamps.

`empty` is distinct from `failed` on purpose: "we researched CA × dental ×
`chemotherapy_handling` and there genuinely is nothing" must never be
re-researched. `failed` retries; `empty` does not. This is the piece
`skip_existing` structurally cannot express.

Keyed on `jurisdiction_id`, so federal dental research runs **once nationally**
and state once per state — chain reuse falls out for free.

### 2. `server/app/core/services/vertical_coverage.py` (new, thin)

- `resolve_vertical(conn, company_id, location)` → `(parent_industry, label,
  industry_tag)`. Most-specific tag from `_get_company_industry_tags` (:115),
  falling back to the detected `facility_attributes.entity_type`.
  **Also persist the specialty onto `companies.healthcare_specialties` if absent** —
  otherwise `_filter_requirements_for_company` (:3140) drops the rows we just
  wrote, because the company doesn't carry the tag they're tagged with.
- `ensure_specialty(conn, parent, label)` → if no `industry_specialties` row or no
  categories tagged, call `discover()` + `confirm()` (`discovered_by='auto'`).
  Returns `(categories, research_context)`. Without this, `expand_scope` and the
  research path silently return **zero** dental categories: `compliance_categories`
  is a hard post-filter (onboarding_scope_ai.py:561), which is exactly why dental
  produces nothing today.
- `missing_cells(conn, chain_jurisdiction_ids, industry_tag, categories)` → ledger diff.
- `fill(conn, company_id, cells, industry_tag, research_context)` → async generator.
  Per cell: mark `in_progress` → `corpus_for_jurisdiction` →
  `research_specialization_for_jurisdiction(..., skip_existing=False)` (the ledger
  now owns that decision) → mark `covered` / `empty` / `failed` with counts.

### 3. Wire into the onboarding build (synchronous, per the chosen UX)

`matcha_x_onboarding.py` `POST /build/stream`: insert a phase after the roster
union (**:517**) and before the terminal `complete` (**:635**), where
`jurisdictions_seen`, `industry`, and the `total_codified`/`total_covered`
counters (:385-386) are all in scope. Emit `vertical_scoping` /
`vertical_researching` / `vertical_codified`; add `vertical` +
`vertical_requirements_added` to the `complete` payload.

The SSE `type` is a plain string and `Step4Build.tsx:eventStyle` has a graceful
`default` case — **new event types need no frontend change** to render. A
first-class icon is a one-line `switch` addition, optional.

Then re-project the affected locations (`_project_chain_to_location` +
`_sync_requirements_to_location`) so the new rows land on the tab in the same
build.

### 4. Serving — no change

The chain projection + industry filter + trigger evaluation fixed earlier today
surface the new rows automatically, for this tenant and every future one.

## Guards

- **Never blanket-tag.** `applicable_industries` is a Postgres `TEXT[]` whose
  ON-CONFLICT unions, and `_filter_requirements_for_company` drops rows whose tags
  don't intersect the company's. Tagging generic labor rows `healthcare:dental`
  would hide them from every non-dental tenant in the jurisdiction — poisoning the
  shared catalog. Only the specialization pass's own output is tagged, which
  `research_specialization_for_jurisdiction` already does correctly.
- Cap cells per build; `log()` what was skipped. Silent truncation reads as
  "covered everything".
- Ungrounded rows stay quarantined by the existing grounding gate.
- The 5 hardcoded `TRIGGER_PROFILES` keep working exactly as today.

## Verification

1. **Dental fill** — the demo tenant's build creates an `industry_specialties`
   row for dental, dental categories in `compliance_categories`, ledger rows for
   (Federal | California | LA) × `healthcare:dental` × N, and catalog rows tagged
   `healthcare:dental`. The Compliance tab shows dental-specific obligations
   (Dental Practice Act, Dental Board licensure/CE, radiation-machine
   registration, infection control, amalgam separator).
2. **Reuse — the whole point.** Create a *second* LA dental office. Its build
   finds every cell `covered`, makes **zero** Gemini calls, and its tab is
   identical and instant. Assert the research-call count is 0.
3. **Generalization — the real test of the claim.** Create a *hospitality*
   company in Austin, TX. The vertical is discovered, confirmed, researched, and
   hospitality rows appear. Nothing in the path is healthcare-specific.
4. **No regression** — `pytest tests/scope_registry tests/compliance
   tests/compliance_evals` (baseline: 7 pre-existing failures) and `tsc --noEmit`.
5. **Re-drive the product by hand** and read every served row. Every bug found
   today was found that way, and none by a test.

## Out of scope (named, not silently skipped)

- Entity/facility *triggers* for new verticals (e.g. dental sedation permit)
  still need `TRIGGER_PROFILES` entries; that tuple is frozen in code and has 3
  consumers. Industry *tagging* — which is what scopes dental — does not.
- Cross-category duplicate obligations ("Final Pay Upon Termination" filed under
  both `final_pay` and `pay_frequency`) — a separate identity bug. **Partly
  addressed:** it bit hard inside a vertical (see Results), so the fill now
  guards it at the prompt and dedupes deterministically. The generic labor
  catalog still has it.
- `expiration_date` is still absent from `RequirementResponse`.
- Backfilling verticals for existing tenants (they fill on their next check).

---

# Results — what shipped, and the two bugs verification found

Everything below was found by driving the product, not by a test.

## The vocabulary was hardcoded, and failing meant researching the wrong subject

The first dental fill reported `new: 153` and every SSE event said success. The
153 rows were California **wage law**, tagged `healthcare:dental`.

`_normalize_category_value` (gemini_compliance.py) gated categories on
`CATEGORY_KEYS` — a **frozen constant compiled from `compliance_registry.py`**.
Oncology's categories are baked into it. Dental's, discovered at runtime and
written to `compliance_categories`, are not. So all 7 dental categories
normalized to `None`, and:

```python
for category in categories or DEFAULT_RESEARCH_CATEGORIES:
    normalized = _normalize_category_value(category)   # None, for every one
    if normalized and normalized not in selected_categories:
        selected_categories.append(normalized)
if not selected_categories:
    selected_categories = list(DEFAULT_RESEARCH_CATEGORIES)   # ← the harm
```

The fallback doesn't under-deliver — it researches a **different subject** and
returns it under the caller's label, and
`research_specialization_for_jurisdiction` then force-tags every row with the
vertical's `industry_tag`. A vertical fill that finds nothing is supposed to look
like nothing; this one looked like a success.

Fixed three ways: the vocabulary now unions the DB's `compliance_categories`
(`register_dynamic_categories` / `refresh_dynamic_categories`, called at the top
of the specialty-research path); an explicit category list that fully drops now
returns `[]` and logs an error rather than silently swapping in the default set;
and unknown categories are logged when dropped.

## `hospitality:hospitality` would have been invisible forever

When the vertical IS the industry (a hotel has no sub-specialty above
hospitality), `industry_tag()` produced `hospitality:hospitality` — but
`_get_company_industry_tags` gives such a company the bare tag `hospitality`, and
`_filter_requirements_for_company` intersects the two. Every row researched for
hospitality would have been filtered straight back out of the tab of the company
that triggered the research. `industry_tag()` now collapses `(x, x)` to `x`, and
the discovery prompt has a top-level branch (asking for the industry's own
obligations instead of ones "beyond the {industry} baseline", which was
self-contradictory).

## Duplicate obligations, inside one vertical

`requirement_key` is `<category>:<regulation_key>` — so the **category is part of
an obligation's identity**. The catch-all `dental_practice_act_scope` returned
the entire dental corpus, so radiology, sedation, infection control and amalgam
each landed twice and the tenant saw every dental obligation listed twice.
Guarded at the prompt (each category call now names its siblings and is told not
to return their obligations) and deduped deterministically afterwards
(`_dedupe_by_regulation_key`, which collapses on `regulation_key` **or** on
normalized title — `regulation_key` is model-generated and drifts between runs,
so a key match alone misses re-researched duplicates).

## Verified on dev

1. **Dental fill** — Sunset Smile Dental (LA) triggers discovery of 7 dental
   categories, researches them, gets **12 distinct dental obligations** spanning
   all three levels: EPA Dental Effluent Guidelines (40 CFR 441, federal), CA
   Dental Practice Act / Dental Board sedation permits / CCR Title 16 § 1005
   infection control / CDPH radiation protection program / CURES PDMP (state),
   and an LA County X-ray shielding plan (county). No duplicates.
2. **Reuse — the whole point.** A *second* LA dental office (Westlake Family
   Dental) builds with `vertical_scoping` → straight to `complete`. Every cell
   reads `covered` from the ledger, **zero** Gemini research calls, identical 12
   dental rows on its tab.
3. **Generalization — the real test of the claim.** A *hospitality* company in
   Austin, TX — nothing healthcare anywhere in the path, zero hospitality rows in
   the catalog beforehand — discovers 8 categories from cold (food safety,
   alcohol service liability, lodging fire codes, pool/spa safety, guest data
   privacy, tip pooling, housekeeping ergonomics, ADA public accommodation) and
   researches Texas Dram Shop Act, TABC, TFER 25 TAC 228, Austin Fire Code, TX
   pool/spa 25 TAC § 265, TDPSA, ADA Title III, FLSA tip pooling. **Zero**
   hospitality rows leaked onto the dental tenant.
4. **No regression** — 756 passing, the same 7 pre-existing failures.

## Still open

- The vertical fill runs only in the **Matcha-X onboarding build**. The periodic
  `compliance_checks` worker and `run_compliance_check_stream` do not trigger it,
  so an existing tenant fills on its next *onboarding* build, not its next check.
- `MAX_CELLS_PER_FILL = 40` caps one build. A vertical with more
  (jurisdiction × category) cells than that fills over successive builds; the
  skipped remainder is not yet surfaced to the user.
- `in_progress` is not self-healing: a crashed fill leaves the cell wedged and a
  later build will not retry it. Deliberate (never double-bill a research call),
  but it needs a sweeper.
- The "no additional rule applies" filler rows the research prompt emits still
  land as real requirements (e.g. "No State-Specific Housekeeping Ergonomics
  Mandate"). They are honest, but they are noise on the tab.
- `vertcov01` is **dev-applied only** — it must run on prod, alongside the still
  un-applied `jparent01` / `jsonfix01` / `rekey01` / `rekey02`.
