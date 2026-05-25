# Gusto HRIS Integration — Review & Fixes

_Last updated: 2026-05-24_

Covers the Gusto HRIS integration (OAuth connect → roster sync → termination webhook),
the issues found in review, the fixes applied, and the deploy/rollout steps that still
need a human.

## Architecture (as built)

| Piece | Where |
|---|---|
| OAuth connect (`authorization_code`) | `server/app/matcha/routes/provisioning.py` — `GET /hris/authorize`, `GET /hris/callback` |
| Roster sync orchestrator | `server/app/matcha/services/hris_sync_orchestrator.py` — `start_hris_sync`, `_sync_single_employee` |
| Gusto API client + normalize | `server/app/matcha/services/hris_service.py` — `GustoHRISService` |
| Termination webhook | `provisioning.py` — `POST /hris/webhook/gusto` (+ `GET /hris/webhook/gusto/token`) |
| Connect modal (frontend) | `client/src/components/employees/HRISSyncModal.tsx` |

Key facts:
- Gusto **demo** base URL is `https://api.gusto-demo.com` (not `api.gusto.com`); `/v1/me`
  404s on demo — use `/v1/companies`.
- OAuth credentials are **app-level** env vars (`GUSTO_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI`),
  not per-company. Fail-fast at import if missing.
- Webhook is **app-level**: one subscription for the whole partner app, verified once by the
  operator. Gusto carries the company in `resource_uuid` (not `company_uuid`).
- Canonical roster state is `employees.employment_status` (VARCHAR: active / on_leave /
  suspended / on_notice / furloughed / terminated / offboarded — `VALID_EMPLOYMENT_STATUSES`
  in `routes/employees/crud.py`). The employees list filters/displays on this column.
  `is_active` (BOOLEAN) is a separate login flag, NOT roster state.
- Employees are matched to Gusto records by `hris_id` (Gusto employee UUID), backed by the
  partial unique index `(org_id, hris_id) WHERE hris_id IS NOT NULL` (migration `emphris0001`).

## Issues found & fixed

### 🔴 #1 — Sync never wrote termination status
`normalize_worker` computed a status from Gusto's `terminated` flag, but `_sync_single_employee`
dropped it: INSERT relied on the DB default `'active'` and UPDATE never touched
`employment_status`. Result: an already-terminated Gusto employee imported as **active**,
"Sync now" never reconciled terminations, and the live webhook was the only path that ever
set `'terminated'` (so a missed webhook was unrecoverable).

**Fix:**
- Renamed normalize key `status` → `employment_status`, mapping to valid roster values
  (`'terminated'` when Gusto `terminated`, else `'active'`) in both Gusto and ADP clients.
- INSERT now writes `employment_status`.
- UPDATE uses a CASE that **propagates** termination and rehire from Gusto but **preserves**
  Matcha-set states (on_leave / suspended / …) when Gusto only says `active`:
  ```sql
  employment_status = CASE
      WHEN $9 = 'terminated' THEN 'terminated'
      WHEN employees.employment_status = 'terminated' AND $9 = 'active' THEN 'active'  -- rehire
      ELSE employees.employment_status
  END
  ```

### 🔴 #1b — Match-by-email regressed against the new unique index
`_sync_single_employee` looked up existing rows only by `(org_id, email)`. With the
`(org_id, hris_id)` partial unique added in the same commit, a Gusto email change meant no
email match → INSERT → unique violation on `hris_id` → row counted as an error and left stale.

**Fix:** look up by `hris_id` first when present, fall back to email for pre-backfill rows.

### 🟡 #2 — Webhook signature not enforced (default-open)
With `GUSTO_WEBHOOK_SECRET` empty (prod state at review), signature verification was skipped
entirely — anyone who knew the URL could POST a forged `employee.terminated` event (needs only
a valid `gusto_company_id` + employee UUID) and mark employees terminated.

**Fix (gated, not hard fail-closed):** the `X-Gusto-Signature` + hex HMAC-SHA256 scheme in the
code had **never been exercised** (secret was empty), so hard-rejecting risked locking out the
working termination flow if the header name/scheme guess is wrong. Verification is now advisory
until proven: signature mismatches are **logged but accepted** unless
`GUSTO_WEBHOOK_REQUIRE_SIGNATURE=true`. See rollout below.

