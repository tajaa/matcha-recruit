# Logs + error tracking — where to look when something breaks

Start here when a user reports a problem. The short version:

| Question | Look at |
|---|---|
| "What broke, and has it broken before?" | **Admin → Server Errors** (`/admin/server-errors`) — deduped, counted, with tracebacks |
| "The page crashed / an API call failed in their browser" | **Admin → Client Errors** (`/admin/client-errors`) |
| "What was the app doing at 14:32?" | `./scripts/logs.sh backend` (recent) or CloudWatch `/matcha/backend` (historical) |
| "Did the request even reach us?" | `./scripts/logs.sh nginx` — host nginx sees every request |
| "Is a scheduled job running?" | `./scripts/logs.sh worker` |

**The Postgres error tables are the durable record, not the container logs.**
Logs rotate and (pre-CloudWatch) died with each deploy; `server_error_reports`
persists with occurrence counts and fingerprint dedup. Reach for logs when you
need surrounding context, not as the primary error store.

## The tooling

```bash
./scripts/logs.sh backend        # live backend (resolves the 8002/8003 blue-green suffix for you)
./scripts/logs.sh worker         # celery worker
./scripts/logs.sh frontend       # frontend container's internal nginx
./scripts/logs.sh nginx          # HOST nginx access log — all vhosts, undifferentiated
./scripts/logs.sh nginx-err      # HOST nginx error log
./scripts/logs.sh errors         # backend filtered to ERROR / Traceback / 5xx
./scripts/logs.sh cw /matcha/backend   # CloudWatch group (local aws CLI)
./scripts/logs.sh -n 500 backend # more history
```

Doing it by hand: `ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107`, then
`docker logs -f matcha-backend-8003` — but **check the suffix first**
(`docker ps`), because blue-green deploys alternate `8002`/`8003` and the name
you used last week may not exist today. That footgun is the reason `logs.sh`
resolves by prefix.

## Where each log actually lives

| Source | Destination | Retention |
|---|---|---|
| Backend / frontend containers | Docker `json-file`, or CloudWatch `/matcha/backend`, `/matcha/frontend` once enabled | 50MB × 3 locally; 90d / 30d in CW |
| Celery worker | same, group `/matcha/worker` | 10MB × 3 locally; 90d in CW |
| Host nginx (all vhosts) | `/var/log/nginx/{access,error}.log` + CW `/matcha/nginx-{access,error}` | logrotate daily × 10; 30d / 90d in CW |
| Unhandled exceptions, `logger.error`+ | Postgres `server_error_reports` | until manually purged |
| Browser JS errors, failed API calls | Postgres `client_error_reports` | until manually purged |
| Legacy pre-`server_error_reports` errors | Postgres `error_logs` | until manually purged |

Container logs used to **vanish on every deploy** — blue-green removes the old
container, taking its logs with it. CloudWatch shipping fixes that; setup and
the ordered rollout live in `deploy/cloudwatch/README.md`. Once enabled,
`docker logs` still works (Docker ≥ 20.10 dual-logging keeps a local ring
buffer) but only shows recent history — CloudWatch is the archive.

Host nginx logs are **not split per vhost**: hey-matcha.com, gummfit.com, and
Cappe tenant subdomains all land in one file. Filter by the `Host` field.

## Correlating one user action across everything

Every request gets a short ID (`app/core/request_context.py`):

- returned to the browser as the `X-Request-ID` response header
- printed on every backend log line for that request: `[rid=a1b2c3d4]`
- stored on the resulting `server_error_reports` row under `context.request_id`
- shown to the user in the crash screen as `Reference: a1b2c3d4`

So a user quoting a reference ID → grep it in the logs → find the error row.
A valid inbound `X-Request-ID` is honored (regex-validated, since it's
client-controlled and lands in the DB), otherwise one is minted.

**Celery tasks don't carry it.** The contextvar doesn't cross the queue, so
worker rows show `request_id` absent — they're identified by `task_id` /
`task_name` in `context` instead. Propagating it through 100+ `.delay()` call
sites was deliberately deferred.

