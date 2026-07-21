# Pilot Grounding Uplift — Technical Plan

**Status:** proposed · **Date:** 2026-07-20 · **Branch:** `claude/pilot-programs-review-04fyts`

Review of the four grounded-AI pilots — **Legal** (`legal_defense`), **Broker**
(broker pilot), **Analysis** (`analysis_pilot`), **Handbook** (`handbook_pilot`) —
found the same failure mode three times over: *a platform service computes
something, and the pilot that should cite it never learned it exists.* This plan
specs the fixes, ordered by effort-to-impact. Every file/line reference below was
verified against the working tree on the date above.

| Workstream | Pilot | What | Effort | Migration? | New flag? |
|---|---|---|---|---|---|
| **A** | Broker | Serialize already-computed property sub-structures + risk index into the corpus | **S** (hours) | no | no |
| **B** | Legal | New evidence sources (leave, agency charges, termination records) + audit-trail packet appendix | **M** (~1 day) | no | no |
| **C** | Handbook | Precedence-resolved compliance floor + full-text drafting (layering refactor with HR Pilot) | **M** (~1–2 days) | no | no |
| **D** | Analysis | "From-platform" dataset adapter (design sketch — held for its own PR) | **L** (2–3 days) | maybe (CHECK constraint) | no |

---

## 1. Background — the shared corpus architecture

All four pilots ground a Gemini conversation on a **flat citation corpus**:
`{sources: {key: {label, records}}, index: {cid: record}, notes: [...]}` where each
record is `{cid, ref, summary, when, ...}`. After generation, the shared
anti-hallucination gate `legal_defense.validate_citations`
(`server/app/matcha/services/legal_defense.py:1393`) drops any cited id not present
in `index`. Deterministic exports (PDF appendices) render from DB rows, never model
text.

Because the corpus shape is identical everywhere, **adding a data source is always
the same move**: mint records with a new (or existing) cid namespace, land them in
`sources`, and the index/gate/renderer machinery picks them up. Nothing in this
plan touches the gate.

Cross-pilot dependency arrows (load-bearing for Workstream C):

```
broker_pilot ──reuses──▶ legal_defense._SOURCES      (gather_native_sources)
hr_pilot_corpus ──imports──▶ handbook_pilot          (build_corpus, cid minting)
ask_hr ──reuses──▶ hr_pilot_corpus                   (get_hr_pilot_corpus + redaction)
```

Consequence #1: anything added to `legal_defense._SOURCES` automatically flows
into Broker Pilot (see §3.4 — one privacy decision required).
Consequence #2: shared pure helpers must live in `handbook_pilot`, not
`hr_pilot_corpus`, or the import becomes circular (see §4.1).

## 2. Current-state grounding matrix

| Source | Legal | Broker | Handbook | HR Pilot (reference) |
|---|---|---|---|---|
| IR/OSHA incidents | ✅ `incident:` | ✅ (via Legal) | — | ✅ `incident:` (own, 90d) |
| ER cases | ✅ `er_case:` | ✅ (via Legal) | — | — |
| Compliance req/alerts/remediation | ✅ | ✅ (via Legal) | — | — |
| Discipline / training / policy acks / accommodations | ✅ | ✅ (via Legal) | — | `ladder:` only |
| Jurisdiction law / legislation / case law | ✅ `law:` `bill:` `case:` | ✅ `jur:` | ✅ `law:` (flat list) | ✅ `law:` + **`floor:` (precedence-resolved)** |
| Handbook sections / policies | — | — | ✅ (280-char previews) | ✅ **full text at prompt time** |
| WC / EPL / limits / loss dev / venue / exclusions | — | ✅ `platform:*` | — | — |
| Property SOV rollup | — | ✅ `platform:property` | — | — |
| Property cat / exposure / plan / risk | — | ❌ **computed, then dropped** | — | — |
| Risk index (`risk_index.py`) | — | ❌ never fetched | — | — |
| Leave requests | ❌ | ❌ | — | — |
| Agency charges (EEOC/NLRB/OSHA) | ❌ | ❌ | — | — |
| Pre-term checks / separations / post-term claims | ❌ | ❌ | — | — |
| Subsystem `*_audit_log` trails | ❌ **(docstring claims them)** | — | — | — |
| Platform tables → Analysis datasets | — | — | — | — (Analysis is 100% upload-only) |

---

## 3. Workstream A — Broker Pilot: stop discarding computed data

