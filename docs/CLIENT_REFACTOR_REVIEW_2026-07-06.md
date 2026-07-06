# Client Refactor Review — 2026-07-06

Review of commit **`7090a0d`** — *"Client security audit: fix token leakage, cache leaks,
guards, fetch races"* (52 files, +479/−160). Verdict up front: **the commit is sound and
complete on everything it claims** — every theme in the commit message was verified present
and correct, `npx tsc --noEmit` is clean, and the three modified server WS files compile.
What follows is (1) what was verified, (2) small issues *inside* the commit, and (3) the
**remaining work** — instances of the same bug classes the audit fixed that are still in the
tree. Section 3 is the actionable backlog.

- **Branch reviewed:** `main` tip (`claude/client-refactor-review-j1x6gu` is even with main)
- **Verification run:** `npx tsc --noEmit` (clean), `python3 -m py_compile` on
  `channels_ws.py` / `project_ws.py` / `thread_ws.py` (clean), plus codebase-wide greps for
  each fixed pattern (commands in [§5](#5-verification-commands)).

---

## Update (2026-07-06) — follow-up fixes applied on this branch

A second commit on `claude/client-refactor-review-j1x6gu` lands the tractable, low-risk items
from the backlog below. `npx tsc --noEmit` clean after the changes.

**Applied:**
- **§3.1 TenantSidebar checkout** — all three pending-sidebar `handleSubscribe` handlers
  (Lite / Compliance / X) converted from raw `fetch` + `localStorage` token to
  `api.post` (401 refresh-and-retry; `ApiError.message` surfaces the server `detail`). The
  now-unused `BASE` const was removed. Fixes the idle-then-Subscribe dead-checkout.
- **§2.2 / §3.2 noopener** — `useCredentialDocuments.ts:68` and `cappeClient.ts:163`
  `window.open` now pass `'noopener'`.
- **§3.5 invite-code encode** — `channels.ts` `joinByInvite` wraps the user-typed `code` in
  `encodeURIComponent`.
- **§2.3 errorReporter** — `api_endpoint` is now query/fragment-stripped and `_scrub`bed
  before it reaches the error store.
- **§3.3 useRiskAssessment** — added the `reqId` stale-response guard (company-switcher race)
  and changed the catch to `e instanceof ApiError && e.status === 404` (was a brittle
  `message.includes('404')` that missed 404s carrying a `detail` body).
- **§3.1 decodeTokenRole removed** — its sole caller (`useRiskAssessment`) now reads the role
  from `useMe()`; the hand-rolled JWT-decoder in `types/risk-assessment.ts` is deleted.
- **§3.6 logout robustness** — `resetAuthCaches()` added to the three hard-navigate logouts
  (`WorkSidebar`, `WerkLiteSidebar`, `PortalSidebar`) so the "every token-removal site resets
  caches" invariant holds even if one is later converted to SPA `navigate()`.
- **§3.1 uploadMedia** — `pages/admin/Newsletter/uploadMedia.ts` uses `api.upload`.

**Deliberately deferred (rationale):**
- **§3.1 `Settings.tsx`** — ~15 `authHeaders()`/`fetch` call sites, each with bespoke
  response handling; a whole-file rewrite with real regression surface. Admin-only (low blast
  radius). Worth a dedicated pass, not folded into this commit.
- **§3.1 public lead-gen / newsletter fetches** (`HandbookGapAnalyzer`, `HandbookGapResult`,
  `NewsletterSignup`, `NewsletterHeroSection`) — these are **intentionally** bare `fetch` with
  an optional token; the client CLAUDE.md documents bare `fetch()` as the pattern for
  public/anon endpoints. Primary users are logged-out visitors, so the token-refresh benefit
  is marginal and converting fights the documented convention. Left as-is.
- **§3.4 voice-WS `?token=`**, **§3.7 WS `?token=` fallback removal**, **§3.8 helper dedupe**
  — unchanged: §3.7/§3.8 need the post-deploy soak window; §3.4 is a low-severity
  short-lived-token parity item.
- **§2.1 useMe broadcast**, **§2.4 kanban comment**, **§2.5 WS loop** — accept-as-is items,
  unchanged.

---

## Table of contents
1. [Verified complete](#1-verified-complete--theme-by-theme)
2. [Issues inside the commit](#2-issues-inside-the-commit)
3. [Remaining work (the backlog)](#3-remaining-work--same-bug-classes-still-in-the-tree)
4. [Do NOT "fix" these](#4-do-not-fix-these)
5. [Verification commands](#5-verification-commands)
6. [Suggested priority order](#6-suggested-priority-order)

---

## 1. Verified complete — theme by theme

| Theme | Status | Evidence |
|---|---|---|
| WS auth via `Sec-WebSocket-Protocol` | ✅ | All 3 web sockets (`channelSocket`, `projectSocket`, `threadSocket`) send `['bearer', token]`; all 3 server endpoints parse it first, echo `"bearer"` on accept (required or browsers fail the handshake), and keep `?token=` + `Authorization` fallbacks. JWT base64url chars (`A-Za-z0-9-_.`) are all valid RFC 6455 subprotocol token chars, so no encoding hazard. `thread_ws.py` correctly relaxed `token: str = Query(...)` → `Optional` so header-only clients aren't rejected by FastAPI validation. |
| errorReporter redaction | ✅ | `_redactUrl` strips query+fragment (catches `/auth/beta?token=`, reset, SSO `?code=`); `_scrub` regex-redacts 3-segment JWTs from message/stack/context/body and truncates (500/4000). |
| `resetAuthCaches()` registry | ✅ | Both **SPA-navigate** logout paths call it: `client.ts:_logout()` (401-refresh-failure path) and `SidebarShell.handleLogout`. `useMe` + `usePinnedResources` register. The three other logout sites (`WorkSidebar`, `WerkLiteSidebar`, `PortalSidebar`) use `window.location.href = '/login'` — a full page reload, so module caches die anyway (no leak; see §3.6 for a robustness note). |
| Role guards | ✅ | `RequireRole` wraps `/admin` (`['admin']`) and `/broker` (`['broker','admin']`); fail-closed on missing user/role; redirects to `/login?next=…` and `Login.tsx:74` already open-redirect-guards `next`. `PortalLayout` flipped to `role !== 'employee'` (blank role no longer falls through). |
| Raw-token fetch → helpers | ✅ | `legalDefense.ts`, `laborClient.ts` use `authStreamHeaders()` (proactive refresh — correct for streams, which can't replay a 401); `dashboard.ts` + `legalDefense.downloadPacket` use `api.download` (verified: `_fetchWithRefresh` does proactive refresh **and** one 401 refresh-and-retry). |
| noopener / encodeURIComponent | ✅ as scoped | The 6 `window.open` and 11 URL-build sites in the diff are all fixed. Remaining sites are cataloged in §3.2/§3.5 — and one (`AgentPanel`) must **not** be changed, see §4. |
| Stale-response guards (12 hooks) | ✅ | All use the monotonic `reqId`/per-loader-counter pattern with unmount-increment; checked each — no guard checks the wrong counter, `finally` blocks are guarded so a stale response can't clear a newer request's `loading`. `useMonteCarloData`'s unmount-increment effect ordering is fine. |
| Debounced employee search | ✅ | 300 ms only when `search` changed; first load and non-search filter changes fire immediately. Because `fetchEmployees` reads `filtersRef.current`, an immediate (non-search) refetch during the debounce window still carries the latest search text — no lost keystrokes. |
| SSE unmount-abort (4 hooks) | ✅ | `useComplianceCheck`, `useIRAnalysisStream`, `useEnrichStream`, `useResearchGaps` all abort in-flight streams on unmount. |
| Perf items | ✅ | Hoisted `Intl` formatters (`dateFormat`, `brokerFormat`), gesture-scoped `AudioContext` (listeners now registered even when `AudioContext` construction would have failed — an improvement over the old early-return), badge poll skips hidden tabs + `markSeen` timer is tracked/cleared, `staleChunk` sessionStorage guarded with in-memory fallback (important: it runs inside error handlers). |
| kanban lowercase-once | ✅ | Both web consumers (`ProjectKanbanBoard`, `KanbanListView`) get tokens exclusively from `searchTokens()`, and neither uses tokens for case-sensitive highlighting — behavior unchanged. (Parity note in §2.4.) |

---

## 2. Issues inside the commit

Small, none blocking. Ordered by importance.

### 2.1 `useMe` stale-while-revalidate doesn't notify mounted components
`_revalidate()` updates the module-level `_cache`, but there is **no subscriber/broadcast
mechanism** — components that already rendered with the stale value don't re-render when the
background refetch lands. So "feature flips appear without reload" is only true **on the next
navigation/remount** (any component newly calling `useMe()` picks up the fresh cache). That's
still a real improvement over never-refreshing, and sidebars remount on route change, so in
practice flips appear within a click. If live propagation is ever wanted, add the same
listener-set pattern `usePinnedResources` uses (`_broadcast()` to subscribed setters).
**Recommendation: accept as-is; document the semantics.**

### 2.2 `useCredentialDocuments.ts:68` — `window.open` without `noopener`, in a file this commit touched
The commit added stale-guards to this exact file but missed its `download()` callback:
`window.open(url, '_blank')` on a presigned S3/CloudFront URL. Low real-world risk (we control
the URL origin) but it's the same class the commit fixed elsewhere — one-line fix.

### 2.3 `errorReporter` doesn't scrub `api_endpoint`
`_redactUrl` covers `url`, `_scrub` covers message/stack/body — but `api_endpoint` is passed
through verbatim. Endpoints with **path-embedded public tokens** (`/s/:token` employee-portal
links, `/candidate-interview/:token`, `/report/:token`) or query-bearing paths
(`?before=…` etc.) get persisted to the error store as-is. JWTs would be caught if they
appeared (they're query/header-borne, not path-borne), but opaque share-tokens are not
JWT-shaped and survive. Fix: run `api_endpoint` through `_redactUrl`-style query-stripping +
`_scrub`.

### 2.4 kanban tokenizer comment now overstates desktop parity
`searchTokens()` now lowercases in the tokenizer; the comment still says it "mirrors the
desktop `KanbanSearch` tokenizer". The web behavior is unchanged end-to-end (matching was
already case-insensitive), but the Swift tokenizer in `platforms/desktop/Werk/` presumably
still lowercases at match time. Harmless drift — either update the Swift side to match or
soften the comment when next touching either file.

### 2.5 WS constructor failure loop (pre-existing, now slightly more likely)
`new WebSocket(url, ['bearer', token])` throws synchronously if the token ever contained a
char invalid in a subprotocol (it can't, for a well-formed JWT) — caught and routed to
`_scheduleReconnect()`, which would retry forever against a deterministic failure. Only
reachable with a corrupted localStorage token. Not worth fixing unless observed.

---

## 3. Remaining work — same bug classes still in the tree

This is the actionable backlog. The commit fixed the instances it enumerated; these are the
instances still outstanding, found by grepping for each pattern.

### 3.1 Raw `localStorage.getItem('matcha_access_token')` + bare `fetch` (no refresh handling) — 9 call sites
These break when the access token is expired (30-min idle): the fetch 401s with no
refresh-retry, surfacing as a dead button / silent failure. Convert to `api.*`,
`authStreamHeaders()`, or `api.download` as appropriate:

| Site | What it does | Suggested fix |
|---|---|---|
| `components/TenantSidebar.tsx:62,141,220` | **Lite/Compliance checkout + pending-status polls** — a user who idles on the pricing page then clicks Subscribe gets "Failed to start checkout" | `api.post` (it's plain JSON, no streaming) — highest-value fix in this table |
| `pages/landing/HandbookGapAnalyzer.tsx:213` / `HandbookGapResult.tsx:76` | lead-gen analyzer calls (auth optional — tier resolution) | `authStreamHeaders()` if streaming, else `api.post` with `skipAuth` semantics preserved |
| `components/NewsletterSignup.tsx:62` / `components/landing/NewsletterHeroSection.tsx:74` | newsletter subscribe (auth optional) | same as above |
| `pages/admin/Newsletter/uploadMedia.ts:5` | admin media upload | `api.upload` |
| `pages/admin/Settings.tsx:9` | admin settings fetch helper | `api.get`/`api.post` |
| `types/risk-assessment.ts:307` `decodeTokenRole()` | decodes JWT payload client-side to read `role` — a **types** file doing auth introspection | replace callers with `useMe().me.user.role`; delete the helper |

(Not in scope: `channelSocket`/`projectSocket`/`threadSocket`/`errorReporter` token reads —
those are the intended socket/reporter mechanics.)

### 3.2 `window.open` without `noopener` — 2 sites
- `hooks/employees/useCredentialDocuments.ts:68` (§2.2).
- `api/cappeClient.ts:163` `openBlob` — opens a same-origin **blob:** object URL; the opened
  document is a browser-rendered blob (PDF), not third-party JS, so risk is ~nil, but add
  `'noopener'` for consistency. (Cappe is its own auth scope — `cappe_*` keys — so nothing
  else from this audit applies to it.)
- **Do not touch `AgentPanel.tsx:48`** — see §4.

### 3.3 Unguarded fetch hooks (stale-response races) — 2 remaining
- `hooks/risk-assessment/useRiskAssessment.ts:41` — admin **company switcher** drives
  `fetchSnapshot`; rapid switching can land an older company's assessment last. Apply the
  same `reqId` pattern. (Also: its `catch` only handles 404 — other errors leave stale data
  displayed with `loading=false`.)
- `hooks/useCappeMe.ts` — same single-flight cache shape as old `useMe`; separate product
  (cappe token scope, own logout), so it doesn't need `onAuthReset`, but it has the same
  unguarded `.then(setAccount)`. Low priority.
- `hooks/employees/useEmployees.ts:28,71` — the once-on-mount departments/onboarding fetches
  are unguarded but effectively race-free (fired once, stable data). Leave.

### 3.4 Token-in-URL WebSocket — 1 remaining, low severity
`hooks/useVoiceSession.ts:139` puts `wsAuthToken` in the query string. This is the
**purpose-built short-lived interview WS token** (`create_interview_ws_token`), not the
session JWT, so exposure in proxy logs is time-bounded and scope-bounded — deliberately a
different risk class. For parity, move it to the `['bearer', token]` subprotocol and extend
the same `_token_from_request` helper to the interview WS endpoint. Do this opportunistically.

### 3.5 Unencoded URL interpolations — worth fixing: 1; ignorable: rest
- `api/channels.ts:339` `join-by-invite/${code}` — `code` is **user-typed** (invite-code
  entry). Encode it.
- Ignorable (numeric/boolean/internal-constant values): `broker.ts:466` (`companyId` UUID),
  `compliance.ts:177,190`, `dashboard.ts:24`, `matchaWork.ts:1128`, `notifications.ts:16`,
  `dealTemplates.ts:16,20` (`key` is an internal enum), `wcRates.ts:53` (`kind` internal).

### 3.6 Logout-path robustness (defensive, not a leak today)
`WorkSidebar:186`, `WerkLiteSidebar:98`, `PortalSidebar:22` remove tokens then hard-navigate
(`window.location.href`), which resets all module caches by reload. If any of these are ever
converted to SPA `navigate()` (the exact refactor that created the pins leak in
`SidebarShell`), they silently become cache leaks. Cheap insurance: call `resetAuthCaches()`
in all three now, so the invariant is "every token-removal site resets caches"
(greppable, refactor-proof).

### 3.7 Legacy `?token=` WS fallback — schedule removal
The query-param fallback on all three WS endpoints exists for pre-deploy tabs still running
the old bundle. It is the leak vector the commit closed, so it should not live forever:
after one deploy cycle (old bundles gone — stale-chunk reload forces refresh anyway), delete
the `query_token` branch from the three `_token_from_request` helpers and the
`token: Optional[str] = Query(None)` params. Suggested: remove in the first deploy after
2026-07-20. (The `Authorization` header path stays — Werk/native clients use it.)

### 3.8 Consolidate the triplicated `_token_from_request`
The commit pasted the identical helper into `channels_ws.py`, `project_ws.py`, and
`thread_ws.py`. Acceptable for a surgical security fix; when doing §3.7, hoist one copy to a
shared module (e.g. `server/app/core/ws_auth.py`) so the fallback removal happens in one
place.

---

## 4. Do NOT "fix" these

- **`AgentPanel.tsx:48`** `window.open(auth_url, 'gmail-oauth', …)` — the Gmail OAuth popup
  **requires** `window.opener`: the callback page posts `'gmail-connected'` back via
  `opener.postMessage` (handler at `AgentPanel.tsx:35`). Adding `noopener` breaks Gmail
  connect. If it needs hardening later, the fix is a BroadcastChannel/localStorage handshake,
  not `noopener`.
- **Socket classes reading localStorage directly** (`channelSocket.ts:80,262` etc.) — that's
  their reconnect/token-rotation mechanism, not a leak.
- **`errorReporter.ts:76` token read** — the reporter must not recurse through `api.*`.
- **`?token=` fallback on WS endpoints** — needed until §3.7's soak window passes.

---

## 5. Verification commands

```bash
# Typecheck (clean as of this review)
cd client && npx tsc --noEmit

# Server WS files compile
cd server && python3 -m py_compile app/core/routes/channels_ws.py \
  app/matcha/routes/project_ws.py app/matcha/routes/thread_ws.py

# Backlog greps (each should shrink as §3 items land)
cd client/src
grep -rn "localStorage.getItem('matcha_access_token')" --include='*.ts*' | grep -v api/client.ts
grep -rn "window.open(" --include='*.ts*' | grep -v noopener
grep -rn 'finally(() => setLoading(false))' hooks/ | grep -v 'if (id'
```

Manual smoke (needs `dev-remote.sh`): open Werk web → channels connect (check DevTools WS
frames: URL has no `?token=`, request header `Sec-WebSocket-Protocol: bearer, eyJ…`, response
echoes `bearer`) → send/receive a message → logout via sidebar → login as a different user →
pinned resources and `useMe` show the new user immediately.

---

## 6. Suggested priority order

1. **TenantSidebar checkout raw-fetch** (§3.1) — revenue path; idle-then-subscribe currently
   fails. ~30 min.
2. **`useCredentialDocuments` noopener + `channels.ts` invite-code encode** (§3.2, §3.5) —
   two one-liners.
3. **errorReporter `api_endpoint` scrub** (§2.3) — share-token hygiene in the error store.
4. **Remaining §3.1 raw-token sites + `decodeTokenRole` removal** — mechanical.
5. **`useRiskAssessment` stale guard** (§3.3).
6. **`resetAuthCaches()` in the 3 hard-navigate logouts** (§3.6) — refactor insurance.
7. **After deploy soak: remove WS `?token=` fallback + dedupe `_token_from_request`**
   (§3.7, §3.8).
8. Opportunistic: voice-WS subprotocol parity (§3.4), `useMe` broadcast if live flag flips
   ever matter (§2.1), cappe items.
