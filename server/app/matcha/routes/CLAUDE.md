# Matcha Routes Zoo

29 routers, ~39,000 lines. Aggregated in `__init__.py` and mounted onto `matcha_router`. Each router corresponds to one product surface or sub-feature.

Loose single-file routers sit at top level; related ones are collected into **grouping folders** (`broker/`, `insurance/`, `pilots/`, `onboarding/`, `intake/`, `employee_lifecycle/`, `work/`, `integrations/` — see below).

**Naming trap:** a grouping folder must not share a name with a top-level module in the same directory — in Python the package shadows the module, so the module silently becomes unimportable. This is why the Coterie carrier router lives at `insurance/carrier.py` rather than staying `insurance.py` beside the `insurance/` package, and why `broker_insurance.py` became `broker/insurance.py`. Check for a same-named `.py` before adding a grouping folder. Grouping folders differ from the split-router packages (`employees/`, `ir_incidents/`, `er_copilot/`, `matcha_work/`, `employee_schedule/`, `labor_relations/`): a split-router package is **one** router carved into submodules; a grouping folder namespaces **several independent** routers, each still self-mounted + self-gated in `__init__.py`. Its `folder/__init__.py` only re-exports the sub-routers under their historical `*_router` names, so the top aggregator's mount block is unchanged by the grouping.

## Router map (by domain)

| Router file | Prefix | Owns |
|---|---|---|
| `companies.py` | `/companies` | Company CRUD + admin tooling |
| `employees/` | `/employees` (+ `/employees/pto`, `/employees/leave`) | Employee CRUD, bulk upload, invitations, onboarding, offboarding, credentials, OIG, leave, incidents, pto/leave admin — **package** (split 2026-05-16; see `employees/CLAUDE.md`) |
| `employee_portal.py` | `/v1/portal` | Employee-facing self-service portal (incl. `/me/schedule*` — view published shifts + file swap/drop/unavailability requests, gated `employee_schedule`) |
| `portal_ask_hr.py` | `/v1/portal/ask-hr` | Employee "Ask HR" — grounded, citation-gated policy Q&A (SSE chat + sessions/messages CRUD). Reuses the HR Pilot corpus + the `hr_pilot_escalation` hard stop, which runs **in the route before any model call**. `require_employee_record` per endpoint; `require_feature("ask_hr")` at the mount |
| `employee_schedule/` | `/employee-schedule` | Employee shift scheduling — shift CRUD + publish + weekly view (`shifts.py`), assignment (`assignments.py`), templates + recurrence generation (`templates.py`), admin request review (`requests.py`). **Package**; `require_feature("employee_schedule")` |
| `onboarding/new_hire.py` | `/onboarding` | New-hire onboarding tasks + notification settings |
| `onboarding/invitations.py` | `/invitations` | Token-based invite acceptance |
| `employee_lifecycle/offer_letters.py` | `/offer-letters` | Offer letter creation, signing, candidate portal (1,288 lines) |
| `interviews.py` | — | Live interview WS + transcript handling (1,522 lines) |
| `er_copilot/` | `/er/cases` (+ `/shared/er-export`) | Employee Relations case mgmt + AI — **package** (split 2026-07-06, 43 routes; see `er_copilot/CLAUDE.md`) |
| `ir_incidents/` | `/ir/incidents` | Incident reporting (matcha-lite) — **already a package** (50 routes incl. no-roster people index), see `ir_incidents/CLAUDE.md` |
| `onboarding/ir.py` | `/ir-onboarding` | IR-only onboarding wizard backend |
| `ir_surveys.py` | `/ir/surveys` | Security survey CRUD (matcha-lite) |
| `intake/inbound_email.py` | (none) | Public intake: anonymous `/report/:token` + per-location magic-link `/intake/:token` forms |
| `employee_lifecycle/accommodations.py` | `/accommodations` | ADA accommodation cases (1,175 lines) |
| `employee_lifecycle/discipline.py` | `/discipline` | Progressive discipline workflow + signatures |
| `risk_assessment.py` | `/risk-assessment` | Risk-assessment dashboard data (849 lines) |
| `pilots/analysis.py` | `/analysis-pilot` | Analysis Pilot — general-purpose bring-your-own-data analysis in a chat UI (upload CSV/XLSX/PDF → deterministic `services/analysis_packs` metrics incl. volatility/risk, financial, insurance, inventory, general stats → grounded SSE chat with highlight-to-chat + proposed extraction corrections → analyst PDF). Company-scoped; `require_feature("analysis_pilot")` |
| `employee_lifecycle/pre_termination.py` | `/pre-termination` | Pre-term review packets (985 lines) |
| `employee_lifecycle/separation.py` | `/separation` | Separation agreement workflow |
| `employee_lifecycle/flight_risk.py` | `/flight-risk` | Flight-risk scoring per employee |
| `employee_lifecycle/training.py` | `/training` | Training programs + completions (1,138 lines) |
| `employee_lifecycle/i9.py` | `/i9` | I-9 verification |
| `employee_lifecycle/cobra.py` | `/cobra` | COBRA admin |
| `dashboard.py` | `/dashboard` | Cross-feature dashboard aggregation (2,141 lines) |
| `broker/brokers.py` | `/brokers` | HR broker admin (1,605 lines) |
| `broker/portfolio.py` | `/broker-portfolio` | Per-broker client roster + cross-client metrics |
| `fractional_hr.py` | `/fractional-hr` | Fractional HR engagement tooling — internal master-admin only (`require_admin` at mount, **not** feature-gated). Clients/scope/tasks/time + aggregate book-of-business overview. `fractional_*` tables; `company_id` nullable (client may have no tenant) |
| `integrations/provisioning/` | `/provisioning` | Google Workspace + Slack + HRIS (Gusto/Finch) auto-provision — **split-router package** (J7, 2026-07-20): `_models.py` (16 Pydantic models), `_shared.py` (json/bool/comma + `_run_payload`), `google.py`, `slack.py`, `runs.py`, `hris.py`; `__init__.py` aggregates the four sub-routers into one `router`. All routes carry full paths so mount order is cosmetic. 29 routes |
| `matcha_work/` | (multiple: `/matcha-work`, `/matcha-work/public`, `/matcha-work/presence`) | Matcha-work projects/threads/tasks/recruiting/AI turns — **package** (split 2026-07-03, 204 routes; see `matcha_work/CLAUDE.md`) |
| `work/journals.py` | `/journals` | Matcha-work journals |
| `billing.py` | (multiple) | Stripe billing + token packs |
| `work/notifications.py` | `/notifications` | Matcha-work notifications |
| `integrations/fake_hris.py` | `/fake-hris` | Mock HRIS connector for demos |
| `work/thread_ws.py` | `/threads` | Matcha-work thread websocket |
| `integrations/twilio_webhook.py` | `/twilio` | Twilio inbound for voice surfaces |

