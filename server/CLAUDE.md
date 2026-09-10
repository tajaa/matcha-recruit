# Server (FastAPI Backend)

Python 3.12, FastAPI + asyncpg + Celery + Gemini. Production runs on EC2 with Postgres in a container on a separate dedicated DB EC2; stopped RDS is only a cold fallback. See root `CLAUDE.md` for connection rules and the **production-safety guard list**.

## Layout

```
server/
├── run.py                       Entry point (uvicorn)
├── venv/                        Python 3.12 venv — local dev
├── requirements.txt             Pinned top-level deps
├── alembic/                     Migrations (use these, don't auto-mutate schema)
├── tests/                       pytest unit tests
├── scripts/                     One-off ops scripts (seed data, etc.)
└── app/
    ├── main.py                  App init, lifespan, CORS, mount /api
    ├── config.py                Pydantic settings from .env
    ├── database/                asyncpg pool + init_db() bootstrap (package — schema reference)
    ├── dependencies.py          Shared auth deps (require_admin etc.)
    ├── protocol.py              AI WebSocket / streaming shapes
    ├── core/                    Auth, admin, compliance, AI chat, policies, resources
    ├── matcha/                  Recruiting + HR domain (incl. matcha-work)
    │   ├── routes/              See routes/CLAUDE.md for the zoo
    │   ├── services/            Business logic — heavy AI calls, signature providers, etc.
    │   ├── models/              Pydantic request/response shapes
    │   └── workers/             (rare — most worker tasks live in app/workers/)
    ├── workers/                 Celery app + scheduled / heavy tasks
    ├── orm/                     SQLAlchemy helpers (legacy reports only — avoid for new code)
    └── uploads/                 Local-only upload temp dir (S3 in prod)
```

## Conventions

**Database**:
- asyncpg pool via `async with get_connection() as conn:`.
- All schema changes go through Alembic (`alembic/versions/`). `database/bootstrap/__init__.py:init_db()` bootstraps a fresh DB but should not be relied on for schema evolution.
- Use parameterized queries. Never f-string user input into SQL.
- Tenant isolation: filter by `company_id` (or `org_id` for employees-related tables) on every multi-tenant table.

**Imports**:
- Absolute imports for module-level (`from app.X import …`). This was the convention enforced during the IR refactor.
- Relative imports tolerated inside packages (e.g. `from ._shared import …` within `ir_incidents/`).
- Lazy imports inside function bodies are OK for circular-import avoidance.

**Auth**:
- JWT bearer token in `Authorization: Bearer …`. Roles: `admin`, `client`, `candidate`, `employee`, `broker`, `creator`, `agency`, `individual` (see root CLAUDE.md).
- Per-endpoint deps: `require_admin`, `require_client`, `require_candidate`, `require_employee`, `require_admin_or_client`, `require_broker_or_admin`.
- Feature-gated routers add `dependencies=[Depends(require_feature("flag"))]` at mount time (see `routes/__init__.py`).

**Models**:
- Pydantic v2 (`BaseModel`, `Field`, `model_validator`).
- Request and response models live in `app/<core|matcha>/models/<domain>.py`, not inline in route files.
- Enum-constrained fields use `Literal[...]` from `typing`.

**Background work**:
- FastAPI `BackgroundTasks.add_task(fn, ...)` for lightweight per-request work — plain `async def` functions, run in the same process after the response is sent.
- Celery for anything that survives the request lifecycle, runs scheduled, or needs separate concurrency limits. Tasks live in `app/workers/tasks/`. The worker container restarts every 15 min via systemd; `@worker_ready` re-dispatches periodic tasks (no celery-beat).

**Email**:
- Gmail API via OAuth2 (`app/core/services/email/`) for transactional. MailerSend for broker invites + a few transactional flows. The send wrapper has a defense-in-depth guard that skips RFC 2606 reserved test domains — see root CLAUDE.md test-data rules.

