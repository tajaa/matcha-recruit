# Logging System Overhaul — Professional Error Catchability (Local + Prod)

## Context

Audit of the logging system (codebase + live prod EC2 + prod RDS) found a genuinely good in-house error backbone (`error_reporter.py` → `server_error_reports` + email alerts + admin UIs — deliberate Sentry replacement) undermined by silent bypasses:

- **Worker errors never persist — confirmed bug.** `error_reporter.py:_upsert_async` (line ~120) uses pool-only `get_connection`; Celery workers are pool-free by design, so every worker-side report dies in a swallowed stderr write. Prod DB: **zero `source='celery'` rows ever** (725 total, all `api`).
- **152 `except → print` sites** bypass the reporter entirely (errors exist only as unlevelled stdout, no traceback). 39/46 worker task files have no logger at all.
- **Unhandled API errors triple-persist + no stdout traceback**: `capture_errors` middleware (main.py:436) persists then re-raises into `unhandled_exception_handler` (main.py:493) which persists again; its `logger.error` (no `exc_info`) creates a third `server_error_reports` row via the DB handler. Prod: 430 `unhandled` + 168 `http_error` rows for the same underlying errors. Traceback never reaches docker logs.
- **No request ID anywhere** — can't stitch nginx → uvicorn → error row.
- **Prod logs die on every blue-green deploy** (old container removed); caps 50m×3 (scripts) vs 10m×3 (compose) mismatch. CloudWatch agent already on the EC2 but ships **metrics only**.
- **Noise**: business 4xx ("Employee is already scheduled", 409) reported by frontend → double-persisted into `server_error_reports` via `client_errors.py:122` `logger.error`; `/health` polled every few sec in access log; celery boot prints ~37 lines/15min (print→WARNING redirect); per-audio-frame + per-WS-subscribe prints.
- Live proof the pipeline works when fed: caught real prod bug today — `UndefinedColumnError: column ev.urgency does not exist` on `GET /api/ems/events` (30 occurrences).

User decisions: CloudWatch Logs shipping; convert error-path prints + worst noise (not full 499 sweep); frontend noise-fix only (no tellus/blob work); full request-ID (middleware + error rows + ErrorBoundary surfacing).

Out of scope: full print sweep, tellus error infra, blob-endpoint reporting, per-route ErrorBoundaries, `server/agent/` overhaul, paid SaaS.

---

## PR 1 — Error-path signal fixes (ship first; fixes the two silent data-loss bugs)

**Files:** `server/app/core/services/error_reporter.py`, `server/app/main.py`, `server/app/core/routes/telemetry/client_errors.py`, `client/src/api/client.ts`, `server/app/core/services/notification_manager.py`, `server/app/matcha/routes/interviews.py`, `server/app/workers/celery_app.py`, NEW `server/app/workers/tasks/debug_error.py`, NEW `server/tests/telemetry/test_error_reporting_paths.py`.

1. **Celery persist fix**: `_upsert_async` switches `get_connection` → `connection_or_direct` (`server/app/database/pool.py:110` — exists exactly for this shared-path case; pooled in API, raw conn in worker).
2. **Debug task** `diagnostics.raise_test_error` (permanent diagnostic; exercises the `task_failure` signal at celery_app.py:412). Add to celery `include`.
3. **exc_info + dedupe in main.py**: new `_unhandled_logger = logging.getLogger("matcha.unhandled")` added to `_IGNORED_LOGGERS` (error_reporter.py:234) so stdout logging doesn't double-write DB. In `capture_errors`: log with `exc_info=real_exc`, set `request.state.error_reported = True` before re-raise. In `unhandled_exception_handler`: if `error_reported`, return 500 JSON early (skip second error_logs insert + second report); otherwise log with `exc_info` + persist. Result: one error_logs row, one server_error_reports row, traceback in docker logs.
4. **Client-error double-persist**: `client_errors.py:122` `logger.error` → `logger.warning` (stays in container logs, below DB-handler ERROR threshold; client errors live only in `client_error_reports`).
5. **Frontend 4xx filter** (`client.ts` report sites ~131, ~165): report only `status === 0 || status >= 500` or not in `{400,401,402,403,404,409,410,422,429}`; keep `/client-errors` loop guard.
6. **Noise kills**: `notification_manager.py:43,50` per-WS-subscribe → `logger.debug`; `interviews.py:690` audio-frame sample print → `logger.debug` (add module logger — file has none); `celery_app.py:on_worker_ready` ~37 "scheduler disabled, skipping" prints → data-driven loop + single summary line `dispatched=… disabled=…`, batch gate lookups into one `SELECT task_key, enabled FROM scheduler_settings`; `/health` uvicorn access spam → `logging.Filter` on `uvicorn.access` matching `'"GET /health '` exactly (not bare substring — would drop healthcare routes).

