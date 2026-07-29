# Huume generic record viewer — plan followed

Implemented 2026-07-28 on `matcha/huume-v2`. Started as a one-off "incident viewer" (Huume
couldn't say what an incident *was*, only count them); redirected mid-build into a general
record viewer so any record type Huume can reach — incident, ER case, employee, credential —
opens in the same right-panel component. This is the plan as executed.

## Context

Bug report: "@huume how many incident reports did we get this year" only got a count, because
`lookup_context`'s `incidents` topic returned aggregate counts by type/severity only. Asked "what
was it," Huume had nothing to say and no way to show it. Requirements:

1. Huume should say **what** the incident is — real per-incident detail, not just a count.
2. On request, the record **pops up in the right side panel** — simple text/ASCII layout.
3. Not just incidents — a **general** viewer for whatever Huume references (IR, ER case,
   employee, credential; legal matters keep their existing richer `LegalMatterViewer`).

Design:

- One `show_record(record_type, record_id)` tool.
- One state key `current_state.huume_record`.
- One endpoint returning a **server-normalized view** so a single generic React component
  renders any record. Adding a record type later is a backend-only change — one builder
  function, zero client code.

Privacy line: the **tool result** (model-visible) stays name-free for legal records
(incident/ER — no involved people, witnesses, reporter). The **panel endpoint** runs under the
admin's own auth and may include names — the admin looking at their own record, not the model.
Enforced structurally: the model-facing SQL never selects those columns.

## Normalized view shape (the contract)

```jsonc
{
  "record_type": "incident",
  "record_id": "<uuid>",
  "title": "IR-2026-004 — Slip in warehouse",
  "subtitle": "Safety · High",                    // optional
  "chips": [{ "label": "High", "tone": "orange" }, { "label": "Investigating", "tone": "amber" }],
  "meta":  [{ "label": "Occurred", "value": "2026-07-12 14:30" }],
  "sections": [{ "label": "Description", "body": "…" },
               { "label": "Witnesses", "items": ["Jane Roe — saw the fall"] }],
  "link": "/app/ir/<uuid>"
}
```
`tone ∈ red | orange | amber | emerald | zinc`, decided server-side; client only maps tone→classes.

## Backend

### `server/app/matcha/services/huume/tools.py`
- `SHOW_RECORD_TYPES = ("incident", "er_case", "employee", "credential")` — the single source
  both the tool schema's enum and `record_view.py`'s dispatch table read from.
- `LOOKUP_TOPICS` gained `"er_cases"`.
- `show_record` tool declaration (`record_type` enum + `record_id`), replacing the discarded
  one-off `show_incident` tool.
- `lookup_context` description widened: incidents topic now names per-incident detail + a
  `days` window; new `er_cases` topic; points at `show_record` generically.

### NEW `server/app/matcha/services/huume/record_view.py`
Two builders per record type, kept structurally separate:
- `_model_*` — minimal, name-free summary handed back to the model via
  `show_record_for_model(*, company_id, record_type, record_id, features)`. Gate-before-SQL
  (flag off → `refused`), bad/garbage UUID → `not_found` before any connection opens, unknown
  type → `error`, never raises.
- `_build_*_view` — the fuller normalized view for the panel, via
  `get_record_view(*, company_id, record_type, record_id)` (no gating here — the route does it
  with the caller's own merged features).
- `RECORD_REQUIRED_FEATURE = {"incident": "incidents", "er_case": "er_copilot", "employee":
  "employees", "credential": "credential_templates"}`.
- Per-type tenancy differs (no shared `WHERE`): `ir_incidents.company_id`, `er_cases.company_id`
  (strict — no admin-sees-NULL exception here), `employees.org_id`, and
  `employee_credential_requirements` joined through `employees.org_id` (that table has no
  tenancy column of its own).
- Incident view: severity/status chips, Occurred/Type/Location/Reported-by meta, Description,
  Witnesses (JSONB, normalized), Involved employees (resolved from `involved_employee_ids`),
  Root cause, Corrective actions. Deep-link `/app/ir/{id}`.
- ER case view: status/category/outcome chips, Case#/Opened/Closed meta, Description, Involved
  employees (JSONB, defensive parsing — entries may be dicts or strings). Deep-link
  `/app/er-copilot/{id}`.
- Employee view: employment-status chip, Email/Job title/Department/Location/Start
  date/Employment type/Manager meta (excludes pay, address, emergency contact). Deep-link
  `/app/employees/{id}`.
- Credential view: status chip (+ Overdue chip when applicable), Employee/Category/Due/
  Verified/Waived meta, waiver reason / notes sections. Deep-link
  `/app/employees/{employee_id}?tab=credentials`.

### `server/app/matcha/services/huume/onboarding_skill.py`
- Rewrote the `incidents` lookup branch: still returns counts by type/severity, plus a capped
  (20, truncation-noted) per-incident list with `days`-window clamping (`_clamp_incident_days`,
  default 90/max 365) and a `query` filter — still never `involved_employee_ids`, witnesses, or
  reporter identity.
- New `er_cases` branch: counts by status + a recent 20 (id, case_number, title, status,
  category, outcome) — titles/status only, never description or involved employees.
- `credentials` topic SELECT gained `ecr.id` so a credential is reachable by `show_record`.
- The one-off `show_incident` function was deleted here; its SELECT moved into
  `record_view._model_incident`.

### `server/app/matcha/services/huume/agent.py`
- `show_record` dispatch branch: calls `record_view.show_record_for_model`, stages
  `state_updates["huume_record"] = {record_type, record_id, label}` on success, records a
  `read`-kind step (`ok`/`rejected`/`error` per result status).

### `server/app/matcha/services/huume/prompt.py`
- `build_state_block` bullet for `huume_record`, alongside the existing `huume_legal` one:
  `- A {record_type} record "{label}" (record_id=…) is open in the side panel.`

### `server/app/matcha/routes/matcha_work/huume.py`
- New `GET /threads/{thread_id}/huume/record?record_type=&record_id=` — reuses
  `_get_owned_thread` for tenant scope, re-checks the record type's own feature flag via
  `huume_store.get_thread_features_and_integrations` (403 if off — a flag flipped off after
  Huume staged a record must not leave it fetchable), 404 on unknown type / not found. Mount
  chain already gates `matcha_work` + `huume`.

## Frontend

### `client/src/work/types.ts`
- `HuumeRecordRef { record_type, record_id, label? }` and `HuumeRecordView` (the normalized
  shape above), replacing the discarded one-off `HuumeIncident`.

### `client/src/work/utils/huumeState.ts`
- `HuumeState.record?: HuumeRecordRef`, cast from `state.huume_record`.
- `hasHuumeContent` includes `!!h.record`.
- New `HuumeArtifact` union member `{ kind: 'record'; key; recordType; recordId; label? }`,
  appended after `legal` in `deriveHuumeArtifacts`, keyed `record:${type}:${id}`.

### `client/src/work/api/matchaWork/huume.ts`
- `getHuumeRecord(threadId, recordType, recordId)` → `GET .../huume/record` (barrel-exported via
  the existing `work/api/matchaWork.ts`).

### NEW `client/src/work/components/panels/HuumePanel/RecordViewer.tsx`
Generic renderer (replaces the discarded one-off `IncidentViewer.tsx`, and
`client/src/api/ir/` was deleted along with it): fetch/loading/error idiom + streaming
true→false refetch (mirrors `LegalMatterViewer`), local `Meta`/`Prose` primitives (mirrors
`ActionDocViewer`), mono header box with title + tone-mapped chips + optional subtitle, meta
grid, arbitrary `sections` (body → prose, items → list), footer deep-link. Exports `recordIcon`
(incident→AlertTriangle, er_case→Briefcase, employee→User, credential→BadgeCheck, default→
FileText) for reuse in the tab bar.

### `client/src/work/components/panels/HuumePanel/index.tsx`
- `tabLabel` case for `'record'` using `recordIcon` + the record's label (truncated at 140px in
  the tab).
- Render branch for `active?.kind === 'record'` → `<RecordViewer>`.
- Auto-focus effect on the record's artifact key, declared **before** the existing
  proposed-action focus effect so a simultaneous staged action still wins.

## Tests

- `server/tests/huume/test_huume_lookups.py`: `TestShowRecord` (per-type off-flag refusal,
  unknown-type error, bad-uuid not-found, a feature-gate-completeness assertion over
  `SHOW_RECORD_TYPES`/`RECORD_REQUIRED_FEATURE`); `TestLookupGating` gained an `er_cases`
  off-flag case; `TestClampIncidentDays` (5 cases) unchanged.
- `server/tests/huume/test_huume_prompt.py`: `huume_record` state-block bullet renders /
  is absent when unstaged.
- `client/src/work/utils/huumeState.test.ts`: round-trip, `hasHuumeContent`, artifact ordering
  and keying for the `record` key.

Result: 223 backend huume tests pass, 34 frontend huumeState tests pass, `tsc --noEmit` clean.

## Docs updated

- Root `CLAUDE.md` huume flag row — `lookup_context`/`show_record` description.
- `server/app/matcha/routes/matcha_work/CLAUDE.md` — huume.py now 3 routes (added
  `GET .../huume/record`), package route count 198→199.
- `server/app/matcha/routes/CLAUDE.md` — matcha_work/ route count updated to match.

## Verification

```bash
cd server && ./venv/bin/python -m pytest tests/huume/ -q
cd client && npx tsc -p tsconfig.app.json --noEmit && npx vitest run src/work/utils/huumeState.test.ts
```

Manual (dev stack `:5174`): ask Huume for incident counts "this year" → gets per-incident detail
with the `days` window honored; "show it to me" → right panel opens the record card with a
deep-link to `/app/ir/{id}`; same flow for an ER case / employee / credential once Huume has an
id for one; a company with the relevant flag off gets a refused step and no tab; reloading the
thread keeps the record tab open (`huume_record` persists in `current_state`).

## Post-review fixes (2026-07-29)

A review of this plan against the shipped code (PR #92 comment) found two doc/implementation
mismatches plus several hardening gaps. Fixed in the same PR:

- **`_model_incident`/`_model_er_case` no longer select `description`.** The 280-char snippet
  was model-visible while the root `CLAUDE.md` row (and this file's own privacy line) documented
  the model summary as narrative-free. The column-level no-names guard (no
  `involved_employee_ids`/witnesses/reporter) was real; the free-text narrative — the single
  densest place a legal record names someone — was not excluded. `description` stays searchable
  in `onboarding_skill`'s `incidents` topic (the `query` filter still matches against it
  server-side); it's just never returned to the model.
- **Dropped the dead `is_anonymous` branch** in `_build_incident_view` — no such column exists on
  `ir_incidents` (it's on `vibe_check_configs`/`enps_surveys` only). `SELECT *` + `.get()` made
  this fail silently rather than raise; it always rendered `reported_by_name` in practice.
- **All four panel builders (`_build_*_view`) now select explicit columns**, matching the
  `_model_*` builders — no more `SELECT *`/`ecr.*`/`e.*`. A phantom column now raises
  `UndefinedColumnError` on first call instead of silently degrading to `None`.
- **The `employees m` manager join is tenant-scoped** (`AND m.org_id = e.org_id`), matching every
  other join in the file.
- **Drift-guard test widened** to all four registries (`SHOW_RECORD_TYPES`,
  `RECORD_REQUIRED_FEATURE`, `_MODEL_BUILDERS`, `_VIEW_BUILDERS`) — a type wired into the enum +
  feature map but missing from `_VIEW_BUILDERS` (or vice versa) previously passed silently.
- **New `tests/huume/test_huume_record_view.py`** covers the pure normalization helpers
  (`_parse_uuid`, `_normalize_json_list`, `_iso`) that every builder leans on — zero coverage
  before, since `TestShowRecord` deliberately never reaches past the gate/uuid-parse boundary.
- **`_clamp_incident_days` coerces a digit-string** (`"30"`) instead of silently defaulting to
  90 — still defaults on genuinely non-numeric input or a `bool` (which `isinstance(_, int)`
  would otherwise accept).
- **Panel refocus fixed for a repeat `show_record` on the same id.** `HuumePanel`'s refocus
  effect keyed only on `record_type`+`record_id`, so asking Huume to reopen a record the admin
  had since navigated away from was a no-op (identical key). `agent.py` now stamps
  `huume_record.opened_at` with the turn's `run_id` (a nonce, not a displayed timestamp) on every
  successful `show_record`, and the panel keys its refocus effect on that instead.
- Dead `lightMode` ternary and a redundant `Meta` empty-check removed from `RecordViewer.tsx`
  (the server always fills a meta row's `value`, falling back to `"—"`, so the component only
  needs to render it).

## v2 — plural working set + the 500 + prompt fix (`matcha/huume-v2.1`)

Live testing after merge surfaced three failures at once, screenshotted by the user: asking
Huume "show me the 3 high severity ones" got the incidents typed out in chat (never the panel),
a follow-up panel fetch 500'd, and a busy testing session hit the 60/hr Huume rate limit.

**1. The 500 — `store.get_thread_features_and_integrations`.** asyncpg hands
`companies.enabled_features` back as a plain `str` on every code path in this app (no jsonb
codec is registered anywhere), and this function did
`dict(company_row["enabled_features"] or {})` directly — which iterates the JSON string's
characters and raises `ValueError: dictionary update sequence element #0 has length 1; 2 is
required`. Pre-existing and latent since the function was written (the identical bug sits on the
plan-execute route too); the chat turn path never hit it because `turn_pipeline.py` gets
`features` from the correctly-defensive `get_company_features()` and only calls this function's
integrations half. The new `GET .../huume/record` route was simply the first caller to reach it
from a browser. Fixed by delegating to `get_company_features(company_id, conn=conn)` instead of
hand-rolling the query.

**2. The model narrated instead of showing.** `show_record`'s tool description said to use it
when the admin asks to see a record, but the system prompt's own "How to work" bullet told the
model to "report the facts [lookup_context] returns plainly" with no carve-out for records the
admin asked to *see* — so it followed the instruction it was actually given. Added a "Showing
records — use the side panel, not the chat" prompt section with an explicit rule (call
`show_record` with every id in one call; reply is one line, no record contents) and a
cross-reference from the `lookup_context` bullet.

**3. Plural records — the actual UX fix.** `show_record` took one id; the admin asked for three.
Per the user's confirmed preference, the panel now **accumulates** an open-record working set
instead of showing one record at a time:

- `show_record(record_type, record_ids)` — up to 8 ids per call.
- `record_view.show_records_for_model` resolves every id it can (a partial hit is still `"ok"`
  with a `not_found` list); pre-parses UUIDs *before* opening a connection so an all-garbage
  batch short-circuits to `not_found` without touching the DB (needed for the gate tests to stay
  DB-free — the naive per-id-inside-the-loop version broke this).
- `record_view.merge_open_records` (pure) — append, dedupe-and-refocus a repeat `show_record` on
  an already-open id (moves it to the end), cap at `MAX_OPEN_RECORDS = 8` dropping from the
  front.
- `current_state.huume_records` (a list) replaces the singular `huume_record`. Two writers now
  exist (the chat tool, the panel's new close button), so writes go through a new
  `store.update_huume_records` — row-locked read-modify-write, same hazard `update_huume_plan`'s
  docstring documents (`apply_update`'s wholesale top-level merge has no lock between a
  concurrent read and write).
- New `DELETE /threads/{id}/huume/record` closes one tab (no feature re-check — closing a stale
  entry must survive a flag flip).
- `HuumePanel/index.tsx`: tab strip renders whenever a record is open (not just when
  `artifacts.length > 1`, since a single open record still needs its own close control); each
  record tab gets an inline `×`; the auto-focus effect keys off the **last** entry (newest, since
  `merge_open_records` appends) instead of a single slot.
- Rate limit `huume_turn` 60/hr → 200/hr/company (`turn_pipeline.py`).

Tests: new `tests/huume/test_huume_store.py` (regression for the 500 — mocks `get_connection` to
return `enabled_features` as a **string**, proving the old code would have raised);
`TestShowRecords`/`TestMergeOpenRecords` in `test_huume_lookups.py`; `test_huume_prompt.py`'s
record-pointer tests reworked for the list. 252 backend huume tests pass; 37 frontend
`huumeState.test.ts` tests pass; `tsc --noEmit` clean.
