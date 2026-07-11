# Scope Registry — from statute text to a codified, grounded obligation

How a regulation goes from "a section exists in the CFR" to "a codified value a
tenant is measured against," what each stage means, how we ran it for the federal
labor chain, and how we verify the AI never became the source.

Companion to `SCOPE_REGISTRY_PLAN.md` (the design) and `EVAL_SYSTEM.md` (the
quality gates). This doc is the **operational** view — the pipeline you actually
run and what the counts mean.

---

## 1. The vocabulary (and one misnomer — see §6)

| Term | Table / field | Plain meaning |
|---|---|---|
| **Authority index** | `authority_indexes` | A book of law we track — an eCFR part (29 CFR 1910) or a curated statute slice (FLSA). |
| **Authority item** | `authority_index_items` | One section of that book, with its `citation`, `heading`, and (once fetched) the official `body_text`. |
| **Classification** | `authority_item_classifications` | The per-item **applicability verdict**: *does this bind, whom, and when?* (`disposition` = universal / category-specific / conditional / excluded), plus an optional `regulation_key` and `jurisdiction_scope`. ← the misnomer. |
| **Regulation key** | `regulation_key_definitions` (RKD) | The vocabulary of obligations (`lockout_tagout`, `national_minimum_wage`). A classification is *keyed* when it names one. |
| **Requirement** | `jurisdiction_requirements` | The stored **value** for an obligation in a jurisdiction ("$7.25/hr", "less than 50 volts"), with provenance. |
| **Codification** | `scope_codifications` | The link: *this classification's key ↔ that requirement value.* A codified obligation is one we can both **scope** (who owes it) and **state** (what it is). |

The two halves the registry joins:

- **Scope** — which obligations a business is liable for (classifications).
- **Store** — the actual value of each obligation (requirements).

**Codified = both.** Classified-but-unkeyed = we know it applies but have no value.
Keyed-uncodified = we have a key but no value yet (the fetch queue).

---

## 2. The pipeline

```
 ingest        classify        confirm        (key)         research        reconcile
┌────────┐   ┌──────────┐   ┌──────────┐   ┌────────┐   ┌────────────┐   ┌──────────┐
│ eCFR / │──▶│ Gemini   │──▶│ human    │──▶│ mint a │──▶│ Gemini     │──▶│ match    │
│ curated│   │ verdict  │   │ confirms │   │ reg_key│   │ EXTRACTS   │   │ key ↔    │
│ → items│   │ per item │   │ (bulk on │   │ if the │   │ value FROM │   │ value    │
│ + body │   │ (locator)│   │  dev)    │   │ obliga-│   │ body_text  │   │ → CODI-  │
│  text  │   │          │   │          │   │ tion   │   │ + cites it │   │  FIED    │
└────────┘   └──────────┘   └──────────┘   │ exists │   └────────────┘   └──────────┘
                                           └────────┘          │               │
                                                               ▼               ▼
                                                        grounding eval    scope_codifications
                                                        (§5: is the        (resolve_scope /
                                                        value really       labor_scope read
                                                        in the text?)      this = "codified")
```

Stage by stage (all live in `server/app/core/services/scope_registry/` unless noted):

1. **Ingest** (`authority_ingest.py`) — pull an index's sections from the official
   eCFR structure API (or curated tables) into `authority_index_items`. Idempotent.
   Bodies are fetched separately (`body_fetch.py`) into `body_text`.
2. **Classify** (`classify.py:classify_index`) — hand Gemini the citations + headings
   and ask one question per section: *who does this bind?* → a `disposition`.
   **Gemini is a locator, never a source**: it is told **not to invent a
   `regulation_key`** — keys are only attached when it's certain of an existing one,
   else `NULL`. Lands `provisional`.
3. **Confirm** (`classify.py:confirm_classifications`) — flip `provisional → confirmed`.
   Only confirmed classifications count. In the UI a human reviews; on dev we bulk-confirm.
4. **Key** (optional, `override_classification`) — if an obligation genuinely exists
   (`regulation_key_definitions`) but the model didn't attach it, an admin mints the
   key onto the section. This is the gate to codification for sections the model left
   unkeyed.
