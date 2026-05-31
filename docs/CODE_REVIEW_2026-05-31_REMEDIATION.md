# Code Review Remediation Plan — Ordered Least-Breaking → Most

_Companion to `docs/CODE_REVIEW_2026-05-31.md` (the findings) and
`docs/TEST_COVERAGE.md` (the test roadmap). This document is the **execution
order**: it re-sorts every finding by blast radius and effort, so work can start
on the safest, cheapest changes and escalate toward the ones that touch core
paths, cross surface boundaries, or change the production database._

## How this differs from the review's own sequencing

The review ends with a **Suggested sequencing** ordered by **security ROI** — it
front-loads the WS-token fix (#1) and the DB tenancy hardening (#2, #3) because
those close the most important holes. That is the right order if the only goal
is risk reduction.

This plan is ordered on a **different axis you asked for: least-breaking →
most.** The two orderings nearly invert — the highest-ROI security items
(WS-token scheme, non-superuser DB role, transaction-local GUCs) are also the
**highest blast-radius** changes, so they land last here, not first.

That tension is real and must be managed deliberately — see
**[Reconciling the two orderings](#reconciling-the-two-orderings)** below. The
short version: do the **low-risk security wins immediately** (Wave 1), but do
**not** let "least-breaking-first" indefinitely defer Waves 4–5 — those are the
two findings that actually turn the security posture from advisory into real.

## Scoring rubric

Each item is tagged:

- **Severity** — carried verbatim from the review (Critical / High / Medium / Low).
- **Effort** — S (< ½ day), M (½–2 days), L (multi-day / cross-surface).
- **Blast radius** — how much can break if the change is wrong:
  - **None** — additive or delete-only; no working path changes behavior.
  - **Local** — one file / one component / one endpoint.
  - **Volume** — individually trivial but many call sites (regression surface is count, not depth).
  - **Subsystem** — one shared module used widely (storage, auth-decode, limiter).
  - **Cross-surface** — backend + web + desktop must agree; coordinated deploy; client version skew.
  - **Core** — every DB connection / every request path.

Ordering within a wave is by blast radius then effort.

## Cross-cutting prerequisite

`docs/TEST_COVERAGE.md` item #1 — **a CI test gate** — should land early (it is
itself near-zero blast: a new workflow file, no app code). Waves 4 and 5 below
should **not** ship without it plus an authorization/tenancy test matrix, because
those waves change core paths where a silent regression leaks cross-tenant data
or breaks every query. Treat "CI gate + tenancy test matrix exist" as the
**entry gate to Wave 4**.

---

## Wave 0 — Zero-risk hygiene

Delete-only / typo-level. No working path changes behavior. Can ship in one
small PR, no coordination.

| Item | Surface | file:line | Sev | Effort | Blast |
|---|---|---|---|---|---|
| Stop logging full WS URL (incl. token prefix) in release | Desktop | `Services/ProjectWebSocket.swift:99` | High | S | None |
| Gate / remove ~58 `print(...)` in release paths (incl. per-message `onMessageGlobal`) | Desktop | `ChannelsWebSocket.swift:358,377,397,415`, `AppState.swift:245-249` | Medium | S | None |
| Hardcoded **real** Gmail debug login → reserved test domain (repo rule) | Desktop | `AuthViewModel.swift:6` | Low | S | None |
| Bare `except:` → `except Exception:` (stop swallowing `KeyboardInterrupt`/`SystemExit`) | Backend | `admin.py:1706,1710` | Medium | S | None |
| Actually reuse cached `JSONDecoder` (currently a fresh decoder per request) | Desktop | `APIClient.swift:105-113,213-215` | Low | S | None |

**Why first:** the WS-URL log line (`ProjectWebSocket.swift:99`) is a *High*
finding fixable by deleting one line — highest value-to-risk ratio in the entire
review. Everything else here is strictly safer-or-equal behavior.

**Exit:** one merged PR; no behavior change observable to users.

---

## Wave 1 — Sweet spot: high security value, low blast radius

Contained logic fixes, each in one file/component. Several are **High** severity
— this is where security ROI and "least-breaking" actually agree, so grab them
right after Wave 0.

| Item | Surface | file:line | Sev | Effort | Blast |
|---|---|---|---|---|---|
| Validate URL scheme in markdown→HTML (allowlist `http/https/mailto`) to block `javascript:` links | Frontend | `components/matcha-work/markdownToHtml.ts:14` (+ TipTap Link `protocols`/`validate`) | High | S | Local |
| `_logout()` redirect path guard (prevent redirect loop) | Frontend | `api/client.ts:39-57` | High | S | Local |
| Concurrent-401 retry that still 401s must call `_logout()` (no half-authed state) | Frontend | `api/client.ts:75-104` | High | S | Local |
| WS reconnect: stop on auth-class close codes + capped backoff (don't loop at 3s forever) | Frontend | `channelSocket.ts:152-160,246-251` (+ thread/project) | Medium | S | Local |
| Force-unwrap → `guard let`/`if let` on user-controlled values | Desktop | `ChannelsService.swift:45,31`, `RichJournalEditor.swift:164`, `InboxView.swift:255` | Medium | S | Local |
| JWT decode: require `exp` (`options={"require":["exp"]}`) + audience hardening; stop relying only on manual `type` field | Backend | `core/services/auth.py:160-164,100,136` | Medium | M | Local (auth-sensitive) |
| Stripe webhook dedupe **fail closed** (return 500 so Stripe retries) when the dedupe insert errors | Backend | `stripe_webhook.py:44-49` | Medium | S | Local (**money — test hard**) |
| IR copilot cold-start effect: add `incidentId` to deps (fix stale closure) | Frontend | `IRCopilotPanel.tsx:150-156` | Medium | S | Local |

**Watch items in this wave:**
- **JWT `require exp`** is auth-sensitive — a misconfigured audience claim can
  reject currently-valid tokens. Verify interview-WS + email-verify token
  issuers set the claims the verifier now requires before shipping.
- **Stripe fail-closed** touches the money path. Small diff, but flipping
  fail-open→fail-closed changes retry semantics — exercise with the Stripe CLI
  (`stripe trigger checkout.session.completed`, forced dedupe-table error) and
  confirm no double token-grant / double feature-flip.

**Exit:** the two *High* client auth-recovery bugs and the `javascript:` link
hole are closed; Stripe webhook can no longer double-process on dedupe failure.

---

## Wave 2 — Broad but mechanical (volume, low per-site risk)

Each change is individually low-risk; the cost and regression surface is the
**number of call sites**. These are mechanical sweeps — do them as focused PRs
per category so review stays tractable.

| Item | Surface | file:line | Sev | Effort | Blast |
|---|---|---|---|---|---|
| Route downloads / SSE streams / multipart uploads through the token-refresh wrapper | FE + Desktop | `api/client.ts:246-279`; ~20 SSE sites e.g. `IRCopilotPanel.tsx:74,170`, `hooks/ir/useIRAnalysisStream.ts:33`, `hooks/useEnrichStream.ts:59`; desktop `AuthService.swift:129`, `ChannelsService.swift:261`, `InboxService.swift:54,92` | High/Med | L | Volume |
| Make `ProjectDetailViewModel` / `ThreadDetailViewModel` / `ThreadListViewModel` class-level `@MainActor` | Desktop | `ProjectDetailViewModel.swift:13`, `ThreadDetailViewModel.swift:4,295`, `ThreadListViewModel.swift:4` | High | M | Volume (compile-cascade) |
| Add `AbortController` to ~127 `api.get().then(setState)` effects (kill setState-after-unmount + response-ordering races) | Frontend | e.g. `hooks/ir/useIRIncident.ts:10-19`, `hooks/useOnlineUsers.ts:18-33` | Medium | L | Volume |
| `useMe` cache: invalidate on SPA-internal user switch (SSO/impersonation), not only full reload | Frontend | `hooks/useMe.ts:5-22` | High | S | Local→Volume (used widely) |
| Index-as-key → stable keys in reorderable lists (171 occurrences) | Frontend | e.g. `BulkUploadModal.tsx:84`, `IRCopilotPanel.tsx:464`, `AnomaliesPanel.tsx:56` | Medium | M | Volume |
| `try?`-collapsed network errors → distinguish auth/500 from "no data" | Desktop | `ChannelsService.swift:278`, `App/DetailPanes.swift:217-220` | Medium | M | Volume |

**Notes:**
- **Token-refresh coverage (#7)** is the most valuable item in this wave — it's
  what makes long sessions stop breaking. Do it first here. It pairs naturally
  with Wave 1's `client.ts` work (same file region).
- **`@MainActor` (#5)** is "mechanical" only at runtime — adding the annotation
  surfaces every off-actor call as a *compile* error you must resolve with
  `await` / `MainActor.run`. Once it compiles, it's safe. Budget for the cascade,
  do it on its own branch, lean on the desktop build.

**Exit:** no fetch/stream/upload path bypasses refresh; the three big desktop
VMs are actor-isolated; unmount/race classes of FE bug retired.

---

## Wave 3 — Single-subsystem behavior changes / new infra deps

Each touches **one shared module or endpoint** but changes real behavior or adds
a dependency. Contained, but needs its own test + a deploy note.

| Item | Surface | file:line | Sev | Effort | Blast |
|---|---|---|---|---|---|
| Anonymous-report rate limiter → Redis (TTL) + parse `X-Forwarded-For` (currently per-worker dict, leaks, miskeys behind nginx) | Backend | `inbound_email.py:36-47,136` | High | M | Subsystem (1 public endpoint) |
| Wrap blocking boto3 `get_object`/`delete_object` + local `open()` in `asyncio.to_thread`; drop/allowlist the HTTP download fallback (SSRF + 30s async stall) | Backend | `storage.py:154,160-166,178,184-185,199,213` | Medium | M | Subsystem (all upload/download) |
| Credential extraction → dispatch to Celery with S3 path (stop holding 10 MB + inline Gemini in `background_tasks`) | Backend | `employee_portal.py:1248-1271` | Medium | M | Subsystem |
| Upload: magic-byte sniff instead of trusting client `content_type`/filename | Backend | `employee_portal.py:1217-1224` | Medium | S | Local |
| Add LIMIT/pagination to unbounded admin/aggregation result sets | Backend | `ir_incidents/analytics.py:66+`, `admin.py:5193` | Medium | M | Subsystem |

**Notes:**
- The **Redis limiter (#4)** is the only unauthenticated, internet-facing *write*
  path — high severity, but contained to one endpoint, so it's safe to do here.
  Requires Redis reachable from the request path (already present for Celery).
- **storage.py async I/O (#9)** is used by every upload/download — wrapping in
  `to_thread` is safe; **dropping the HTTP fallback** is the breaking part, so
  allowlist-or-remove deliberately and grep for callers first.

**Exit:** public write path is Redis-limited + correctly keyed; storage I/O no
longer stalls the event loop; SSRF fallback closed.

---

## Wave 4 — Cross-surface, coordinated deploy

**Entry gate: CI test gate + tenancy/authorization test matrix exist (see
[prerequisite](#cross-cutting-prerequisite)).** These changes require backend
and clients to agree, and the **desktop app ships separately** (App Store /
TestFlight) — so old clients keep running against new backend during rollout.
Design for a backward-compatible window.

| Item | Surface | file:line | Sev | Effort | Blast |
|---|---|---|---|---|---|
| **Move JWT out of WebSocket URLs** (+ stop logging it): issue a short-lived single-use WS ticket over HTTPS (mirror `create_interview_ws_token`) **or** send JWT in `Sec-WebSocket-Protocol`; update backend handshake; migrate all 6 client call sites | BE handshake + FE + Desktop | FE `channelSocket.ts:81`, `threadSocket.ts:41`, `projectSocket.ts:77`, `useVoiceSession.ts:139`; Desktop `ChannelsWebSocket.swift:74`, `ProjectWebSocket.swift:95` | **High (#1)** | L | **Cross-surface** |
| Audit: confirm **server-side** feature gating on every `/ir/*`, `/handbooks/*`, `/discipline/*`, etc. — `<FeatureGate>` is UX only, not a security boundary | Backend (audit) + FE | `FeatureGate.tsx:30-41`, `useMe.ts:55-58`, `utils/tier.ts` | **Critical (FE)** per review | M | Cross-surface (investigation) |

**Coordination rules for the WS-token change:**
1. Backend first: accept **both** the new ticket/header **and** the legacy
   `?token=` during a migration window.
2. Ship web clients (instant) + desktop clients (lag — users update on their own
   schedule) to the new scheme.
3. Only after desktop adoption is high: remove the legacy `?token=` path
   server-side. Removing it early breaks every un-updated desktop client's
   real-time channels/threads/projects.

**Why this is the review's #1 but this plan's Wave 4:** it's the single
highest-ROI security change *and* the highest-coordination one. It cannot be a
"safe early win" because a mis-sequenced backend deploy breaks live WS for
shipped desktop builds.

**Exit:** no bearer token in any WS URL or log; backend handshake reads
ticket/header; feature gates verified server-authoritative.

---

## Wave 5 — Core DB tenancy (highest blast radius, production database)

**These two land together, dev-first, and require explicit approval to touch the
production database role.** They rewrite the path **every connection** takes
(`database.py:109-138`, policy at `:575`). A wrong grant or a missed policy
fails *every* query or silently leaks cross-tenant — so this wave is gated on the
test harness from Waves 0/4 and a full-route regression pass.

| Item | Surface | file:line | Sev | Effort | Blast |
|---|---|---|---|---|---|
| Run the app DB role as **non-superuser, non-owner** so `FORCE ROW LEVEL SECURITY` actually binds (superusers + owners bypass RLS) | Backend / **prod DB** | `database.py:120-123,575` | **High (#2)** | L | **Core** |
| Make tenant GUCs **transaction-local** (`set_config(..., true)` inside an explicit transaction) so a tenant id can't outlive a request under pool reuse | Backend | `database.py:109-138` | **High (#3)** | M | **Core** |

**Hard gates (from `CLAUDE.md`):**
- `CREATE ROLE` / `GRANT` / ownership changes need **explicit user approval**,
  especially against **prod `matcha-postgres-prod:5433`**.
- Apply to **dev `:5432` first**, run the full authorization/tenancy test matrix,
  then prod — and apply schema/role changes to **both** so they don't drift
  (`alembic_version` parity).
- Audit every `GRANT` the new role needs before flipping; default connections to
  **deny** so a query missing `WHERE company_id = $1` fails instead of leaking.
- Transaction-local GUCs change connection semantics — any code path that
  assumed autocommit / session-scoped config must be found first (grep
  `get_connection` callers; the review counts `_verify_project_access` used 95×
  as one example of how wide tenant checks already are).

**Why last:** correct, but the most likely single change to cause a
production-wide outage if a grant or policy is missing. Do it when the test
harness can prove the route surface still works.

**Exit:** RLS is a real backstop, not advisory; tenant id cannot leak across
pooled requests.

---

## Wave 6 — Maintainability (after the test harness)

Real but lowest-urgency; the review explicitly says these should **follow** the
correctness/security work and ideally land **alongside** the test harness so the
refactors are covered. None are blocking.

- Split giant files: FE `pages/admin/Newsletter.tsx`, `AdminCompanyDetail.tsx`,
  `work/MatchaWorkThread.tsx`, `work/ChannelView.tsx` (1,000–1,300 LOC);
  Desktop `TaskViewerSheet.swift` (1,960), `MatchaWorkService.swift` (1,829
  god-object), `ProjectFilesView.swift` (1,560).
  _Note: `matcha_work.py` (8,902) is flagged **cohesive** by the review — not a
  split candidate._
- De-duplicate: checkout logic (7×, `TenantSidebar.tsx:45-62` + validate
  `data.checkout_url`), `_serialize_*`/metadata-coercion helpers, ad-hoc Swift
  `JSONDecoder`/`ISO8601DateFormatter` allocations (central
  `dateDecodingStrategy`).
- Low-severity cleanups: `: any` (~25 sites), non-null assertions on optional
  params, `useMe` derived object memoization, N+1 in Stripe tip handler
  (`stripe_webhook.py:167-169`), `LIMIT 0` probe queries, `ChannelStarStore`
  local-only prefs, `restoreSession()` network-vs-auth ambiguity.

---

## Reconciling the two orderings

"Least-breaking-first" is the right default for *velocity and safety*, but taken
literally it pushes the two most important security fixes (Waves 4–5) to the end.
Recommended reconciliation:

1. **Now:** Waves 0–1. Cheap, safe, and they already capture several *High*
   security findings (WS-URL logging, `javascript:` links, auth-recovery bugs,
   Stripe fail-closed). High value, near-zero risk.
2. **In parallel:** stand up the **CI test gate + tenancy/auth test matrix**
   (`docs/TEST_COVERAGE.md` tier 1–2). This is itself low-blast and is the
   **prerequisite that makes Waves 4–5 safe**.
3. **Next:** Waves 2–3 as mechanical sweeps and contained subsystem changes.
4. **Then, gated on the test harness:** Wave 4 (WS-token scheme, coordinated
   deploy) and Wave 5 (DB role + transaction-local GUCs). Do **not** let these
   slip indefinitely just because they're high-blast — they are the findings
   that turn the security posture from advisory into real.
5. **Last / opportunistic:** Wave 6, alongside the tests that cover the refactors.

## Review action # → wave

| Review # | Item | Wave |
|---|---|---|
| 1 | JWT out of WS URLs | 4 |
| 2 | Non-superuser DB role | 5 |
| 3 | Transaction-local tenant GUCs | 5 |
| 4 | Redis-backed anon-report limiter + `X-Forwarded-For` | 3 |
| 5 | Desktop `@MainActor` on 3 VMs | 2 |
| 6 | Block `javascript:` links in markdown | 1 |
| 7 | Token-refresh for downloads/streams/uploads | 2 |
| 8 | Stripe webhook dedupe fail-closed | 1 |
| 9 | Async storage I/O + SSRF fallback | 3 |
| 10 | WS reconnect: auth-stop + capped backoff | 1 |

_(FE "feature gating is client-side only" Critical → Wave 4 audit. Remaining
Medium/Low items map into Waves 2–3 and 6 as listed above.)_
