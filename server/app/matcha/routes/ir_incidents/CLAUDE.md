# IR Incidents Routes Package

Backend routes for matcha-lite's Incident Reporting product. Package was split from a 5,061-line flat `ir_incidents.py` into per-domain submodules. URL surface unchanged; external import path `app.matcha.routes.ir_incidents` stable.

## Layout

| File | Concern | Endpoints |
|---|---|---|
| `__init__.py` | Routing assembly + external re-exports | — |
| `_shared.py` | Cross-cutting helpers + shared constants | — |
| `crud.py` | Collection root + per-incident lifecycle | 7 |
| `copilot.py` | IR Copilot transcript, stream, accept, skip, close | 5 |
| `analytics.py` | Summary, trends, locations, WC metrics, risk-matrix, risk-insights, consistency | 7 |
| `ai_analysis.py` | Categorize, severity, root-cause, recommendations, similar, policy-mapping, clear-cache | 9 |
| `investigation_interviews.py` | Create, batch, resend, generate-link, list, cancel witness interviews | 6 |
| `people.py` | Per-person identity (no-roster): search + per-person role-aware history | 2 |
| `osha.py` | 300/301/300A logs + CSV + **300A PDF + save** + recordability + AI determine + **ITA bulk export/validate** (per-establishment; `_osha_pdf.py` holds the WeasyPrint Form 300A template) | 11 |
| `documents.py` | Upload, list, delete incident documents | 3 |
| `anonymous_reporting.py` | Token mgmt: company-wide `/report/:token` + per-location `/intake/:token` magic links | 6 |
| `info_requests.py` | IR Copilot "Request More Info": admin-side token create/list/resend for the public `/request-info/:token` form (public GET/POST live in `inbound_email.py`) | 3 |
| `audit_log.py` | Get audit trail for an incident | 1 |
| **Total** | | **60 routes** |

**No-roster people index** (`people.py` + `ir_people` / `ir_incident_people` tables, migration `irp1a2b3c4d5e`): people named in incidents (reporter / involved / witness / interviewee) are auto-indexed for per-person history WITHOUT a managed employee roster. Identity = the typed name, normalized for dedup (`_normalize_person_name`, `_gather_incident_people`, `_sync_incident_people` in `_shared.py`). Wired into `crud.create_incident` / `update_incident` (roles reporter/involved/witness, re-synced on edit) and `investigation_interviews` (role interviewee, managed separately so an incident edit's re-sync won't drop it). Distinct from `involved_employee_ids`, which targets the real `employees` roster. The truly-anonymous `/report/:token` intake (`inbound_email.py`) intentionally does NOT auto-mint people; the attributed per-location `/intake/:token` magic link DOES, since it shares `create_incident_core` with the authed create. Endpoints use 2+ segment paths (`/people/search`, `/people/{id}/incidents`) to avoid the `/{incident_id}` shadow.

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
2. `app/matcha/services/ir_ai_orchestrator.py` — add to `IR_ACTION_TYPES` set and the prompt-template guidance section.
3. `app/matcha/routes/ir_incidents/copilot.py` — add the `elif action_type == "<new>"` branch in `accept_copilot_card`. Set `event_summary` and `event_extra` appropriately. The trailing `append_message` + `log_audit` block already handles the rest.

## External symbols re-exported by `__init__.py`

Other routers consume these via `from .ir_incidents import …`. Keep the re-exports working when moving things around:

- `compute_wc_metrics` ← `analytics.py` (used by `broker_portfolio.py`)
- `_parse_occurred_at`, `generate_incident_number`, `send_ir_notifications_task`, `send_ir_info_request_notification_task`, `create_incident_core`, `_location_label` ← `_shared.py` (used by `inbound_email.py` — public `/report` + `/intake` + `/request-info` intake). `create_incident_core` is the shared INSERT→people-index→OSHA→bg-task tail used by both `crud.create_incident` and the public location magic-link submit; the caller owns the (tenant-scoped) connection and schedules the returned bg tasks. `_build_public_link` also lives in `_shared.py` (moved there from `anonymous_reporting.py` when `info_requests.py` needed it too) — any submodule minting a public token URL should import it from there, not redefine it.
- `_close_incident_via_copilot` ← `copilot.py` (future cross-router; currently only used internally)

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

- **Circular imports between `_legacy`-era modules**: ai_analysis.py, crud.py, and `_shared.py` all reference `_auto_map_policy_violations`. To avoid a circular module-level import it's a **lazy** `from .ai_analysis import _auto_map_policy_violations` inside function bodies (callsites: `_shared.create_incident_core` — the shared create tail, now used by both `crud.create_incident` and the public location intake — `crud.update_incident`, and an inline copilot path). Keep this pattern if any submodule needs to call functions defined in a later-loaded submodule.
- **Absolute imports throughout**: every submodule uses `from app.X import …`, not `from ..X` or `from ...X`. The relative-imports-to-absolute conversion was pre-step-0 of the split; new code should keep using absolute paths so the file can be moved without breaking imports.
- **Don't define `_safe_json_loads` again**: it's in `_shared.py` (singular definition — the original flat file had two duplicate defs that got deduped during the migration). Same for `_sse`, `log_audit`, `parse_witnesses`, `row_to_response`.

## Tests

- `server/tests/ir_incidents/test_ir_incidents.py` — 116 passing unit tests covering pure helpers + scoring math.
- `server/tests/test_ir_copilot_smoke.py` — copilot smoke that imports modules without booting the app.
- Run: `cd server && ./venv/bin/python -m pytest tests/ir_incidents/ tests/test_ir_copilot_smoke.py -q`
- Don't add tests that boot the full FastAPI app + DB unless you're prepared to require the SSH tunnel — keep unit tests fast (current suite is 132 tests / 0.4s).
