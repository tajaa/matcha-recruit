# Tenant-triggered vertical coverage: auto-scope any US industry, once, for everyone

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
  both `final_pay` and `pay_frequency`) — a separate identity bug.
- `expiration_date` is still absent from `RequirementResponse`.
- Backfilling verticals for existing tenants (they fill on their next check).
