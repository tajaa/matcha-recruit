# Pilot Grounding Uplift — Implementation Guide

**Status:** ready to execute · **Date:** 2026-07-19 · **Companion to:** `docs/plans/PILOT_GROUNDING_UPLIFT_PLAN.md` (PR #61)

This is the follow-along document for the four workstreams in the plan. The plan
holds the rationale and design; this file holds the ordered task lists, the
**resolved** open questions the plan flagged as unverified, and the per-PR
acceptance criteria. Check items off as they land.

Progress tracker:

| PR | Workstream | Branch | Status |
|---|---|---|---|
| 1 | A — Broker Pilot: property sub-records + risk index | — | ☐ not started |
| 2 | B — Legal Pilot: evidence sources + audit appendix | — | ☐ not started |
| 3 | C — Handbook Pilot: floor records + full-text drafting | — | ☐ not started |
| 4 | D — Analysis Pilot: from-platform datasets | — | ☐ design confirmation pending |

---

## 0. Open questions from the plan — now resolved (verified against tree 2026-07-19)

These were the plan's "read first / not verified in this review" items. All
verified; implementers can rely on the shapes below without re-deriving them.

### 0.1 Property builder return shapes (needed by A1)

**`property_cat.company_cat_exposure(conn, company_id) -> dict`** (`services/property_cat.py:481`, delegates to `summarize`, `:433`):

```python
{
  "worst_tier": str | None,          # None when no geocoded buildings — emit nothing
  "worst_peril": str | None,
  "worst_peril_documented": bool | None,
  "by_peril": {peril: tier},         # e.g. {"flood": "high", "wind": "moderate"}
  "by_peril_detail": {peril: {"tier": str, "annual_probability": float | None}},
  "documented_probability_perils": [str],
  "severe_high_count": int,
  "buildings_total": int,
  "buildings_geocoded": int,
}
```

**`property_exposure.portfolio_exposure(buildings) -> dict`** (`services/property_exposure.py:110`):

```python
{
  "total_aal": int,
  "worst_pml": int,
  "worst_pml_peril": str | None,
  "coinsurance_shortfall": int,
  "by_peril": {peril: {"aal": int, "pml": int}},
  "buildings": {building_id: {...per-building...}},   # skip in the corpus summary
  "basis": str,
}
```

**`property_recommendations.build_plan(...) -> dict`** (`services/property_recommendations.py:43`):

```python
{
  "fixes": [ {"key", "label", "severity", "detail", "impact",
              "building_id"?, "building_name"?} ],   # ranked, capped at _MAX_FIXES
  "summary": {"total": int, "by_severity": {...}, "shown": int},
}
```

**`property_risk.portfolio_risk(buildings) -> dict`** (`services/property_risk.py:90`):

```python
{
  "score": int | None,     # None when nothing rated — emit nothing
  "grade": str | None, "risk_level": str | None,
  "by_building": {id: {...}},          # skip in the corpus summary
  "top_risks": [ ...max 5... ],
  "rated": int,
}
```

### 0.2 Risk index return shape (needed by A2)

**`risk_index.compute_risk_index(conn, company_id) -> dict`** (`services/risk_index.py:445`):

```python
{
  "company_id": str,
  "index": int | None, "band": str | None,
  "components": [ {"key": "wc"|"epl"|"compliance"|"property",
                   "label", "weight", "score", "detail", "confidence"} ],
  "top_fixes": [...],
  "coverage": float | None,            # fraction of universe weight present
  "components_missing": [...],
  "index_confidence": str,
}
```

Confirmed: it fetches `enabled_features` itself via `merge_company_features` and
drops `property` from the universe when the flag is off — no extra gating at the
call site.

### 0.3 Compliance floor — **the plan's proposed cache helper is unnecessary** (changes C1)

`matcha_work_node.build_compliance_context(company_id) -> ComplianceContextResult`
(`services/matcha_work_node.py:392`) is **already Redis-cached** — key
`mw:compliance_ctx:{company_id}`, TTL 120s, per-key build locks — and the cache
round-trip **preserves `reasoning_chains`** (`_ctx_cache_set` at `:411-413`
stores them; `_compliance_result_from_cache` at `:421` restores them).

So the plan's §5 C1 "cost control" section (`get_compliance_floor` helper, new
`pilot:floor:{company_id}` key) is superseded: **Handbook Pilot calls
`build_compliance_context(company_id)` directly** and reads
`result.reasoning_chains`. The expensive precedence resolution already runs at
most once per company per 120s window regardless of which pilot (HR, Handbook,
or the matcha-work compliance mode) asks. Do not add a second cache layer.

