# IR Incidents Routes Package

Backend routes for matcha-lite's Incident Reporting product. Package was split from a 5,061-line flat `ir_incidents.py` into per-domain submodules. URL surface unchanged; external import path `app.matcha.routes.ir_incidents` stable.

## Layout

| File | Concern | Endpoints |
|---|---|---|
| `__init__.py` | Routing assembly + external re-exports | — |
| `_shared.py` | Cross-cutting helpers + shared constants. DB-backed card dispatchers (`next_case_step` / `ensure_osha_case_rows` / `_persist_osha_emergency_alert`) stay here and import the builders from `services/ir/ir_cards.py` directly (`_cards.py`, a thin re-export shim over that module, was deleted — it had exactly one importer). The pure, no-DB/no-routes helpers (`_parse_occurred_at`, `generate_incident_number`, `_detect_osha_reportable_keywords`, `_to_naive_utc`, `_utc_now_naive`, `_safe_json_loads`) moved to `services/ir/ir_incident_parsing.py` and `services/_shared/{time,jsonio}.py`, and `_shared.py` aliases them back in — this is what let `services/ir/ir_incident_create.py`, `ir_wc_metrics.py`, and `ir_osha_cases.py` stop lazily importing this package (which runs the whole IR router `__init__.py`, ~2,300 modules / ~2s cold) just to reach a regex match or a `datetime.now()` call | — |
| `crud.py` | Collection root + per-incident lifecycle (+ `_report_html.py`, the pure single-incident PDF HTML builder, lifted out 2026-07-27) | 8 |
| `copilot.py` | IR Copilot transcript, stream, accept, skip, close. The card/chain **state machine** (chain emitters, the OSHA description + recordable chains, the quick-reply/numeric/text input handlers, `_close_incident_via_copilot`, corrective-action seeding, transcript coercion, the protected-card guard) moved to `services/ir/ir_copilot_flow.py` 2026-07-27; `copilot.py` re-exports every name, so existing imports and tests are unchanged | 5 |
| `analytics.py` | Summary, trends, locations, WC metrics, risk-matrix, risk-insights, consistency | 9 |
| `ai_analysis.py` | Categorize, severity, root-cause, recommendations, similar, policy-mapping, clear-cache | 9 |
| `investigation_interviews.py` | Create, batch, resend, generate-link, list, cancel witness interviews | 6 |
| `people.py` | Per-person identity (no-roster): search + per-person role-aware history | 2 |
| `capa.py` | Structured corrective actions (CAPA): per-incident list/create + per-action update/delete + company-wide open/overdue list. Table `ir_corrective_actions` (migration `ircapa01`); accountable layer over the free-text `corrective_actions` column. Owner/due-date/status/effectiveness. The deadline worker (`ir_deadline_alerts`) chases these. | 7 |
| `osha/` | 300/301/300A logs + CSV + **300A PDF + save** + recordability + AI determine + **ITA bulk export/validate** (per-establishment) — **package** (split 2026-07-27, fresh-aggregator): `logs.py` (300 log + CSV + privacy cases + 301), `summary_300a.py` (300A view/save/PDF/CSV), `ita.py` (validate/CSV/credentials/submit/history), `recordability.py` (manual update + AI determine), `_shared.py` (attestation gate + 300A aggregation + headcount), `_pdf.py` (WeasyPrint Form 300A template, was `_osha_pdf.py`). The 4 groups share no state beyond `_shared.py`. `__init__.py` re-exports `_missing_ita_fields` / `_mask_from_reason` / `_resolve_osha_description` / `_injured_persons` / `_osha_case_views` / `_attest_export` / `EXPORT_DISCLAIMER` so `from …ir_incidents.osha import X` is unchanged | 16 |
| `documents.py` | Upload, list, delete incident documents | 4 |
| `anonymous_reporting.py` | Token mgmt: company-wide `/report/:token` + per-location `/intake/:token` magic links | 11 |
| `info_requests.py` | IR Copilot "Request More Info": admin-side token create/list/resend/revoke for the public `/request-info/:token` form (public GET/POST live in `inbound_email.py`) | 4 |
| `audit_log.py` | Get audit trail for an incident | 1 |
| `broker_sharing.py` | Broker visibility opt-in for an incident | 3 |
| `claims_readiness.py` | Claims-readiness packet for an incident | 1 |
| `voice.py` | `POST /voice/parse` — Gemini dictation intake (`ir_voice_intake`) | 1 |
| **Total** | | **87 routes** (per-file counts re-derived from the live route table 2026-07-27; the previous numbers had drifted) |

