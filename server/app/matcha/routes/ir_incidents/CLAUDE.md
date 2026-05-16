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
| `osha.py` | 300/301/300A logs + CSV + recordability + AI determine | 7 |
| `documents.py` | Upload, list, delete incident documents | 3 |
| `anonymous_reporting.py` | Public token mgmt for `/report/:token` form | 3 |
| `audit_log.py` | Get audit trail for an incident | 1 |
| **Total** | | **48 routes** |

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
- `_parse_occurred_at`, `generate_incident_number`, `send_ir_notifications_task` ← `_shared.py` (used by `inbound_email.py` — public anonymous-report intake)
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
2. Submodules append via `include_router` in this order: anonymous_reporting → documents → osha → investigation_interviews → ai_analysis → analytics → copilot → audit_log.

Safe because `/{incident_id}` (1-segment) cannot match any 2+segment submodule path. The only 1-segment static route is `/export`, which lives in `crud.py` ordered BEFORE `/{incident_id}` (preserved from the original file order).

**Don't add a 1-segment static route to a submodule** — it would be shadowed by CRUD's `/{incident_id}` catch-all registered earlier. Put 1-segment routes in `crud.py`.

## Common pitfalls

- **Circular imports between `_legacy`-era modules**: ai_analysis.py and crud.py both reference `_auto_map_policy_violations`. To avoid a circular module-level import, CRUD does a **lazy** `from .ai_analysis import _auto_map_policy_violations` inside its function bodies (three callsites: `create_incident`, `update_incident`, and an inline copilot path that was already moved). Keep this pattern if any submodule needs to call functions defined in a later-loaded submodule.
- **Absolute imports throughout**: every submodule uses `from app.X import …`, not `from ..X` or `from ...X`. The relative-imports-to-absolute conversion was pre-step-0 of the split; new code should keep using absolute paths so the file can be moved without breaking imports.
- **Don't define `_safe_json_loads` again**: it's in `_shared.py` (singular definition — the original flat file had two duplicate defs that got deduped during the migration). Same for `_sse`, `log_audit`, `parse_witnesses`, `row_to_response`.

## Tests

- `server/tests/ir_incidents/test_ir_incidents.py` — 116 passing unit tests covering pure helpers + scoring math.
- `server/tests/test_ir_copilot_smoke.py` — copilot smoke that imports modules without booting the app.
- Run: `cd server && ./venv/bin/python -m pytest tests/ir_incidents/ tests/test_ir_copilot_smoke.py -q`
- Don't add tests that boot the full FastAPI app + DB unless you're prepared to require the SSH tunnel — keep unit tests fast (current suite is 132 tests / 0.4s).
