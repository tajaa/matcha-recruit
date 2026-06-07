# Security Review & Remediation — 2026-06-06

Full vulnerability review of `/server` (FastAPI) and `/client` (React) plus the fixes that
shipped. This is the **reference doc** — if something breaks after these changes, jump to
[§ Troubleshooting](#troubleshooting--if-something-breaks).

- **Branch the work landed on:** `security-hardening-6-6`
- **Commits (oldest → newest):**
  | Hash | Title |
  |---|---|
  | `3fd66af` | pass 1 — Critical+High (anon company delete, free-Pro signup, PDF SSRF, XSS, SSO scoping, ER bucket, email guard, XFF) |
  | `b8b3963` | pass 2 — SAML takeover, missing-auth, IDOR, react-router bump |
  | `18d4e6e` | medium backlog — docs/secrets/SSRF/limits hardening |
  | `5d03e49` | session revocation — real logout + refresh-token invalidation |
  | `e80da98` | **Werk (macOS)** — external-URL scheme allowlist + delete dead local-git code (branch `werk-6-7`, 2026-06-07) |
  | `270c06d`+ | **Werk Low backlog** — WS header auth, Keychain ThisDeviceOnly, log redaction, https assert, entitlement trim, remaining NSWorkspace sinks (2026-06-07) |
- **Scope:** server + client (`3fd66af`–`5d03e49`) **and** the macOS **Werk** app (`e80da98`, Low-backlog commit) — see [§ Werk (macOS app)](#werk-macos-app).

> ## ⚠️ One action still required
> Commit `5d03e49` adds Alembic migration **`authsess01`** (`users.tokens_valid_after`). It is
> **written but NOT applied to any database.** Apply it before/with the next deploy:
> ```bash
> ./scripts/migrate-dev.sh && ./scripts/migrate-prod.sh
> ```
> The code is deploy-safe and works whether or not the migration is applied (session
> revocation is simply a silent no-op until it is) — see [§ Session revocation](#session-revocation-commit-5d03e49).

---

## Table of contents
1. [How the review was done](#how-the-review-was-done)
2. [Fixes by severity](#fixes-by-severity)
3. [New shared utilities](#new-shared-utilities)
4. [New config / env knobs](#new-config--env-knobs)
5. [Session revocation (deep dive)](#session-revocation-commit-5d03e49)
6. [Troubleshooting — if something breaks](#troubleshooting--if-something-breaks)
7. [Werk (macOS app)](#werk-macos-app)
8. [Verified clean (don't re-audit)](#verified-clean-dont-re-audit)
9. [Remaining backlog](#remaining-backlog)
10. [Verification commands](#verification-commands)

---

## How the review was done

Parallel audit agents, one per vulnerability class: auth/tenant-isolation, injection
(SQLi/cmd/SSRF/path/deser), client-side (XSS/secrets/redirects), file-upload + public
endpoints, secrets/config/CORS/webhooks. A second pass added a **systematic per-endpoint
auth sweep** (every route × its dependency), a SAML-protocol audit, a billing-logic audit,
and real `pip-audit` / `npm audit` runs. Every finding below was re-verified against real
code before fixing.

---

## Fixes by severity

Format: **what was wrong → where → what changed**.

### CRITICAL

| ID | Vulnerability | Location | Fix |
|---|---|---|---|
| C1 | `DELETE /api/companies/{id}` had no auth — anyone could cascade-delete a tenant | `matcha/routes/companies.py:delete_company` | Added `Depends(require_admin)` |
| C1b | `GET /api/companies` (list) had no auth — dumped the whole tenant roster incl. EIN/PII | `companies.py:list_companies` | Added `Depends(require_admin)` |
| C2 | Public `register/business` granted **full Pro** + auto-approved when a public `broker_ref` slug was supplied — free Pro tier, no payment | `core/routes/auth.py` register/business | `broker_ref` is attribution-only now; Pro features + approval only with a valid admin **invite token**, else `pending` with no paid features |
| C3 | WeasyPrint rendered user/AI HTML with the default URL fetcher → `<img src="file:///etc/passwd">` (local read) and `http://169.254.169.254/...` (cloud-metadata SSRF) | ~21 PDF callsites across 14 files | New `safe_url_fetcher` (data:-only) on every render; storage-owned assets inlined as base64 first |
| C4 | Assistant markdown rendered with `rehype-raw` and **no sanitizer** → stored/prompt-injection XSS, steals `localStorage` tokens | `client/.../matcha-work/MessageBubble.tsx` | Removed `rehypeRaw` (assistant content is markdown; raw HTML not needed) |
| C5 | **SAML ACS cross-company / admin account takeover** — the assertion email was looked up globally with no tie to the validated config; any SSO-enabled customer could mint a signed assertion naming any email (incl. a platform admin) | `core/routes/sso.py` ACS handler | Email domain must equal `config.email_domain` **and** an existing user must already belong to `config.company_id`; `default_role` re-validated against the allowlist at auto-provision |

### HIGH

| ID | Vulnerability | Location | Fix |
|---|---|---|---|
| H1 | SSO config GET/PUT/from-metadata not tenant-scoped → cross-tenant IdP overwrite (takeover) | `sso.py` admin/config endpoints | Ownership check (`_assert_company_access`) on all; `default_role` allowlist (`employee`/`client` only, never `admin`) |
| H2 | `GET /api/companies/{id}` unauthenticated → leaked any tenant's EIN/executive contact | `companies.py:get_company` | `require_admin_or_client` + ownership |
| H3 | ER case-export PDFs uploaded to the **public** bucket, bypassing the password-gated download | `matcha/routes/er_copilot.py` | `upload_private_file` (private bucket; streamed download unchanged) |
| H4 | Reserved-domain bounce-storm guard missing on the **MailerSend fallback** path | `core/services/email/client.py:_send_with_fallback` | Guard moved to be transport-independent |
| H5 | Rate limiting trusted client `X-Forwarded-For` (leftmost entry) → spoofable, defeated all IP limits | `core/services/redis_cache.py:client_ip` | Proxy-aware: take the rightmost trusted entry; `TRUSTED_PROXY_COUNT` env (default 1 = single nginx) |
| H6 | SAML replay — IdP-initiated SSO has no `InResponseTo`, so a captured `SAMLResponse` was replayable until expiry | `sso.py` ACS | One-time-use assertion-ID cache (Redis `SETNX`, 24h TTL; degrades open if Redis down) |
| H7 | `POST /api/bulk/companies` + `/api/bulk/positions` unauthenticated mass-writes into core tables | `core/routes/bulk_import.py` | `Depends(require_admin)` on both |
| H8 | `interviews` GET-by-id, list-by-company, and analysis endpoints unauthenticated + unscoped → candidate transcripts leaked cross-tenant | `matcha/routes/interviews.py` | `require_admin_or_client` + company-ownership (404 on mismatch) |
| H9 | **react-router 7.11.0** — XSS, open-redirect, and a turbo-stream deserialization RCE (npm advisories) | `client/package-lock.json` | Bumped to **7.17.0** in-range (`npm audit fix --legacy-peer-deps`) |

### MEDIUM (commit `18d4e6e` unless noted)

| ID | Vulnerability | Location | Fix |
|---|---|---|---|
| M1 | `/docs`, `/redoc`, `/openapi.json` exposed in prod — free endpoint/schema map | `app/main.py` | Served only when `DEBUG` is set |
| M2 | `JWT_SECRET_KEY` / `CHAT_JWT_SECRET_KEY` silently fell back to a random per-process key | `app/config.py` | **Fail closed in prod** (raises if missing when AWS Secrets Manager or `ENV=prod`) |
| M3 | Employee bulk-CSV defaulted `send_invitations=True`, no row cap (bounce-storm risk) | `employees/bulk_upload.py` | Default **False** + 1000-row cap |
| M4 | Anonymous report + per-location intake tokens were 48-bit (`token_hex(6)`) | `ir_incidents/anonymous_reporting.py` | 192-bit `token_urlsafe(24)` (= 32 chars, fits the `VARCHAR(32)` columns) |
| M5 | SSO `from-metadata` did `parse_remote(url)` on a client URL — authenticated SSRF | `sso.py:_assert_safe_external_url` | Reject non-http(s) + private/loopback/link-local/metadata-IP hosts before fetch |
| M6 | `?next=` open redirect on the login page | `client/src/pages/Login.tsx` | Only honor same-origin relative paths |
| M7 | `/logout` was a no-op; refresh tokens non-revocable for 30 days | many (auth path) | [Session revocation](#session-revocation-commit-5d03e49) — commit `5d03e49` |

---

## New shared utilities

Reuse these instead of re-rolling the pattern.

- **`server/app/core/services/pdf.py`**
  - `safe_url_fetcher(url)` — WeasyPrint URL fetcher allowing only `data:` URIs. Pass it as
    `HTML(string=..., url_fetcher=safe_url_fetcher)` on **every** new PDF render.
  - `render_pdf(html, **kw)` — convenience wrapper that applies it.
- **`server/app/core/services/storage.py`** (`StorageService`)
  - `inline_image_data_uri(src)` — download a storage-owned image → `data:` URI (or `None`).
  - `inline_storage_images(html)` — inline all storage-owned `<img src>` in an HTML string.
  - Use these **before** rendering a PDF so logos/covers survive the `safe_url_fetcher` (external
    URLs stay blocked, by design).
  - `upload_private_file(...)` — private-bucket upload (already existed); use for any confidential doc.
- **`server/app/core/dependencies.py`**
  - `session_revoked(conn, user_id, token_iat)` — True if a token predates the user's revocation
    watermark. Call in any new auth path that mints/accepts long-lived tokens.
  - `revoke_user_sessions(conn, user_id)` — bump the watermark (call on logout / credential change).
- **`server/app/core/routes/sso.py`**
  - `_assert_company_access(user, company_id)` — tenant check for SSO config endpoints.
  - `_assert_safe_external_url(url)` — SSRF guard for server-side URL fetches (reusable pattern).

---

## New config / env knobs

| Env var | Default | Effect |
|---|---|---|
| `DEBUG` | unset (off) | When `1`/`true`: enables `/docs` + `/redoc` + `/openapi.json` and the wildcard-localhost CORS regex. **Leave unset in prod.** |
| `TRUSTED_PROXY_COUNT` | `1` | Number of trusted reverse proxies in front of the app. `client_ip()` takes the Nth-from-rightmost `X-Forwarded-For` entry. Set higher if a CDN sits in front of nginx. |
| `ENV` | unset | `prod`/`production` (or presence of `AWS_SECRETS_MANAGER_SECRET_ID`) makes missing JWT secrets fail closed at boot. |
| `GUSTO_WEBHOOK_REQUIRE_SIGNATURE` | `false` | (Pre-existing.) Flip to `true` **after** verifying the HMAC header/scheme against a real signed delivery — see backlog. |

---

## Session revocation (commit `5d03e49`)

The operationally riskiest change — read this before debugging any auth weirdness.

**What it does.** Access + refresh tokens now carry an `iat` (issued-at). A new column
`users.tokens_valid_after` is a per-user watermark: any token with `iat < tokens_valid_after`
is rejected. `/logout`, change-password, and reset-password set the watermark to `NOW()`,
which immediately invalidates **all** of that user's existing access + refresh tokens.

**Where it's enforced.**
- `core/dependencies.py:get_current_user` — every authenticated request.
- `core/routes/auth.py:refresh_token` — so a revoked refresh token can't mint new tokens.

**Deploy safety.** `get_current_user` caches (once per process) whether the column exists. If
the `authsess01` migration hasn't been applied, the check **degrades to a no-op** — auth keeps
working, revocation is just inactive. So deploying the code before running the migration will
NOT lock anyone out. `revoke_user_sessions` likewise swallows `UndefinedColumnError`.

**Grandfathering.** Tokens minted before this shipped have no `iat`; they are treated as valid
until they expire (access 24h, refresh 30d). Full enforcement kicks in once everyone has
re-logged-in post-deploy.

**Migration:** `server/alembic/versions/authsess01_add_tokens_valid_after.py`
(`down_revision = mwjf0001`). Apply with `./scripts/migrate-dev.sh && ./scripts/migrate-prod.sh`.
`database.py:init_db` also adds the column on a fresh bootstrap.

**Not included:** per-token rotation / reuse-detection (this is *global* revocation per user).
Listed in the backlog.

---

## Troubleshooting — if something breaks

Symptom → most-likely cause → resolution.

| Symptom | Cause | Resolution |
|---|---|---|
| **Server won't boot**, `ValueError: JWT_SECRET_KEY is required in production` | M2 fail-closed: prod (AWS Secrets Manager or `ENV=prod`) with the secret unset | Set `JWT_SECRET_KEY` (and `CHAT_JWT_SECRET_KEY`) in the environment / Secrets Manager. This is intended — it was silently using a random key before. |
| **Users randomly get "Session has been revoked. Please log in again."** | Session revocation + **clock skew** between app servers (token `iat` vs DB `NOW()`), or a password reset/logout legitimately fired | Sync server clocks (NTP). If it only happens right after password change/logout, that's correct behavior. |
| **Everyone seems logged out after the migration** | Should NOT happen (old tokens are grandfathered). If it does, a process is setting `tokens_valid_after` in the future | Check for clock skew / a bad bulk `UPDATE users`. |
| **PDFs are missing a logo / image** | C3 `safe_url_fetcher` blocked a non-storage URL | If it's a storage-owned asset, inline it with `storage.inline_storage_images()` before render. If it's a deliberately external asset, it's blocked by design — inline it as base64 or add a narrow allowlist in `pdf.py`. Known flagged spot: `offer_letters.py` remote-logo fallback. |
| **SSO login fails: 403 "Email domain not permitted for this IdP"** | C5: the user's email domain ≠ the SSO config's `email_domain` | Fix `company_sso_configs.email_domain` to match the IdP's user domain. |
| **SSO login fails: 403 "User does not belong to this company"** | C5: the user isn't linked (via `employees`/`clients`) to the config's company | Expected for cross-company attempts. For a legit user, ensure they're provisioned in that company. Platform admins must log in by password, not tenant SSO. |
| **SSO login fails: 403 "SAML assertion already used"** | H6 replay cache rejected a re-submitted assertion | Normal if it's a genuine replay/double-submit. If Redis is down it degrades open (no rejection). |
| **SSO login fails: 403 "SSO is misconfigured (invalid default role)"** | H1: `default_role` is not `employee`/`client` | Set `company_sso_configs.default_role` to `employee` or `client`. |
| **SSO "save from metadata URL" returns 400 "disallowed address"** | M5 SSRF guard: the metadata URL resolves to a private/loopback/metadata IP | Use a public IdP metadata URL. |
| **`/docs` or `/openapi.json` is 404 in an environment where you want it** | M1: docs are DEBUG-only now | Set `DEBUG=1` in that (non-prod) environment. |
| **Bulk employee upload no longer sends invitations** | M3: default is now `send_invitations=False` | Pass `?send_invitations=true` explicitly (the UI toggle does this). |
| **Bulk employee upload returns 413 "Too many rows"** | M3: 1000-row cap | Split the CSV into ≤1000-row files. |
| **`GET /api/companies` or `/companies/{id}` now returns 401/403** | C1b/H2: these are admin-only / ownership-scoped now | Call them authenticated as admin (list) or as the owning company (by-id). The admin UI uses `/admin/companies/*`, which is unaffected. |
| **Interview transcript endpoints now 401/403/404** | H8: scoped to admin or the owning company | Call authenticated and scoped to the right company. |
| **`/api/bulk/*` now returns 401** | H7: admin-only now | Call as a platform admin. |
| **Rate limits feel wrong** (one user limits everyone, or limits never trigger) | H5: `TRUSTED_PROXY_COUNT` doesn't match the real proxy-hop count | If only nginx is in front, keep `1`. If a CDN is added, set to the number of trusted proxies so the correct XFF entry is used. |
| **Gusto webhook starts rejecting events** | `GUSTO_WEBHOOK_REQUIRE_SIGNATURE=true` was set before the HMAC scheme was verified | Unset it, watch logs for "signature mismatch", confirm a real signed delivery verifies, then re-enable. |
| **`npm install` fails with an ERESOLVE peer-dep error** | Pre-existing: `react-simple-maps@3` wants React ≤18, project is React 19 | Use `npm install --legacy-peer-deps` (and `npm audit fix --legacy-peer-deps`). Not caused by this work. |
| **(Werk) a link/attachment won't open** | W1 `SafeURL` opens only `http`/`https`; `file://`/`smb://`/etc. are intentionally blocked | If it's a legit web link, ensure it has an `http(s)` scheme. Non-web schemes are blocked by design. |
| **(Werk) saving a link does nothing** | W1: `addLink` now rejects non-web schemes (a bare host is auto-prefixed `https://`) | Enter a web URL. |
| **(Werk) build error: cannot find `GitService`/`RepoSnapshotService`** | Those files were deleted (dead code) | Nothing should reference them; the live path is `MatchaWorkService.scanCommitsFromGitHub`. If a stale reference remains, remove it. |
| **(Werk) WS connection fails after Low-backlog deploy** | W2: Werk now sends `Authorization: Bearer` header; backend accepts both header and `?token=` query param | Web client still uses `?token=` and is unaffected. If a backend deploy lags, the header path returns 4001 "Missing token" — redeploy the backend first. |
| **(Werk) a checkout / PDF / OAuth URL won't open** | W8: now gated by `SafeURL` (http/https only) | Ensure the URL from the server uses an `https://` scheme. Non-http schemes are intentionally blocked. |

---

## Werk (macOS app)

Reviewed 2026-06-07 (`desktop/Werk`, SwiftUI). Same 4-class fan-out (credentials/storage,
network/transport, local-exec/files, URL-handling/IPC). **Overall much healthier than
server/web — zero Critical, one High.** Tokens are in the Keychain, no hardcoded secrets, no
cert-validation bypass, ATS at the secure default, no WKWebView, no custom URL scheme (so no
forgeable OAuth callback), app is sandboxed.

### Fixed (commit `e80da98`)

| ID | Severity | Issue | Fix |
|---|---|---|---|
| W1 | High | Peer/server-controlled URL fields (chat attachments, project links, element notes, file storage URLs, channel attachments — all `Codable` from API/WS) were opened via `NSWorkspace.shared.open` with **no scheme check** → a malicious peer could plant `file://`, `smb://` (remote-share mount → credential leak), `ssh://`, `x-apple.*` and have a click trigger it | New `Matcha/Services/Support/SafeURL.swift` (http/https only); all 5 open sinks routed through it + write-time validation in `addLink` |
| W3 | (latent) | `GitService.swift` + `RepoSnapshotService.swift` were **orphaned dead code** (commit-scan re-implemented server-side via the GitHub API) carrying a latent symlink-escape arbitrary-file-read → exfil and a git arg-injection gap | Deleted both files + the unused `MatchaWorkService.scanCommits` / `putElementRepoSnapshot` methods. Live `scanCommitsFromGitHub` path unaffected. Verified `xcodebuild BUILD SUCCEEDED` |

Reuse `SafeURL.open(_:)` / `SafeURL.isAllowed(_:)` for any future external-URL open of
network/user data. The pre-existing safe pattern at `JournalContentView.swift:394` is the precedent.

### Fixed — Low backlog (2026-06-07)

| ID | Issue | Fix |
|---|---|---|
| W2 | JWT in WebSocket URL `?token=` → log-leak + proxy log exposure | Backend `channels_ws.py` / `project_ws.py`: added `_token_from_request()` — prefers `Authorization: Bearer` header, falls back to `?token=` (web clients). Werk clients (`ChannelsWebSocket`, `ProjectWebSocket`): switched to `URLRequest` + `Authorization` header; token no longer appears in any URL or log |
| W4 | Keychain used `kSecAttrAccessibleAfterFirstUnlock` — tokens synced via iCloud Keychain / iTunes backup to other devices | Changed to `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` (`KeychainHelper.swift:35`). Existing items migrate on next `save()` (every token refresh) |
| W5 | Decode-failure log printed a 500-byte response snippet — would leak `access_token`/`refresh_token` if an auth endpoint response failed to decode | `APIClient.swift:222`: redact snippet to `<redacted>` when `path` contains `/auth` or `token` |
| W6 | `MATCHA_API_URL` env override had no scheme validation → HTTP downgrade in release builds | `APIClient.swift:76`: `precondition(override.hasPrefix("https://"))` in `#if !DEBUG` blocks |
| W7 | `com.apple.security.network.server` entitlement was over-broad — app is a pure client, never opens listening sockets | Removed from `Matcha.entitlements` |
| W8 | Six remaining `NSWorkspace.shared.open` sinks for server-derived URLs (Stripe checkout, Gmail OAuth consent, Presentation PDF, channel checkout ×2, Gmail connect in AgentPanel) bypassed SafeURL scheme check | Routed all six through `SafeURL.open(_:)`. Note: Gmail OAuth uses browser-handoff + server-callback (no registered URL scheme), so `ASWebAuthenticationSession` is not applicable — polling is correct |

### Werk — verified clean

Keychain token storage (data-protection keychain, legacy UserDefaults leak already migrated out),
no hardcoded secrets, no cert-validation bypass / no ATS exception, no WKWebView, no custom URL
scheme or deep-link handler, no insecure deserialization (`Data(contentsOf:)` is on user-picked
files only), `SecureField` for passwords, no secrets to pasteboard, sandbox entitlements otherwise
minimal, the single `Process()` (now deleted) used the safe argv-array pattern (no shell).

---

## Verified clean (don't re-audit)

These were checked and found sound — no action taken:

- **Stripe webhook** signature verification (fail-closed + idempotent via `stripe_webhook_events`).
- **Billing logic** — server-side pricing only (no client-controlled price/quantity/amount),
  entitlements granted **only** by the signed webhook (no client "confirm/success" grant path),
  atomic token-budget deduction (`SELECT … FOR UPDATE`), no billing IDOR, personal vs business
  pricing enforced.
- **SQL injection** — all queries parameterized; dynamic SQL is built from hardcoded fragments only.
- **Command injection** — zero `subprocess`/`shell=True` in `app/`; git integration is GitHub-API based.
- **Path traversal** — `storage._resolve_local_upload_path` uses `realpath` + boundary check; S3 keys are server-generated UUIDs.
- **Secrets** — no hardcoded secrets; no committed `.env`/`.pem`/`token.json`.
- **CORS / headers** — explicit origin allowlist (no `*` + credentials), full security headers + HSTS, `TrustedHostMiddleware`.
- **JWT** — algorithm pinned (`HS256`), `require_exp` enforced (no `alg:none`).
- **Long-tail routers** (accommodations, pre_termination, separation, training, cobra, i9, flight_risk,
  broker_portfolio, notifications, employee_portal, …) — tenant-scoped.
- **WebSockets** (interview / channel / thread / project / chat) — authenticate via JWT (Werk native: `Authorization: Bearer` header; web: `?token=` query) and check membership before join.
- **OAuth callbacks** (Gusto/Finch/Slack) — state-validated.
- **`pip-audit`** — no known vulnerabilities.

---

## Remaining backlog

Low / ops / breaking-only — none are exploitable Critical/High:

- **Gusto webhook fail-open** — intentional rollout gate; flip `GUSTO_WEBHOOK_REQUIRE_SIGNATURE=true`
  after verifying the HMAC scheme (ops action, not code).
- **Free-token-grant lazy-create** — dual lazy-create is fragile but not exploitable; create the
  budget row at company creation (`token_budget_service`).
- **Admin refund** doesn't verify `charge_id` belongs to the company — low (admin-only; Stripe enforces account ownership).
- **Access-token TTL** is 24h — now mitigated by session revocation; consider shortening to 15–60 min.
- **SAML per-token reuse-detection / refresh-token rotation** — this pass added *global* per-user
  revocation; true per-token rotation is a further enhancement.
- **npm transitive advisories** (excalidraw / mermaid → nanoid/uuid) — 1 critical + 6 high remain,
  fixable only with a breaking `npm audit fix --force` major bump of the diagram widget.

---

## Verification commands

```bash
# Backend compiles
cd server && ./venv/bin/python -m compileall -q app/

# Alembic chain (head should be authsess01)
cd server && ./venv/bin/alembic heads

# Frontend typecheck + audit
cd client && npx tsc --noEmit
cd client && npm audit --legacy-peer-deps

# Dependency audit (server)
cd server && ./venv/bin/pip-audit -r requirements.txt
```

**Live checks (need the dev tunnel up — `./scripts/dev-remote.sh`):**
```bash
# C1/C1b/H2 — expect 401/403, not 200
curl -i -X DELETE  $API/api/companies/<uuid>
curl -i            $API/api/companies
curl -i            $API/api/companies/<uuid>

# C3 — a project section containing <img src="file:///etc/hostname">, exported to PDF,
#      must NOT contain the file's contents.

# M7 — log in, hit a protected endpoint (200), POST /api/auth/logout, retry with the
#      same access token → expect 401 "Session has been revoked" (after authsess01 applied).
```