**Gotchas**: worker report opens raw conn per report — fine (rare + fingerprint upsert dedup). `logger.warning` path depends on `LOG_LEVEL ≤ INFO` — documented in PR4 runbook.

**Verify**: pytest for the 3 paths (celery persist via monkeypatched `connection_or_direct`; single-persist on raised route; client POST logs at WARNING); `npx tsc -p tsconfig.app.json --noEmit`; dev worker `celery call diagnostics.raise_test_error` → `source='celery'` row + alert email. **Prod post-deploy (user-run)**: same call via `docker exec matcha-worker`, check Admin → Server Errors.

---

## PR 2 — Request-ID correlation

**Files:** NEW `server/app/core/request_context.py`, `server/app/main.py`, `server/app/core/services/error_reporter.py`, `client/src/api/errorReporter.ts`, `client/src/api/client.ts`, `client/src/components/shared/ErrorBoundary.tsx`, NEW `server/tests/telemetry/test_request_id.py`.

- Pure ASGI middleware (NOT BaseHTTPMiddleware — no body buffering, covers WS, contextvar survives): validate/accept inbound `X-Request-ID` (`^[A-Za-z0-9-]{4,64}$`) else `uuid4().hex[:8]`; set contextvar; add `X-Request-ID` response header. Register LAST in main.py (= outermost).
- `logging.setLogRecordFactory` injects `record.request_id` (default `"-"`); basicConfig format gains `[rid=%(request_id)s]`. Factory only referenced in main.py's format — celery format untouched (no KeyError risk).
- `report_server_error` merges `{"request_id": rid}` into `context` JSONB — **no migration** (DDL rule respected).
- Uvicorn access-log format left alone (nginx is the authoritative access log, shipped in PR4). Optional later: nginx `proxy_set_header X-Request-ID $request_id` — note in LOGS.md only.
- Celery propagation deferred (100+ dispatch sites, low payoff) — noted as limitation.
- Frontend: `client.ts` captures `res.headers.get('x-request-id')` → `noteRequestId()` in errorReporter.ts (respects existing import direction); reports attach it in context; ErrorBoundary panel shows "Reference: {id}". Add `expose_headers=["X-Request-ID"]` to CORS kwargs.

**Verify**: pytest — header unique per request, inbound honored, invalid replaced, error-row context carries rid; log lines show `[rid=…]`; prod `curl -sI` any API endpoint shows header.

---

## PR 3 — except→print sweep + worker task loggers (mechanical, isolated for review)

- Regenerate the target list at implementation time via AST scan (except-handlers containing `print` calls) — audit's list has drifted slightly. Known heavy files: `app/core/services/gemini_compliance.py` (~40), `compliance_service/_run.py` (~36), `_research.py` (~33), `leads_agent.py`, `cms_coverage_api.py`, `legislation_watch.py`, `routes/chat/websocket.py:310`, `routes/content/blog.py:175`, `routes/compliance/payer_policies.py:152`, `app/main.py:137`.
- Rules: except-block failure print → `logger.exception(...)` (inside except); expected/recoverable condition (fallback, retry, skip) → `logger.warning`/`info` — **loops get warning, only genuine per-run failures get error** (guards against upsert/email floods; notifier caps 10/hr + 6h dedup blunt the rest). Add `logger = logging.getLogger(__name__)` where missing.
- Add module loggers to the 39/46 `app/workers/tasks/*.py` files lacking one.
- Leave `error_reporter.py`'s own stderr fallbacks (load-bearing recursion guards).
- Split commits by area (core/services, workers, routes); zero behavior change beyond log emission.

**Verify**: full pytest; re-run AST scan → 0 remaining (minus explicit allowlist); dev smoke a compliance stream + worker cycle.

---

## PR 4 — CloudWatch shipping, deploy alignment, LOG_LEVEL, runbook, logs.sh