**AI**:
- Gemini via `google.genai` SDK with `settings.gemini_api_key` (from the `LIVE_API` env var). Some services also honor a `GEMINI_API_KEY` env override. Native Google AI only — no Vertex.
- Per-feature analyzer singletons (e.g. `get_ir_analyzer`, `get_er_analyzer`) cache the model handle; don't instantiate per request.
- **Rate limiting is per PROVIDER** (`core/services/rate_limiter.py:ApiRateLimiter`). `ApiRateLimiter()`
  is the Gemini bucket (`gemini_hourly_limit`/`gemini_daily_limit`); the OpenAI agent loops construct
  `ApiRateLimiter(provider="openai")` and count against `openai_*_limit`. Before `ratelimit01` this
  counted every row in `api_rate_limits` with no filter against the Gemini ceiling, so OpenAI traffic
  spent the Gemini allowance and a Gemini sweep could 429 a Huume turn. A new provider needs a bucket
  here and its own limits, not a share of someone else's.
- Not every model call is limited: `huume/er_skill`, the legal/handbook pilot chats and the Espresso
  project agents call their provider without going through the limiter at all, so the budget
  understates real spend. Pre-existing; gating them changes behaviour and is deliberately separate.

**Streaming**:
- SSE for AI analysis runs (`StreamingResponse(event_stream(), media_type="text/event-stream")`).
- WebSocket for chat / channels / voice interviews. JWT in query param `?token=…`, validated on `accept`.

## Local dev

Use `./scripts/dev-remote.sh` from repo root. It SSH-tunnels Postgres from EC2 (treat as production — see root CLAUDE.md), starts Redis tunnel, backend on :8001, frontend on :5174, local chat model on :8080. Requires `secrets/roonMT-arm.pem`.

To run the backend alone (assumes tunnels are up):
```bash
cd server && ./venv/bin/python run.py     # :8001
```

## Tests

```bash
cd server && ./venv/bin/python -m pytest tests/<domain>/ -q
```

**After applying fixes — from `/code-review --fix`, `/simplify`, or by hand —
run the WHOLE server suite before reporting, not just the file you touched:**

```bash
cd server && ./venv/bin/python -m pytest tests -q
```

~8,900 tests in about 25 seconds (nearer two minutes under `--cov`), and no
database required — nothing in the default run opens a connection. Running only the
touched file is the tempting shortcut and the wrong one here: much of this
suite is cross-cutting registry and contract assertions, so a fix in one
module routinely trips an assertion in another package. That is how the
`waste_*` staged-action gaps surfaced — a Huume prompt change was caught by
`tests/huume/test_huume_assets.py`, which the edit never touched. A failure is
a blocking finding, reported with its name and output, never a footnote.

CI additionally gates **diff coverage at 80% of the lines a PR changes**
(`diff-cover`, `.github/workflows/ci.yml`). A fix that adds a branch needs a
test in the same change or CI fails — write the test with the fix, not after.

Nothing in that run touches a database — the tests that need one are opt-in
(table below).

**Walking a route table? Use `tests._helpers.routes.iter_api_routes(router)`,
not `router.routes`.** Since FastAPI 0.141 (the `requirements.txt` floor)
`include_router` appends an `_IncludedRouter` wrapper instead of copying the
child's routes up, so reading `.path`/`.dependant` off `router.routes` raises
`AttributeError: '_IncludedRouter' object has no attribute 'path'`. Six tests
did exactly that and failed in CI only — a stale local `venv/` still had 0.136,
which is its own warning: `./venv/bin/python -m pip install -r requirements.txt`
if a test passes locally and fails in CI for a library reason.

If the same pass touches `client/`, add
`cd client && npx tsc -p tsconfig.app.json --noEmit`. The bare
`npx tsc --noEmit` checks NOTHING (root tsconfig is `files: []` + project
references, so it always exits 0).

**The suite runs in CI now, and it did not before.** Until 2026-09-08 the
`server-tests` job ran `alembic upgrade heads` against an empty database, hit
the root revision's `REFERENCES companies(id)` (a table `init_db()` creates, not
a migration), accepted that as a pinned baseline, and fell back to
`pytest --collect-only`. ~8,700 tests were imported and never executed, for
months. The schema step was never needed — this suite is unit-level and passes
with no database at all — so it is gone, along with the fallback. Oceanlab runs
as its own step against the service container its conftest hardcodes.