`ComplianceContextResult` fields: `context_text`, `reasoning_chains: list[dict] | None`,
`truncated`, `has_legacy_locations`, `threshold_status`.

### 0.4 Analysis Pilot CHECK constraint (needed by D) — **migration confirmed required**

Migration `analysispilot01` creates `analysis_pilot_datasets.source_kind
VARCHAR(12) NOT NULL CHECK (source_kind IN ('csv','xlsx','pdf'))`. Admitting a
`'platform'` value needs a migration that drops and re-creates the CHECK
(VARCHAR(12) already fits). Also audit code that switches on `source_kind`
(extraction-confirm flow, PDF report labels) for exhaustive matches before
adding the value.

---

## PR 1 — Workstream A: Broker Pilot stops discarding computed data

Plan §3. All changes in `services/broker_pilot.py` + `routes/broker/submission.py`.
No migration, no flag, no gate change.

### Tasks

- [ ] **A1 — serialize property sub-structures** in `_platform_records`
      (`broker_pilot.py:716-730`), which today reads only `prop["rollup"]`.
      Using the §0.1 shapes, add guard-railed records (existing
      `add(cid, ref, summary)` convention — a missing/empty section emits nothing):
  - [ ] `platform:property.cat` — from `prop["cat"]`: worst tier + peril,
        `severe_high_count`/`buildings_total`, and the `by_peril` tier map.
        Emit nothing when `worst_tier` is None.
  - [ ] `platform:property.exposure` — from `prop["exposure"]`: `total_aal`,
        `worst_pml` + peril, `coinsurance_shortfall`. Skip the per-building map.
  - [ ] `platform:property.plan.<i>` — one record per entry in
        `prop["plan"]["fixes"]` (label, severity, impact; mirrors
        `platform:exclusions.<i>`).
  - [ ] `platform:property.risk` — from `prop["risk"]`: score/grade/risk_level +
        top risk contributor. Emit nothing when `score` is None.
  - [ ] Guards must be `isinstance(dict)`-style — external clients'
        `detail.get("property")` (`submission.py:244`) is a different shape and
        must silently produce zero records, never a KeyError.
- [ ] **A2 — risk index into the corpus**:
  - [ ] `_tenant_context` (`submission.py:186-193`): add
        `risk = await _safe(risk_index.compute_risk_index(conn, company_id), None, "risk_index")`,
        return as `"risk_index"`. (Accepted side effect: additive key in the
        `ctx` fed to submission-PDF renderers — they ignore unknown keys.)
  - [ ] `_platform_records`: `platform:risk` headline (index + band +
        `index_confidence`) and `platform:risk.<component>` per §0.2 components
        list (score + weight + detail) — mirrors `platform:epl.<factor>`
        (`broker_pilot.py:611-618`). External clients get none (tenant-only,
        precedented by controls/readiness).
- [ ] **Prompt**: add one line to `_SYSTEM` (`broker_pilot.py:937` region) naming
      the new property sub-records and `platform:risk` namespaces.
- [ ] **A3 (stretch — only if trivial)**: `platform:fleet` from
      `driver_risk.build_fleet`/`summarize` (`services/driver_risk.py:119/:100`),
      `_safe()`-fetched in `_tenant_context`, gated on the client company's
      `driver_risk` flag. Defer freely.

### Tests / acceptance

- [ ] Unit tests on `_platform_records` (pure): synthetic `ctx` with full
      property + risk sub-structures → assert minted cids + summary content.
- [ ] Malformed/external-shape `ctx` case → zero property/risk records, no exception.
- [ ] Existing broker-pilot tests pass unmodified.
- [ ] `cd server && python3 -m pytest tests/ -k broker -v`

**Done when:** a broker chat about a property-enabled tenant can cite
`platform:property.cat/exposure/plan/risk` and `platform:risk[.component]`, and
an external (off-platform) client still produces a working corpus.

---

## PR 2 — Workstream B: Legal Pilot evidence + audit-trail appendix

Plan §4. All changes in `services/legal_defense.py` + one exclusion in
`services/broker_pilot.py`. No migration, no flag.

Contract reminders (plan §B0 — verified): every `_src_*` keeps the exact
signature `fn(conn, company_id, start, end, loc_id, state, topic=_BROAD)` —
Broker calls with **six positional args** (`broker_pilot.py:813`). Reuse
`_scope_employee(n)` (`legal_defense.py:578`). No topic filters on new sources in v1.

