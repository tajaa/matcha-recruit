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

## Round 2 — closing the remaining gaps

_Migrations applied. Everything below then shipped in `bc32714..db58da8`._

### The KEY editor — the step that had no UI

`PUT /items/{id}/classification` existed with **zero** frontend callers, so an
item Gemini classified with a NULL `regulation_key` was permanently stalled: no
key means `codify.py` can never match it to a catalog row, and there was no way
to supply one short of curl. The confirm queue could only rubber-stamp Gemini,
never correct it.

* `GET /vocabulary` — dispositions + taxonomy + RKD keys by category. The editor
  cannot exist without it: `validate_proposal` rejects any category slug outside
  the taxonomy and downgrades any key outside the RKD, so a free-text field would
  be a guessing game against a vocabulary the server already knows.
* `ClassificationEditor` — disposition, key-category → regulation-key cascade,
  applies-to/excludes chips, excluded-reason. Lands **confirmed**.

**The editor surfaces the server's warnings instead of swallowing them.** The
gates *downgrade* rather than reject: a key not in the RKD is stored as NULL with
a warning. Swallowing that is the worst possible outcome here — the operator
believes they keyed the item (the entire point) while it stays uncodifiable. My
first live attempt did exactly that, and the UI would have reported success.

Verified: ingested the CA authority slices (52 provisional classifications, 14
keyless incl. AB701 §2100-2105), drove the editor's exact call — `8 CCR § 3395`
is now confirmed + keyed to `heat_illness_prevention` and codifiable.

### §9 acceptance test — through the real SQL

An LA warehouse gets AB 701 + 1910.147 lockout/tagout, and does **not** get
1910.119 PSM. Every prior test asserted this against hand-built dicts via the
pure `classification_matches` helper, so the disposition logic was covered but
the SQL feeding it was not. Seeds its own index in a transaction and rolls back.
Also asserts the conditional *fires* once the facility does hold PSM chemicals
(else the exclusion would pass for the wrong reason), that a non-warehouse
doesn't inherit AB 701, and that provisional classifications contribute nothing.

**It immediately earned its keep.** The fixture had a typo — a leaf saying `op`
where it meant `operator` — and the test caught PSM being served to a warehouse.
Root cause: `_eval_condition` returned `True` for an unrecognized node, silently
turning a **conditional** obligation into a universal one.
`jurisdiction_requirements.trigger_conditions` are written by **Gemini research
with no shape gate** (unlike scope-registry classifications, which
`validate_proposal` rejects), so a plausible model typo was enough to serve the
PSM standard to every company. Now fails closed and logs — the same convention
the function already used for an unevaluable numeric comparison. 110 live rows
carry triggers, **zero** are malformed, so no live behavior changed.

### Collision re-key — the curation `b694559` left to a human

All six resolved. `duplicate_active_obligation` findings: **6 → 0**.

`minimum_wage` was the hard one: it derives its write identity from **rate_type**,
not `regulation_key`, so the key alone cannot separate the NY rows. The new
`exempt_salary_regional` rate-type dialect is what makes them two identities.

`requirement_key` is recomputed by **calling `_compute_key_parts`**, never by
rebuilding the string. Dry-running that caught a corruption before it touched
anything: `applicable_entity_types` comes back as a JSONB *string* on this
driver, so `aet[0]` grabbed the `[` character and would have written the identity
`[:billing_integrity:medicaid_provider_enrollment`.

`rekey02` then healed 3 rows whose **stored** composite no longer matched what
the upsert computes. That matters: a re-key leaving a stale composite re-opens
the collision on the very next research pass, because `ON CONFLICT` matches
nothing and a twin is minted. Both migrations skip-and-report rather than
overwrite when a target identity is taken — collapsing two rows is a *merge*
decision, not a re-key. Applied to dev: 34 re-keyed, 3 healed, 0 skipped,
**identity drift 0**.

### Citations now reach customers

The CA authority is ingested and confirmed, so CA-level authority lands **direct**
stamps on CA rows: 57 operative citations (`Cal. Lab. Code § 512` on the CA meal-
break requirement, etc.), plus the floor relations. The citation chip is no longer
unexercised.

### Two bugs found by driving it

* **Dispatch lied about success.** `.delay()` onto a broker with no worker
  succeeds — the task sits in Redis forever — so Ingest/Classify returned
  "running" and nothing happened. Now reports `worker_online` + a
  `queued_no_worker` status, and the cockpit shows it. (`dev-remote.sh` *does*
  run a worker — as a **process**, not a container, which is why a `docker ps`
  check misses it.)
* **A stateless location 500'd the compliance page.** `_filter_with_preemption`
  called `state.upper()` unguarded; **10 live locations** have a NULL state and
  every one was serving a 500. Pre-existing (`9dbf4e2`), found while verifying
  the citation surface across real tenants.

---

## Still open

* **Data authoring** (5 states, city slices, industry keysets, golden facts) —
  the review's #1 priority. Nothing here moves it; it's skills work, not code.
* **Schedulers stay seeded disabled** (`compliance_evals`,
  `scope_registry_research`). Flipping them on is a go-live step, and the
  research cycle **makes live Gemini calls**.
* **`trigger_conditions` have no write-time shape gate.** Read-time now fails
  closed, but a malformed Gemini-authored trigger still persists silently. The
  scope-registry side validates at write (`validate_proposal`); the research side
  should too.
* **Migrations `rekey01`/`rekey02` are dev-applied only** — they must run on prod
  before the next research pass, or prod re-mints the twins they just removed.

**Sharp edge:** `scope_codifications.source` was `VARCHAR(20)` and
`'scheduled_research'` is 18 — two characters of slack. Overflowing it raises
`StringDataRightTruncationError` *inside* the reconcile transaction, rolling back
every link and citation stamp the run computed. `codify03` widens it to 64 and
the code clamps + warns; a test pins the clamp to the migration's width.
