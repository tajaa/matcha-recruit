# Full Code Review — Backend, Frontend, Desktop/Werk

_Conducted: 2026-05-31. Read-only review; no code was changed._

Scope: the three first-party surfaces of Matcha Recruit —
- **Backend** — FastAPI + asyncpg + Celery, `server/app` (342 files, ~189k LOC)
- **Frontend** — React/TS SPA, `client/src` (480 files, ~104k LOC)
- **Desktop/Werk** — SwiftUI macOS app, `desktop/Werk/Matcha` (138 files, ~41k LOC)

Findings are concrete and carry `file:line` references and a suggested fix.
Severity is the reviewer's judgement (Critical / High / Medium / Low). This is a
review document, not a changelog — implementation is tracked separately.

---

## Executive summary

Overall the codebase is in **better shape than its size suggests**. The backend
uses parameterized SQL throughout (no SQL injection found), tenant isolation is
applied consistently, and the Stripe/webhook/public-input paths show real
security thought. The frontend has **zero `dangerouslySetInnerHTML`** and a
correctly-built refresh-dedup. The desktop app stores tokens in the
data-protection Keychain and gates paid features server-authoritatively.

**No Critical issues were found in the frontend or desktop apps.** The backend
has no string-formatted-SQL or unauthenticated-admin-route classes of bug. The
highest-value work is a small number of **High** items, several of which share a
single root cause across surfaces.

### Cross-cutting theme: JWT in WebSocket URLs (fix once, fix everywhere)
The same credential-leak appears on **both** clients: the access token is passed
as `?token=<jwt>` on WebSocket connects, and on desktop it's also logged.
Query strings land in nginx/proxy access logs, browser history, `Referer`, and
crash reports — leaking a full bearer credential.

- Frontend: `client/src/api/channelSocket.ts:81`, `threadSocket.ts:41`, `projectSocket.ts:77`, `hooks/useVoiceSession.ts:139`
- Desktop: `Services/ChannelsWebSocket.swift:74`, `Services/ProjectWebSocket.swift:95` (+ logged at `ProjectWebSocket.swift:99`)

**Fix once:** issue a short-lived single-use WS ticket over HTTPS (the interview
WS already does this via `create_interview_ws_token`) or send the JWT in the
`Sec-WebSocket-Protocol` header, and update the backend handshake to read it
there. Then migrate all six client call sites. This is the single highest-ROI
change in the review.

### A second cross-cutting theme: raw `fetch`/upload paths bypass token refresh
Both clients have call sites that read the token directly and skip the
refresh-and-retry wrapper, so an expired token mid-session produces a hard 401
with no recovery (broken downloads, broken AI streams, broken uploads).
- Frontend: `client/src/api/client.ts:246-279` (downloads), ~20 SSE/stream sites (e.g. `components/ir/IRCopilotPanel.tsx:74,170`)
- Desktop: multipart uploads in `Services/AuthService.swift:129`, `ChannelsService.swift:261`, `InboxService.swift:54,92`

---

## Prioritized action list (the short version)

| # | Item | Surface | Severity |
|---|---|---|---|
| 1 | Move JWT out of WebSocket URLs (+ stop logging it) — single-use ticket / header | FE + Desktop + BE handshake | High |
| 2 | Run the app DB role as **non-superuser, non-owner** so `FORCE ROW LEVEL SECURITY` actually binds | Backend | High |
| 3 | Make tenant GUCs transaction-local (`set_config(..., true)`) so they can't outlive a request under pool reuse | Backend | High |
| 4 | Back the anonymous-report rate limiter with Redis + parse `X-Forwarded-For` (currently per-worker, leaks memory, miskeys behind nginx) | Backend | High |
| 5 | Make `ProjectDetailViewModel` / `ThreadDetailViewModel` / `ThreadListViewModel` class-level `@MainActor` | Desktop | High |
| 6 | Validate URL scheme in markdown→HTML to block `javascript:` links | Frontend | High |
| 7 | Route all downloads/streams/uploads through the token-refresh wrapper | FE + Desktop | High/Med |
| 8 | Stripe webhook dedupe should **fail closed** (500 → Stripe retries) when the dedupe table errors | Backend | Medium |
| 9 | Wrap blocking boto3/`open()`/`urlopen` storage calls in `asyncio.to_thread`; drop/allowlist the HTTP download fallback (SSRF) | Backend | Medium |
| 10 | WS reconnect should stop on auth-class close codes + use capped backoff | Frontend | Medium |

