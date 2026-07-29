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
