# One Compliance System — how the admin surfaces connect

**Thesis.** Matcha has *one* compliance/regulatory system, not three. Three admin
surfaces author and audit it from different angles, but they read and write **one
library** (`jurisdiction_requirements`) through **one taxonomy** (`compliance_categories`),
and the scope registry (`SCOPE_REGISTRY_PLAN.md`) is the engine that decides what a given
business is liable for. This doc is the map — what is already shared, what is
disconnected, and the target shape.

> Companion docs: `SCOPE_REGISTRY_PLAN.md` (the authority-anchored scoping engine),
> `EVAL_SYSTEM.md` (the catalog audit layer).

---

## The one thing to internalize

**"General regulatory library" and "specialization scope" are not separate stores. They
are the untagged vs. tagged rows of the same table.**

`jurisdiction_requirements` (`database.py:3007`) holds every codified obligation — federal
minimum wage, Cal/OSHA IIPP, an oncology radiation-safety rule — in one table. The only
thing separating "universal, every business needs it" from "specialization overlay" is one
column:

- `applicable_industries TEXT[]` **empty/NULL** ⇒ **general** — every company sees it.
- `applicable_industries = {healthcare:oncology}` ⇒ **specialization overlay** — only
  matching companies see it.

`_filter_requirements_for_company` (`compliance_service.py:2698`) is the exact boundary: a
read-time set-intersection of the row's industry tags against the company's tags. Untagged
rows pass to everyone; tagged rows only to matching industries.

So the general↔specialization split is **one column + one filter**, not two systems.

---

## The three surfaces

### 1. `/admin/jurisdiction-data` — the Library (keep as-is)

The regulatory **library manager**. Ten tabs (`JurisdictionData.tsx:27`): explorer,
policies, quality, **evals**, key-index, integrity, penalties, preemption, api-sources,
bookmarks.

- **Holds** the universal corpus (untagged rows: federal/state/city labor, OSHA, minimum
  wage, …).
- **Keeps it current** — the single catalog writer `_upsert_requirements_additive`
  (`compliance_service.py:1624`) is fed by Gemini research passes + the eCFR /
  government-API orchestrator; `structured_data_fetch`, `legislation_watch`, and
  `compliance_checks` workers supply upstream Tier-1 data and early-warning signals.
  `applicable_industries` is merged **additively** — a healthcare pass can't strip a labor
  tag.
- **Measures it** — the `compliance_evals` suite (`EVAL_SYSTEM.md`) is read-only over the
  catalog and scores completeness / authority / tagging / accuracy(golden) / freshness,
  gating onboarding readiness.

This surface is already the "what we've stored, is it correct/current?" layer. **No
conceptual change** — it just gains visibility into the scope registry's *authority
indexes* (the enumerable backbone of what law exists), see target-state §A.

### 2 + 3. `/admin/industry-requirements` and `/admin/specialization-research` — two halves of one lifecycle

These are **not two features**. They are the front and back of a single specialization
lifecycle, sharing the same Gemini core (`discover_specialization_categories`,
`compliance_service.py:8906`) through two different wrappers — and they don't connect:

| Step | `/admin/industry-requirements` | `/admin/specialization-research` |
|---|---|---|
| **derive** categories for a specialty | ✅ (via `industry_specialties.discover`) | ✅ (calls the core directly) |
| **persist scope** (empty categories = the *to-codify* worklist) | ✅ `industry_specialties.confirm` | ❌ |
| **research** values into the library | ❌ | ✅ writes `jurisdiction_requirements` tagged with the `industry_tag` |

The disconnect: an admin derives categories on one page, then **re-derives and re-enters**
on the other to research them. The "to codify" gap the matrix computes is exactly the
research page's input — but there is no wire, and the two pages even use different industry
vocabularies and specialty lists (one DB-derived, one a static `HEALTHCARE_SPECIALTIES`
constant).

---

## How a company actually gets its compliance today