Turning execution on surfaced 190 failures, all test rot from code that moved
while nothing ran (stale fake-connection queues, `mock.patch` targets pointing
at package facades, signatures that gained a `company_id`). Those are repaired.
What remains is recorded as `xfail(strict=True)` with the reason in place, never
as a fingerprint pinned in the workflow — a strict xfail goes red the moment the
underlying issue is fixed, which forces the marker off instead of letting it rot:

| Marked | Why |
|---|---|
| `tests/workers/test_discipline_policy_sweep.py` (6) | `discipline` is in `RETIRED_COMPANY_FEATURES` (f37b8f3), so `merge_company_features` strips the key for every company and `discipline_policy_sweep_enabled` can never return True — every scanned incident takes the `_stamp_ineligible` branch instead of being checked. The removal was **partial**; these all still gate on the retired flag and are now dead: `workers/tasks/discipline_policy_sweep.py:60`; the `discipline_draft`/`discipline_from_incident`/`discipline_decision` staged actions (`huume/actions.py:114,120,121`), whose tools are still offered to the model and now always refuse; `pilots/legal_defense/gather.py:97`, so progressive-discipline evidence silently drops out of every defense memo and packet; `core/routes/auth/register_business.py:281,364`, still writing an inert `discipline: True` at signup; and `broker/epl_readiness.py:184`, now always reporting "(discipline not enabled)". `services/discipline/` and the root CLAUDE.md entry also remain. |
| `tests/compliance/test_compliance_schema_redesign.py` (1) | 24 category keys have no `CATEGORY_DOMAIN_MAP` entry. No runtime consumer (it seeds from migrations); the proposed mapping is in the test's comment. |
| `tests/dependencies/test_feature_gate_wiring.py` (1) | `offer_letters_plus` is gated in a route but exists nowhere else in the codebase, so that endpoint 403s for every tenant. |

`tests/employees/test_internal_mobility_routes.py` was deleted: the feature it
covered was removed in `4020e58` and the file had been failing collection ever
since.

Some tests load a route module through `importlib.util.spec_from_file_location(...)`
with a hard-coded relative path — `tests/infrastructure/test_ai_chat.py` had one
that was off by a directory and silently turned all 25 of its assertions into a
`FileNotFoundError`. Avoid the form; import normally, or `inspect.getsource()`.

**DB-touching tests are opt-in, and a plain `pytest tests/` must never write.**
Root CLAUDE.md forbids auto-running DB-mutating tests; the enforcement is a
module-level `skipif` on an explicit env var, because a `DATABASE_URL` read out
of `server/.env` is always present on a dev laptop and is therefore not a guard:

| File | Opt-in | Shape |
|---|---|---|
| `tests/scope_registry/test_gap_surfaces_integration.py` | `RUN_DB_GAP_TESTS=1` | read-only |
| `tests/employees/test_employees_google_workspace_api_integration.py` | `RUN_DB_WRITE_TESTS=1` | INSERTs, and `close_pool()`s the process-global pool |
| `tests/{matcha_work/test_progress_note_realdb,matcha_work/test_project_task_toggle_realdb,channels_ws/test_invitable_users_realdb,employees/test_employee_incidents,infrastructure/test_rls_isolation}.py` | `RUN_DB_TESTS=1` | open a real connection; two of the five write |

Those five used to gate on `DATABASE_URL` being non-empty, which reads correctly
and is not: ~40 modules
`os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")`
at import so `app.config` can load, so in a full-suite run the variable is
ALWAYS set. They skipped when run alone and dialled a nonexistent database when
run together — 29 errors locally, and on the 2026-09-08 CI run `FATAL: password
authentication failed for user "test"`, because there a Postgres really is
listening on 5432. Use `tests._helpers.db.requires_real_db()` and
`real_database_url()` instead; `tests/_helpers/test_db_guard.py` fails any
module that goes back to reading the variable directly.

Don't fix unrelated failures as part of other work — but don't trust a stale list either. Re-measure before citing one.

