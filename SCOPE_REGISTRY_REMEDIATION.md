# Scope-Registry Remediation — what shipped, what it fixed, what's still open

_Work log for the 8 commits `c4f1ab6..c5b8c2b` (merged to `main`). Companion to
`COMPLIANCE_SYSTEM_GAP_REVIEW.md`, which is the audit this executes against —
read that first for the system's state; read this for what changed and why._

**One-line summary:** the codification engine was built end-to-end but inert —
never authoritative, minting zero rows, measured by nothing. It now runs, guards
its own correctness, and is drivable from the UI. Along the way, **the review's
own fixes turned out to contain a critical self-reverting bug, and the engine
was writing false legal citations to customers** — both found by *running* the
thing, not by reading it.

---

## The headline: what actually running it found

Three defects were invisible to the code-only audit, to the eval suites, and to
`tsc`. Each was writing wrong data to a customer-visible field.

### 1. Cross-country citations (found: driving reconcile the first time)

`reconcile` matched classifications to catalog rows on `regulation_key` alone.
Registry keys are a *global* vocabulary — `national_minimum_wage` is as true of
the UK as of the US — so the US federal FLSA citation `29 U.S.C. § 206` was
stamped onto **"UK National Living Wage"**, Mexico's **ZLFN border-zone wage**,
and French/Singaporean working-hours rows. A statute with no force in those
countries, presented as their legal basis.

The existing jurisdiction guard couldn't catch it: it guards *states*, and those
rows have no state. Its docstring said "federal law applies everywhere" — true,
but *everywhere* means everywhere **in the United States**.

→ Country guard added to `match_codifications`. 6 bogus stamps cleared from dev.

### 2. Cross-*level* citations — the same bug, one level down (found: driving the tenant read path)

Same root cause, and worse because it was invisible until you looked at values:

| Jurisdiction | Value | What reconcile stamped |
|---|---|---|
| Texas | `$684.00/week` | `29 CFR § 541.600` — **correct**, is the FLSA figure |
| **California** | **`$70,304/year`** | `29 CFR § 541.600` — **false**, that's CA law |
| **New York** | **`$1,275/week`** | `29 CFR § 541.600` — **false**, that's NY law |

We were telling a customer their $70,304 California obligation came from a
federal reg that says $684. **All 51** federal→non-federal stamps had this shape.

The fix is the user's model: **reconcile with jurisdictional logic, store both
circumstances, set precedence where it applies.**

* **direct** → `statute_citation`. The authority *is* this row's operative law:
  same level (a CA code section on a CA row), **or** a higher level whose value
  the row **restates verbatim** (TX's $684 *is* the FLSA floor, so the federal
  cite genuinely is its statute).
* **baseline** → `metadata.jurisdictional_basis`. The authority sits above and
  the row sets its **own** value. The relation is real and worth keeping (CA
  must meet or exceed the federal floor) — it just isn't CA's statute.
  Precedence is explicit in the record: **the row's own jurisdiction governs;
  the cited authority is the floor.**

Restatement test = `numeric_value` first, then normalized text, against the
authority-level row for that key. **No basis codified ⇒ baseline, never a
guessed stamp** — a wrong citation is worse than none.

Surfaced to the customer as a floor chip, so we *gained* signal rather than just
deleting citations. Live: 49 false stamps demoted, AZ/FL keep the ones they
genuinely restate.

### 3. The `unclassified_count` fix was silently self-reverting (found: adversarial review)

The original fix made "unclassified" mean *"has no **confirmed** classification"*
— closing a hole where a Gemini-classified-but-unconfirmed index read as fully
classified, opening the completeness gate on a shrunken denominator (the one
place in the system that fails toward the score **lying high** rather than going
dark).

But **three** code paths write that column and only one was fixed.
`strata.py`'s bulk refresh runs on **every admin confirm**; `authority_ingest._recount`
runs on **every ingest**. Both still used the any-row predicate — so the first
confirm would rewrite the column and re-open the exact hole.

The earlier end-to-end run missed it because it confirmed *once* and read the
count *before* strata's refresh landed.

→ All three writers agree. The test asserts the filter lives in the JOIN's `ON`
clause (in the `WHERE` it inverts the count to 0) and **fails if any writer
drifts back** — verified by reverting `strata.py` and watching it go red.

---

## What shipped