5. **Research** (`compliance_service.research_specialization_for_jurisdiction`, via
   `POST /admin/scope-registry/fetch-queue/research`) — for **keyed** worklist items,
   build a **grounded corpus** from the fetched `body_text` and have Gemini **extract
   the value FROM that text and cite the excerpt** (`grounded.py`). A value not backed
   by the corpus is dropped, not persisted (`penalties_stripped` reports how many).
6. **Reconcile** (`codify.py:reconcile_codifications`) — match each confirmed keyed
   classification's `regulation_key` against a stored requirement value; a match writes
   `scope_codifications` and stamps the verified citation. **This is what makes the
   green "codified" count move.**

Only **keyed** classifications can codify. `chain_uncodified` splits the worklist into
`keyed` (researchable) and `unkeyed` (needs a key minted first).

---

## 3. How we codified the federal labor chain (worked example)

Starting state (dev): **94 classified / 240 unclassified**, 4 federal codifications.

**A. Full classify** — ran `classify_index` on the 3 unclassified labor books:

```
OSHA-1904 : 3 subparts classified →   7 sections inherited
OSHA-1910 : 60 subparts          → 147 sections inherited
FMLA-825  : 5 subparts           →  18 sections inherited
→ unclassified 240 → 0;  confirm 240 → confirmed;  classified 94 → 334
```