**A test that patches a collaborator must patch the module that DEFINES the caller, not a facade that re-exports it.** `monkeypatch.setattr(pkg, "helper", fake)` is silently ignored when the function using `helper` lives in `pkg.submodule` — the call then reaches the real collaborator, often a live DB or Gemini client, and the test still looks like it ran. The 2026-07 service-package splits turned five such patches into no-ops; each is now pointed at its submodule with a comment saying why. Grep for `setattr(` / `patch("` against any module you are about to split.

The IR-incidents tests (445 passing) are the model to follow.

## Migration authoring rules

Prod is a dedicated DB EC2 at the far end of an SSH tunnel (~100ms per round-trip),
and `migrate-prod.sh` gates every run: uncommitted migrations abort, pending
revisions are printed, a logical dump is streamed to S3, the whole upgrade is **rehearsed
against live prod rows and rolled back**, and you type `migrate prod` to commit.
Write migrations that survive that:

- **Set-based SQL, never row-by-row Python loops.** A loop that is instant on the
  local dev container is ~20,000 sequential round-trips against prod and does not
  finish — it looks like a lock, but it is the DB idle, waiting on you.
  `jparent01` is the template: a TEMP table holds the plan, ~20 statements do the
  work, four seconds end to end.
- **Every `LIMIT 1` needs a deterministic `ORDER BY`.** Otherwise the pass and its
  own post-check can disagree, and the terminal `raise` rolls back the lot.
- **Repointing rows onto a UNIQUE column needs an explicit dedupe pass first**
  (ctid + `ROW_NUMBER()`, as in `jparent01`). Merging one row at a time hides the
  collision; merging a set does not.
- **Write a real `downgrade()`** where feasible. If it is genuinely irreversible,
  say so in the docstring — the pre-migration S3 dump is then the only rollback.
- **Commit the migration before applying it to ANY database, dev included.** Dev
  and prod running different bytes of the same revision id is a silent drift with
  no alarm on it.
- **Rehearse:** `MIGRATE_REHEARSAL=1 DATABASE_URL=… alembic upgrade heads` runs
  the migration for real inside the upgrade transaction and raises at the end to
  force the rollback. `migrate-prod.sh` does this for you; run it by hand against
  dev while authoring. Its elapsed time is the signal — a slow rehearsal is a
  migration that will hang.

## Common pitfalls

- **Don't run Alembic upgrade automatically.** Schema changes require explicit user approval (see root CLAUDE.md production-safety list).
- **Don't introduce new SQLAlchemy code.** `app/orm/` exists for a few legacy reports; everything else is asyncpg.
- **Don't bypass `require_feature`.** Frontends will URL-hop to a feature page; the gate is what surfaces the upsell instead of 403.
- **Don't trust client-supplied `company_id`/`org_id`.** Always derive from `current_user` and verify ownership of the requested resource.
- **Don't define helpers in the route file when a service exists.** AI analyzers, signature providers, storage, email — all live under `services/` and are instantiated via getters.

## Symbol map (backend)

Moved from root `CLAUDE.md`'s Symbol Map section.

### Auth + identity

- Backend auth deps → `server/app/core/dependencies.py` (`require_admin`, `require_candidate`) + `server/app/matcha/dependencies.py` (`require_client`, `require_employee`, `require_admin_or_client`, `get_client_company_id`)
- Public-token interview WS auth → `server/app/core/services/auth.py:create_interview_ws_token`

### Email + notifications

- Email service (Gmail API + MailerSend) → `server/app/core/services/email/` (`EmailService`, `get_email_service()`)
- Reserved-domain guard (blocks `@example.com` / `*.test` / `*.invalid`) → `server/app/core/services/email/_shared.py:_is_reserved_test_domain`
- Employee invitation send → `server/app/core/services/email/employee.py:send_employee_invitation_email` (callsite: `server/app/matcha/services/employees/invitations.py:_send_invitation_with_conn`)
- IR lifecycle notifications → `server/app/matcha/services/ir/ir_notifications.py:send_ir_notifications_task` (aliased through `routes/ir_incidents/_shared.py`)
- Onboarding reminder cron → `server/app/workers/tasks/onboarding_reminders.py`

### Feature gating + tiers