| Commit | What |
|---|---|
| `c4f1ab6` | **P0 correctness** — arbitrary `category_id` fallback (×2), `unclassified_count`, citations on the flat surface, grounding provenance, decorative cache, dead-table docstring |
| `75cc7c1` | **Engine wiring** — headless grounded research→reconcile loop, ungrounded quarantine, shadow→cutover gate, `'new'`-drift classify dispatch, specialty research grounded |
| `c544aca` | **Eval fixes** — golden chain inheritance, federal criticals gate readiness, scope subscore, partial-verdict overlay |
| `d9d8c03` | **Cockpit UI** + cross-country citation fix |
| `ca9e7e5` | Doc: cross-country bug into the gap review |
| `5fb91c1` | **Review findings** — 1 critical, 4 high, 5 medium (see below) |
| `ed0929a` | **Jurisdictional logic** — direct vs. floor, store both circumstances |
| `c5b8c2b` | `scope_codifications.source` widened — `VARCHAR(20)` was a tripwire |

### The engine can now grow the library

* **Headless loop** (`scope_registry.research_cycle`): `chain_uncodified` →
  group → prefetch statute bodies → **grounded** research → reconcile, per
  configured chain (federal+CA, capped 5 units/cycle). Gated on a
  seeded-**disabled** scheduler row (`scoperg02`).
* **Ungrounded quarantine**: a req that *was* given fetched statute text and
  still failed to cite it lands `status='under_review'` — narrower than "any
  ungrounded row", so the legacy ungrounded-by-design paths are untouched.
  `_load_jurisdiction_requirements` (the single choke point every tenant-sync
  and gap-detection read goes through) excludes it, so it reads as a **gap to
  re-research**, never as served coverage.
* **Cutover**: `cutover.py` unions engine-definitive keys into the bank
  projection for an allowlisted `(state, industry)` set — **additive only**.
  The shadow diff still compares against the **pre-union** set, so a cut-over
  coordinate can't inflate the agreement rate that's supposed to justify
  widening the allowlist.

### The pipeline is drivable from the UI

`AuthorityCockpit` surfaces the 12 previously curl-only endpoints: index list +
confirm funnel, Ingest/Classify, confirm queue, strata, Reconcile, shadow-log
with agreement rollup. Previously the empty state told the operator to go run a
Python script, and since classify only ever writes `provisional` while every
engine read filters `confirmed`, **the registry could never leave the empty
state from inside the app.**

> The confirm queue needed a backend change to work at all: `classified=false`
> means *"no classification row at all"*, so it was blind to provisional rows.
> Verified live — with 4 provisional classifications waiting, `classified=false`
> returned **0 items**, `confirmed=false` returned **4**.

---

## Review findings fixed in `5fb91c1`

A 4-lane adversarial review of the branch found 12 real defects, several **in the
fixes themselves**:

* **CRITICAL** — `unclassified_count` self-reverting (above).
* **HIGH** — the category guard was **dropping legitimate rows**. 10 registry
  categories have no `compliance_categories` seed row (verified on dev:
  `pay_transparency`, `drug_testing`, `non_compete`, `whistleblower` — *all four
  in the default research sweep* — plus 6 life-sciences). Skipping them meant
  every research result in those categories silently vanished. Now parked on the
  `uncategorized` sentinel (never an arbitrary row — the original bug), and the
  upsert **forward-repairs** a mis-tagged `category_id` once the seed lands.
* **HIGH** — **quarantine was a one-way trap.** `under_review` was terminal: a
  re-research that *passed* grounding left the row quarantined, while
  `chain_uncodified`/`reconcile` both skip non-active rows — so the key stayed
  on the research worklist and **re-burned live Gemini every scheduled cycle,
  forever.** Grounding verdicts now move status both ways (quarantine / promote
  / leave alone), and the cycle guards its own cadence off
  `scheduler_settings.last_run_at`.
* **HIGH** — **rejected values were served to tenants.** `/under-review/decide`
  sets `repealed`, but the tenant read path only excluded `under_review` — so an
  admin's explicit *"this value is wrong"* put it straight back into coverage.
  Also: re-research can no longer overwrite a `repealed` row (it exists only as
  an audit trail), and the id-keyed finalize projection no longer bypasses the
  choke point.
* **HIGH** — the **live readiness endpoint** still dropped federal `NULL`
  criticals, so it contradicted the stored run it mirrors (run: `NOT_READY`,
  live: `READY`, same broken federal baseline). Also omitted the scope subscore.
* **MEDIUM** — specialty-research grounding was a **silent no-op**:
  `corpus_for_jurisdiction` went through `chain_uncodified`, whose `labor_only`
  default drops the very `licensed_professions` index a specialty pass is about,
  and which returns only the *uncodified* worklist (so a section's text vanished
  from the corpus the moment its key codified).
* **MEDIUM** — golden chain-inheritance rolled federal facts up **without
  pinning country**, so the first non-US national fixture would inherit UK facts
  into every US city.