Reconcile after this moved codified by **0** — the 240 new sections were **unkeyed**
(Gemini won't invent keys), so nothing new could link. Classified ≠ codified.

**B. Research the 2 keyed items** — `chain_uncodified` federal returned exactly 2
researchable keyed items (`daily_weekly_overtime` §207, `injury_illness_recordkeeping`
Subpart C). Grounded research extracted their values from the fetched statute text →
reconcile **inserted 3** → **4 → 7 codified**. `penalties_stripped=1` (a recalled
penalty not in the text was dropped).

**C. Extend the key vocabulary for OSHA safety** — the `machine_safety` category had
**zero** RKD keys, so real standards (lockout/tagout, machine guarding, …) could be
classified but never codified. Migration `oshakeys01` seeded 5 keys, each cited to its
eCFR section and severity-tagged from the curated map:

```
lockout_tagout (1910.147) · machine_guarding (1910.212) · confined_space (1910.146)
· electrical_safety (1910.333) · powered_industrial_trucks (1910.178)
```

Then: minted each key onto its section → grounded research (values pulled from the
§1910 body text: "less than 50 volts", "fan blades less than 7 feet", oxygen
thresholds) → reconcile **inserted 5** → **7 → 12 codified**. `penalties_stripped=5`.

Net for the session: **classified 94 → 334, codified 4 → 12**, all new values grounded.

### Why "just classify everything" doesn't codify it
Classification answers *who owes it*. Codification needs *what it is* — a key + a
value. Gemini deliberately under-keys (a locator, not a source), and a key only exists
if the RKD vocabulary has it. So codifying more means, in order: **mint a key** (if the
obligation is real and unkeyed) → **research** (ground a value from official text) →
**reconcile**. The 208 still-unkeyed federal sections are correct to sit in the fetch
queue: they need a key minted before they can carry a value.

---

## 4. Running it yourself (dev)

UI: **Scope Studio** (`/admin/scope-studio`) → set State/City → the Labor-scope panel
auto-loads; the "codified / to fetch / classified" counts and the classify/research
actions are there. Endpoints (all `require_admin`, under `/admin/scope-registry`):

| Action | Endpoint |
|---|---|
| classify an index (Gemini, async) | `POST /authority/{slug}/classify` |
| confirm classifications | `POST /classifications/confirm` |
| mint/override a classification (set `regulation_key`) | `PUT /items/{item_id}/classification` |
| research the fetch queue (grounded) + reconcile | `POST /fetch-queue/research` |
| reconcile only | `POST /reconcile` |

Migrations that back this are **author-only** — apply with `./scripts/migrate-dev.sh`
then `./scripts/migrate-prod.sh` (`oshakeys01` was applied to dev only so far).

---

## 5. Trust: is the value actually in the cited text?

`grounding='grounded'` proves only that Gemini **cited a real excerpt** — not that the
value appears in it. A recalled number can wear a genuine citation. The **grounding
eval** (`compliance_evals/grounding.py`, `EVAL_SYSTEM.md` §2.6) closes the gap, tier-1
deterministic: strip citation references from the value, extract numeric tokens, and
check each against the cited `body_text` (comma + spelled-out legal forms). Verdicts:

- `value_in_text` — grounded for real.
- `value_not_in_text` — **critical**: real citation, absent number → blocks onboarding
  readiness via the existing open-critical gate.
- `corpus_stub` — the cited body is a heading (< 500 chars); "grounded" is hollow.
- `value_unverifiable` — prose value, no numeric claim tier-1 can judge.

Session result over the 8 federal grounded rows: **6 `value_in_text`, 0
`value_not_in_text`, 1 stub, 1 prose → score 100** (stubs/prose excluded from the
denominator — unmeasured ≠ pass). Independent confirmation that "50 volts", "7 feet",
etc. are genuinely in the CFR text, not recalled.

**Tier-2a — golden cross-check** (`cross_check_rows`, pure): a grounded value that
DISAGREES with a hand-verified golden fact for the same key is a critical
`grounded_but_wrong` — the pipeline extracted the wrong number (harder than
not-in-cited-text). Reuses `golden.compare`; overrides the tier-1 verdict for scoring.

**Tier-2b — adversarial LLM verifier** (`grounding_verifier.py`, flag-gated by
`GROUNDING_LLM_VERIFIER_ENABLED`): for the rows tier-1 can't settle, ONE refute-framed
Gemini call over the cited excerpt ("does the text state this value? default false, no
outside knowledge") — `llm_refuted` → critical `grounded_value_refuted`, `llm_confirmed`
on a prose row → now verified. Verdicts cached by `(requirement_id, input_hash)` in
`compliance_eval_grounding_verdicts` (migration `groundver01`) so unchanged data costs 0
calls; flag ON makes grounding a Celery-routed network suite, OFF keeps it inline.

Remaining follow-up: spot-check sampling — re-run the verifier on random `value_in_text`
rows (golden is curated, not exhaustive); and having `build_grounded_corpus` exclude
sub-threshold stubs so a heading can't "ground" a value (it then honestly lands ungrounded).

---

## 6. Naming: "classification" is the wrong word

`authority_item_classifications` (and calling a row a "classification") reads like we're
sorting items into a taxonomy. We're not. Each row is a **decision about whether and to
whom an obligation applies** — an applicability judgment (`disposition` = the verdict),
optionally carrying the key and sub-jurisdiction scope. "Classified" then collides with
its everyday sense, and the plural drifts toward "classifieds" (ads). The concept
deserves a name that says *applicability decision*.

Candidates:

| Name | Row = | For | Against |
|---|---|---|---|
| **applicability** (`authority_item_applicability`, "an applicability") | "who this section binds" | Says exactly what the `disposition` decides; reads well as a count ("94 applicabilities resolved"). | Slightly abstract noun. |
| **scope ruling** (`authority_item_scope`) | "the scope decision for this item" | Ties to the product name (scope registry); "ruling" implies a reviewed verdict. | "scope" is overloaded (we already say scope everywhere). |
| **binding** (`authority_item_bindings`) | "does this bind, and whom" | Short, legal, concrete. | "binding" also means data-binding in code. |
| **disposition** (promote the field to the row) | "the disposition of this item" | The field is *already* named this; zero new vocabulary. | The row is more than the disposition (key, scope live on it too). |
| **coverage** (`authority_item_coverage`) | "who this section covers" | Insurance-adjacent, matches the domain. | Overlaps with "coverage %" reporting. |

**Recommendation: `applicability`.** It names the actual decision, the disposition field
sits naturally under it, "unclassified" becomes "unresolved / undetermined applicability"
(clearer — the item hasn't been ruled on, not mis-sorted), and it never reads as
"classifieds." A rename is a real refactor (table, ~130 code references, the admin UI
labels, `SCOPE_REGISTRY_PLAN.md`) — worth doing as its own change, not smuggled into a
feature PR. This doc flags it; the rename is a follow-up decision.