- Backend default flags → `server/app/core/feature_flags.py:DEFAULT_COMPANY_FEATURES`
- Backend feature dep → `server/app/matcha/dependencies.py:require_feature`

### IR (Incident Reporting)

- Backend package overview → `server/app/matcha/routes/ir_incidents/CLAUDE.md`
- IR orchestrator (Gemini prompt + intent detection) → `server/app/matcha/services/ir/ir_ai_orchestrator.py:generate_guidance`
- IR Copilot close-incident helper (server) → `server/app/matcha/services/ir/ir_copilot_flow.py:_close_incident_via_copilot` (re-exported by `routes/ir_incidents/copilot.py`)
- IR analysis runners (categorize / severity / root-cause / etc.) → `server/app/matcha/routes/ir_incidents/ai_analysis.py`
- Policy mapping helpers → `server/app/matcha/routes/ir_incidents/ai_analysis.py:_auto_map_policy_violations` + `_get_handbook_policy_entries`
- Anonymous IR intake → `server/app/matcha/routes/intake/inbound_email.py` (public `/report/:token` endpoint)
- Anonymous report token mgmt → `server/app/matcha/routes/ir_incidents/anonymous_reporting.py`

### EMS (channel-logged events)

- Intake classify + urgency overlay → `server/app/matcha/services/ems/event_intake.py` (`classify_event`, `apply_urgency_overlay`, `fallback_classification`)
- Urgent-event fan-out (in-app + email) → `server/app/matcha/services/ems/urgent_notify.py:send_urgent_event_notifications`
- Company protocol file (fetch/upsert + prompt excerpt) → `server/app/matcha/services/ems/protocols.py`
- WS dispatch (intake + clarify + ask) → `server/app/werk/routes/channels_ws.py:_bg_ems_intake` / `_bg_ems_clarify` / `_bg_ems_ask`
- Channel store scope lookup (used by every @huume dispatch handler) → `server/app/werk/routes/channels_ws.py:_channel_location`
- Channel `@huume` ASK grounding (bounded tool-calling loop beyond `ems_events`) → `server/app/matcha/services/ems/channel_agent.py:answer_channel_question`, policy registry at `server/app/matcha/services/ems/channel_grounding.py:run_topic_lookup`
- Channel `@huume` "who can cover a shift" → `server/app/matcha/services/ems/channel_grounding.py:run_coverage_lookup` → `server/app/matcha/services/scheduling/coverage.py:find_coverage_candidates`
- Channel `@huume` shift EDITS (swap/reassign/unassign/retime/cancel) → `services/scheduling/schedule_chat.py:build_edit_proposal` / `execute_edit_proposal`, writing through the four shared cores in `services/scheduling/shift_writes.py` (`apply_assignment_core`, `remove_assignment_core`, `retime_shift_core`, `cancel_shift_core`)
- Channel ASK-loop NL schedule-change tool (anaphora/compound asks) → `services/ems/channel_agent.py:propose_schedule_change` tool → `services/ems/channel_grounding.py:run_schedule_change`
- Thread Huume schedule tools (`find_shift_coverage` read, `propose_schedule_change` staged) → `services/huume/schedule_skill.py`
- Agent-path assignment guard (POLICY caps, intra-batch overlap, reject-at-stage) → `services/scheduling/assignment_guard.py`; the `ScheduleReview` contract → `services/scheduling/schedule_review.py`; jurisdiction on-file check → `services/scheduling/shift_compliance.py:jurisdiction_rule_status`
- Server-side "fill the open shifts" planner → `services/scheduling/week_builder.py:plan_vacant_fill` (+ `_load_vacant_demand`); what a scheduler should see (roster load, open seats, policy, jurisdiction) → `services/scheduling/planning_inputs.py:build_planning_inputs`; REST preview/apply/discard + planning-inputs → `routes/employee_schedule/planning.py`
- Adopting a REST fill scenario as the thread's staged action (Schedule Pilot "Stage this") → `services/scheduling/schedule_assistant_session.py:adopt_editor_proposal`, route `POST /employee-schedule/assistant/sessions/{id}/adopt-proposal`
- Week-builder compliance preflight (fail-closed, advisories kept, checked replans) → `services/scheduling/week_builder.py:_preflight_compliance` / `_plan_with_preflight`; concentration / double-booking / advisory / jurisdiction findings → `week_builder._concentration_findings` & co.; the week-draft `ScheduleReview` → `services/scheduling/schedule_review.py:build_week_draft_review`
- Channel receipt/invoice attachment ingest (@huume + a dropped CSV/PDF/photo) → `werk/routes/channels_ws.py:_bg_inventory_receipt` / `_bg_receipt_reply`, staging table `inventory_receipt_drafts` (migration `receiptdraft01`)