### Tasks

- [ ] **B1 — `_src_leave`** per the plan's query sketch. Table `leave_requests`
      (**`org_id`**, not `company_id`). cid `leave:<id>`. Summary: type, status,
      dates, intermittent, employee name — **never `reason`**. Registry entry
      gated `lambda f: bool(f.get("employees"))`.
- [ ] **B2 — `_src_agency_charges`**. Table `agency_charges` (`company_id` +
      `employee_id NOT NULL`). cid `charge:<id>`; ref `charge_number` falling
      back to `agency_name`; summary includes status, filing date,
      `resolution_amount`. Window on `filing_date`; `JOIN employees` +
      `_scope_employee`; gate `employees`.
- [ ] **B3 — three termination-lifecycle sources**, each a copy of the
      `_src_incidents` pattern (`legal_defense.py:614-635`):
  - [ ] `pre_termination` / `pre_termination_checks` / `preterm:<id>` / gate `employees`
  - [ ] `separations` / `separation_agreements` / `separation:<id>` / gate `separation_agreements`
  - [ ] `post_term_claims` / `post_termination_claims` / `ptclaim:<id>` / gate `employees`
- [ ] **Registry**: append the five `(key, label, fn, enabled)` entries to
      `_SOURCES` (`legal_defense.py:1081-1100`). The disabled-source note
      (`:1149/:1181-1185`) covers them automatically — don't bypass the registry.
- [ ] **B4 — audit-trail appendix** (packet-time only, **no corpus change, no new cids**):
  - [ ] `_detail_*`-style fetchers (mirror `_detail_discipline`, `:1924`) for
        **cited** records only: `ir_audit_log WHERE incident_id=$1`,
        `er_audit_log WHERE case_id=$1`, `discipline_audit_log WHERE
        discipline_id=$1` (actor col `actor_user_id`; join `users` for email).
  - [ ] Render compact chain-of-custody table (timestamp, actor, action) under
        each record's existing appendix section; summarize/omit `details` JSONB;
        cap ~30 rows (first N + last N + elision note).
  - [ ] Wrap in `_appendix_safe` (`:1895-1899`) — failed fetch degrades to no
        table, never a failed packet.
- [ ] **B5 — broker exclusion** in `broker_pilot.gather_native_sources` (`:809`):
      `_BROKER_EXCLUDED_SOURCES = {"leave"}`, skip in the loop. Do **not** widen
      the `_SOURCES` 4-tuple. `charge`/`preterm`/`separation`/`ptclaim` flow to
      Broker deliberately.
- [ ] **Prompt**: add the five new cid namespaces to the `_SYSTEM` cid list
      (`legal_defense.py:1240` region). Verify the packet renderer tolerates
      cited records with no bespoke appendix section (it does today for
      non-detail types — confirm nothing asserts on unknown prefixes).

### Tests / acceptance

- [ ] Unit tests: record shape + summary composition per source (stub conn);
      the six-positional-arg call path; `_BROKER_EXCLUDED_SOURCES` skips `leave`
      and only `leave`.
- [ ] Unit test: leave summaries never contain the `reason` column's content.
- [ ] DB-touching integration tests written for **manual** run, reserved-domain
      test data only (repo rule).
- [ ] Existing legal-defense + broker-pilot suites pass.
- [ ] `cd server && python3 -m pytest tests/ -k "legal or broker" -v`

**Done when:** a wrongful-termination matter can cite `leave:`/`charge:`/
`preterm:`/`separation:`/`ptclaim:` records; a packet citing an incident/ER
case/discipline record carries its chain-of-custody table; Broker Pilot grounds
on charges + termination records but never leave.

---

## PR 3 — Workstream C: Handbook Pilot floor + full-text drafting

Plan §5, **amended by §0.3 above** (no new cache helper). Changes in
`services/handbook_pilot.py` + `services/hr_pilot_corpus.py`. Import direction
rule: shared pure helpers move **into `handbook_pilot`** (hr_pilot_corpus
imports it; the reverse would be circular).

### Tasks