```
compliance_categories (taxonomy of KINDS)
      │  expand_scope: one Gemini call names category slugs   onboarding_scope_ai.py:307
      ▼
jurisdiction_requirements (the library)   ──regulation_key──▶ regulation_key_definitions (dormant)
      │  map_to_bank: grab EVERY row in the scoped categories × jurisdictions   :571
      ▼  {existing: [requirement_id, …]}
compliance_requirements (per-company projection, location-keyed)   admin_onboarding.py:219
      │  read time: _filter_requirements_for_company (industry-tag intersection)   :2698
      ▼
what the company sees at /app/compliance
```

This works but is **per-session, uncached, uncited, category-granular** — the second LA
manufacturer pays for a fresh Gemini call and may get a different answer, and nothing says
*why* a category is in scope. That is the problem the scope registry exists to solve.

---

## Target architecture — one system, two authoring surfaces, one engine

Nothing is torn down. The wiring is the work.

### A. The Library — `/admin/jurisdiction-data` (keep + surface authority)

The stored corpus: the universal baseline **plus** the scope registry's **authority
indexes** (`authority_indexes` / `authority_index_items` — the enumerable eCFR + curated CA
backbone of *what law exists*). Evals stay here. Add an authority-index view so "what
exists" sits beside "what we've codified."

### B. The Scope Studio — merge surfaces 2 + 3 into one page

One continuous flow for a `business-category × jurisdiction` coordinate:

1. **Pick coordinate** — industry/specialty (one canonical vocabulary,
   `scope_registry/categories.py`) + jurisdiction chain.
2. **Derive / resolve scope** — the shared discover core for a *new* specialty (persist via
   `industry_specialties.confirm`); `resolve_scope` for the applicable set once the engine
   is authoritative.
3. **See the matrix** — applicable / codified / **to-codify gap** (the fetch-queue).
4. **Research the gap inline** — the existing `specialization-research/run` SSE loop, driven
   by the **confirmed to-codify worklist** instead of a re-derived list. Values land in the
   same library, tagged.

Derive-once, scope-once, research-the-gap — no re-entry across two pages.

### C. The Engine — the scope registry (`SCOPE_REGISTRY_PLAN.md`)

Makes the general↔specialization split **structural** instead of a string tag:

- **universal strata** (federal×ALL, state×ALL) = the general baseline.
- **category-specific strata** = the specialization overlay.
- **fetch-queue** (applicable-but-uncodified) = the "to codify" worklist the Scope Studio
  shows and the research pass fills.

`resolve_scope` becomes the **one** definition of "what does business X in jurisdiction Y
need," read by both the runtime (onboarding, replacing `expand_scope → map_to_bank`) and
the Scope Studio matrix. `applicable` = strata resolution; `codified` = the library; the
delta = the worklist. It joins back into the existing library through the shared
`regulation_key`, and populates the dormant `regulation_key_definitions` applicability
columns as derivation hints from confirmed classifications.

---

## The layers, named

| Layer | Table(s) | Role | Where industry tagging lives |
|---|---|---|---|
| **Library** | `jurisdiction_requirements` | codified obligation values | per-row `applicable_industries` (the live seam) |
| **Taxonomy** | `compliance_categories` + `regulation_key_definitions` | kinds of compliance + per-key contract | `compliance_categories.industry_tag`; RKD applicability cols (dormant) |
| **Per-company** | `compliance_requirements` | tenant projection | none — filtered at read time |
| **Engine** | `business_categories` + `authority_*` + `scope_strata` | authority-anchored, structural scope | `business_categories` (canonical, hierarchical) + `applies_to`/`excludes` on classifications |

---

## Build sequence

Engine-first (decided), each its own commit, this PR's line of work:

1. **Commit 4** — `classify.py` (Gemini pre-classification at subpart level), `seed.py`,
   `recompute_strata()`, `resolve_scope()`, + endpoints (fetch-queue, resolve-preview, and
   the Library authority read views). This is where scope becomes queryable.
2. **Commit 5** — shadow `resolve_scope` alongside the live `expand_scope` on onboarding
   finalize (`expand_scope` stays authoritative; diff logged to `scope_shadow_log`).
3. **Commit 6** — eval `scope` suite + repoint `completeness` at resolved scope, and merge
   `/admin/industry-requirements` + `/admin/specialization-research` into the **Scope
   Studio**.

Prereqs already merged (PR #26): the canonical taxonomy (`categories.py`), the `scoperg01`
schema, and authority ingest (eCFR + curated CA).