**Mechanism: `awslogs` docker log driver + Docker dual-logging** (local ring buffer keeps `docker logs` working — verify host Docker ≥ 20.10 first). Rejected: CW-agent file collection (container IDs churn every deploy → racy discovery), journald. `mode=non-blocking` so CW outage can't block stdout.

- `scripts/deploy-backend-bluegreen.sh` (~95-108) + `deploy-frontend-bluegreen.sh` (~71-81): replace `--log-opt max-*` with `--log-driver awslogs --log-opt awslogs-region=us-west-1 --log-opt awslogs-group=/matcha/backend|frontend --log-opt awslogs-stream="$NEW_CONTAINER" --log-opt mode=non-blocking --log-opt max-buffer-size=4m`. Stream = container name (8002/8003 alternating) — appends across same-color deploys. **Logs now survive container removal.**
- NEW `docker-compose.logging.yml` (worker override → `/matcha/worker`), applied only on EC2; base compose stays json-file so local dev needs no AWS creds. `update-ec2.sh` scps it + adds `-f` pair to worker up. **Pre-step: `cat ~/matcha/scripts/worker-cycle.sh` on host** (systemd ExecStart, repo copy stale) — if it recreates the worker it needs the same `-f` pair.
- NEW `deploy/cloudwatch/logs.json` (CW agent append config): `/var/log/nginx/access.log` → `/matcha/nginx-access` (30d), `error.log` → `/matcha/nginx-error` (90d). Apply via `amazon-cloudwatch-agent-ctl -a append-config` — existing metrics config (Drooli/EC2) keeps working.
- NEW `deploy/cloudwatch/README.md` (deploy/nginx/README.md scp pattern) with ordered manual steps: **(1) IAM verify FIRST** — instance role name via IMDSv2, needs `logs:CreateLogStream/PutLogEvents/DescribeLogStreams` on `/matcha/*`; ship `logs-policy.json` + `put-role-policy` one-liner; **if instance has no role, STOP and discuss**. (2) Pre-create 5 log groups + retention (90d app/worker/nginx-error, 30d access/frontend). (3) Agent config apply. Ordering critical: **awslogs auth failure makes `docker run` refuse to start** — bluegreen health gate keeps old container alive, rollback = revert driver lines.
- `LOG_LEVEL=INFO` added to `~/matcha/.env.backend` on EC2 (manual, documented).
- NEW `docs/ops/LOGS.md` runbook: where logs live (docker cmds incl. port-suffix dance, CW groups, nginx paths + logrotate daily/10, `server_error_reports`/`client_error_reports`/legacy `error_logs` + admin UIs), request-id story + celery limitation, tail-prod how-to, CW Logs Insights sample queries, LOG_LEVEL must stay ≤ INFO, alert-email behavior (`error_alert_email`, 6h dedup, 10/hr cap), dual-logging = `docker logs` recent-only. One line: `server/agent` service out of scope.
- NEW `scripts/logs.sh` (agent.sh:cmd_logs conventions): `./scripts/logs.sh backend|worker|frontend|nginx|nginx-err [-n N]` — resolves live container by name prefix, `docker logs -f`; `cw <group>` subcommand → `aws logs tail --follow`.

**Prod manual actions (all user-run/approved, listed in PR description)**: IAM verify+policy, log-group creation, CW agent apply, LOG_LEVEL env edit, worker-cycle.sh check.

---

## Order + sizing

| PR | Size | Notes |
|---|---|---|
| 1 signal fixes | ~10 files, small | first — fixes silent data loss |
| 2 request-id | ~7 files, medium | independent |
| 3 print sweep | ~40-60 files, mechanical | after 2 (format settled) |
| 4 shipping + ops | scripts/docs/config | last — CW never ingests pre-cleanup noise |

All work on current branch `matcha/operator-scope` unless user says otherwise (no branch creation without permission). Deploys user-run per repo rules.

## Verification (end-to-end, after all PRs)

1. Dev: raise test error via debug task → `source='celery'` row + email; raise route error → single row, traceback + `[rid=…]` in logs.
2. Prod after deploy: `aws logs tail /matcha/backend --follow` shows startup; `docker logs` still works; worker summary line every 15 min in `/matcha/worker`; nginx groups ingest; Drooli/EC2 metrics still publish; `curl -sI` API endpoint → `X-Request-ID`.
3. Admin → Server Errors: business 4xx noise gone, celery fingerprints appear for real failures only.