## Grouping folders (namespace only — not split-router packages)

Each folder's `__init__.py` re-exports the members' routers under their historical
`*_router` names; the top `__init__.py` imports those names from the folder and mounts each
member with its own prefix + gate (unchanged). None of these members cross-import a sibling, so
every moved file uses **absolute** imports (`from app.matcha.services.X import …`,
`from app.database import …`); no intra-folder relative imports.

| Folder | Members (file → router) |
|---|---|
| `employee_lifecycle/` | `accommodations`→accommodations_router, `cobra`→cobra_router, `discipline`→discipline_router + discipline_public_router, `flight_risk`→flight_risk_router, `i9`→i9_router, `offer_letters`→offer_letters_router + offer_letters_candidate_router, `pre_termination`→pre_termination_router, `separation`→separation_router, `training`→training_router (HR workflows across an employee's tenure; each its own feature gate) |
| `work/` | `journals`→journals_router, `notifications`→mw_notifications_router, `project_ws`→project_ws_router, `thread_ws`→thread_ws_router (matcha-work web surfaces; the two WS modules also expose non-router symbols — `thread_manager`, `broadcast_task_event`, project-fanout start/stop — imported directly by module path, e.g. `app.matcha.routes.work.thread_ws`, not fronted by the package) |
| `integrations/` | `fake_hris`→fake_hris_router, `provisioning`→provisioning_router, `twilio_webhook`→twilio_webhook_router (external integrations + inbound webhooks; no feature gate) |

## Mounting convention

Every router lands through `__init__.py` with three knobs:
```python
matcha_router.include_router(<name>_router, prefix="/<path>", tags=["<name>"],
                             dependencies=[Depends(require_feature("<flag>"))])
```
- `prefix` lives **at the mount**, not on the sub-router itself. Sub-routers use bare `APIRouter()`.
- `require_feature("<flag>")` enforces the company's `enabled_features` JSONB; flag names match `feature_flags.py:DEFAULT_COMPANY_FEATURES` keys.
- `tags` show up in OpenAPI; convention is the router slug.

## Cross-router conventions

- **Tenant isolation**: every endpoint that touches a per-company table must verify ownership before reading/writing. Pattern (used everywhere): `await get_client_company_id(current_user)` → 404 on mismatch. Don't trust the path-parameter alone.
- **Auth dep**: `require_admin_or_client` for business-side endpoints, `require_admin` for platform admin, `require_employee` for portal self-service, `require_candidate` for offer-letter signing.
- **DB**: asyncpg pool only — `async with get_connection() as conn:`. SQLAlchemy is used in `app/orm/` for a few legacy reports; not for new code.
- **Audit log**: per-domain routers maintain their own audit tables (e.g. `ir_audit_log`, `er_audit_log`, `discipline_audit_log`). Call the domain's `log_audit` helper inside the transaction.
- **Background tasks**: heavy work goes through Celery (`app/workers/tasks/*`). Lightweight per-request work uses FastAPI `BackgroundTasks.add_task(fn, ...)` — these are plain `async def`, not Celery tasks. Do not import Celery for `BackgroundTasks` work.
- **WebSockets**: live in their own routers (`thread_ws.py`, `interviews.py`, matcha_work voice surfaces). Auth via JWT in query param (`?token=`), validated server-side.

## When to split a router

Use the `ir_incidents/` package (see `ir_incidents/CLAUDE.md`) as the template. Split when:
- File exceeds ~2,000 lines AND
- Owns 4+ unrelated concerns AND
- Edits regularly require reading unrelated sections

Completed splits: `ir_incidents/` (2026-05-16), `employees/` (2026-05-16), `matcha_work/` (2026-07-03), `er_copilot/` (2026-07-06).

Reuse the IR pattern: `git mv` to `_legacy.py`, split into per-domain submodules, flip package router to the one owning empty-path collection routes, delete `_legacy.py`. **Variant used by `matcha_work/`**: if no submodule declares an empty-path route (check first — grep `@router\.\w+\("")`), skip the crud-owns-router step and just use a fresh `APIRouter()` aggregator in `__init__.py` instead; `_legacy.py` becomes the last remaining domain submodule (renamed to its real name, e.g. `threads.py`) rather than being deleted.

## Test layout

`server/tests/<domain>/` mirrors `server/app/matcha/routes/<domain>.py`. Tests that import the route module directly via `importlib.util.spec_from_file_location` exist for some domains (employees, er_copilot) and are brittle — they break when the path layout changes. If you split a router, check those test files for hard-coded paths and update them.