### A1. Property sub-structures (pure serialization change)

`_tenant_context` (`server/app/matcha/routes/broker/submission.py:186-193`) already
builds the full property picture:

```python
property_ctx = {**sov, "cat": cat, "exposure": exp, "plan": plan, "risk": risk}
```

but `_platform_records` (`server/app/matcha/services/broker_pilot.py:716-730`)
serializes **only** `prop["rollup"]` (building count, TIV, COPE grade, ITV). The
cat exposure, portfolio exposure, recommendation plan, and portfolio risk objects
are dropped on the floor.

**Change:** extend the property section of `_platform_records` with guard-railed
accessors (same `add(cid, ref, summary)` convention as every other section):

- `platform:property.cat` — flood/quake/wildfire/wind tier summary from
  `property_cat.company_cat_exposure` output (counts of buildings per peril tier).
- `platform:property.exposure` — portfolio exposure highlights from
  `property_exp.portfolio_exposure`.
- `platform:property.plan.<i>` — one record per recommendation in
  `property_recs.build_plan` output (mirrors `platform:exclusions.<i>`).
- `platform:property.risk` — portfolio risk headline from
  `property_risk_svc.portfolio_risk`.

**Implementation notes:**
- Read the four builders' return shapes first (`services/property_cat.py`,
  `property_exposure.py`, `property_recommendations.py`, `property_risk.py`) —
  the exact keys were not verified in this review; the accessors must be
  `dict`-guarded like the rest of `_platform_records` ("a missing/empty section
  emits nothing").
- External clients: `_external_context` (`submission.py:244`) returns
  `detail.get("property")`, a **different shape** (off-platform snapshot). The
  guards must tolerate it silently — no records is fine; a KeyError is not.
- The `_SYSTEM` prompt (`broker_pilot.py:937`) lists cid namespaces —
  `platform:*` already covers these; no prompt change strictly needed, but add
  one line naming the property sub-records so the model knows to look.

### A2. Risk index

`risk_index.compute_risk_index(conn, company_id)`
(`server/app/matcha/services/risk_index.py:445`) is the same composite 0–100
engine the broker already sees at `/broker/risk-index`. It never enters the pilot.

**Change:**
1. In `_tenant_context` (`submission.py`), add alongside the other optional
   sections: `risk = await _safe(risk_index.compute_risk_index(conn, company_id), None, "risk_index")`
   and return it as `"risk_index": risk`. (`compute_risk_index` fetches
   `enabled_features` itself and includes the property component only when
   enabled — no extra gating needed here.)
2. In `_platform_records`, serialize:
   - `platform:risk` — headline: composite score + band.
   - `platform:risk.<component>` — one per component in the breakdown (wc,
     epl, compliance, property), with score + weight. Mirrors the
     `platform:epl.<factor>` pattern at `broker_pilot.py:611-618`.

**Tenant-only:** `_external_context` gets no risk index (no platform data to
compute it from) — same asymmetry as controls/readiness, already precedented.

**Side effect (accepted):** the same `ctx` dict feeds the submission-packet PDF
renderers; an extra `risk_index` key is additive and ignored by renderers that
don't read it. If the submission PDF should *also* show the risk index, that's a
separate, optional follow-up — don't couple it to this change.

### A3. Stretch (defer unless trivial): driver risk

`driver_risk.build_fleet` / `summarize` (`services/driver_risk.py:119/:100`) —
fleet grade + MVR mix is directly relevant to commercial-auto conversations.
Same recipe: `_safe()` fetch in `_tenant_context` gated on the client company's
`driver_risk` flag, serialize as `platform:fleet`. Defer if the return shape
needs massaging; A1+A2 are the core of this workstream.

**Testing (A):** `_platform_records` is pure — extend the existing unit tests
with a synthetic `ctx` carrying full property/risk sub-structures and assert the
minted cids + summaries; add a malformed/external-shape ctx case asserting zero
records and no exception.

---

## 4. Workstream B — Legal Pilot: missing evidence + the promised audit trails

### B0. Registry contract (read first)

`_SOURCES` (`legal_defense.py:1081-1100`) is a list of
`(key, label, query_fn, enabled(features))`. Every `query_fn` has the signature
`fn(conn, company_id, start, end, loc_id, state, topic=_BROAD)`.

⚠️ **Broker Pilot calls these with six positional args** —
`fn(conn, company_id, None, None, None, None)` at `broker_pilot.py:813` — relying
on the `topic` default. New sources must keep this exact signature.

Scoping helpers to reuse: `_scope_employee(n)` (`legal_defense.py:578`) for tables
reached via `employees e`; `_topic_filter` (`:547`) only if a source gets a theory
allowlist (v1: none of the new sources do — the "broad is the only honest scope"
principle at `:540-542` applies; these tables are small and cross-cutting).

### B1. `_src_leave` — leave requests (FMLA/PFML/medical)

The EEO theory's keyword set already includes `fmla` / `pregnan*` / `accommodat*`
(`legal_defense.py:293-304`) and accommodations are gathered — but the natural
companion evidence for FMLA-interference/retaliation matters is absent.

Table: `leave_requests` (migration `d0a8f93f3fd0`) — **note `org_id`, not
`company_id`**. Columns: `leave_type`, `reason`, `start_date`, `end_date`,
`expected_return_date`, `actual_return_date`, `status`, `intermittent`.

```python
async def _src_leave(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT lr.id, lr.leave_type, lr.status, lr.start_date, lr.end_date,
               lr.actual_return_date, lr.intermittent, e.first_name, e.last_name
        FROM leave_requests lr
        JOIN employees e ON e.id = lr.employee_id
        WHERE lr.org_id = $1
          AND ($2::date IS NULL OR COALESCE(lr.end_date, lr.start_date) >= $2)
          AND ($3::date IS NULL OR lr.start_date < ($3::date + 1))
          {_scope_employee(4)}
        ORDER BY lr.start_date DESC
        """,
        company_id, start, end, loc_id, state,
    )
    ...  # cid f"leave:{r['id']}"
```

- **Summary content rule:** type, status, dates, intermittent flag, employee
  name. **Never `reason`** — free-text medical detail stays out of the AI corpus.
  (The packet detail fetcher may include more; see B4 note.)
- Registry entry: `("leave", "Leave of absence (FMLA / PFML / medical)",
  _src_leave, lambda f: bool(f.get("employees")))` — matches the
  `pre_termination` mount gate (`routes/__init__.py:249`).
- **Excluded from Broker** — see B5.

### B2. `_src_agency_charges` — EEOC / NLRB / OSHA / state-agency charges

The single most on-topic table for the pilot's declared matter types, and it is
not gathered. Table: `agency_charges` (`database.py:1826`) — `company_id`,
`employee_id NOT NULL`, `charge_type` (`eeoc|nlrb|osha|state_agency|other`),
`charge_number`, `filing_date`, `agency_name`, `status`
(`filed|investigating|mediation|resolved|dismissed|litigated`),
`resolution_amount/date/notes`.

- cid `charge:<id>`; ref = `charge_number` (falls back to agency_name);
  summary = type, agency, status, filing date, resolution status. Include
  `resolution_amount` — settlement history is legitimate defense context.
- Scope via `JOIN employees e` + `_scope_employee`; window on `filing_date`.
- Gate: `lambda f: bool(f.get("employees"))` (FK to employees is NOT NULL).
- **Included in Broker** — agency-charge history is core EPL underwriting
  context; brokers already see discipline records with employee names.

### B3. Termination-lifecycle records (three small sources)

All three are direct defense evidence for the wrongful-termination / EEOC matter
types in `_MATTER_TYPE_THEORY`:

| Source key | Table | cid | Gate | Summary fields |
|---|---|---|---|---|
| `pre_termination` | `pre_termination_checks` (`database.py:1694`) | `preterm:<id>` | `employees` | overall_band + score, outcome, is_voluntary, computed_at, employee. *Shows diligence ran **before** the termination — the point.* |
| `separations` | `separation_agreements` (`database.py:6020`) | `separation:<id>` | `separation_agreements` | status, severance_weeks, ADEA flags (`is_adea_applicable`, consideration/revocation windows), presented/signed dates, employee |
| `post_term_claims` | `post_termination_claims` (`database.py:1860`) | `ptclaim:<id>` | `employees` | claim_type, status, filed_date, resolution_amount, employee |

Each is a copy of the `_src_incidents` pattern (`legal_defense.py:614-635`):
one parameterized query, `_scope_employee`, date-window on the natural date
column, compact record. No topic filter v1.

### B4. Audit-trail appendix — the docstring's unkept promise

The module docstring (`legal_defense.py:6`) says the packet pulls "the immutable
`*_audit_log` trails." It does not: the only audit table touched is
`legal_matter_audit_log` (`_fetch_audit_log`, `:1902`) — the matter's own
chain-of-custody. `ir_audit_log` (`database.py:2130`), `er_audit_log` (`:1966`),
and `discipline_audit_log` (`:1810`) are never queried.

**Design decision — packet-time, not corpus.** Audit rows are high-volume,
low-semantic-density ("field updated at T"). Feeding 50 of them to the model buys
nothing; their legal value is chain of custody: *"this discipline record was
created before the complaint, contemporaneously, and never retro-edited."* That is
appendix evidence. So:

- **No corpus change, no new cids, no gate interaction.** Zero anti-hallucination
  surface — the appendix is already rendered deterministically from DB rows.
- In the packet build, for each **cited** `incident:` / `er_case:` /
  `discipline:` record, add a `_detail_*`-style fetcher (mirror
  `_detail_discipline`, `:1924`) pulling that record's audit rows:
  - `ir_audit_log WHERE incident_id = $1` (join `users` for actor email)
  - `er_audit_log WHERE case_id = $1`
  - `discipline_audit_log WHERE discipline_id = $1` (actor col is `actor_user_id`)
- Render as a compact chain-of-custody table under each record's existing
  appendix section: timestamp, actor, action. Summarize `details` JSONB to a
  short phrase or omit; **cap at ~30 rows per record** (first N + last N with an
  elision note) — audit trails on old incidents can be long.
- Failure isolation: wrap in the existing `_appendix_safe` pattern
  (`legal_defense.py:1895-1899`) — a failed audit fetch degrades to no table,
  never a failed packet.
- These fetchers run **only for cited records** (same rule as the other
  `_detail_*` fetchers, comment at `:1917-1922`) — not the whole corpus.

*Optional follow-up, out of scope here:* leave `reason` and full audit `details`
could surface in the appendix (attorney-facing, not model-facing) — decide when
implementing B4 whether the packet should carry them; default to omitting.

### B5. Broker interplay — one explicit filter

Because `gather_native_sources` iterates `legal_defense._SOURCES`
(`broker_pilot.py:809`), B1–B3 land in Broker Pilot automatically. That is
desirable for `charge`/`preterm`/`separation`/`ptclaim` (EPL underwriting
context) and **not** for `leave` (medical-adjacent; a broker chat has no business
grounding on who took FMLA).

**Change:** in `broker_pilot.gather_native_sources`, add

```python
_BROKER_EXCLUDED_SOURCES = {"leave"}  # medical-adjacent; legal-defense only
...
for key, label, fn, enabled in ldef._SOURCES:
    if key in _BROKER_EXCLUDED_SOURCES:
        continue
```

Do **not** widen the `_SOURCES` tuple to carry a broker flag — two call sites
unpack it as a 4-tuple (`legal_defense.py:1151`, `broker_pilot.py:809`) and the
exclusion is a broker-side policy, so it belongs in broker code.

**Testing (B):** new `_src_*` fns are DB-touching — follow the repo rule
(integration tests written to be run manually; reserved-domain test data). The
pure parts (record shape, summary composition, the broker exclusion set) get unit
tests. Verify the six-positional-arg call path with a stub conn. Update the
`_SYSTEM` prompt cid list (`legal_defense.py:1240` region) with the new
namespaces, and confirm the packet renderer's cid-prefix dispatch has a fallback
for record types without a bespoke appendix section (it does today for
non-detail types — verify nothing asserts on unknown prefixes).

---

## 5. Workstream C — Handbook Pilot: draft against the governing rule, from full text

Handbook Pilot has the thinnest corpus of the four, and both fixes already exist
in `hr_pilot_corpus.py` — which imports `handbook_pilot`, so the shared pieces
move **down** the dependency arrow, not up.

### C1. Precedence-resolved compliance floor (`floor:` records)

**Today:** `gather_grounding` (`handbook_pilot.py:82-165`) grounds on the *flat*
per-state list from `hb._fetch_state_requirements` (`:118`) — every overlapping
federal/state/local rule, undifferentiated, capped 40/state. A drafting tool
picking clauses from that is drafting against noise. HR Pilot already mints the
governing requirement per category as `floor:` records
(`hr_pilot_corpus._floor_records`, `hr_pilot_corpus.py:376-437`) from
`matcha_work_node.build_compliance_context` reasoning chains.

**Change:**

1. **Move `_floor_records` into `handbook_pilot.py`** (it is pure; keep a
   re-export in `hr_pilot_corpus.py` so its tests and any callers don't break).
2. `gather_grounding` fetches the chains best-effort (same degrade-to-empty
   convention as every other source in that function) and returns them as
   `grounding["reasoning_chains"]`.
3. `build_corpus` (`handbook_pilot.py:351-379`) adds a `compliance_floor` group
   when chains are present, and appends the existing "no floor available" note
   otherwise (copy the wording from `hr_pilot_corpus.py:656-660`).
4. **`build_hr_pilot_corpus` (`hr_pilot_corpus.py:611-`) stops re-minting**: it
   currently calls `build_corpus(grounding)` then adds its own
   `compliance_floor` group (`:626-629`). After the move, it passes the chains
   through `grounding` and deletes its own group-add — otherwise the group is
   built twice (same cids, so the index survives, but the prompt block renders
   the records twice). Keep its signature (`reasoning_chains` param) and feed
   the param into `grounding` for back-compat.
5. The drafting prompt gains one instruction line: *when a flat `law:` record
   and a `floor:` record cover the same category, the `floor:` record is the
   governing requirement — cite it.*

**Cost control (the real design decision):** `build_compliance_context` does
precedence resolution and is not free; `gather_grounding` runs **per turn**.
HR Pilot solves this with a 120s Redis cache (`mw:hr_pilot_ctx2:{company_id}`)
— but that caches the *HR* corpus, not the chains. Extract the narrow piece:

- New cached helper (suggested home: `hr_pilot_corpus.py` or a small
  `services/compliance_floor.py`): `get_compliance_floor(company_id) ->
  reasoning_chains`, Redis TTL ~120s, key `pilot:floor:{company_id}`.
- Both HR Pilot's corpus build path and Handbook Pilot's `gather_grounding`
  consume it → the expensive resolution runs once per company per TTL window
  regardless of which pilot asks. Verify `build_compliance_context`'s exact
  signature/return against its caller in `matcha_work_node.py` before wiring
  (not re-verified in this review).
- Fallback unchanged: empty chains → flat `law:` list only + the note. This is
  exactly HR Pilot's existing degrade path.

`validate_citations` needs nothing: `floor:` cids enter `index` like any group.
The legacy-cid recovery path (`lookup_record`/`_legacy_prefix`,
`handbook_pilot.py:386-426`) is untouched — `floor:` is a new namespace with no
legacy form.

### C2. Full-text drafting (stop drafting from 280-char previews)

**Today:** existing handbook sections are truncated to 280 chars by
`_existing_section_records` (`handbook_pilot.py:295-305`) and policy records
carry **no body at all** (`gather_grounding` selects only
`id,title,category,status,description` at `:145-154`) — yet the model is asked
to draft replacements for them. HR Pilot documented and solved exactly this:
`render_corpus_block(corpus, full_text)` (`hr_pilot_corpus.py:812-839`) injects
full bodies at prompt time while stored records stay index-sized (see its
docstring — the rationale is written there).

**Change:**

1. **Move `render_corpus_block` into `handbook_pilot.py`** (pure; re-export from
   `hr_pilot_corpus` for compat — same move as C1, same reason: import direction).
2. `gather_grounding` already selects `hs.content` (`:127`); add `content` to
   the policies SELECT.
3. Build a `full_text` map at prompt-assembly time in `_generate`
   (`handbook_pilot.py:579-618`): `{f"handbook:{id}": section_content,
   f"policy:{id}": policy_content}`, each value capped (suggest 4,000 chars per
   record with a truncation marker) and render the corpus block via
   `render_corpus_block(corpus, full_text)`.
4. **Prompt budget guard:** 60 sections × 4k chars is worst-case ~240k chars.
   Add a total budget (suggest ~120k chars of full text; beyond it, fall back to
   summaries for the overflow and append a truncation note — the notes channel
   already exists for exactly this). Records stay 280-char in storage so
   session/message metadata doesn't balloon (HR Pilot's invariant, keep it).

### C3. Stretch (separate decision, not this PR)

Stored **handbook audit findings** and **freshness findings**
(`handbook_freshness_checks`/`_findings`) as `audit:`/`fresh:` corpus records —
"your current handbook fails X" is high-value drafting context. Deferred because
Handbook Pilot's on-demand `run_compliance_scan` (`handbook_pilot.py:809-883`)
partially covers it and the marginal value should be assessed after C1/C2 land.

**Testing (C):** all moved/changed pieces are pure → unit tests without DB:
floor-record dedupe across locations (the `applies_to` widening at
`hr_pilot_corpus.py:404-410`), no-double-mint after the hr_pilot_corpus change
(extend `test_no_cid_collisions_across_groups`), full-text render with caps, and
the "no chains → note present" path. Existing handbook-pilot tests must pass
unmodified — the re-exports exist so they do.

---

## 6. Workstream D — Analysis Pilot: from-platform datasets (design sketch)

**Held for its own PR** — this is a feature, not an integration gap-fill. Sketch
recorded here so the design conversation has an anchor.

**Today:** ingestion is hard-wired to uploads (`_read_upload` /
`upload_dataset`, `routes/pilots/analysis.py:262-268/:381`); the only
non-`analysis_pilot_*` table read is `companies` for the PDF letterhead. Yet the
normalized model is deliberately source-agnostic
(`analysis_packs/base.py:41-49`):

```python
normalized = {"series": {...}, "periods": [...], "roles": {...}, "kind": "...", "meta": {...}}
```

and the `insurance_loss` pack is literally shaped for loss runs.

**Why it's cheaper than it looks:** the extraction-confirm flow exists because
Gemini PDF extraction is untrusted. A deterministic builder over platform rows
needs no confirm step — the dataset arrives pre-confirmed.

**Proposed shape:**
- `POST /analysis-pilot/sessions/{sid}/datasets/platform` with
  `{"source": "<key>"}`.
- A registry of builders, each
  `(key, label, required_feature, build(conn, company_id) -> normalized)`:
  - `ir_monthly` — monthly incident counts by type, trailing 24 months →
    `kind="timeseries"` → `general_stats` applies. Gate: `incidents`.
  - `loss_runs` — the rows `loss_development.build_development` reads →
    `kind="loss_run"`, roles mapped → `insurance_loss` applies. **Open
    question:** those rows are keyed to broker subjects
    (`build_development(conn, broker_id, "company", company_id, ...)`) — verify
    the company-facing pilot has a legitimate read path before committing to
    this source.
- Snapshot semantics: a platform dataset is a point-in-time snapshot
  (`meta.as_of`, `meta.source_kind="platform"`); refresh = create a new dataset.
  No sync, no drift problem.
- Per-source feature gate enforced in the route (the builder registry carries
  `required_feature`); the `analysis_pilot` mount gate is unchanged.
- **Pre-implementation check:** whether `analysis_pilot_datasets` constrains its
  kind/source column with a CHECK (migration `analysispilot01`) — if so, one
  small migration to admit the platform value.

---

## 7. Cross-cutting

- **No schema migrations for A/B/C.** Every table referenced already exists.
  D may need one (CHECK constraint, see §6).
- **No new feature flags.** All changes ride existing per-source gates.
- **Prompt-size discipline:** B grows Legal's corpus by ≤5 sources × 100 cap
  (Legal `_PER_SOURCE_CAP`) and Broker's by ≤4 × 50 — consistent with existing
  scale. C2 is the only change that materially grows a prompt; its budget guard
  is specified in §5.
- **"Absence ≠ nonexistence" invariant:** Legal's disabled-source note
  (`legal_defense.py:1149/:1181-1185`) automatically covers the new gated
  sources — no extra work, but don't bypass the registry for them.
- **Convention (add one line to root CLAUDE.md when A lands):** *when a new
  `services/*.py` analytics/risk engine lands, the same PR adds its corpus
  records to whichever pilots ground on that domain* — three of the four gaps in
  this plan are that omission, once each.

## 8. Sequencing

| PR | Contents | Depends on |
|---|---|---|
| 1 | **A1 + A2** (property sub-records, risk index) — optional A3 | — |
| 2 | **B1–B5** (leave, charges, termination sources; audit appendix; broker exclusion) | — (independent of PR 1) |
| 3 | **C1 + C2** (floor records + shared cache helper; full-text drafting) | — (independent; touches HR Pilot corpus assembly — run its test suite) |
| 4 | **D** (from-platform datasets) | design confirmation on the loss-run access question |

PRs 1–3 are mutually independent and individually revertible. Each should update
the affected pilot's `_SYSTEM`/prompt cid documentation and the relevant
CLAUDE.md feature-table rows only if behavior described there changes (A/B/C do
not change any flag semantics).