### Inventory (channel stock tracking)

- Intent classification → `server/app/matcha/services/ems/intent.py` (`INVENTORY` constant + `_INVENTORY_RE`)
- WS dispatch (request + confirm/clarify reply) → `server/app/werk/routes/channels_ws.py:_bg_inventory_request` / `_bg_inventory_reply`
- Service package (matching, reorder math, rules, pills, extraction, DB services) → `server/app/matcha/services/inventory/`
- REST router (items/movements/orders/suggestions) → `server/app/matcha/routes/inventory.py`
- Per-location item resolution → `server/app/matcha/services/inventory/movements.py:list_item_names` / `find_or_create_item`
- Receipt ingest (invoice/packing-slip → `in` movements) → `server/app/matcha/services/inventory/receipts.py`, routes at `routes/inventory.py` `/receipts/*`
- Stock audit (bulk count → `adjust` movements) → `server/app/matcha/services/inventory/audits.py`, routes at `routes/inventory.py` `/audit/commit`
- Voice stock-count dictation (`inventory_voice`) → `server/app/matcha/services/inventory/voice_audit.py`, route `/audit/voice-parse`

### Employees

- Employee CRUD → `server/app/matcha/routes/employees/crud.py` (10 routes; package split 2026-05-16 — see `server/app/matcha/routes/employees/CLAUDE.md`)
- Bulk CSV upload → `server/app/matcha/routes/employees/bulk_upload.py:bulk_upload_employees_csv`
- Send invitation → `server/app/matcha/services/employees/invitations.py:_send_invitation_with_conn` (callable from single + bulk + multi-batch paths, via `routes/employees/_shared.py:send_single_invitation`)
- Auto-invitation toggle (per-company setting) → `onboarding_notification_settings.auto_send_invitation` column

### Billing + Stripe

- Stripe checkout endpoints → `server/app/core/routes/resources/checkout.py` (matcha-lite: `POST /resources/checkout/lite` + `/compliance` + `/lite-addon` + `/lite-upgrade`) + `server/app/matcha/routes/work/billing.py` (matcha-work)
- Stripe webhook handler → `server/app/core/routes/billing/stripe_webhook.py:stripe_webhook` mounted at `POST /api/webhooks/stripe` (NOT billing.py). Routes on `event_type` + `metadata.type`; `checkout.session.completed` w/ `type='matcha_lite'` flips `enabled_features.incidents=true`; `customer.subscription.deleted` flips it back. Top-level dedupe via `stripe_webhook_events` (fail-closed).
- Personal Matcha-work checkout → `server/app/matcha/routes/work/billing.py:POST /api/checkout/personal`
- Token packs → `server/app/matcha/routes/work/billing.py:POST /api/checkout`
- Lite checkout redirect is **URL-based** — backend returns `checkout_url`, FE does `window.location.href = checkout_url` (`TenantSidebar.tsx`); **no `loadStripe`/publishable key/`redirectToCheckout` anywhere**, so swapping Stripe keys needs no frontend rebuild. Lite pricing = DB table `matcha_lite_pricing` (`services/matcha_lite_pricing.py`, admin-configurable; code fallback `$50/block-of-10`, min 1/max 300).
**Prod Stripe config (keys, accounts, mode) — non-obvious:**
- Prod Stripe keys live in **`~/matcha/.env.backend` on the app EC2** (`54.177.107.107`), read at container start via `docker run --env-file .env.backend`. NOT in the repo, NOT in AWS Secrets Manager (the `AWS_SECRETS_MANAGER_SECRET_ID` path in `config.py:load_settings` exists but is unused — prod uses the plain `.env.backend`). Local dev keys are in `server/.env`.
- **No deploy script overwrites `.env.backend`** — `update-ec2.sh` only scps `docker-compose.yml` + runs `deploy-backend-bluegreen.sh` (which pulls `:latest` and `--env-file`s the host `.env.backend`). So a host-side key edit **persists across `build-and-push.sh` + `update-ec2.sh`**. To reload env without shipping new code, recreate the backend container pinned to its current image id (skip `docker pull`) — the bluegreen script always pulls `:latest`.
- **Two Stripe accounts** (keys are per-account): dev/local = **Matcha Technologies LLC** (`acct_1S2GdG…`), prod historically = **Ahnimal** (`acct_1QcZE2…`, the legacy/discontinued sister product). As of 2026-07-04 prod `.env.backend` was switched to **Matcha Technologies LLC test-mode** keys (backup of the old Ahnimal keys at `~/matcha/.env.backend.bak.ahnimal-*`). Test webhook endpoint in the Matcha-Tech account → `https://hey-matcha.com/api/webhooks/stripe` (events: `checkout.session.completed`, `customer.subscription.deleted`, `invoice.paid`, `checkout.session.expired`).
- **Prod is in Stripe TEST mode** (pre-customer) — real cards are rejected. **Before go-live:** put Matcha-Tech **live** keys in `.env.backend` + register a **live** webhook endpoint (different `whsec_`) in the Matcha-Tech live dashboard, then recreate the backend. Test/live keys + webhook endpoints are per-mode and must be swapped as a matched pair (secret key + webhook secret + endpoint) or activation webhooks fail signature.