### 🟡 #3 — Verification-token endpoint leaked across tenants
`GET /hris/webhook/gusto/token` returned the latest `gusto_webhook_tokens` row with no company
scoping — any client admin could see the last-registered token for any company.

**Fix:** restricted to `require_admin`. The webhook is app-level (one operator verifies it once),
so platform-admin-only is the correct scope; no schema change needed.

### 🟡 #4 — Debug PII logging left in
`RAW: {body…}` logged full webhook payloads (employee names/ids) at INFO on every event.

**Fix:** removed the RAW line. Remaining `event/entity/company` log is identifiers only.

### 🔵 Not changed (low priority, documented)
- **#5 Dead Gusto mock path** — `_GUSTO_MOCK_EMPLOYEES` + the `mode=="mock"` branch in
  `GustoHRISService.fetch_workers` are unreachable (the factory returns ADP `HRISService` for
  `mode="mock"`). Delete or give mock a `provider` key if dev-testing Gusto is ever needed.
- **#6 Legacy `/v1/me`** in `test_connection` + `resolve_company_uuid` — 404s on gusto-demo;
  only reachable via the dead client_credentials manual-connect path (OAuth uses `/v1/companies`).
- **#7 No resync debounce** — `employee.updated` fires a full roster re-sync per event; a bulk
  Gusto edit = N full syncs. Fine at current scale.
- **#8 Modal nits** — already fixed in current code (`setConnectionStatus(null)` at effect start,
  accurate disconnect comment, credential form removed).

### ✅ Already fixed before this pass
fetch_workers guard ordering, `isinstance(batch, list)` type guard, `resp.text[:300]` truncation,
`client_id` moved to config (decrypt-loop bug gone), `require_feature("hris_import")` on all
`/hris/status|connect|disconnect|sync|sync/history|sync/{id}` endpoints.

## Files changed in this pass
- `server/app/matcha/services/hris_service.py`
- `server/app/matcha/services/hris_sync_orchestrator.py`
- `server/app/matcha/routes/provisioning.py`

## Deploy & rollout (human steps)

These are **code-only** changes — migration `emphris0001` (adds `employees.hris_id` + partial
unique) was already deployed.

1. **Deploy:** `build-and-push.sh` → `update-ec2.sh`.
2. **Sync now:** open the HRIS modal → "Sync now". This now backfills `employment_status` on
   existing employees AND reconciles anyone already terminated in Gusto who currently shows
   active.

### Enforcing webhook signatures (do this carefully)
The signature scheme is an unverified guess until proven against a real signed delivery:

1. Get the signing secret from Gusto's webhook config.
2. Set `GUSTO_WEBHOOK_SECRET` in local `.env` **and** prod `.env.backend`. Redeploy.
3. Watch logs: `docker logs matcha-backend 2>&1 | grep "Gusto Webhook"`.
   - `signature mismatch` warnings on real deliveries → header name / HMAC scheme is wrong.
     Fix `X-Gusto-Signature` / the HMAC construction in `provisioning.py` before enforcing.
   - No mismatch warnings + terminations applying → scheme confirmed.
4. Once a real signed delivery verifies clean, set `GUSTO_WEBHOOK_REQUIRE_SIGNATURE=true` in
   prod `.env.backend` → fully fail closed (forged/unsigned events rejected).

## Env vars
| Var | Purpose |
|---|---|
| `GUSTO_OAUTH_CLIENT_ID` / `GUSTO_OAUTH_CLIENT_SECRET` / `GUSTO_OAUTH_REDIRECT_URI` | App-level OAuth (required; fail-fast if missing) |
| `GUSTO_BASE_URL` | Defaults `https://api.gusto-demo.com` |
| `GUSTO_WEBHOOK_SECRET` | Webhook HMAC signing secret (empty = unsigned events accepted with warning) |
| `GUSTO_WEBHOOK_REQUIRE_SIGNATURE` | `true` = fail closed on unsigned/bad-signature events. Default off until scheme verified |

## Verification
- Unit (no DB): `normalize_worker({terminated: true})` → `employment_status == 'terminated'`;
  `{terminated: false}` → `'active'`; no stale `status` key.
- E2E (manual, user-run): terminate in Gusto-demo → "Sync now" → confirm roster shows terminated
  (not just via webhook). Then re-terminate with webhook live and grep `[Gusto Webhook]` logs.
- Single alembic head: `cd server && ./venv/bin/python -m alembic heads` → `emphris0001`.