---

## Backend (`server/app`)

**Critical:** none found.

**High**
- **RLS escape hatch is permanently wide for non-tenant connections** — `database.py:120-123` (+ policy at `database.py:575`). Any `get_connection()` opened with the admin contextvar sets `app.is_admin='true'`, and the DB user is a Postgres **superuser** (per CLAUDE.md), so superusers ignore RLS unless `FORCE` + non-owner. RLS is therefore defense-in-depth only — any query missing its `WHERE company_id = $1` leaks cross-tenant. _Fix:_ run as a non-superuser non-owner role and default connections to deny.
- **Session-scoped `set_config` with manual reset is fragile under the pool** — `database.py:109-138`. GUCs are set session-level (third arg `false`) and only cleared in `finally`; asyncpg's default `DISCARD ALL` on release currently saves it, but an exception between `acquire()` and the resets, or a pool-default change, can carry one tenant's `app.current_tenant_id` into the next request. _Fix:_ transaction-local config (`set_config(..., true)`) inside an explicit transaction.
- **In-process anonymous-report rate limiter is per-worker + unbounded** — `inbound_email.py:36-47`. Module-level dict keyed by IP → real limit is `5 × worker_count`, dict never evicts (slow leak) on a public unauthenticated endpoint. _Fix:_ Redis with TTL.
- **Rate-limit key uses `request.client.host`, not forwarded header** — `inbound_email.py:136`. Behind nginx that's the proxy IP, so the whole internet shares one bucket (or a constant). _Fix:_ parse `X-Forwarded-For` (consistent with how the file already trusts `X-Forwarded-Host`).

**Medium**
- JWT decode lacks `options={"require":["exp"]}` / audience hardening; interview-WS + email-verify tokens share the session secret/algorithm, relying only on a manual `type` field — `core/services/auth.py:160-164` (`:100`, `:136`).
- Stripe webhook dedupe **fails open**: if the `stripe_webhook_events` insert raises, `_claim_event` returns `True` and processing continues → double token grants / duplicate feature flips on Stripe retries — `stripe_webhook.py:44-49`. _Fix:_ fail closed.
- Legacy CloudFront/HTTP download is a latent SSRF **and** a blocking `urllib.request.urlopen` in async (up to 30s loop stall) — `storage.py:160-166`.
- Blocking boto3 `get_object`/`delete_object` + local `open()` in `async def` (only uploads use an executor) — `storage.py:154,178,184-185,199,213`.
- Credential extraction runs Gemini inline via `background_tasks` holding 10 MB bytes in-process — compounds the documented PDF/WeasyPrint memory pressure — `employee_portal.py:1248-1271`. _Fix:_ dispatch to Celery with the S3 path.
- Upload trusts client `content_type` + filename; no magic-byte sniff — `employee_portal.py:1217-1224`.
- Bare `except:` swallows `KeyboardInterrupt`/`SystemExit` and masks JSON corruption — `admin.py:1706,1710`.
- Unbounded aggregation/admin result sets (no LIMIT/pagination) — `ir_incidents/analytics.py:66+`, `admin.py:5193`.

**Low**
- N+1 in Stripe tip handler (`stripe_webhook.py:167-169`); `matcha_work.py` breadth + duplicated `_serialize_*`/metadata-coercion (well-isolated tenant checks, though — `_verify_project_access` used 95×); per-request `LIMIT 0` subquery probing (`admin.py:8213-8226`, `dashboard.py:1297`); random JWT secret generated (not fail-fatal) when env-configured (`config.py:208-212`).

**Done well:** parameterized SQL everywhere (no SQLi); Stripe signature verification + event-id dedupe; hardened public endpoints (honeypot, single-use token burn under `FOR UPDATE`, server-derived company/location, `secrets.token_hex`); admin `company_id` overrides correctly restricted to `role=="admin"`; path-traversal guard via `realpath` containment; reserved-domain email guard implemented + called; Celery tasks use `bind=True`+`max_retries`+`task_acks_late`.