- [ ] **C1 — precedence-resolved floor records**:
  - [ ] Move `_floor_records` from `hr_pilot_corpus.py:376` into
        `handbook_pilot.py`; leave a re-export in `hr_pilot_corpus` (its tests
        and callers keep working).
  - [ ] `gather_grounding` (`handbook_pilot.py:82-165`): best-effort
        `result = await matcha_work_node.build_compliance_context(company_id)`
        (already cached + lock-protected, chains survive cache — §0.3); return
        `grounding["reasoning_chains"] = result.reasoning_chains`. Degrade to
        empty on any exception, same as every other source there.
  - [ ] `build_corpus` (`handbook_pilot.py:351-379`): add the `compliance_floor`
        group when chains present; otherwise append the "no floor available"
        note (copy wording from `hr_pilot_corpus.py:656-660`).
  - [ ] `build_hr_pilot_corpus` (`hr_pilot_corpus.py:611`): **stop re-minting** —
        pass chains through `grounding`, delete its own group-add (`:626-629`).
        Keep the `reasoning_chains` param for back-compat and feed it into
        `grounding`.
  - [ ] Drafting prompt: one instruction line — when a flat `law:` record and a
        `floor:` record cover the same category, `floor:` is the governing
        requirement; cite it.
- [ ] **C2 — full-text drafting**:
  - [ ] Move `render_corpus_block` from `hr_pilot_corpus.py:812-839` into
        `handbook_pilot.py`; re-export for compat.
  - [ ] `gather_grounding`: policies SELECT (`:145-154`) gains `content`
        (sections already select `hs.content` at `:127`).
  - [ ] `_generate` (`handbook_pilot.py:579-618`): build
        `full_text = {f"handbook:{id}": ..., f"policy:{id}": ...}`, per-record
        cap 4,000 chars with truncation marker; render via
        `render_corpus_block(corpus, full_text)`.
  - [ ] **Budget guard**: total full-text budget ~120k chars; overflow records
        fall back to summaries + a truncation note (notes channel exists for
        this). Stored records stay 280-char (HR Pilot's metadata invariant).
- [ ] `validate_citations`: nothing to change — `floor:` cids enter `index` like
      any group. Legacy-cid recovery (`handbook_pilot.py:386-426`) untouched.
- [ ] **C3 (deferred, separate decision):** `audit:`/`fresh:` records from stored
      handbook audit/freshness findings — reassess after C1/C2 land.

### Tests / acceptance

- [ ] Floor-record dedupe across locations (the `applies_to` widening,
      `hr_pilot_corpus.py:404-410`) — test moves with the function.
- [ ] No double-mint of `compliance_floor` after the hr_pilot_corpus change —
      extend `test_no_cid_collisions_across_groups`.
- [ ] Full-text render: per-record cap, total budget fallback, truncation notes.
- [ ] "No chains → note present" path.
- [ ] **HR Pilot + Ask HR suites pass unmodified** (re-exports exist so they do) —
      this PR touches their corpus assembly.
- [ ] `cd server && python3 -m pytest tests/ -k "handbook or hr_pilot or ask_hr" -v`

**Done when:** a Handbook Pilot draft cites `floor:` records for governing
requirements and drafts replacements from full section/policy text, and HR
Pilot/Ask HR behavior is byte-identical.

---

## PR 4 — Workstream D: Analysis Pilot from-platform datasets

**Blocked on design confirmation** (plan §6). Do not start until the loss-run
access question is answered: `loss_development.build_development` is keyed to
broker subjects — confirm the company-facing pilot has a legitimate read path.

Known-now (from §0.4): admitting `source_kind='platform'` **requires a
migration** (CHECK constraint re-create on `analysis_pilot_datasets`).

Sketch when unblocked: `POST /analysis-pilot/sessions/{sid}/datasets/platform`
+ a builder registry `(key, label, required_feature, build(conn, company_id) ->
normalized)`; first sources `ir_monthly` (gate `incidents`) and possibly
`loss_runs`; datasets are point-in-time snapshots (`meta.as_of`,
`meta.source_kind="platform"`), pre-confirmed (no extraction-confirm step).

---

## Cross-cutting checklist (every PR)

- [ ] `_SYSTEM`/prompt cid documentation updated for any new namespace.
- [ ] CLAUDE.md feature-table rows touched **only** if flag semantics change
      (A/B/C change none).
- [ ] When PR 1 lands, add the convention line to root CLAUDE.md: *when a new
      `services/*.py` analytics/risk engine lands, the same PR adds its corpus
      records to whichever pilots ground on that domain.*
- [ ] No schema surprises: A/B/C ship zero migrations; if one appears necessary
      mid-implementation, stop — something diverged from the plan.
- [ ] Post-edit hook covers Python syntax; run the targeted pytest selection
      listed in each PR section before opening the PR.