**No-roster people index** (`people.py` + `ir_people` / `ir_incident_people` tables, migration `irp1a2b3c4d5e`): people named in incidents (reporter / involved / witness / interviewee) are auto-indexed for per-person history WITHOUT a managed employee roster. Identity = the typed name, normalized for dedup (`_normalize_person_name`, `_gather_incident_people`, `_sync_incident_people` — moved to `services/ir/ir_people_index.py`, refactor round 2 stage 3). Wired into `crud.create_incident` / `update_incident` (roles reporter/involved/witness, re-synced on edit) and `investigation_interviews` (role interviewee, managed separately so an incident edit's re-sync won't drop it). Distinct from `involved_employee_ids`, which targets the real `employees` roster. The truly-anonymous `/report/:token` intake (`inbound_email.py`) intentionally does NOT auto-mint people; the attributed per-location `/intake/:token` magic link DOES, since it shares `create_incident_core` with the authed create. Endpoints use 2+ segment paths (`/people/search`, `/people/{id}/incidents`) to avoid the `/{incident_id}` shadow.

## Package router pattern

The package's exported `router` is **`crud.router` directly** — not a wrapping `APIRouter()`. CRUD owns the empty-path collection routes (`@router.post("")`, `@router.get("")`); wrapping it in a bare parent would trip FastAPI's "Prefix and path cannot be both empty" check. All other submodules append into `crud.router` via `router.include_router(...)` in `__init__.py`.

**Consequence**: when adding a new submodule, **never use `@router.X("")` (empty path)**. The empty-path routes only work on the outermost router and that is reserved for CRUD.

## Adding a new endpoint

1. Find the right submodule by domain (or create one if genuinely new).
2. In that submodule, `router = APIRouter()` already exists. Add `@router.<method>("/<path>", ...)`.
3. Helpers come from `from ._shared import ...`. Don't define them locally if `_shared.py` already has them.
4. Tenant isolation: every endpoint that takes `incident_id` must call `_get_incident_with_company_check(conn, incident_id, current_user)` from `_shared` — it raises 404 on cross-company access.
5. Audit: write-side actions go through `await log_audit(conn, ...)` from `_shared`.
6. If new submodule: add `from .<name> import router as _<name>_router; router.include_router(_<name>_router)` to `__init__.py`.

## Adding a new IR Copilot action type

When the AI emits a new action card type (currently `run_analysis`, `set_field`, `request_info`, `escalate`, `close_incident`):

1. `client/src/components/ir/IRCopilotCard.tsx:5` — extend the `CopilotCardAction.type` union.
2. `app/matcha/services/ir/ir_ai_orchestrator.py` — add to `IR_ACTION_TYPES` set and the prompt-template guidance section.
3. `app/matcha/routes/ir_incidents/copilot.py` — add the `elif action_type == "<new>"` branch in `accept_copilot_card` (the only part of the copilot that is still in the route file; the handlers it dispatches to live in `services/ir/ir_copilot_flow.py`). Set `event_summary` and `event_extra` appropriately. The trailing `append_message` + `log_audit` block already handles the rest.

## External symbols re-exported by `__init__.py`

Other routers consume these via `from .ir_incidents import …`. Keep the re-exports working when moving things around:

- `compute_wc_metrics`, `compute_behavioral_friction` ← `services/ir/ir_wc_metrics.py` (used by `broker_portfolio.py` / `broker/risk_index.py` / `broker/submission_readiness.py` / the `broker_risk_alerts` and `broker_milestones` Celery tasks — all of which import these directly from `services.ir.ir_wc_metrics`, not through this package, specifically so they don't boot the router `__init__.py`). `compute_behavioral_friction` currently has no live caller — `_run_broker_risk_alerts` builds its metrics from `compute_wc_metrics` alone, so the fully-implemented "Behavioral Friction" alert branch can't fire; pre-existing gap, tracked in the function's own docstring.
- `_parse_occurred_at`, `generate_incident_number` ← `services/ir/ir_incident_parsing.py`, `create_incident_core` ← `services/ir/ir_incident_create.py`, `send_ir_notifications_task` ← `services/ir/ir_notifications.py` — all three aliased through `_shared.py`. `send_ir_info_request_notification_task`, `_location_label` are genuinely local to `_shared.py`. All (used by `inbound_email.py` — public `/report` + `/intake` + `/request-info` intake). `create_incident_core` is the shared INSERT→people-index→OSHA→bg-task tail used by both `crud.create_incident` and the public location magic-link submit; the caller owns the (tenant-scoped) connection and schedules the returned bg tasks. `_build_public_link` also lives in `_shared.py` (moved there from `anonymous_reporting.py` when `info_requests.py` needed it too) — any submodule minting a public token URL should import it from there, not redefine it.
- `_close_incident_via_copilot`, `resume_copilot_after_info_request` ← `copilot.py`, which now re-exports them from `services/ir/ir_copilot_flow.py` (`resume_copilot_after_info_request` is used by `intake/inbound_email.py`; `ensure_case_chain` is lazily imported by `osha/recordability.py`)

## Mounting + feature gate

Parent mount in `app/matcha/routes/__init__.py:64`:
```python
matcha_router.include_router(ir_incidents_router, prefix="/ir/incidents", tags=["ir-incidents"],
                             dependencies=[Depends(require_feature("incidents"))])
```
- Prefix and feature-gate live there — **do not** add them inside this package.
- `require_feature("incidents")` stacks through `include_router`, so every submodule transparently inherits the gate. Don't re-declare it.

## Trailing-slash trap

The collection root uses `@router.post("")` (empty string), NOT `@router.post("/")`. FastAPI does NOT normalize these — `POST /ir/incidents` and `POST /ir/incidents/` behave differently. Preserve `""` exactly. The OpenAPI-diff verification in the split plan caught this.

## Route ordering

In a single `APIRouter`, FastAPI matches routes in registration order. Today:
1. CRUD routes register first (because `crud.router` is the package router).
2. Submodules append via `include_router` in this order: anonymous_reporting → info_requests → documents → osha → investigation_interviews → people → ai_analysis → analytics → copilot → audit_log → claims_readiness → voice.

Safe because `/{incident_id}` (1-segment) cannot match any 2+segment submodule path. The only 1-segment static route is `/export`, which lives in `crud.py` ordered BEFORE `/{incident_id}` (preserved from the original file order).

**Don't add a 1-segment static route to a submodule** — it would be shadowed by CRUD's `/{incident_id}` catch-all registered earlier. Put 1-segment routes in `crud.py`.

## Common pitfalls

- **Circular imports between `_legacy`-era modules**: ai_analysis.py, crud.py, and `services/ir/ir_incident_create.py` all reference `_auto_map_policy_violations`. To avoid a circular module-level import it's a **lazy** `from .ai_analysis import _auto_map_policy_violations` inside function bodies (callsites: `ir_incident_create.create_incident_core` — the shared create tail, now used by both `crud.create_incident` and the public location intake — `crud.update_incident`, and an inline copilot path). Keep this pattern if any submodule needs to call functions defined in a later-loaded submodule.
- **Absolute imports throughout**: every submodule uses `from app.X import …`, not `from ..X` or `from ...X`. The relative-imports-to-absolute conversion was pre-step-0 of the split; new code should keep using absolute paths so the file can be moved without breaking imports.
- **Don't define `_safe_json_loads` again**: the real definition is `services/_shared/jsonio.py:safe_json_loads` (singular — the original flat file had two duplicate defs that got deduped during the migration), aliased into both `_shared.py` and `osha/_shared.py` so `from ._shared import _safe_json_loads` keeps working at either level. Same singular-definition rule for `_sse`, `log_audit`, `parse_witnesses`, `row_to_response` (still local to `_shared.py`). The 2026-07-27 osha/ split left a second copy here and this doc recorded it as a permanent exception on "different default semantics" (`None` vs `{}`) — that was wrong: all 8 OSHA call sites pass an explicit `{}`, so the divergent branch was unreachable, and the values come from JSONB columns with no asyncpg codec (always `str`/None), so the one remaining disagreement (a bare int) can't occur either. Unified in the stage-4/5 audit after checking every call site.

- **Patching a Copilot collaborator: there are THREE possible targets, and
  picking the wrong one fails SILENTLY (the real DB/Gemini gets called and the
  test still reads green).** Pick by where the *calling* function is defined:

  | The function doing the calling lives in… | Patch |
  |---|---|
  | `services/ir/ir_copilot_flow.py`, calling a `_shared` helper via the `_ir` proxy | `ir_incidents._shared` |
  | `services/ir/ir_copilot_flow.py`, calling something defined in that same module | `ir_copilot_flow` |
  | `routes/ir_incidents/copilot.py` (i.e. a route body) | `copilot` |

  The first row exists because a plain `from ...ir_incidents._shared import X` at
  the flow module's scope is a live cycle (importing the flow imports this
  package, whose `__init__` imports `copilot.py`, which imports the flow back,
  half-built). The `_ir` proxy re-resolves each attribute off `_shared` on every
  access, so patching `_shared` works and patching `copilot` is ignored — see
  `tests/ir_incidents/test_osha_privacy_case.py`'s `next_case_step` patch.

  The third row is the one a stale comment in `copilot.py` used to deny: that
  file re-exports ~40 flow names with `from … import`, which **binds them into
  its own namespace at import time**. A route body therefore reads
  `copilot.X`, not `ir_copilot_flow.X`, and patching the flow module does not
  reach it.