---

## Frontend (`client/src`)

**Critical**
- **JWT in WS query string** — see cross-cutting theme above (`channelSocket.ts:81`, `threadSocket.ts:41`, `projectSocket.ts:77`, `useVoiceSession.ts:139`).
- **Feature gating is client-side only** — `FeatureGate.tsx:30-41`, `useMe.ts:55-58`, `utils/tier.ts`. Acceptable ONLY if every backend route is independently `Depends(require_feature(...))`; treat `<FeatureGate>` as UX, not a security boundary. _Action:_ verify server-side gating exists for all `/ir/*`, `/handbooks/*`, `/discipline/*`, etc.

**High**
- `_logout()` redirect has no path guard → potential redirect loop — `api/client.ts:39-57`.
- Concurrent-401 retry that still 401s throws without `_logout()`, leaving a half-authed state — `api/client.ts:75-104`.
- `download()`/`downloadPost()` bypass refresh-and-retry — `api/client.ts:246-279`.
- Markdown→HTML emits unvalidated `href`, allowing `javascript:` links from AI/collaborator content — `components/matcha-work/markdownToHtml.ts:14`. _Fix:_ scheme allowlist + TipTap Link `protocols`/`validate`.
- `useMe` module cache only invalidated via full reload; SPA-internal user switches (SSO/impersonation) serve stale `me` — `hooks/useMe.ts:5-22`.
- `MeResponse.profile` nullability vs access in tier dispatch — `TenantSidebar.tsx:28-31`, `utils/tier.ts:11-39` (mostly `?.`-safe; make `profile` optional in types).

**Medium**
- IR copilot cold-start effect deps `[loading]` only → stale closure if `incidentId` changes — `IRCopilotPanel.tsx:150-156`.
- ~20 streaming/SSE sites read `localStorage` token directly, no refresh — `IRCopilotPanel.tsx:74,170`, `hooks/ir/useIRAnalysisStream.ts:33`, `hooks/useEnrichStream.ts:59`.
- WS reconnect loops forever at 3s even on auth-reject close — `channelSocket.ts:152-160,246-251` (+ thread/project).
- `useEmployees` double-fetch/waterfall — `hooks/employees/useEmployees.ts:48`.
- ~127 `api.get().then(setState)` effects lack AbortController → setState-after-unmount + response-ordering races — e.g. `hooks/ir/useIRIncident.ts:10-19`, `hooks/useOnlineUsers.ts:18-33`.
- `useSidebarBadges.markSeen` `setTimeout` without cleanup — `hooks/useSidebarBadges.ts:91`.
- Index-as-key in reorderable lists (171 occurrences) — e.g. `BulkUploadModal.tsx:84`, `IRCopilotPanel.tsx:464`, `AnomaliesPanel.tsx:56`.
- Checkout logic duplicated 7× + unvalidated `data.checkout_url` redirect — `TenantSidebar.tsx:45-62`.

**Low**
- `: any` in ~25 sites (`api/broker.ts:20`, `JurisdictionDetailPanel.tsx:88,131,606`); non-null assertions on optional params (`HandbookForm.tsx:107,243`); largest components 1,000–1,300 LOC (`pages/admin/Newsletter.tsx`, `AdminCompanyDetail.tsx`, `work/MatchaWorkThread.tsx`, `work/ChannelView.tsx`); `useMe` derived object not memoized (`useMe.ts:60-69`).

**Done well:** no `dangerouslySetInnerHTML` anywhere (content via TipTap schema); refresh-dedup singleton handles concurrent 401s; thoughtful error reporter (dedup window, in-flight cap, `keepalive`, root `ErrorBoundary`); disciplined WS classes (`_closed` flag, paired ping/`_stopPing`, malformed-message guards, shared-channel singleton); rigorous `useVoiceSession` teardown; streaming hooks already use AbortController; optimistic-UI loopback dedup in `ChannelView`.

---

## Desktop / Werk (`desktop/Werk/Matcha`)

**Critical:** none. No `try!`, no plaintext token storage, no hardcoded secrets, no `NSAllowsArbitraryLoads`, Plus gating is server-authoritative.

