# The Codification System — How It Works & The Path to Full Coverage

_How the compliance/jurisdictional engine turns raw law into a business-consumable
catalog, and the plan to codify every regulation an employer is responsible for._

Companion docs: `COMPLIANCE_GAP_ANALYSIS.md` (audit + implementation blueprint),
`EVAL_SYSTEM.md` (the measurement layer), `docs/architecture/scope-registry-codification.md`
(deep pipeline reference).

---

## 1. The core idea

A business reads its obligations from **one table: `jurisdiction_requirements`** (the
catalog). Each row is a single obligation — a value ($7.25/hr), a citation (29 U.S.C.
§ 206), an effective date, a penalty, an applicability rule — for one jurisdiction.

Everything else in the system exists to get **correct, current, provenance-backed
rows into that table** and keep them there. The unit of "done" is a **codified row**:
a real obligation, bound to the statute it comes from, carrying a grounded value.

**Codification is what makes a row trustworthy.** It is the durable binding

```
authority section   ↔   obligation key        ↔   catalog row
(29 U.S.C. § 207)       (daily_weekly_overtime)    (1.5×, cited, penalty ≤ $2,414)
```

- **Isomorphism** — one statute section ↔ one keyed obligation ↔ one catalog row.
  An uncodified item is floating statute text with no row; there is nothing for a
  business to read and nothing for an update to attach to.
- **Idempotency** — the obligation **key** is the row's stable identity, so
  re-researching an obligation UPDATES the same row instead of spawning a duplicate,
  and a change in the law diffs against the same key. Without codification (no key,
  no row), every re-run would create orphans. Codification is precisely what buys
  both properties.

---

## 2. The pipeline — raw law → codified row

Authority (statutes/regs) flows through the **scope registry** (`server/app/core/services/scope_registry/`)
in stages. Each stage is a table + a gate; a row only advances when the prior gate passes.

```
INGEST ─▶ CLASSIFY ─▶ CONFIRM ─▶ KEY ─▶ RESEARCH (fetch queue) ─▶ CODIFY ─▶ (RECONCILE / DRIFT)
  │           │           │        │            │                     │
authority   authority   human    reg-       grounded value      scope_codifications
_index_     _item_      verifies  key        from body_text      → jurisdiction_
items       classifi-   the tag   bound      + citation gate       requirements row
(body_text) cations                          (grounded.py)
```

| Stage | What happens | Table | Gate to advance |
|---|---|---|---|
| **Ingest / enumerate** | Pull official section structure + `body_text` from eCFR (live API) or a curated statute list | `authority_indexes`, `authority_index_items` | text fetched |
| **Classify** | AI assigns **applicability**: `universal_in_domain` / `category_specific` / `conditional` / `excluded` (+ industry tags, sub-jurisdiction scope, trigger conditions). *This is "does it apply, to whom" — NOT a value.* | `authority_item_classifications` | disposition set |
| **Confirm** | A human reviews the AI classification (provisional until confirmed) | `…classifications.confirmed_at` | admin confirms |
| **Key** | Bind the classification to a `regulation_key` (our obligation vocabulary) | `…classifications.regulation_key` / `key_definition_id` → `regulation_key_definitions` | key assigned |
| **Research (fetch queue)** | For a keyed obligation with no value yet, AI extracts the value **from the fetched `body_text`**, citation-gated (Gemini is a *locator*, never a source) | writes `jurisdiction_requirements` w/ `metadata.grounding='grounded'` | value grounded |
| **Codify** | Record the key-precise join classification ↔ catalog row | `scope_codifications` | key match |
| **Reconcile / drift** | Re-ingest diffs against enumerated items; changes flag the codified row `needs_review` | `authority_index_drift` | on re-ingest |

### The UI states (Scope Studio, per jurisdiction)
- **enumerated** — section ingested, text present.
- **classified** — applicability decided.
- **awaiting confirm** — classified, not yet human-verified.
- **to fetch** — confirmed + keyed, value not yet researched → the **fetch queue**.
- **codified** — the payoff: keyed + grounded value + join recorded.

### Worked example — US Federal today
```
334 sections enumerated & classified   (213 universal, 78 conditional, 36 category, 7 excluded)
  → ~11 keyed                          ← the bottleneck (AI deliberately under-keys)
     → 5 codified                      ← exempt-salary ×2, injury recordkeeping, min wage, overtime
27 to fetch · 240 awaiting confirm
```
The funnel narrows at **keying then value research**, not classification.

---

## 3. What we do NOT codify (and why "5" is a floor, not a target)

**334 enumerated sections ≠ 334 catalog rows.** Most sections are *mechanics of one
obligation*: `29 CFR 1904.10` (hearing loss), `.11` (TB), `.30` (multiple
establishments), `.33` (retention) are all sub-clauses of **one** obligation —
injury recordkeeping. Codifying each as its own row is noise a business can't act on.

