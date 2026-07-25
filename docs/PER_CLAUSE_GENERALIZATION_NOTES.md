# Per-clause compliance: does it generalize past SB 553, and why it matters

**Status:** research notes, not a plan. No implementation designed, no scoping decisions made.
**Date:** 2026-07-24
**Context:** written after `b808c0f` (the 15 review fixes on `compliance/per-clause-audit`).
Related: `docs/SB553_COMPONENT_AUDIT_PLAN.md` — the plan this follows. Both live in `docs/`,
per commit `64bb63a`.

---

## Part 1 — Does the feature extend beyond SB 553?

### As built: no. And structurally so.

- **`requirement_components` has exactly one write path** — the hand-written
  `scripts/seed/sb553_components.sql` seed pack. No admin route, no research path, nothing
  else in `app/` inserts into it. (Verified: the only other references are a read in
  `compliance_service/_checks.py:1688` for the `has_components` flag, the checklist route,
  and the status service.)
- **`derivable` requires a hand-coded `_derive_*` Python function.** That's why only 1 of
  SB 553's 5 clauses derives (`wvp_training`), and why the next statute would start at 0.

So today it is a one-statute demo, not a feature. What shipped is the **runtime** for a
general feature — status model, reconcile, attest, checklist UI, audit trail, the
blind-never-violating invariants — with a hardcoded **content** layer of exactly one statute.

### But it generalizes cleanly, because the pieces already exist

**1. `compliance_registry.py` already has 539 `RegulationDef` entries**
(`grep -c "RegulationDef(" app/core/compliance_registry.py`), keyed by the same
`regulation_key` the catalog uses — curated name, category, enforcing agency, severity,
state_variance, authority sources. Clause definitions belong there as one more field.
Author once per regulation → covers every state carrying that key, instead of one SQL pack
per statute per jurisdiction.

**2. The registry→DB sync pattern is already established.**
`alembic/versions/rkdsev01_rkd_severity.py` imports `compliance_registry` *inside the
migration* and backfills `regulation_key_definitions.severity` from it. Its own comment
states the principle: *"the DB column is the runtime source, this map is the authority."*
Same shape works for clauses. Precedent chain: `v7w8x9y0z1a2_enrich_key_definitions` →
`rkdsev01`.

**3. The derivation problem is a vocabulary problem, not 539 functions.**
The tables to check record-existence against all exist already:

| table | useful columns |
|---|---|
| `policies` | `status='active'`, `category`, `effective_date`, `review_date` |
| `handbook_sections` | `section_key`, `last_reviewed_at` (company scope via `handbook_versions`) |
| `training_requirements` | `training_type`, `frequency_months`, `is_active` |
| `training_records` | `completed_date`, `expiration_date`, `requirement_id`, `status` |
| `policy_signatures` | acknowledgment proof per policy |

~5 generic parameterized checkers (`policy_exists`, `handbook_section_exists`,
`training_current`, `document_on_file`, `review_completed`) would cover most clauses of most
statutes with **zero new Python per law**. For SB 553 specifically this would make
`written_plan`, `hazard_assessment` and `annual_review` derivable instead of attest-only.

**4. For the long tail there is already an AI-clause-extraction precedent.**
`app/workers/tasks/cba_clause_extraction.py` extracts a clause library from a CBA PDF via
Gemini and leaves it **advisory until a human confirms it** (never clobbers HR edits).
And `requirement_components.verified_at` **already exists and is completely unused** — a
ready-made confirm gate for AI-drafted clause decompositions.

### Summary

Making it general is mostly (a) moving clause authorship into the registry and (b) replacing
per-statute Python derivations with a parameterized vocabulary. **Not new infrastructure.**

---

## Part 2 — How does generality serve "keep all companies 100% compliant"?

### Reframe first: 100% *compliant* isn't verifiable. 100% *coverage* is.

The catalog answers "what does the law require?" The clause layer answers "does this company
do it?" Two different databases, and only the second can be driven to a number.