* **MEDIUM** — `exempt_salary_threshold_regional` was clobbered out of
  `EXPECTED_REGULATION_KEYS` (that dict *replaces* the RegulationDef-derived
  set), so the key minted for the NY re-key would have thrown `invalid_key`
  findings on every row carrying it.
* **MEDIUM** — the `engine_partial` badge rendered over false zeros.

---

## Verification

Everything below was run against the **real dev Postgres**, in rolled-back
transactions where it mutated data — not inferred from tests.

* **Quarantine lifecycle**: failed grounding → quarantined → ordinary
  re-research **stays** quarantined → *passing* grounding **self-heals** to
  active → once rejected, **frozen** (re-research can't overwrite the audit
  trail).
* **Category guard**: unseeded category → **written**, parked on
  `uncategorized`; once seeded → **forward-repairs** its own `category_id`.
* **`unclassified_count`**: 19 provisional classifications stay counted across
  *both* previously-broken writers; confirming 3 drops it to exactly 16.
* **Tenant read path**: `under_review` and `repealed` rows excluded; promoting
  one brings it back.
* **Jurisdictional logic**: CA's `$70,304` no longer claims a federal reg;
  serves `federal floor: 29 CFR § 541.600` as the relation it actually is.
* **`codify03`** applies cleanly (metadata-only `VARCHAR` widen); the 25-char
  label that originally blew up mid-run now inserts.

**Test suite: zero new failures.** Baseline (`f01dd0f`) = 71 failed / 2,476
passed. This work = **58 failed / 2,502 passed** — the same 58, none new. The
13-failure delta is my own regression tests, which fail against the *old* code
and pass against the fix (i.e. they catch the bugs rather than asserting current
behavior). The 8 failures in the touched area were **checked at `f01dd0f` and
fail identically there** — pre-existing (`test_compliance_schema_redesign` globs
for migration filenames that no longer exist, + `test_build_dossier_full`).
`tsc` clean.

---

## Still open

**Migrations are authored, NOT applied.** Heads: `cmpreqdrop01`, `scoperg02`,
`catseed01`, `codify03`. The tree has multiple heads and needs a merge migration
before `alembic upgrade head` can reach them. `catseed01` is the load-bearing
one — until it runs, 4 labor categories in the default research sweep park on
`uncategorized` instead of their own row.

**Gaps deliberately not closed:**

* **No KEY-assignment editor.** `PUT /items/{id}/classification` still has zero
  frontend callers. The cockpit's Key column is display-only; the amber "no key"
  label is the *only* KEY surface, and its tooltip points at a UI that doesn't
  exist. **Unkeyed items remain permanently stalled** — this is the review's own
  HIGH gap and it is still open. Same for the *override* half of the confirm
  queue (no way to correct a wrong Gemini disposition from the UI).
* **No `resolve_scope` §9 acceptance test** — the LA-warehouse → AB701 + 1910.147
  (excludes 1910.119 PSM) case is still asserted nowhere through a real read path.
* **Ingest/Classify are fire-and-forget Celery dispatches** with no completion
  feedback. With no worker running (the dev default) the button 200s and
  **nothing happens, silently**.
* **Collision data re-key** — the 2 registry keys landed
  (`medicaid_provider_enrollment`, `exempt_salary_threshold_regional`) but the
  data migration did not. The live rows have inconsistent `requirement_key`
  composites (`minimum_wage:exempt_salary`, `medi_cal:billing_integrity:...`)
  that `_compute_key_parts` derives from rate_type/title/jurisdiction, one row
  carries a free-text `regulation_key`, and SB 306 spans 16 jurisdictions — a
  title-matched UPDATE would corrupt the upsert identity. **This is the curation
  pass `b694559` explicitly left to a human.**
* **Data authoring** (5 states, city slices, industry keysets, golden facts) —
  the review's #1 priority. Nothing here moves it; it's skills work, not code.
* **Schedulers stay seeded disabled** (`compliance_evals`,
  `scope_registry_research`). Flipping them on is a go-live step, and the
  research cycle **makes live Gemini calls**.

**Worth knowing before judging the feature by what's on screen:** the two direct
citation stamps that survived reconcile (AZ/FL) aren't linked to any tenant
location, so **no customer currently sees a `statute_citation`** — only floor
relations. Correct behavior, but the citation chip is effectively unexercised in
the UI until more authority is codified.

**Sharp edge:** `scope_codifications.source` was `VARCHAR(20)` and
`'scheduled_research'` is 18 — two characters of slack. Overflowing it raises
`StringDataRightTruncationError` *inside* the reconcile transaction, rolling back
every link and citation stamp the run computed. `codify03` widens it to 64 and
the code clamps + warns; a test pins the clamp to the migration's width **and**
asserts every shipped label still fits the pre-migration width (since the
migration isn't applied yet).