**High**
- JWT in WS URL — `ChannelsWebSocket.swift:74`, `ProjectWebSocket.swift:95` (cross-cutting).
- Full WS URL (incl. token prefix) logged to unified logging in release — `ProjectWebSocket.swift:99`.
- `ProjectDetailViewModel` (1,454 LOC) is `@Observable` but **not** class-level `@MainActor`; mixed annotated/unannotated methods mutate observable arrays SwiftUI reads in `body` → data race — `ViewModels/ProjectDetailViewModel.swift:13`.
- `ThreadDetailViewModel` / `ThreadListViewModel` same issue; rely on hand-placed `MainActor.run` (e.g. `streamingTask` mutated off-actor at `ThreadDetailViewModel.swift:295`) — `ThreadDetailViewModel.swift:4`, `ThreadListViewModel.swift:4`. _Fix:_ annotate the classes `@MainActor`.

**Medium**
- Force-unwraps: `components.url!` / `URLComponents(string:)!` on a user-controlled query — `ChannelsService.swift:45,31`; `as! NSTextView` — `RichJournalEditor.swift:164`; `URL(string:"about:blank")!` fallback — `InboxView.swift:255`.
- Multipart uploads bypass the 401-refresh/maintenance-retry path — `AuthService.swift:129`, `ChannelsService.swift:261`, `InboxService.swift:54,92`.
- `try?` collapses network errors to empty (500/auth looks like "no data") — `ChannelsService.swift:278`, `App/DetailPanes.swift:217-220`.
- ~58 `print(...)` in release paths, incl. per-inbound-message in `AppState.onMessageGlobal` — `ChannelsWebSocket.swift:358,377,397,415`, `AppState.swift:245-249`, etc.
- `SplitSwitcherModel` (`DetailPanes.swift:200-228`) / non-isolated observable classes read state off-actor.

**Low**
- Cached `JSONDecoder` not actually reused (fresh decoder per request) + ~25 ad-hoc decoders — `APIClient.swift:105-113,213-215`; scattered `ISO8601DateFormatter()` allocations (no central `dateDecodingStrategy`); hardcoded real Gmail debug login (`AuthViewModel.swift:6` — should be reserved-domain per repo rules); `ChannelStarStore` local-only (notification prefs lost on reinstall — `ChannelStarStore.swift:9-11`); `restoreSession()` can't distinguish network vs auth failure → premature logout (`AuthService.swift:77-87`); large files (`TaskViewerSheet.swift` 1,960, `MatchaWorkService.swift` 1,829 god-object, `ProjectFilesView.swift` 1,560).

**Done well:** tokens in data-protection Keychain with self-cleaning legacy migrations (plaintext-UserDefaults branch removed); Plus gating server-authoritative (client only toggles an upgrade affordance); refresh-token stampede handled via shared in-flight `Task`; robust WS lifecycle (capped exponential backoff, token refresh before reconnect, App-Nap assertion, room replay on handshake); consistent `[weak self]` (no retain cycles found); thoughtful SwiftUI perf (badge observation split-out, memoized kanban grouping, bounded LRU VM store); correct `.task(id:)` usage.

---

## Suggested sequencing

1. **WS token handling** (action #1) — one backend ticket/header change unlocks fixing all six client call sites; highest ROL and closes a real credential leak on both clients.
2. **DB tenancy hardening** (#2, #3) — non-superuser role + transaction-local GUCs turn RLS from advisory into an actual backstop.
3. **Public-endpoint hardening** (#4) — Redis-backed limiter + correct client-IP; it's the only unauthenticated, internet-facing write path.
4. **Token-refresh coverage + WS reconnect** (#7, #10) and the **`javascript:` link** fix (#6) — small, contained client changes.
5. **Desktop `@MainActor`** (#5) — mechanical but eliminates a class of intermittent UI races.
6. Stripe dedupe fail-closed (#8) and async storage I/O (#9) as backend follow-ups.

Maintainability items (giant files on all three surfaces) are real but should
follow the correctness/security work, and ideally land alongside the test
harness described in `docs/TEST_COVERAGE.md` so refactors are covered.