### 1. A clause is a unit of work; a requirement isn't.

"You are non-compliant with Cal. Lab. Code § 6401.9" is unactionable — fix what? "You have no
hazard assessment on file for the Fresno site" is a task with an owner and a due date. 100%
compliance is only reachable if it decomposes into a finite worklist. Generality means every
law produces tasks, not just SB 553.

### 2. It makes the denominator honest.

Coverage measured per requirement overstates: one green check can hide four unmet obligations
inside the same statute. You cannot manage to 100% on a metric that lies at the granularity
you measure it. Decomposition is what makes the percentage mean something — the same reason
`compliance_evals` refuses to score unmeasured as 100.

### 3. The codified tags are what make it self-maintaining — the real payoff.

A company is compliant *on a date*, not permanently. The tags already being codified are
exactly the inputs that keep it true over time:

- **`effective_date`** → a clause that isn't in force yet shouldn't be scored; one that just
  became effective should open work automatically.
- **cadence (`frequency_months`, `review_date`)** → an annual obligation attested 18 months
  ago silently stops being compliance. With a cadence tag it deterministically re-opens
  instead of sitting green forever. (Same idiom already used for the 396-day training window
  in `_derive_wvp_training`.)
- **`category`** → what lets a clause auto-check against the right records (a policy in
  category X, a training program of type Y) with **no per-statute code**.

Without this you get a snapshot. With it you get a system that re-opens work as law and time
move — which is what "keep companies compliant" actually requires.

### 4. Change propagation gets precise.

When `legislation_watch` (or `handbook_freshness`) sees a law move, a clause-level model tells
you *which specific obligation* just went unmet at which locations. Without it you can only
say "this requirement changed, go re-read it."

### 5. The economics are shared-catalog, like the rest of the system.

Author a decomposition once per `regulation_key` and it serves every state carrying that key
and every tenant in them — the same payoff shape as the `jurisdiction_vertical_coverage`
ledger, where the second dental office in a city costs zero Gemini calls.

### The limit worth being clear-eyed about

Derivation only reaches obligations we hold records for. Everything else is attestation — a
**claim, not proof**. So "100%" is really three buckets:

| bucket | meaning |
|---|---|
| `derived` | proven from the company's own data |
| `attested` | a human said so |
| `unknown` | blind |

Generality **shrinks the blind bucket**. Evidence + cadence is what stops the claimed bucket
from quietly rotting into fiction. Nothing gets to a guarantee — but *"every obligation has a
known status, and every unmet one has an owner"* is defensible to an underwriter or a
regulator, and that is the sellable version of 100%.

---

## Loose ends / open questions (not decided)

- **Where clauses are authored:** registry `RegulationDef.clauses` (curated, code-reviewed,
  covers all 50 states per key) vs AI-extracted per catalog row behind the `verified_at`
  confirm gate vs both (curated for the `_SEVERITY_CRITICAL` set, AI for the tail).
- **Strengthening pieces**, each separable: declarative derivation vocabulary · recert
  cadence/decay · component→requirement rollup (deferred from the last PR — until it lands,
  filling in the checklist never moves the dollar number, so there's no incentive to do it) ·
  evidence artifacts (link a real record or upload a PDF via `storage.upload_private_file`;
  splits `basis` into `attested_with_evidence` vs bare `attested`).
- **Consumers to wire** (standing repo rule: a new engine ships wired into the pilots that
  ground on its domain): a `components` suite in `compliance_evals` · clause-level rows in
  `controls_evidence.CONTROL_CATALOG` → Proof-of-Controls PDF + broker submission packet ·
  a `clause:` citation group for Legal Pilot / Handbook Pilot via the shared
  `legal_defense.validate_citations` gate.
- **Invariants any of this must not break:** `unknown` never scores as compliant · blind ≠
  violating (an unbuilt context group or an unsold feature returns None, never
  `non_compliant`) · attestation must stay reachable wherever nothing can derive.