The codification **target** is the set of **distinct obligations an employer is
responsible for** — the **baseline master-list**
(`server/app/core/services/compliance_evals/baseline_masterlist.py`): ~27 federal +
~23 CA general-employer labor obligations, each individually cited. That list is the
denominator. "5 codified" means **4/27 of the federal baseline = ~15% done**, not
"done." The enumerated corpus above and beyond the master-list still earns its keep:

- it is the **grounding source** — a value is only trusted if it appears in the
  fetched `body_text` (anti-hallucination), so the corpus is read even before codification;
- classifications are **reusable applicability verdicts** for when we do codify;
- re-ingest **drift detection** runs against enumerated items.

But a tenant at `/app/compliance` sees **only codified rows**. For business value,
only codified counts.

---

## 4. The measurement layer — how we know coverage & correctness

The eval suites (`server/app/core/services/compliance_evals/`, admin UI:
Compliance Library → Evals) measure the catalog **read-only**. "Unmeasured" always
scores `null`, never 100.

| Suite | Answers | Gates |
|---|---|---|
| **baseline** | "Is the federal / CA-state base layer done?" — base jurisdiction's own rows vs the master-list | own scorecard (does NOT block per-company readiness) |
| **completeness** | Per (jurisdiction × industry): fraction of expected obligations present (via the inherited chain) | onboarding-readiness gate |
| **grounding** | Does each grounded value actually appear in its cited statute text? tier-1 string check + tier-2a golden cross-check + tier-2b adversarial LLM verifier | critical findings block readiness |
| **golden** | Does the catalog match hand-verified ground-truth facts? | critical findings block readiness |
| **authority** | Are the cited source URLs live + primary-source? | scored |
| **tagging** | Key/category integrity; untagged industry-specific rows | structural findings |
| **scope** | Scope-registry coverage: classified-but-uncodified backlog | findings + totals |

The **baseline suite is the codification scoreboard**: it turns "only 5 codified"
into a tracked percentage per base layer, and every miss carries the citation to
research next.

---

## 5. The plan — codify every regulation an employer owes

Dependency-ordered; each phase stacks on the prior. Detail + file targets in
`COMPLIANCE_GAP_ANALYSIS.md` Part II.

### Phase 1 — Define "done" ✅ (shipped)
Enumerated, cited **master-list** of federal + CA-state labor obligations + a
`baseline` eval scoring the base jurisdictions against it directly. Makes "is
federal done?" a number (federal 4/27, CA 22/23 today).

### Phase 2 — Fill the federal base layer (next)
Drive the ~23 remaining federal baseline obligations through the pipeline:
add authority sources (eCFR parts + a `curated_us` statute list for USC-only laws:
Title VII, ADA, WARN, I-9, COBRA, NLRA, USERRA, FCRA…) → classify → confirm → key →
grounded research → codify. Baseline climbs 4/27 → 27/27; grounding verifies every
new value; add golden facts for the highest-stakes numbers (FMLA 50/12wk, WARN
60-day/100, OT 1.5×/40).

### Phase 3 — Local jurisdictions + industry keysets (the on-ramp)
Make "add San Diego" possible without code: DB-backed curated authority sources so a
new city/county enters Scope Studio like federal/CA do, + per-industry core keysets
(e.g. food-service) so coverage is measurable per tenant type. Then repeat the Phase-2
pipeline per new jurisdiction.

### Phase 4 — Keep it current (freshness)
Turn on the scheduled loop and wire discovery: legislation-watch + eCFR re-ingest
drift **propose** new/changed obligations into a review queue (human-gated → grounded
research → codify), plus a global catalog changelog. New law becomes new codified
rows without a human hand-running research each time.

### Phase 5 — Serve it correctly (roster mapping)
Headcount/attribute gating (FMLA-50 class), industry-tag hygiene, surface
"applicable-but-not-yet-codified" to tenants, view consistency — so what a business
sees is exactly what applies to it.

### The steady state
Every regulation an employer is responsible for exists as a **codified row**:
grounded value, live citation, penalty, applicability rule — bound to its statute
(isomorphic) and updated in place as the law changes (idempotent). The baseline +
completeness evals stay green because the fill + freshness loops keep them green. The
scope registry's enumerated corpus keeps growing as new authority is ingested; the
codified subset grows to cover every *distinct obligation* that corpus implies —
never every sub-clause, always every obligation.

---

## 6. Where things live (quick map)

- Pipeline engine: `server/app/core/services/scope_registry/` (`authority_ingest`, `classify`, `codify`, `resolve`, `grounded`, `authority_sources`, `curated_ca`)
- Catalog: `jurisdiction_requirements` table; reads via `core/services/compliance_service.py`
- Obligation vocabulary: `server/app/core/compliance_registry.py` (`EXPECTED_REGULATION_KEYS`, `regulation_key_definitions`)
- Codification target: `compliance_evals/baseline_masterlist.py`
- Measurement: `compliance_evals/` (baseline, completeness, grounding, golden, authority, tagging, scope)
- Admin surfaces: Scope Studio (`pages/admin/ScopeStudio.tsx`), Compliance Library (`pages/admin/JurisdictionData.tsx` → Evals), Gap Analysis (`pages/admin/GapDashboard.tsx`)