## Tests

- `server/tests/ir_incidents/test_ir_incidents.py` — 116 passing unit tests covering pure helpers + scoring math.
- `server/tests/test_ir_copilot_smoke.py` — copilot smoke that imports modules without booting the app.
- Run: `cd server && ./venv/bin/python -m pytest tests/ir_incidents/ tests/test_ir_copilot_smoke.py -q`
- Don't add tests that boot the full FastAPI app + DB unless you're prepared to require the SSH tunnel — keep unit tests fast (current suite is 132 tests / 0.4s).

## Feature flags (full specs, moved from root CLAUDE.md)

## `ir_voice_intake` (default ❌)

**Voice dictation on the IR create form** (all IR products — shared `IRCreateIncidentModal`). Optional "Dictate" button: the reporter records a spoken account → one Gemini multimodal call transcribes + extracts the form fields (`services/ir/ir_voice_parser.py`) → prefills description / reporter / date / location / witnesses + a suggested type/severity hint, which the user **reviews and edits before submitting** (never auto-creates — it's a legal record). Audio captured as WAV via the existing PCM AudioWorklet (Gemini rejects `MediaRecorder` webm/opus). Gates `POST /ir/incidents/voice/parse` (2-segment, stacks on the `incidents` gate) + the button (`hasFeature('ir_voice_intake')`). Default off; admin-toggle; NOT bundled.

## `osha_logs` (default ✅)

Interactive OSHA 300/301/300A recordkeeping within IR (`ir_incidents/osha/`, a package since 2026-07-27). Default on — forced **off** for the no-roster `matcha_lite_essentials` config (no employee roster to log injured persons against). Sub-gates the interactive-only endpoints (300 log JSON, 301 form, privacy cases, 300A PDF, AI recordability determination) via a per-route `_gate=Depends(require_feature("osha_logs"))`; the CSV/export endpoints instead ride `osha_logs` OR `osha_export` (see that flag) via `require_any_feature` on the `osha/` sub-router include. Gates the full `/app/ir/osha` page (export-only tenants get a stripped view — see `osha_export`) + the OSHA Logs sidebar entry.

## `osha_export` (default ❌)

**CSV-download-only** slice of OSHA logging, split out of `osha_logs` (2026-07-30) so `/admin/products` can compose "OSHA export without the interactive log UI" (e.g. a cheap Lite tier). Gates 300-log CSV, 300A view/save/CSV, and the manual (non-AI) recordability write — together with `osha_logs` via `require_any_feature("osha_logs","osha_export")` on the `osha/` `logs.py`/`summary_300a.py`/`recordability.py` sub-routers. **Default OFF, deliberately additive** — every existing `osha_logs` tenant already passes the `require_any_feature` check without this flag stored, so it needs no backfill; a tenant with `osha_logs` off (essentials, or an admin toggle) must NOT silently regain OSHA capability, which a default-True would have caused. Not in `FEATURE_REQUIRES` — see `ir_copilot`'s row for why.

## `ir_magic_links` (default ✅)

**All public token intake** for IR: anonymous company-wide `/report/:token`, per-location `/intake/:token`, and single-use `/request-info/:token`, plus their admin-side token-mgmt routers (`anonymous_reporting.py`, `info_requests.py`). Split out of `incidents` (2026-07-30) so `/admin/products` can compose without it. **Default ON and deliberately SUBTRACTIVE** (unlike the OSHA pair above) — its parent is `incidents` itself, and the `ir_incidents` router mount already requires that, so an any()-with-incidents gate would be a no-op; the only way to withhold it is a stored explicit `False` (a materialized product tenant, or an admin toggle). Consequence: every `enabled_features` write that stomps the whole dict to `False` and then re-grants `incidents` (`TIER_SIGNUP_PRESETS["matcha_lite"/"matcha_lite_essentials"/"matcha_x"/"ir_only_self_serve"]`, and the matching branches in `routes/auth/register_business.py`) must ALSO re-grant this flag, or the stomp silently denies it — caught by review on PR #103 after the initial default-True-with-no-reassertion version broke every real Lite/X/IR signup. The public endpoints in `routes/intake/inbound_email.py` read the company's **raw stored** `enabled_features` (not the merged/overlaid shape) and treat a missing key as **allowed** (matches the default) — only an explicit `False` blocks them; see `_public_intake_allowed`.

## `ir_copilot` (default ✅)

IR Copilot chat **and** the per-incident AI analysis runners (categorize/severity/root-cause/recommendations/similar/policy-mapping), split out of `incidents` (2026-07-30) as one combined sellable unit. Same subtractive-default rules as `ir_magic_links` — see that row. Neither this flag nor `ir_magic_links` is in `FEATURE_REQUIRES`: the route-level gates already make them inert without `incidents`, and enforcing the dependency there broke `PATCH /admin/company-features` (couldn't disable `incidents` on any company with a default-True dependent) and `PATCH .../tier` for `tier="bespoke"` (whose preset carries the pair True with no `incidents` key at all) — also caught on PR #103.

## `osha_auto_report` (default ❌)

**Electronic ITA submission** (`osha/ita.py` — validate/export.csv/credentials/submit/submissions; already built, just re-gated), split out of `osha_logs` so it can be priced/withheld separately from the log UI. Default off, additive, same rationale as `osha_export`.