**Uvicorn access lines don't carry it either** — that logger has its own
format. Host nginx is the authoritative access log; the app log lines and error
rows are what carry the ID. (Optional future upgrade: nginx
`proxy_set_header X-Request-ID $request_id` would unify the two, and the
middleware already honors a valid inbound header.)

## Log levels

`LOG_LEVEL` in `~/matcha/.env.backend` on the host, default `INFO`.

**Keep it at `INFO` or lower.** Several log calls sit at `WARNING`
*deliberately* — most notably the client-error reports in
`server/app/core/routes/telemetry/client_errors.py`, which are `WARNING` and
not `ERROR` specifically so `ServerErrorDBHandler` (attached to root at
`ERROR`) doesn't double-persist every browser error into
`server_error_reports`. Raising `LOG_LEVEL` past `INFO` drops them from the
logs entirely.

Level conventions in app code:

- `logger.exception` — a genuine failure worth a durable record; the root
  handler persists it to `server_error_reports` and may email an alert
- `logger.warning` — expected/recoverable: a per-item failure inside a batch
  loop, a rate limit, a retry. Deliberately below the DB-handler threshold, so
  a bad batch run doesn't create dozens of rows and alert emails
- `logger.info` — lifecycle and progress
- `logger.debug` — per-frame / per-event detail (WS audio frames, subscribe
  churn); off in prod

`/health` is filtered out of the uvicorn access log — it's polled every few
seconds by the docker healthcheck and the deploy gate, and it drowned
everything else.

## Error alerting

`server/app/core/services/error_notifier.py` emails `error_alert_email`
(default `aaron@hey-matcha.com`, override with `ERROR_ALERT_EMAIL`) when a
**genuinely new** fingerprint appears. Not on every occurrence:

- fingerprint = day-bucket + kind + exception type + message head + top frame
- repeat occurrences bump a counter on the existing row, no new email
- 6h per-fingerprint dedup, 10 emails/hour global cap
- unset the address to disable entirely

This is why level choice matters: an `exception` inside a hot loop can burn the
hourly cap and mask a real alert.

## CloudWatch Logs Insights queries

Once shipping is on (`deploy/cloudwatch/README.md`):

```
# 5xx by path, last hour — run against /matcha/nginx-access
fields @timestamp, @message
| filter @message like /" 5\d\d /
| stats count() by bin(5m)

# Everything for one request ID — /matcha/backend
fields @timestamp, @message
| filter @message like /rid=a1b2c3d4/
| sort @timestamp asc

# Worker task failures — /matcha/worker
fields @timestamp, @message
| filter @message like /ERROR|Traceback/
| sort @timestamp desc
```

## Verifying the error pipeline end to end

A permanent diagnostic task exists for exactly this:

```bash
ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107 \
  "docker exec matcha-worker python -m celery -A app.workers.celery_app \
     call app.workers.tasks.debug_error.raise_test_error"
```

A row with `source='celery'` should appear in Admin → Server Errors within
seconds. This path was silently broken for a long time (the reporter used a
pool-only DB connection, and workers are pool-free by design), so it's worth
re-checking after any change to the worker or the reporter.

## Known gaps

- **Nothing restarts the worker on a schedule.** The design assumes periodic
  tasks re-dispatch via `@worker_ready` on a ~15-minute restart cycle, but the
  host has no cron and no systemd timer — the container just runs continuously
  (`restart: unless-stopped`). In practice scheduled tasks only re-fire when a
  deploy restarts it. Most scheduler rows are disabled anyway, so this is
  latent rather than actively broken, but it means enabling a `scheduler_settings`
  row is not sufficient to make that task run on a cadence.
- **No external uptime monitoring.** No CloudWatch alarms, no third-party
  pinger. The only automated health signal is the blue-green deploy gate
  (which rolls back a bad deploy) and the error-alert email.
- `server/agent/` (the standalone ops agent on :9100) has none of this — no
  error reporter, its own logging config. Out of scope so far.