### Tell-Us internal admin

- `TELLUS_ADMIN_EMAILS` — comma-separated allowlist gating every `/tellus/admin/*` route (`app/tellus/dependencies.py:_is_tellus_admin`, `require_tellus_admin`). Empty ⇒ nobody passes (fail-closed), same shape as `master_admin_email`. Set in `server/.env` for dev. For prod, add it to **`~/matcha/.env.backend`** on the app EC2 alongside the Stripe keys above — same persistence rule applies (no deploy script overwrites that file).
- Beyond the changelog (`/admin/updates`), the admin package (`app/tellus/routes/admin/`) covers account lifecycle (suspend/force-logout/verify-email/password-reset/manual points adjust), brand plan overrides + owner assignment, cross-brand review/DM moderation, and points-economy config editors (earning rules/badges/listings) — every mutation logged to `tellus_admin_audit` in the same transaction. Full spec → `server/app/tellus/CLAUDE.md`.

### Compliance + jurisdictions

- Compliance check service → `server/app/core/services/compliance_service/`
- Jurisdiction-aware preemption logic → same file, search `preemption`
- Compliance research worker → `server/app/workers/tasks/compliance_checks.py`
- Legislation watch cron → `server/app/workers/tasks/legislation_watch.py`

### Matcha-work (collaborative AI workspace)

- Backend routes → `server/app/matcha/routes/matcha_work/` (package, split 2026-07-03 — see its CLAUDE.md; 203 routes)
- Project service → `server/app/matcha/services/matcha_work/project_service/`
- AI directives → `server/app/matcha/services/matcha_work/matcha_work_ai/` (facade package since 2026-07-27: `provider.py` is the Gemini provider, `_prompts.py` the prompt literals, `_fields.py` the per-skill write whitelists, `_models.py` model selection, plus `compaction.py` / `task_draft.py` / `_images.py` / `_text.py`)
- Channels (WS) → `server/app/werk/routes/channels.py` + `channels_ws.py` (+ `channels` / `channel_members` tables)

### Database access

- Connection pool helper → `server/app/database/pool.py:get_connection` (re-exported as `app.database.get_connection`)
- Schema bootstrap (reference only — use Alembic for changes) → `server/app/database/bootstrap/__init__.py:init_db`
- Alembic migrations → `server/alembic/versions/*`

### Routing assembly

- Backend route aggregator → `server/app/matcha/routes/__init__.py`
- IR-incidents package router → `server/app/matcha/routes/ir_incidents/__init__.py` (re-exports `crud.router` as the package router)
