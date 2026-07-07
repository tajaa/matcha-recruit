# Matcha Routes Zoo

29 routers, ~39,000 lines. Aggregated in `__init__.py` and mounted onto `matcha_router`. Each router corresponds to one product surface or sub-feature.

## Router map (by domain)

| Router file | Prefix | Owns |
|---|---|---|
| `companies.py` | `/companies` | Company CRUD + admin tooling |
| `employees/` | `/employees` (+ `/employees/pto`, `/employees/leave`) | Employee CRUD, bulk upload, invitations, onboarding, offboarding, credentials, OIG, leave, incidents, pto/leave admin — **package** (split 2026-05-16; see `employees/CLAUDE.md`) |
| `employee_portal.py` | `/v1/portal` | Employee-facing self-service portal |
| `onboarding.py` | `/onboarding` | New-hire onboarding tasks + notification settings |
| `invitations.py` | `/invitations` | Token-based invite acceptance |
| `offer_letters.py` | `/offer-letters` | Offer letter creation, signing, candidate portal (1,288 lines) |
| `interviews.py` | — | Live interview WS + transcript handling (1,522 lines) |
| `er_copilot/` | `/er/cases` (+ `/shared/er-export`) | Employee Relations case mgmt + AI — **package** (split 2026-07-06, 43 routes; see `er_copilot/CLAUDE.md`) |
| `ir_incidents/` | `/ir/incidents` | Incident reporting (matcha-lite) — **already a package** (50 routes incl. no-roster people index), see `ir_incidents/CLAUDE.md` |
| `ir_onboarding.py` | `/ir-onboarding` | IR-only onboarding wizard backend |
| `ir_surveys.py` | `/ir/surveys` | Security survey CRUD (matcha-lite) |
| `inbound_email.py` | (none) | Public intake: anonymous `/report/:token` + per-location magic-link `/intake/:token` forms |
| `accommodations.py` | `/accommodations` | ADA accommodation cases (1,175 lines) |
| `discipline.py` | `/discipline` | Progressive discipline workflow + signatures |
| `risk_assessment.py` | `/risk` | Risk-assessment dashboard data (849 lines) |
| `risk_pilot.py` | `/risk-pilot` | Risk Pilot — bring-your-own-data volatility & risk analysis (upload CSV/XLSX/PDF → deterministic `services/risk_analyzers` metrics → grounded SSE chat → analyst PDF). Company-scoped; `require_feature("risk_pilot")` |
| `pre_termination.py` | `/pre-termination` | Pre-term review packets (985 lines) |
| `separation.py` | `/separation` | Separation agreement workflow |
| `flight_risk.py` | `/flight-risk` | Flight-risk scoring per employee |
| `training.py` | `/training` | Training programs + completions (1,138 lines) |
| `i9.py` | `/i9` | I-9 verification |
| `cobra.py` | `/cobra` | COBRA admin |
| `dashboard.py` | `/dashboard` | Cross-feature dashboard aggregation (2,141 lines) |
| `brokers.py` | `/brokers` | HR broker admin (1,605 lines) |
| `broker_portfolio.py` | `/broker-portfolio` | Per-broker client roster + cross-client metrics |
| `fractional_hr.py` | `/fractional-hr` | Fractional HR engagement tooling — internal master-admin only (`require_admin` at mount, **not** feature-gated). Clients/scope/tasks/time + aggregate book-of-business overview. `fractional_*` tables; `company_id` nullable (client may have no tenant) |
| `provisioning.py` | `/provisioning` | Google Workspace + Slack auto-provision (1,606 lines) |
| `matcha_work/` | (multiple: `/matcha-work`, `/matcha-work/public`, `/matcha-work/presence`) | Matcha-work projects/threads/tasks/recruiting/AI turns — **package** (split 2026-07-03, 204 routes; see `matcha_work/CLAUDE.md`) |
| `journals.py` | `/journals` | Matcha-work journals |
| `billing.py` | (multiple) | Stripe billing + token packs |
| `notifications.py` | `/notifications` | Matcha-work notifications |
| `fake_hris.py` | `/fake-hris` | Mock HRIS connector for demos |
| `thread_ws.py` | `/threads` | Matcha-work thread websocket |
| `twilio_webhook.py` | `/twilio` | Twilio inbound for voice surfaces |

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
