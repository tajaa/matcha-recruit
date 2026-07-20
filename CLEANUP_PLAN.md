# Cleanup Plan — LOC, refactor, security, efficiency

Audit date: 2026-07-19. Part 1 (Phases A–G): `client/` (main Matcha SPA), ~170k LOC in `client/src`. Part 2 (Phases H–J, second sweep same day): `work/`, cross-domain client widgets/utils, and `server/app`. Part 3 (Phases K–M, third sweep): client domain scaffolds, server round 2, side apps. Cappe excluded by request (G3's lazy-routes note predates that call and stays).

Goal: first client wave removes ≈4,200 LOC while adding ~700 LOC of shared code; all parts together reach ~9–12k removed with materially better modularity. Phases F (security) and G (bundle) are LOC-neutral but independently worth doing.

One PR per phase, ordered by risk. Every client phase ends with `cd client && npx tsc -p tsconfig.app.json --noEmit` (bare `tsc` checks nothing — root tsconfig is `files: []` + project references) plus the listed smoke tests. Paths relative to `client/src` (client phases) or `server/app` (server phases) unless noted.

Totals table + sequencing at the bottom.

---

# Part 1 — client/src

## Phase A — Dead-code delete (~2,050 LOC, zero risk)

All verified zero importers; only residual textual refs are prose comments.

Delete:
- `pages/landing/animations/` — whole dir (5 files, 1,261 LOC; barrel + `ANIMATION_BY_SIZZLE_ID` unused)
- `components/landing/IrAnalysisPanel.tsx` (215)
- `components/landing/TimelineConstructor.tsx` (213)
- `components/compliance/ComplianceOverviewTab.tsx` (143)
- `components/widgets/PinnedResourcesPanel.tsx` (78) + `data/resourceCatalog.ts` (132, sole importer is the panel). Do NOT touch `api/resourcePins.ts` / `hooks/usePinnedResources.ts` — live via `PinButton`.

Also: reword stale comment in `components/landing/RiskInsightsHero.tsx:10` ("lives in IrAnalysisPanel").

Verify: tsc; `grep -rn "IrAnalysisPanel\|TimelineConstructor\|ComplianceOverviewTab\|PinnedResourcesPanel\|resourceCatalog\|landing/animations" .` → zero hits; one `npm run build` (animations were lazy chunks).

## Phase B — SSE helper `api/sse.ts` (~600 LOC across 26 files)

> **STATUS 2026-07-20 — Phase B COMPLETE.**
>
> `api/sse.ts` is now the only file in `client/src` that calls `getReader()` or
> parses `data: ` lines — verified by grep. It exports `consumeSSE` / `postSSE` /
> `streamPilotChat` / `SSEHttpError`, plus the E1 shared types (`SessionStatus`,
> `PilotMessage<TMeta>`, `ChatHandlers<TResult>`).
>
> Deviations from the plan as written, for whoever reads this next:
> - **`PilotSession` was NOT hoisted.** Its shape genuinely differs per pilot
>   (`company_id` vs `broker_id`, different counters). The plan was wrong to list it
>   alongside `PilotMessage`/`SessionStatus`.
> - **The plan understated the pilots' divergence.** The read loop was byte-identical,
>   but only 2 of 5 had a try/catch, only 2 took a `signal`, only 1 extracted `detail`.
>   The shared helper is the union, so three pilots gained abort handling.
> - **23 loops across 22 files, not 26 files.** `useCopilotPanel.ts` carried *two*
>   (stream + accept). Four URL helpers (`getEnrichStreamUrl`, `getResearchGapsUrl`,
>   `getLocationCheckUrl`, `getComplianceCheckUrl`, `getMatchaXBuildStreamUrl`)
>   existed only to prepend the API base and became `…Path` helpers, since postSSE
>   prepends it.
> - **Two dedupes fell out that the plan didn't anticipate**: a shared
>   `work/api/matchaWork/_base.ts:uploadFilesStream` behind the three multipart
>   uploaders (messaging.ts 368 → 118 lines), and one `runScan` driver behind the
>   five near-identical jurisdiction scans in `useJurisdictionDetail.ts`.
> - **`JurisdictionDetailPanel/helpers.ts:readSSEStream` was deleted** — it was an
>   already-correct buffered parser someone had written to fix this exact bug
>   locally. `consumeSSE` supersedes it.
>
> **Bugs fixed in passing** (all were silent):
> - `HelpAssistant.tsx`, `StudioAssistant.tsx`, `LibraryTab.tsx` (×2),
>   `usePipeline.ts`, `JurisdictionData.tsx` called `decoder.decode(value)` with no
>   `{stream:true}` **and** kept no cross-chunk buffer, so the trailing partial line
>   of every chunk was discarded — including a `data: [DONE]` that landed on a
>   boundary, which is why some post-stream refetches never fired.
> - `HelpAssistant.tsx` never checked `res.ok`, so a 500 rendered as an empty reply.
> - `portalAskHr.ts` read `matcha_access_token` straight from localStorage, bypassing
>   the proactive refresh — against the house rule in `client/CLAUDE.md`.
> - `consumeSSE` cancels the reader in a `finally`, releasing the body lock on the
>   early-return (`[DONE]`) path that every hand-rolled loop leaked.
>
> **Gotcha to preserve if you touch this again:** check whether a loop treats a bare
> `[DONE]` as an *error*. `sendMessageStream` does — `[DONE]` with no preceding
> complete/error means the turn never settled and the composer stays stuck on
> "Thinking…" with the input disabled. `consumeSSE` returns silently on `[DONE]`, so
> that case needs an explicit `settled` flag checked after the await.
>
> **Still owed:** the plan's manual click-through (one turn per pilot console, portal
> Ask HR, help widget, ER outcome gen, abort via session-switch). tsc + build only so far.

## Phase C — `hooks/useAsync.ts` (hook + 15-file tranche; ~250 now, 1,500+ full rollout)

> **STATUS 2026-07-20 — hook landed, tranche 1 partial (7 of 15).**
>
> `hooks/useAsync.ts` exists with `useAsync` + `useAsyncAction`, 17 tests.
> One addition beyond the spec: an optional third `initial` argument (typed via
> overload, so `data` is `T` when supplied and `T | undefined` otherwise).
> Without it every list migration needed `?? []` at the read site and
> `(prev ?? [])` inside each optimistic update — most of the boilerplate the
> hook exists to remove.
>
> Migrated: `admin/Individuals`, `admin/Companies`, `admin/ServerErrors`,
> `broker/BrokerExternalClientDetail`, `app/risk/Tcor`, `app/risk/DriverRisk`,
> `app/risk/ControlsEvidence`.
>
> **Migration hazard, hit once:** `ControlsEvidence` kept a `useEffect(load, [])`
> after its `load` became `useAsync`'s `reload` — a silent double fetch on every
> mount. When converting, grep the file for a leftover mount effect; `useAsync`
> already runs on mount.
>
> **Remaining ~76 candidates** — re-enumerate with the plan's grep:
> `grep -rln "finally(() => setLoading(false))" pages components | xargs grep -ln "useState(true)"`.
> `admin/PayerData` and `admin/DealFlow` (both named as seeds) were skipped: each
> has 3+ interacting fetch effects and deserves its own diff rather than riding a
> mechanical sweep.

No shared async hook exists: 213 files carry the `try/catch/finally` + `setLoading`/`setError` triad, 287 combine `useState`+`useEffect`. A hand-rolled hook stays compatible with the house rule against React Query/SWR.

New `hooks/useAsync.ts` (~90 LOC):
- `useAsync<T>(fn, deps)` → `{data, loading, error, reload, setData}`. `reload()` refetches WITHOUT clearing data (matches prevailing pattern, no flash); out-of-order responses discarded via run counter; `fn` in a ref so inline closures are fine; `setData` exposed for optimistic updates; `error` is a string (`e.message`). Guarded params: `fn: () => id ? fetch(id) : Promise.resolve(null)`.
- `useAsyncAction<A,R>(fn)` → `{run, busy, error, reset}`; `run()` resolves `undefined` on failure (keeps the `const r = await run(); if (!r) return` shape).

Tranche rule: a file qualifies with the full quadruplet (data `useState`, `useState(true)` loading, fetch-in-`useEffect`, `.finally(() => setLoading(false))`). Enumerate: `grep -rln "finally(() => setLoading(false))" pages components | xargs grep -ln "useState(true)"`. Tranche 1 = top 15 by fetch-effect count, seeded with `pages/admin/Individuals.tsx`, `pages/admin/Companies.tsx`, `pages/broker/BrokerExternalClientDetail.tsx`, plus `PayerData`/`DealFlow`/`ServerErrors` (D2 touches them anyway — same diff, avoid double churn). Later tranches: opportunistic in files already being touched, plus dedicated ~15-file PRs; never mix a useAsync sweep with behavior changes.

Verify: tsc; each converted page renders, a filter change refetches, one mutation (token grant on Individuals) refreshes.

## Phase D — UI consolidation

> **STATUS 2026-07-20 — D2 and D4 partial. D1 and D3 NOT started.**
>
> - **D2**: `components/ui/DataTable.tsx` exists (chrome lifted verbatim from
>   Companies.tsx) and `Companies.tsx` + `Brokers/BrokerTable.tsx` are migrated.
>   **`FilterPills` was deliberately NOT built** — `components/ui/PillTabs.tsx`
>   already is that component (same `{options, value, onChange}` shape, 6
>   existing consumers). The admin filter rows the plan wanted it for are
>   `<Button variant={active ? 'primary' : 'ghost'}>` loops, which look different
>   from PillTabs' joined segmented control, so swapping them is a visual change
>   to admin pages, not a refactor. Decide that with eyes on it.
>   **LOC estimate was wrong**: the plan said ~300 across 5 pages; Companies saved
>   6 lines. Rich cells relocate into `render` closures unchanged, so the JSX
>   moves rather than disappearing. The real win is that the table chrome and the
>   loading/empty ladder stop being copied 29 times.
> - **D4**: `newsletter/SendModal` + `newsletter/CsvImportModal` migrated. Both
>   GAINED Escape-to-close and click-outside — neither had them. Remaining tranche-1
>   files (`PolicyDetailPage`, `AdminOnboarding`, `Individuals`, `MatchaWork`,
>   `BlogEditModal`, `SpecialtyReviewModal`, `LifecycleActions`, `SubscribersTab`)
>   are untouched. Enumerate the rest with
>   `grep -rln "fixed inset-0" pages components --include="*.tsx"` minus
>   `ui/Modal.tsx`/`Drawer.tsx`.
> - **D1 (tier signup) and D3 (pilot chat hook) are NOT started.** Both are
>   substantial and neither is mechanical: D1 touches the revenue path (three
>   signup pages → Stripe checkout) and D3 rewires all four pilot consoles.
>   Each wants its own PR and its own manual click-through.

### D1. Tier signup (~380 LOC; medium risk — revenue path)

`MatchaLiteSignup` (253) / `ComplianceSignup` (282) / `MatchaXSignup` (238) share a byte-identical local `Field`, an identical brokerRef seat-invite effect, and an identical register→Stripe `handleSubmit`. Divergences confirmed (Compliance adds industry + jurisdictions; MatchaX has a hardcoded price fn) ⇒ **no config-driven form DSL** — hoist the shared pieces, keep tier fields inline per page.

New `components/auth/TierSignup.tsx` (~150 LOC): `SignupField` (the Field, verbatim), `useBrokerSeatInvite(brokerRef)`, `registerAndCheckout({registerBody, successPath, checkout})` (register → store tokens → invalidateMeCache → broker-pays branch → Stripe redirect; throws `Error(detail)`), `SignupShell` (header + invite banner + error + submit + footer; children = tier-specific fields). Each page drops to ~90–120 LOC. **Skip `IrSignup.tsx`** (no checkout step, different flow); adopt `SignupField` only if the markup matches — check at implementation time.

Verify: tsc; each page reaches the Stripe checkout redirect (test mode); `?ref=<invalid>` renders normally; a valid seat-invite ref pins company name + headcount.

### D2. `DataTable<T>` + `FilterPills` (5 admin pages, ~300 LOC)

29 admin pages hand-roll `<thead>/<tbody>` (79 files app-wide hand-roll `<table>`); `components/ui/` has `Badge` and `Modal` but no table primitive.

New `components/ui/DataTable.tsx` — exact Companies.tsx chrome (`rounded-xl border-zinc-800`, `thead bg-zinc-900/50`, `px-4 py-3` cells, hover row). Props: `columns: {key, header, render, align?, className?}[]`, `rows`, `rowKey`, `loading?`, `emptyText?`, `onRowClick?`. New `components/ui/FilterPills.tsx`: `{value, onChange, options, label?}`. Export both from `components/ui/index.ts`. No sorting/pagination/search-hook in v1 (search stays a one-line `.filter` in the page).

Tranche 1: `pages/admin/{Companies,Individuals,PayerData,DealFlow,ServerErrors}.tsx`. Pattern: thead/tbody → a `columns` array of `render` closures (closures capture the page's action handlers, so row buttons move unchanged); filter button rows → `FilterPills`. Later tranches: `grep -rln 'bg-zinc-900/50' pages/admin`.

Verify: tsc; rows render, pills filter (and refetch where server-side), search filters, row actions work.

### D3. Pilot chat hook (~400 LOC; all 4 consoles, one PR)

The four consoles share the `send()` core verbatim (optimistic user echo, AbortController ref with unmount abort, "Thinking…" status, `hadError` tracking, `finally { if (!aborted) onTurn() }`, scroll-to-bottom, Enter-to-send) but render transcripts completely differently ⇒ **no monolithic PilotConsole** — hook + two primitives, message rendering stays per-page.

New `hooks/usePilotChat.ts`: `usePilotChat<TMsg,TResult>({initial, stream, makeUserMessage, makeAssistantMessage, onTurnEnd?, thinkingLabel?, onBeforeSend?})` → `{messages, setMessages, input, setInput, busy, status, setStatus, send, scrollRef, textareaRef}`. Internals reproduce `pages/app/handbook-pilot/Console.tsx:56-99` exactly, including the StrictMode-safe unmount abort and error-status persistence. The handbook autoSeed `setTimeout` stays page-local.

New `components/ui/ChatComposer.tsx` (textarea + Send + Enter-no-shift; `children` slot above the input row for analysis's focus chips) + `components/ui/ChatStatusRow.tsx` (Loader2 + status text).

Migrate: `pages/app/handbook-pilot/Console.tsx`, `pages/app/analysis-pilot/Console.tsx`, `pages/broker/pilot/Console.tsx`, `pages/app/legal-defense/index.tsx` (chat portion). Note: broker Console currently clears status unconditionally in `finally` (no `hadError` guard) — the hook slightly improves its error UX; flag in the PR.

Verify: tsc; one full turn per console; abort via session-switch; new-session goal auto-send fires exactly once (StrictMode dev check).

### D4. Modal migration (10-file tranche, ~200 LOC now, ~31 files eventually)

`components/ui/Modal.tsx` already provides backdrop + Escape + click-outside + a `bare` escape hatch + `width`. Migrate only true centered-panel dialogs (`{cond && <div className="fixed inset-0…">}` + centered zinc-900 panel); skip lightboxes/full-screen takeovers; panels with custom chrome use `bare`. Pattern: conditional wrapper → `<Modal open onClose title width>`, delete backdrop/panel divs + local Escape handlers.

Tranche 1: `pages/admin/{PolicyDetailPage,AdminOnboarding,Individuals,MatchaWork}.tsx`, `pages/admin/Blogs/BlogEditModal.tsx`, `pages/admin/studio/SpecialtyReviewModal.tsx`, `pages/admin/company-detail/LifecycleActions.tsx`, `pages/admin/newsletter/{CsvImportModal,SubscribersTab,SendModal}.tsx`. (Individuals overlaps C/D2 — do its modal in that PR.) Rest: `grep -rln "fixed inset-0" pages components --include="*.tsx"` minus `ui/Modal.tsx`/`Drawer.tsx`.

Verify: tsc; open/close each migrated modal incl. Escape + backdrop click.

## Phase E — Structural refactors (mostly LOC-neutral; maintainability)

Boundary audit came back clean — no `components/` → `pages/` imports, no `work/` ↔ matcha cross-app imports. Nothing to fix there.

### E1. Pilot shared types (fold into Phase B — near-free)
`ChatHandlers` is declared 5×, `ChatResult` 4×, `PilotSession`/`PilotMessage`/`SessionStatus` 3× — each pilot api file redeclares the same shapes. Export the shared ones from `api/sse.ts` (or `api/pilot-types.ts`) during the B1 migration; per-pilot result payloads stay local.

### E2. God-component split via the established colocated-hook pattern
30 `.tsx` files exceed 450 LOC mixing fetching + logic + render. The repo already has the pattern — `Page/usePage.ts`, 15 precedents including `work/pages/ProjectView/useProjectView.ts`, `pages/broker/BrokerClients/useBrokerClients.ts`, `pages/admin/Customers/useCustomers.ts`. Rule: when Phase C/D touches a >450-LOC file, extract its data/state into a colocated `use<Page>.ts` in the same diff. Dedicated splits only for the top 5: `pages/broker/client-detail/WcTab.tsx` (544), `pages/app/employees/EmployeeSchedule.tsx` (537), `components/employees/CredentialManager.tsx` (526), `pages/admin/FractionalClientDetail.tsx` (525), `components/er/ERGuidancePanel.tsx` (518).

### E3. Raw-fetch outliers → api layer
True `fetch(` bypass sites are few: `pages/admin/Settings.tsx` (10 calls — the real outlier; move to `api/admin/`), `components/admin/JurisdictionDetailPanel/useJurisdictionDetail.ts` (5), signup pages (3 each — already absorbed by D1's `registerAndCheckout`). `pages/shared/*` public-token pages and `hooks/useMe.ts` are legitimate (no auth client available); a thin shared `publicFetch` helper is optional and low priority (see also K2).

### E4. Flatten pages/admin (defer unless it hurts)
`pages/admin/` has 37 flat `.tsx` files (subdirs `studio/`, `newsletter/`, `Blogs/` already exist). Grouping by domain like `pages/app/<domain>/` is pure file moves + import updates. `client/CLAUDE.md` marks this "deferred on purpose" — only do it as its own mechanical PR, and update `client/CLAUDE.md` when done.

## Phase F — Security fixes (small diffs, can ride PR 1)

The 2026-06-06 audit fixes were all verified still in place: no `rehypeRaw`/`allowDangerousHtml` anywhere (MessageBubble clean), `Login.tsx:76` `?next=` same-origin guard intact, react-router ≥7.11. Also confirmed clean: postMessage listeners validate `e.source`, all `window.open`/`target="_blank"` carry noopener, `/admin` `/broker` `/portal` route trees fail closed, no secrets in `VITE_` vars, `SSOCallback.tsx` strips tokens from the URL fragment. New findings:

- **F1 (MED)** Admin preview iframes render server HTML via `srcDoc` with **no `sandbox`**: `pages/admin/DealFlow.tsx:443`, `LiteEditionPanel.tsx:112`, `BrokerTab.tsx:241`, `BookPricingTab.tsx:278`, `FullDealTab.tsx:199`. Those proposal/deal docs embed tenant-supplied fields, so any unescaped field executes JS in the admin's session at app origin. Fix: add `sandbox=""` (or `sandbox="allow-same-origin"` if CSS needs it — never together with `allow-scripts`). Siblings `TrafficReport.tsx:55` and cappe `CanvasModeView.tsx:35` already sandbox, so this is an inconsistency, not a design choice.
- **F2 (LOW-MED)** `pages/app/analysis-pilot/MetricViews.tsx:12` injects backend-generated SVG via `dangerouslySetInnerHTML`; SVG can carry `<script>`/`onload`, and chart labels derive from user-uploaded datasets. Fix without a new dep: render as `<img src={"data:image/svg+xml;utf8," + encodeURIComponent(svg)}>` — images cannot script.
- **F3 (LOW)** `components/ui/CitationSources.tsx:94` renders `href={c.source_url}` raw, while `work/components/panels/MessageBubble.tsx:259` wraps the **same** server-corpus field in `safeUrl()` (blocks `javascript:`/`data:`). Fix: import `safeUrl`, drop the link when null.
- **F4 (LOW)** `layouts/AppLayout.tsx` has no fail-closed `!me` guard (only the `isPersonal` → `/werk` redirect), unlike `RequireRole` (/admin, /broker) and `PortalLayout`. Routes without a `FeatureGate` render the shell until a fetch 401s. Backend still enforces authz, so this is consistency, not a leak. Fix: `!me → <Navigate to={'/login?next=…'} replace>`.
- **F5 (LOW, defense-in-depth)** ~15 sites assign `window.location.href = checkout_url | oauth_url` straight from API responses (sidebars, signup pages, `work/layout/WorkLayout.tsx:74`, cappe `DomainManager.tsx:68`, HRIS/OAuth modals). All come from our own authenticated backend today. Fix: a tiny `utils/externalRedirect.ts` allowlisting same-origin + `*.stripe.com` + OAuth hosts; adopt it inside D1's `registerAndCheckout` and the sidebars.
- **F6 (LOW, optional)** `work/hooks/useVoiceSession.ts:139` passes its ws auth token in the query string, while the other three sockets deliberately use `Sec-WebSocket-Protocol` to keep tokens out of nginx access logs. The token is ephemeral and per-session, so impact is low — align when next touching the file.
- **F7 (hygiene)** Remove unused `three` + `@types/three` from `client/package.json` (zero import sites anywhere in `src`). The remaining `npm audit --omit=dev` (17: 10 moderate, 7 high) is entirely transitive under excalidraw→mermaid and react-simple-maps→d3-color; the only fix is a breaking `--force` downgrade, and there's no direct code path feeding the ReDoS inputs — defer.

Verify: tsc; open one admin deal preview (renders, no script execution), one analysis-pilot chart, citation links still open, a logged-out `/app/...` hit redirects to login, Stripe checkout still redirects.

## Phase G — Efficiency (bundle + runtime)

Baseline is healthy: 8 route trees + ~50 marketing/auth pages already use `lazy()`; excalidraw/xyflow panels are lazy; only `Home` (apex) and `Login` (funnel) are eager, deliberately. **Do NOT add vite `manualChunks`** — `client/vite.config.ts` documents a React 19 cross-chunk init-order crash; that comment is a landmine warning.

- **G1 (HIGH bundle)** framer-motion (~60–110 KB gz) rides the eager apex `/` chunk three ways: `pages/home/Hero.tsx:5` → `ProductCarousel` + `instruments/shared`, and `pages/home/index.tsx` → `PricingContactModal`. Fix: `lazy()` the below-fold carousel/instruments and the modal.
- **G2 (HIGH bundle)** recharts (~100–150 KB gz, bundles d3) is statically imported by `components/landing/RiskInsightsHero.tsx:3`, which `pages/simpler-pages/Lite/Hero.tsx:3` imports statically — a decorative scrolling hero on a public marketing page. Fix: lazy the chart, or replace with a lightweight inline SVG.
- **G3 (MED bundle)** `cappe/routes.tsx` eagerly imports all ~24 Cappe pages including the ~1.5k-LOC `PageEditor` site-builder, so hitting `/cappe/login` loads the whole editor. Fix: `lazy()` PageEditor + the `site/*` sub-pages.
- **G4 (trivial)** `components/ui/Toast.tsx:56` passes `value={{ toast }}` — a fresh object each render on an app-wide provider, so every toast re-renders all consumers. Wrap in `useMemo`.
- **G5 (deferred)** No list virtualization anywhere: `work/pages/ChannelView/MessageList.tsx:31` and the big admin tables render every row. Adding a windowing lib is a deliberate dependency call — defer until a real perf complaint.
- **G6 (LOC + bundle, ~1.5–2k of 2,885 LOC)** `pages/simpler-pages/{Brokers,Lite,Compliance,Platform}` each duplicate `instruments.tsx` / `PillarsGrid.tsx` / `useLoopCycle.ts` / `Hero.tsx` framer-motion scaffolds. Consolidating into shared components also shrinks the G1/G2 footprint per page.

Verify: tsc; `npm run build` before/after and compare the main + lite-page chunk sizes; smoke `/`, `/matcha-lite`, cappe login, one toast.

---

# Part 2 — Second sweep: work/, cross-domain widgets, server/

## Phase H — work/ app (matcha-work web surface)

Dead-code check came back **clean**: every `components/panels/*` has a live consumer (the long chain `ComplianceDecisionTree` → `ComplianceReasoningPanel` → `MessageBubble` is live), all pages are routed (`pages/ChannelInviteLanding.tsx` registers one level up in `App.tsx` as `/join-channel/:code` — not dead), all api modules have importers. All payoff is dedup + splitting.

- **H1 (trivial, do first)** `work/routes/WorkRoutes.tsx` and `work/routes/WerkRoutes.tsx` are line-for-line identical except the `WorkSurfaceProvider value` prop (`"matcha-work"` vs `"werk"`). Merge into one `WorkRouteTree({ surface })`; entry files become 3-line wrappers. ~38 LOC + removes the two-place edit hazard on every new route.
- **H2 (high payoff, low risk)** `BaseSocket` extraction: `work/api/threadSocket.ts` (174) / `projectSocket.ts` (275) / `channelSocket.ts` (293) carry byte-identical transport — `getWsBase()`, ping fields, `connect()` skeleton (token subprotocol, onopen reset+ping+rejoin, onclose stop+reconnect), `disconnect()`, `_startPing/_stopPing/_send`, and the same `Math.min(30000, 3000 * 2 ** attempts)` backoff. Only the WS path, `onmessage` dispatch, and rejoin payload differ. Abstract `BaseSocket` with `path()` / `handleMessage()` / `rejoin()` hooks; subclasses shrink to dispatch tables. ~120–150 LOC net + normalizes real drift (channelSocket alone answers `server_ping`→`pong`; the others lack it).
- **H3 (mechanical)** Modal adoption inside work/: ~18 true dialogs hand-roll `fixed inset-0` backdrop + Escape + click-outside; `components/ui/Modal` (incl. `bare` mode) is sanctioned for work/ per client/CLAUDE.md ("any app may import components/ui"), yet only `components/inbox/ComposeModal.tsx` uses it. Candidates: `shell/{AiDraftReviewModal,TemplateComposeModal}`, `shell/ProjectKanbanBoard/{TaskDetailPanel,TaskActionSheet}`, `shell/WorkSidebar/ProjectTypePickerModal`, `panels/{RejectCandidateModal,InterviewReviewModal,HiringClientPickerModal,DiagramEditor}`, `channels/{ChannelAnalytics,CreateJobPostingModal,TipModal,JobPostingDetail,JobPostingsPanel,AddMembersModal}`, `pages/ChannelView/ChannelHeader`, `pages/MatchaWorkList`. ~150–180 LOC + behavior consistency (several omit Escape today). Extends D4's tranche system.
- **H4** Hook extractions (colocated `use*.ts` house pattern), god files with none yet: `panels/LanguageTutorPanel.tsx` (539), `pages/MatchaWorkList.tsx` (479 — 13 api calls), `shell/ProjectKanbanBoard/TaskDetailPanel.tsx` (445), `panels/DiagramEditor.tsx` (424), `inbox/MessageThread.tsx` (423), `panels/SectionEditor.tsx` (420). Rides E2's rule.
- **H5 (defer / opportunistic)** `useOptimisticMessages<T>` shared between `useChannelView.ts` and `useThreadController.ts` (same temp-id append + reconcile-on-echo pattern, ~60–80 LOC, medium risk — different message types; do after H2). Composer unification (`ChannelView/MessageComposer` vs `MatchaWorkThread/ChatComposer`, divergent theming) and a shared `useWizard` for the 4 wizards — only if already in those files.

Verify: tsc; werk + matcha-work both load (`/work`, `/werk`), channel send/receive + reconnect after killing the dev server briefly, one modal per migrated cluster, thread send with optimistic echo.

## Phase I — cross-domain client widgets + utils

Checked clean (don't re-investigate): `types/` has **zero** dead exports (86+50+44 interfaces spot-checked); the two `api/**/types.ts` files are disjoint domains, legitimately colocated; `api/` functions all have callers; `hooks/` + `utils/` no dead exports; no strong broker↔client scorecard duplication.

- **I1 (~400–600 LOC)** Pilot **surface** scaffold (complements D3, which unifies behavior — this unifies chrome): `pages/app/legal-defense/`, `pages/broker/pilot/`, `pages/app/analysis-pilot/`, `pages/app/handbook-pilot/` each ship their own `Console.tsx`, `index.tsx`, `shared.ts`, `Masthead.tsx`, `howItWorksSteps.ts`, `NewSessionModal.tsx`, Evidence/Packets panels. Verified: the two `EvidencePanel.tsx` are ~85% identical JSX; `fmtWhen`/`fmtSize` verbatim in every `shared.ts`; `Masthead` ~160 LOC ×2. Build `components/pilot/` (EvidencePanel, PacketsPanel, Masthead, fmt helpers, NewSessionModal) parameterized by source type.
- **I2 (~150–250 LOC + consistency)** Formatting consolidation: `utils/dateFormat.ts` is imported by only 2 files while `toLocaleDateString` appears 84× inline; 5+ competing relative-time helpers (`relativeTime` in `ir/IRRiskInsightsTab` + `dashboard/Notifications`, `timeAgo` in `dashboard/FlagsTable` + `ask-expert/EscalatedQueries`, `formatRelative` in `broker/client-detail/shared` + `marketing/BlogComments`); money formatting only in `utils/broker/brokerFormat.ts` (`fmtMoney`), reimplemented in risk-assessment + landing calculators. Extend `utils/` with one date/relative/money module; migrate inline sites opportunistically (dateFormat also fixes the UTC-midnight off-by-one).
- **I3 (~100–200 LOC)** Badge variant maps: `ui/Badge` already has `low/medium/high/critical` variants, yet ~40 files define inline `bg-/text-` color maps and 9 hand-roll `severity|priority → BadgeVariant` micro-maps (7 in `components/er/` — `ERGuidancePanel.tsx:15-31` alone defines three). Export shared `severityVariant`/`priorityVariant` maps beside `Badge`.
- **I4 (low)** StatCard: two unrelated implementations (`components/dashboard/StatCard.tsx`, `pages/admin/GapDashboard/StatCard.tsx`) + inline tiles in property/company-detail/client-detail/risk-assessment → one shared primitive.
- **I5 (low)** `<IRAnalysisPanel>` wrapper: `IRRecommendationsPanel`/`IRRootCausePanel`/`IRSimilarIncidentsPanel` repeat the same run-button + streaming-box + result-box scaffold (~40 LOC each).

Verify: tsc; one pilot surface per migrated piece renders (evidence list expands, packet download), spot-check dates/badges on dashboard + ER case detail.

## Phase J — server/app

Order: dead code → convention sweeps → structural splits. House styles to follow: split-router package = `matcha_work/` pattern (aggregator `__init__.py` + `_shared.py`); service sub-packaging = `scope_registry/`, `email/`, `compliance_evals/`, `analysis_packs/` precedents. Non-targets (already right): tenant isolation via `get_client_company_id` (300+ uses), storage centralized in `core/services/storage.py`, gumfit remnants = only the two documented.

- **J1 dead code (~2,020 LOC)** `matcha/services/pre_termination_service.py` (1,891 lines) is production-dead: sole writer of `pre_termination_checks`, referenced only by itself + its (known-brittle) test; the mounted `/pre-termination` route only reads the table for analytics. Verify no frontend trigger, then delete. (Fits: the dead `PreTerminationAnimation.tsx` in Phase A suggests the whole surface was cut.) Also `core/services/jina_reader.py` (128, never imported) + the unused `config.jina_api_key`. Flag, don't delete: `penalty_facts.py` is runtime-orphaned but has real tests calling it "the single read API over penalty figures" — wire in or decide explicitly.
- **J2 genai factory sweep (~40 files, compliance-relevant)** `genai.Client(...)` instantiated directly in ~40 files instead of `core/services/genai_client.py:get_genai_client()` — the documented Vertex/BAA cutover blocker (known deliberate deferral; the cutover itself waits on a signed BAA). The sweep is mechanical, safe pre-cutover (factory returns the consumer client while `USE_VERTEX_AI` is off), and converts the eventual cutover into a real flag flip.
- **J3 render_pdf conformance (security; wider than first thought)** ~25 call sites inline `HTML(string=..., url_fetcher=safe_url_fetcher).write_pdf()` (or worse, a local `_no_net` fetcher clone) instead of the shared `core/services/pdf.py:render_pdf`: the register services (`controls_evidence`, `driver_risk`, `claims_readiness`, `loss_development`, `risk_transfer`, `limit_adequacy`, `resident_care`, `submission_packet`), `acord_forms`, `leave_notices_service`, `matcha_work_document`, the three pilots, `training_pdf`, `discipline_pdf`, plus routes (`admin.py` ×4, `admin_onboarding`, `handbook_gap_analyzer`, `offer_letters`, `matcha_work/pdf_export` ×3, `ir_incidents` ×4, `er_copilot/export`). Sweep all of them through `render_pdf` (add an async wrapper — see L2). Rides with J2 as a conformance PR.
- **J4 log_audit helper (~150 LOC)** Near-identical audit-insert helpers ×5 (`ir_incidents/_shared.py:253`, `er_copilot/_shared.py:96`, `employee_schedule/_shared.py:51`, `employee_lifecycle/accommodations.py:198`, `fractional_hr.py:66`) + ~20 raw `INSERT INTO *_audit_log`. One `log_audit(conn, table, id_col, ...)` helper — per-domain **tables** stay (deliberate), only the helper body is shared.
- **J5 admin.py split (biggest modularity win)** `core/routes/admin.py` = 13,085 lines, 172 routes, 53 inline Pydantic models. Routes cluster cleanly: jurisdictions (38), companies (18), deal-flow (15), brokers (9), platform-settings (7), posters (6), users (5), schedulers (5), research/studio (~15). Split into `core/routes/admin/` package per the `matcha_work/` pattern; inline models → `core/models/admin_*.py`.
- **J6 mega-service sub-packaging** `core/services/compliance_service.py` (10,703 lines, 143 defs) and `handbook_service.py` (5,147; one ~2,900-line class) → `core/services/compliance/` + `core/services/handbook/` sub-packages, matching the existing precedents. No behavior change.
- **J7 further router splits** `matcha/routes/integrations/provisioning.py` (2,388 — Google Workspace vs Slack are independent), `matcha/routes/dashboard.py` (2,272, 29 inline models), `matcha/routes/broker/brokers.py` (2,103). Inline-model foldout (also `resources.py` 16, `newsletter.py` 15, `billing.py` 11, …) rides each split.
- **J8 (small)** Shared grounding-prompt fragment: the "EVIDENCE CORPUS / cite ONLY bracketed ids" preamble is copy-pasted across 6 AI services (`compliance_pilot`, `analysis_pilot`, `ask_hr`, `broker_pilot`, `handbook_pilot`, `legal_defense`). Extract one constant. Scope guard: the `build_corpus()` functions are legitimately distinct — do NOT merge them.
- **J9 (small)** Duplicated Pydantic shapes: `AuditLogEntry`/`AuditLogResponse` verbatim in `matcha/models/er_case.py:415/428` and `matcha/models/accommodation.py:124/137`; `Outreach*` dups. Consolidate the audit pair; don't over-merge the rest.

Verify per J-phase: `python3 -m py_compile` via the post-edit hook; `cd server && python3 -m pytest tests/ -v` for touched domains; J5/J6/J7 are import-graph refactors — server boots (`python3 run.py`) + `/api/openapi.json` route count unchanged before/after. J1 delete needs an explicit grep for frontend callers of `/pre-termination/checks` first.

---

# Part 3 — Third sweep: client domain scaffolds, server round 2, side apps

## Phase K — client domain-page scaffolds (`pages/app/*`, `pages/shared/*`, wizards)

Dead-code check clean again: `AuthorityCockpit`, `JurisdictionDetailPanel` (flat file + subdir both live), `components/admin/onboarding/*`, all four `pages/home/instruments/*` — every one has live importers. Also already well-factored, no action: `pages/home/instruments/shared.tsx`, detail-page tabs (all on shared `ui/PillTabs`), `components/admin/jurisdiction/` (parent-fed), `pages/portal/*` (uses the ui kit + api layer properly).

- **K1 (~300–400 LOC)** Register/tracker page family — `WorkforceCompliance.tsx` (488), `risk/{ResidentCare,DriverRisk,ControlsEvidence,Insurance,RiskProfile}.tsx`, `limit-adequacy/LimitAdequacy.tsx` — all re-implement the same "summary strip + section cards with inline add-form + status chips + PDF export" shape. Verbatim repeats: the `h-64` centered-spinner loading gate (13 files under `pages/app`), the page-header block, the FileDown-with-spinner download button (5 files identical), `const inputCls = 'w-full bg-zinc-900 …'` (10 files), `today()` helper, and the section pattern (Card + "Add" toggle → grid form → row list + empty state + Trash2 delete, 5+ files). Build `<RegisterPageShell>` + `<RegisterSection>` + hoist `inputCls`/`today()`; `AiSuggest`/`RequirementBanner` are already extracted, this is the remaining shell. New register-style features (there will be more) then start from the shell.
- **K2 (~250–350 LOC)** Public token-page scaffold — `pages/shared/SignPolicy.tsx` (266) vs `SignEmployeeDocument.tsx` (238) are ~90% identical (same local `Shell`, same `Stage` state machine `validating|invalid|used|form|submitting|submitted|error`, same verify-GET + submit-POST flow); across all 9 `pages/shared` files: raw-`fetch` BASE scaffold ×9, local `Shell` ×5, `Stage` machine ×6, `inputCls` ×5. Build `usePublicToken(basePath)` + `<PublicPageShell>`; collapse the two Sign* pages into one config-driven component.
- **K3 (~100–150 LOC)** Wizard shell — `ir/onboarding/IrOnboardingWizard.tsx` (166) and `matcha-x/onboarding/MatchaXOnboardingWizard.tsx` (146) contain a byte-identical `Stepper` + the same shell (loading gate, `ORDER` array + `advance()` clamp); `pages/app/employees/Onboarding.tsx` (323) and `pages/admin/AdminOnboardingWizard.tsx` share the shape. Build `<WizardStepper>` + `<WizardShell>` + `useWizardSteps(ORDER)`. Scope: ir/matcha-x/employees/admin only (work/ wizard stays app-local per boundary rules).
- **K4 (~80–120 LOC, pairs with K1)** `<MetricStrip>` — the `grid gap-px bg-white/10` mono-font stat strip is re-implemented ~9× with 5 independent local `Stat`/`Metric` components (the register pages + `EmployeeSchedule`, `property/sections`, two IR components). Distinct from `dashboard/StatCard` (bordered icon card — that's I4).
- **K5 (~60–90 LOC)** `<SignatureAttestation>` — the agree-checkbox + typed-legal-name + "name/date/IP recorded" block duplicated in `shared/SignPolicy`, `shared/SignEmployeeDocument`, and portal `EmployeeSignDocument` (needs a styling prop: public pages are raw inputs, portal uses the ui kit).

Verify: tsc; one register page full add/delete/PDF cycle; both public sign pages against a real token (dev); one onboarding wizard end-to-end.

## Phase L — server round 2

- **L1 (~100 LOC, cleanest win)** Fenced-JSON parse helper defined byte-for-byte ~10× under five different names (`_clean_json_text`/`_strip_json_fence`/`_parse_json_response`/`_parse_gemini_json`/`_extract_json_payload`) — `gemini_compliance.py:371`, `gemini_leads.py:52`, `handbook_audit_service.py:395`, `onboarding_scope_ai.py`, `handbook_service.py:2253`, `legislative_tracker.py:111`, `legislation_watch.py:123`, `protocol_analysis_service.py:90`, `er_analyzer.py:731`, `ir_analysis.py:675`. Precedent already exists (`compliance_evals/grounding_verifier.py:100` imports one cross-module). One `parse_model_json(text)` next to the genai factory; replace all 10.
- **L2 (~150–200 LOC, do with J3)** Insurer/register PDF scaffold — identical `<style>` block + stat-cell HTML grid verbatim in 6–8 services (`driver_risk`, `limit_adequacy`, `risk_transfer`, `resident_care`, `controls_evidence`, `submission_packet`, variants in `loss_development`/`claims_readiness`); `_esc()` redefined ×8 (`risk_transfer.py:622` already aliases `la._esc` — author knows); 3-line async `_render_pdf` wrapper ×3 (pilots + legal_defense). Extend `core/services/pdf.py` with `REGISTER_PDF_CSS`, `esc()`, `stat_cells()`, `render_pdf_async()` — same PR as the J3 sweep.
- **L3 (~150–200 LOC)** Worker scheduler-gate boilerplate — 18 tasks inline the same `scheduler_settings` enabled-check try/except. Add `scheduler_gate(conn, task_key)` to `workers/utils.py` (takes an existing conn — respects the pool-free convention). Files: `coi_expiry`, `auto_archive`, `discipline_expiry`, `broker_milestones`, `broker_risk_alerts`, `cappe_booking_reminders`, `cappe_domain_renewals`, `compliance_checks`, `compliance_action_reminders`, `grievance_deadline_alerts`, `handbook_freshness`, `ir_deadline_alerts`, `hr_proactive_push`, `leave_agent_tasks`, `location_fips_backfill`, `onboarding_reminders`, `risk_assessment`, `training_cadence`.
- **L4 (trivial delete, ~130 LOC)** `matcha/models/benefits.py` dead — all 10 classes zero references (`benefits_eligibility.py` defines its own shapes). Verify grep then delete.
- **L5 (~500 LOC moved)** `ir_incidents/_shared.py` (1,878 lines) — extract the ~15 cohesive OSHA/copilot card builders (lines ~957–1450, `build_osha_*_card`, `build_*_query_card`, …) into `ir_incidents/_cards.py`, leaving genuinely-shared CRUD/audit/upload helpers.
- **L6** `matcha/services/matcha_work_document.py` (2,786 lines — biggest single service) bundles ≥5 concerns (storage scope, jsonb coercion, email-HTML renderers, thread CRUD, token accounting) → `matcha_work_document/` sub-package, same pattern as J6.
- **L7 (~80–120 LOC/file, after J2)** ER/IR analyzer + precedent plumbing — `ERAnalyzer`/`IRAnalyzer` duplicate the model-fallback/retry/parse loop; `er_precedent.py`/`ir_precedent.py` share the identical two-phase skeleton with near-identical `enrich_with_semantics`. Dedup the LLM-call plumbing into a shared base; scoring dimensions stay domain-specific (deliberate).
- **L8 (small)** `_get_company_admin_contacts` query ×3 (`ir_deadline_alerts.py:50`, `leave_agent.py:84`, `compliance_service.py:4319`) → shared helper.
- **L9 (lower)** `core/routes/resources.py` (1,630 — assets/checkout/state-guides/pins/waitlist/qualify grab-bag) and `core/routes/compliance.py` (1,925) — split by concern when touched; lower payoff than L1–L4.
- **Router watchlist addition** (>1,000 lines, beyond Part 2's list): `matcha_work/messaging.py` (1,400), `matcha_work/ai_turn.py` (1,391), `ir_incidents/{analytics 1353, ai_analysis 1261, crud 1196}`, `employees/crud.py` (1,127), `broker/portfolio.py` (1,064), `er_copilot/guidance.py` (1,054). The `_shared.py`-equipped families already have partial extraction — lower urgency.

Verify: py_compile hook per edit; pytest for touched domains; L2/J3 sweep → render one PDF per family (register, pilot packet, OSHA log, offer letter) and diff visually; L3 → run one gated task manually with the row disabled/enabled.

## Phase M — side apps (tellus, cappe backend, agent-ui)

Sweep verdict: both side frontends small and fully live (zero dead files; all routed/imported); `server/app/tellus` has no dead functions; import-boundary rule holds (single documented `geo.py` exception). agent-ui is lean (1,235 LOC of TS; its 970-line `index.css` is just a lot of styling — leave). tellus frontend mirroring the main client's 401-refresh interceptor is by-design (separate Vite project, can't share without a workspace package) — flag only.

- **M1 (~95 LOC + drift-hazard removal)** `tellus/services/auth.py` (98) and `cappe/services/auth.py` (98) are near-verbatim twins — same four functions, revocation checks byte-identical, only the scope constant differs. Extract `app/core/services/scoped_auth.py:make_token_helpers(scope)`; both files become ~15-line wrappers. Respects the "import only from app/core" rule — core is the right home.
- **M2 (~25–30 LOC, same PR or skip)** The `require_*_account` dependency skeleton (decode → UUID parse → status check → revocation → 401) duplicated in `tellus/dependencies.py` + `cappe/dependencies.py`; SQL + returned models stay product-specific.
- **Non-target:** tellus/cappe email services share only a thin skeleton (~15–20 LOC) — not worth the coupling.

Verify: py_compile; login + refresh + logout on a tellus account and a cappe account (dev); revoked-token 401 still fires for both scopes.

---

## Sequencing + totals

| Phase | PR | LOC removed | Risk |
|---|---|---|---|
| A dead code | 1 | ~2,050 | none |
| B SSE helper | 2 | ~600 | low |
| C useAsync tranche | 3 | ~250 (1,500+ full rollout) | low |
| D1 signup | 4 | ~380 | medium (Stripe smoke) |
| D2 DataTable | 5 | ~300 | low |
| D3 pilot chat hook | 6 | ~400 | medium (abort/StrictMode) |
| D4 modals | 7 | ~200 | low, mechanical |
| E1 pilot types | with PR 2 | ~50 | none |
| E2 god-component splits | opportunistic + top-5 PR | ~0 (structure) | low |
| E3 Settings.tsx → api layer | with PR 3 or own | ~30 | low |
| E4 flatten pages/admin | optional, own PR | 0 (moves) | low |
| F security (F1–F4, F7) | with PR 1 or own | ~0 | low |
| G1–G4 bundle/perf quick wins | own PR | ~0 LOC, large bundle cut | low |
| G6 simpler-pages consolidation | own PR | ~1,500–2,000 | low-med (marketing visual QA) |
| H1 work route merge | quick win, any PR | ~38 | none |
| H2 BaseSocket | own PR | ~130 | low |
| H3 work modal adoption | D4-style tranches | ~150–180 | low |
| H4–H5 work hook extractions / optimistic | opportunistic | ~0–80 | low-med |
| I1 pilot surface scaffold | own PR (pairs with D3) | ~400–600 | medium |
| I2 formatting consolidation | opportunistic + one PR | ~150–250 | low |
| I3 badge variant maps | one PR | ~100–200 | low |
| J1 server dead code | own PR (verify first) | ~2,020 | low |
| J2 genai factory sweep | own PR | ~0 (conformance) | low, mechanical |
| J3 render_pdf conformance | with J2 | ~0 (security) | low |
| J4 log_audit helper | own PR | ~150 | low |
| J5 admin.py package split | own PR, careful | ~0 (structure) | medium |
| J6 mega-service sub-packaging | 2 PRs | ~0 (structure) | medium |
| J7 router splits + model foldout | per-router PRs | ~0 (structure) | medium |
| K1+K4 register shell + MetricStrip | own PR | ~400–500 | low-med |
| K2+K5 public-page scaffold + attestation | own PR | ~300–400 | low-med (token flows) |
| K3 wizard shell | own PR | ~100–150 | low |
| L1 fenced-JSON helper | quick PR | ~100 | low, mechanical |
| L2 PDF scaffold (with J3 sweep) | own PR | ~150–200 | low |
| L3 scheduler-gate helper | quick PR | ~150–200 | low |
| L4 dead benefits.py models | with L1 | ~130 | none (verify grep) |
| L5 ir _shared.py card split | own PR | ~0 (structure) | low |
| L6 matcha_work_document split | own PR | ~0 (structure) | medium |
| L7 analyzer/precedent plumbing | after J2 | ~200–300 | medium |
| M1+M2 scoped_auth factory | own PR | ~120 | low (auth smoke both scopes) |

Client first wave ≈ 4,200 LOC removed against ~700 LOC of new shared code; full rollout of the C/D/G6 tranches reaches ~6–7k. Part 2 adds ~3,000–3,500 more removable LOC (J1 + I1–I3 + H1–H3) plus the two big structural wins (admin.py 13k split, compliance/handbook service sub-packaging). Part 3 adds ~1,700–2,300 more (K1–K5 + L1–L4 + L7 + M1) plus three structural splits (ir _shared cards, matcha_work_document, resources.py). Grand total realistic: **~9–12k LOC removed** across client+server with materially better modularity.

## Key reference files

- `client/src/api/client.ts` — `authStreamHeaders`/`ApiError` that `api/sse.ts` builds on
- `client/src/api/handbook-pilot/handbookPilot.ts` — canonical pilot SSE + `ChatHandlers` shape to preserve
- `client/src/pages/app/handbook-pilot/Console.tsx` — reference semantics for `usePilotChat` (abort, StrictMode, error-status rules)
- `client/src/pages/auth/ComplianceSignup.tsx` — superset signup page; defines what `TierSignup.tsx` must and must not absorb
- `client/src/pages/admin/Companies.tsx` — template for `DataTable`/`FilterPills` chrome and the useAsync filter-deps pattern
- `client/vite.config.ts` — read the manualChunks comment before touching chunking

## Doc drift noted during the audit

Root `CLAUDE.md` says React 18; `client/package.json` pins `react ^19.2.0` (and vite.config's comment references React 19). Worth correcting when next editing that section.

---

## STATUS — Phases E, F, G (2026-07-20)

### Phase E — partial
- **E1** already landed in Phase B (`api/sse.ts` exports the shared pilot types).
- **E3 done for the real outlier.** `pages/admin/Settings.tsx`'s 10 raw `fetch()` calls →
  new `api/admin/platformSettings.ts` + `useAsync`. This was not just tidying: the page's
  own `authHeaders()` read `matcha_access_token` from localStorage and so **bypassed
  `api/client.ts`'s 401-refresh-and-retry**. With an aged-out access token every call on
  the page failed, and because the page swallowed errors (`catch {}` / `if (res.ok)`) it
  rendered as an empty settings screen. Error branches added where the UI had nowhere to
  put a failure.
  Still open: `components/admin/JurisdictionDetailPanel/useJurisdictionDetail.ts` (5 calls).
- **E2 / E4 not started** — E2 is explicitly opportunistic ("when Phase C/D touches a
  >450-LOC file"), E4 is marked deferred in `client/CLAUDE.md`.

### Phase F — done except F6
- **F1** `sandbox=""` on all 5 admin `srcDoc` preview iframes.
- **F2** analysis-pilot chart SVG now renders as an `<img>` data-URI instead of
  `dangerouslySetInnerHTML` — a passive image cannot script, so an escaping bug upstream
  can't become XSS.
- **F3** `CitationSources` gates `source_url` through `safeUrl`. **`safeUrl` moved to
  `utils/safeUrl.ts`** — it lived in `work/components/panels/markdownToHtml.ts`, and a
  `components/ui` file importing from `work/` would break the cross-app boundary rule in
  `client/CLAUDE.md`. `markdownToHtml` re-exports it, so existing importers are unchanged.
- **F4** `AppLayout` fails closed on `!me` (matches `RequireRole` / `PortalLayout`).
- **F5 skipped deliberately** — the plan scopes `externalRedirect` adoption to D1's
  `registerAndCheckout`, and D1 isn't built yet. Doing it now means touching ~15 sites
  twice.
- **F7** `three` + `@types/three` removed (zero import sites); lockfile synced.

### Phase G — done except G5/G6
- **G1** `ProductCarousel` (+ its 4 instruments) and `PricingContactModal` lazy on the apex.
  The modal is **latched mounted after first open**, not `isOpen &&` — it owns an
  `<AnimatePresence>` keyed on `isOpen`, so unmounting on close would cut its exit animation.
- **G2** `RiskInsightsHero` (recharts + d3) lazy on the Lite marketing page, with a
  reserved-height fallback so the late chunk doesn't cause layout shift.
- **G3** Cappe's 12 `site/*` pages incl. the ~1.5k-LOC `PageEditor` are lazy behind one
  `<Suspense>`; `/cappe/login` no longer downloads the site builder.
- **G4** `ToastProvider` context value memoised.
- **G5 / G6 not done** — G5 is marked deferred (needs a windowing dependency); G6 is a
  ~2k-LOC marketing-page consolidation that wants its own PR.

**Measured, not assumed:** eager entry chunk **463,885 → 432,772 bytes raw, 147,362 →
140,106 gz (−7.3 KB gz)**. That is real but well short of the plan's "~60–110 KB gz"
estimate for G1 — most of framer-motion was evidently not in the entry chunk to begin
with, so the estimate was wrong, not the change. The Cappe (G3) and Lite (G2) wins are on
their own route chunks and are not visible in this entry number.

**Still owed:** the manual click-through. Everything since Phase B has been verified by
tsc + tests + build only. F1–F4 in particular are visual/behavioural (do the deal previews
still render sandboxed, do citation links still open, does a logged-out `/app/*` hit
redirect) and no automated check in this repo covers them.

---

## STATUS — Phases H, I, J (2026-07-20)

### Phase H — H1 + H2 done
- **H1** `WorkRoutes`/`WerkRoutes` merged into `WorkRouteTree({ surface })`; entries are 8-line
  wrappers. `WerkLiteRoutes` deliberately NOT merged — it has its own login route, auth guard,
  `werk_lite` FeatureGate and a narrower route set; folding it in means re-adding all of that
  as conditionals.
- **H2** `BaseSocket` extracted; thread/project/channel sockets shrink to path + dispatch +
  rejoin. 742 LOC across three files → 413 + a 195-line base. **This normalized real drift**:
  only `channelSocket` answered the server's `server_ping` with a `pong`, so thread and project
  connections looked unresponsive to the server's liveness probe. Now in the base for all three.
  Covered by `work/api/baseSocket.test.ts` (17 tests, fake WebSocket) — backoff schedule and
  cap, backoff reset on clean open, no-reconnect on 4001/4003, rejoin-on-reconnect, leave-frame
  ordering, ping lifecycle, token-not-in-URL.
  Two further fixes came out of review: `connect()` is now **genuinely idempotent** (it bails on
  an OPEN/CONNECTING socket and cancels a pending retry) — `getSharedChannelSocket`'s comment had
  claimed this for as long as it has existed while the code happily overwrote `this.ws` and
  orphaned a still-open socket; and `onConnected`/`onDisconnected` became **listener sets**
  (`addConnectedListener` returning an unsubscribe) rather than single slots. The channel socket
  is a process-wide singleton shared by three hooks, so `socket.onConnected = fn` had the last
  hook to mount silently clobber the others, and `= null` on unmount removed whichever handler
  happened to be registered. `channelSocket` had already solved exactly this for messages with
  `addMessageListener`; lifting the single-slot version into the base generalized the wrong one
  of the two patterns.
- **H3 / H4 / H5 not started** — mechanical but large; H3 extends D4's tranche system, which is
  itself only 2 of 10 done.

### Phase I — I2 + I3 done
- **I2** new `utils/format.ts` (`relativeTime`, `formatMoney`, `formatBytes`) + 21 tests; the 10
  local relative-time copies migrated. Some of what looked like duplication was genuine drift —
  `components/dashboard/FlagsTable.tsx` never rolled over past hours, so a 30-day-old flag read
  "720h ago". **But some of it was not drift, and the first version of this change wrongly
  flattened it** (caught in review): an inbox list rendered '' for a conversation with no
  messages and jumped straight to a bare "Mar 5", a notification dropdown used a sentence-cased
  "Just now" and a narrow absolute format, channel analytics counted days forever, blog comments
  went absolute after 7 days and echoed an unparseable timestamp rather than showing a visitor an
  em dash. Those are per-surface presentation decisions, not accidents.
  So `relativeTime` takes named options (`empty`, `justNowLabel`, `yesterdayLabel`,
  `maxRelativeDays`, `absolute`, `onInvalid`) — every one of which exists because a real call
  site needed it — and each has its own test. Defaults match what the majority of sites did.
- **I3** new `components/ui/badgeMaps.ts` (severity/priority/confidence/determination); the
  ER panels' local copies removed. Domain-specific status maps stay put — same shape, different
  meaning. `ERTimelinePanel`'s `confidenceVariant` keeps its own map: it maps low → `danger`
  where the others use `neutral`, and that may be intentional for a legal timeline, so it is
  flagged rather than silently flattened.
- **I1 / I4 / I5 not started** — I1 is the pilot surface scaffold and pairs with D3, which is
  still unbuilt; doing the chrome before the behavior means touching the four consoles twice.

### Phase J — J1 + J9 done; J8 rejected on inspection
- **J1** deleted `matcha/services/pre_termination_service.py` (1,891), its test (550), and
  `core/services/jina_reader.py` (128) + the `jina_api_key` config. Verified before deleting:
  the service's only importer was its own test, and the mounted `/pre-termination` router never
  imports it.
  **⚠️ This surfaced a live product issue, not just dead code.** That service was the SOLE
  writer of `pre_termination_checks` and was unreachable — no route, worker, or frontend called
  it. So the table cannot have been written for as long as that has been true, while
  `GET /pre-termination/checks/analytics` still serves it and `components/risk-assessment/
  SeparationRiskCard.tsx` still renders the result to users. The card is showing analytics over
  a table nothing can fill. **Left in place deliberately** — removing a user-visible card is a
  product call, not a cleanup one. Decide: rebuild the writer, or retire the card + endpoint.
- **J9** `AuditLogEntry`/`AuditLogResponse` (byte-identical in `er_case.py` and
  `accommodation.py`) → `models/audit_log.py`, re-exported from both so importers are untouched.
  `IRAuditLogEntry` NOT folded in — different field set, and IR's audit log is a compliance
  artifact that shouldn't track two unrelated domains' schema churn.
- **J8 NOT DONE — the plan's premise doesn't hold.** Reading all six "EVIDENCE CORPUS" preambles,
  they are not copy-paste: each names its own id namespaces (`metric:`/`ratio:` vs `clause:`/
  `jur:` vs `law:`/`playbook:`) and its own domain-specific "NEVER invent" list, and `ask_hr`'s
  is written in a different voice entirely (employee-facing, explains the consequence of a
  dropped citation). The only genuinely shared text is the one-line corpus header. Extracting a
  constant would either be trivial or would force a parameterized template that flattens
  deliberate differences. Recommend dropping J8 from the plan.
- **J2 / J3 / J4 / J5 / J6 / J7 not started.** J3 (render_pdf conformance, ~25 sites) is the one
  with security weight and should be its own PR. J5 (13,085-line `admin.py`) and J6 (10,703-line
  `compliance_service.py`) are import-graph refactors that need the boot + route-count check the
  plan specifies — not something to bundle into a mixed commit.

**Verification:** tsc clean, 136 client tests (up from 110; +13 socket, +13 format), build clean.
Server: `python3 -m pytest` shows the same 19 pre-existing collection errors before and after
these changes (missing local deps — `audioop_lts` and friends), so the delete broke nothing;
the deselected count drops by exactly the 60 pre-termination tests removed.

**Still owed:** the manual click-through, now including a socket smoke test — send/receive in a
channel, kill the dev server briefly, confirm reconnect and rejoin. The socket tests cover the
state machine but not a real server handshake.

---

## STATUS — Phases K, L, M (2026-07-20)

Done: **L1, L3 (partial), L4, L8, M1, M2, K3**. The rest is deferred with reasons below —
this batch stuck to work that is mechanical, independently verifiable, and safe to land in a
mixed commit.

### Landed
- **L4** deleted `matcha/models/benefits.py` — all 10 classes verified zero-reference
  individually before deleting (the router of the same name is unrelated and stays).
- **L1** new `core/services/model_json.py` (`strip_json_fence` / `clean_model_json` /
  `parse_model_json`) + 20 tests. **The plan's premise was wrong**: it describes ~10
  byte-identical copies; there are 15 helpers and, normalising names and indentation, only
  TWO are actually identical. They differ in *robustness*, which is the real finding — the
  model emits the same malformed output to everyone but only some callers recover.
  `gemini_compliance` and `commit_scan_service` rewrite Python literals (`True`/`None`),
  which Gemini emits regularly; `ticket_draft_service`, otherwise the same helper, does not
  and so simply failed to parse those responses. Migrated the 5 sites whose contract matches.
  **Deliberately NOT migrated:** `protocol_analysis_service` and `accommodation_service` let
  `json.loads` raise so their caller can react — swapping in `parse_model_json` would convert
  a loud failure into a silent default. The remaining sites need per-site judgment, not a sweep.
- **L8** new `core/services/company_contacts.py` — the identical DISTINCT clients-join-users
  query from `ir_deadline_alerts`, `leave_agent` and `compliance_service`. The connection-taking
  form is primary because workers are pool-free; `get_company_name_and_contacts` uses
  `connection_or_direct` for the one caller with no connection in hand.
- **L3 (all 21, zero inline gates left)** `workers/utils.py` gains `scheduler_settings_row`
  + `scheduler_enabled`. The helper returns a **bool/row, not an early return**: each task
  answers a disabled scheduler with its own payload (`{"checked": 0}`, `{"status": "disabled"}`,
  …) and flattening those would change what every caller reports. Most tasks (15) need
  `max_per_cycle` alongside `enabled`, hence the row form.
  **The fail policy is an explicit `default` argument, not a house convention**, because the
  tasks genuinely disagree and getting it backwards is expensive one way: `auto_archive` and
  friends fail **open** (idempotent bookkeeping; a DB hiccup silently disabling them is worse
  than an extra run), while `cappe_domain_renewals` (buys domain renewals) and
  `vertical_coverage_sweep` (live Gemini calls, seeded disabled on purpose) fail **closed**.
  A naive sweep would have flipped those two to fail-open and started them spending.
  10 tests cover both directions.
- **M1/M2** new `core/services/scoped_auth.py:make_token_helpers(scope)`; `cappe/services/auth.py`
  and `tellus/services/auth.py` drop from 98 lines each to 28. This is the security-weighted one:
  the decode path's scope check is the *only* thing stopping a Cappe token authenticating
  against Tell-Us (all products sign with the same `jwt_secret_key`), and two copies meant a
  fix to one silently left the other exposed. 18 tests, including every cross-scope
  rejection direction.
  **Writing those tests found a live latent bug**: python-jose calls `token.rsplit(...)` with
  no type check, so `decode_*_token(None)` raised `AttributeError` — which neither copy's
  `except (JWTError, KeyError, TypeError)` caught. No caller passes None today, but a function
  documented to return None for anything invalid must not raise for ANY input, or the first
  caller that forwards a missing header turns a 401 into a 500. Now caught.
- **K3** `components/ui/WizardStepper.tsx`; IR + Matcha-X wizards use it. Their render bodies
  were identical but the plan's "byte-identical" is again not quite right — Matcha-X has a
  terminal `done` state past the last step. The shared component takes `activeIndex` already
  computed rather than a step key, so it needn't know either wizard's step union.

### Deferred, with reasons
- **J2** (~40 files, `genai.Client` → factory), **J3 + L2** (~25 `render_pdf` sites + the
  shared PDF scaffold). J3 carries security weight and L2 rides with it; together they are a
  focused conformance PR whose verification is "render one PDF per family and diff visually" —
  that does not belong bundled with unrelated work.
- **J5** (`admin.py`, 13,085 lines / 172 routes), **J6** (`compliance_service.py` 10,703 +
  `handbook_service.py` 5,147), **L5**, **L6** (`matcha_work_document.py` 2,786), **L9**.
  Import-graph refactors; the plan's own verification is "server boots + `/api/openapi.json`
  route count unchanged before/after", which needs a clean tree to be meaningful.
- **L7** explicitly sequenced after J2.
- **K1, K2, K4, K5** — the register/public-token/metric-strip/attestation shells. Real payoff
  (~700–1,000 LOC) but each is a multi-page visual refactor whose verification is a click-
  through of pages this branch already owes one for. K2 in particular rewrites two public
  token-gated signing pages — worth its own PR and a real token test.
- **D1** (tier signup → Stripe), **D3** (four pilot consoles), **I1** (pilot chrome, pairs
  with D3), **H3/H4/H5**, **I4/I5** — unchanged from earlier notes.
- **J8** rejected on inspection (see the H/I/J status block).

**Verification:** client tsc clean, 148 tests, build clean. Server: 38 new tests pass; full
suite goes from **98 failed / 3277 passed → 97 / 3278** (the one flipped failure is the
None-token test, which fails without the AttributeError fix and passes with it). The 97
remaining failures and 48 collection errors are pre-existing and environmental — missing local
deps (`audioop`, `segno`) — identical before and after.

### Review fixes on the K/L/M batch (2026-07-20)

- **`clean_model_json` was corrupting string data.** The colon-anchored regex every local copy
  used (`re.sub(r":\s*True\b", ": true")`) does not confine matches to JSON value positions,
  because string values contain colons: `{"note": "Status: True positive"}` became
  `"Status: true positive"`. The model's own words were edited on the way to the parser,
  invisibly. Replaced with a single-pass scanner that tracks string state and backslash
  escapes and substitutes only outside strings. It also fixes a second latent bug the regex
  had: literals in **array positions** (`[True, False, None]`) have no preceding colon and were
  never converted at all.
- **`clean_model_json` no longer narrows to arrays by default** (`allow_array=False`). The
  widening was a real bug: its three callers expect an object and call `data.get(...)` OUTSIDE
  the try that wraps `json.loads` (`ticket_draft_service.py:286`, `commit_scan_service.py:215`),
  so a model returning `[...]` parsed fine and then died on an uncaught AttributeError, where
  before `json.loads` raised inside the try and the fail-closed path handled it.
  `parse_model_json` opts in, since a top-level array is legitimate there.
- **`parse_model_json` has a caller now** — `labor_relations_ai._parse_json_block` (returns
  None on failure, caller does `or {}`) was an exact contract match. `risk_assessment_service`
  was re-examined and left alone: its `raw_decode` fallback still raises, so it is not a match.
- Import placement fixed in `compliance_service.py` (was ~5,100 lines below its use — the AST
  heuristic took a file-wide `max()` over top-level imports and this file has a stray
  `import hashlib` near the end; now it targets the contiguous header block). Unused `import re`
  removed from two files. Leftover blank runs collapsed at every removal site.
- `get_company_name_and_contacts`'s switch from `get_connection` to `connection_or_direct` is
  now documented as a deliberate widening (makes it worker-callable) with the constraint that
  keeps it safe: it must touch nothing request-scoped.

**Verification note:** the earlier docstring-import bug (imports landing inside module
docstrings, where `ast.parse` happily accepts them and the name is never bound) is why this
round ends with a real `importlib.import_module` of every touched module — **44 modules, 0
failures** — rather than a syntax check. Server suite: 98 failed / 3302 passed → **98 failed /
3317 passed**, 20 collection errors → 19. Identical failures, +15 passes.

### Pre-merge review fixes (2026-07-20)

A whole-branch pass before merge caught three instances of the same mistake: reasoning
carefully about a failure mode, fixing it in one place, and not applying it to the siblings.

- **The forced-logout fix reached only 3 of 5 route guards.** `PortalLayout` and
  `RequireBusinessAccount` still redirected on `!me`, so the *employee portal* — the surface
  most likely to be hit by a non-admin — still logged users out on a transient `/auth/me`
  failure. All five now gate on `authFailed` and render a recoverable "could not verify your
  session" state for the unknown case.
- **`uploadFilesStream` had no `settled` guard**, though `sendMessageStream` (which shares its
  transport) documents at length why silence is unacceptable. A proxy cutting a 200 mid-stream
  left the resume/inventory upload spinner running forever with no message.
- **Timeout detection no longer relies on `AbortSignal.reason`.** Where the reason is not
  populated, a timeout was misread as a user cancel and reported silently — reintroducing the
  stuck-composer state the `settled` flag exists to prevent. Both call sites now track an
  explicit local `timedOut`.

Also fixed:
- `<Modal>` gains `dismissible` (default true). Dialogs migrated in D4 previously had an X
  button ONLY; adopting the shared modal handed them Escape-and-click-outside for free, which
  is right for a form and wrong for a newsletter **mid-send**. `SendModal` and `CsvImportModal`
  pass `dismissible={!busy}`.
- `<Modal>` Escape now closes only the **topmost** dialog. Each instance registered its own
  document listener, so one Escape collapsed a whole stack. 6 tests; verified by reverting.
- `postSSE` treats a `null` body as empty (`body == null`) rather than sending the literal
  string `"null"`, which FastAPI 422s against a Pydantic model.
- New `hooks/useDebounced`; `ServerErrors`' search box no longer fires a list+stats request
  pair per keystroke. (Pre-existing on main, but now a one-line fix at a single call site.)

**Verification:** tsc clean, **154 client tests** (up from 148), build clean.

---

## STATUS — J2 + J3 + L2 conformance (2026-07-20)

The server conformance PR. Mechanical, security-weighted, and unblocks L7.

### J2 — genai factory sweep (DONE)
All **44** `genai.Client(...)` / `_genai.Client(...)` call sites across **39 files** now
route through `core/services/genai_client.py:get_genai_client()`. Zero raw instantiations
remain (grep-verified). Safe pre-cutover — the factory returns the consumer client while
`USE_VERTEX_AI` is off, so this is a no-op today and turns the eventual Vertex/BAA cutover
into a real flag flip.
- The one non-trivial site (`gemini_session.py`, `**client_kwargs`) works unchanged — the
  factory forwards `**kwargs`.
- Import placement anchored on each file's existing genai import line (module-level or
  in-function), never a docstring — the hazard the L1 round hit. Confirmed by `importlib`
  of the factory sites: 10/10 clean, 0 failures.
- **A substring bug was caught and fixed mid-sweep**: replacing `genai.Client(` before
  `_genai.Client(` turned the latter into `_get_genai_client(` (the `genai.Client(`
  substring matched first) at 6 sites. Corrected; grep confirms none left.
- Dead imports cleaned: 7 top-level + 6 in-function `from google import genai` lines that
  the swap orphaned were removed (types-only imports kept).

### J3 + L2 — render_pdf conformance (DONE, minus the CSS/stat-cell dedup)
All **37** inline `HTML(string=..., url_fetcher=...).write_pdf()` sites now go through
`core/services/pdf.py`. Zero raw `.write_pdf(` outside `pdf.py`; zero `safe_url_fetcher`
imports outside `pdf.py` (grep-verified).
- New `render_pdf_async()` in `pdf.py` folds the `asyncio.to_thread` wrapper + the SSRF-safe
  fetcher into one call. The four hand-rolled async renderers (`resident_care`,
  `submission_packet`, `benefits_eligibility`, and the `WeasyHTML`-aliased `er_copilot/
  export`) adopt it or `render_pdf`.
- **The two `_no_net` fetcher clones are gone** — `resident_care` and `submission_packet`
  each defined their own local SSRF guard instead of the shared `safe_url_fetcher`. This was
  the security-weight part: one place to audit the fetcher now, not three.
- `to_thread`/`wait_for(timeout=...)` wrappers were preserved (the inner lambda body was
  swapped to `render_pdf`), so no async timeout semantics changed.
- `matcha_work_document`'s one `stylesheets=[CSS(...)]` kwargs site → `render_pdf(html,
  stylesheets=...)`; the `CSS` import stays. `pdf.py` is the only file still importing
  `HTML` from weasyprint. `importlib` of 10 PDF services: clean.

### J4 — log_audit helper (DONE, scoped to the identical-shape trio)
New `core/services/audit_log.py:insert_audit_log(conn, *, table, id_column, id_value, ...)`
holds the shared write body. The three helpers that were byte-identical modulo table name +
FK column — `ir_incidents/_shared.py`, `er_copilot/_shared.py`,
`employee_lifecycle/accommodations.py` — are now thin wrappers calling it, **signatures
unchanged**, so every call site is untouched. `table`/`id_column` are hardcoded literals at
each wrapper (never user input), so interpolating them is safe under the SQL rule; every
value still binds as a parameter. 3 DB-free tests (fake conn) assert the SQL column order and
the `details or {} → NULL` rule match the old bodies exactly.
- **`schedule_audit_log` and `fractional_audit_log` deliberately NOT folded in** — different
  column set/order (`schedule`: `company_id`-first, `actor_user_id`, no `ip_address`, `::jsonb`
  cast; `fractional`: 4 columns, singular `detail`). A shared helper flexible enough for both
  would be worse than two small honest functions.
- **The 18 raw `INSERT INTO *_audit_log` sites NOT swept** — they span 13 tables
  (pilot/provisioning/legal_matter/discipline/…), each a distinct column shape, not the shared
  7-column one. Converting them needs per-site mapping and full-suite verification, which the
  local env can't run (missing `audioop`/`segno`). Left for a DB-capable follow-up.

### L5 — ir_incidents/_shared.py card split (DONE)
The venv (`server/venv`) has the deps the system python3 lacked (`audioop`/`segno`), so the
server **boots and the full test suite runs** — which unblocked this. New
`ir_incidents/_cards.py` (477 lines) holds the ~15 pure `build_*_card` factories +
`compose_root_cause_text` + their constants (`OSHA_INJURY_TYPES/_LABELS`, `OSHA_EMERGENCY_*`,
`ROOT_CAUSE_*`, `ROOT_CAUSE_INTERVIEW_STEPS`). `_shared.py` drops 1878 → 1475 lines and
**re-exports every moved name**, so `copilot.py` and the DB-backed dispatchers that stay in
`_shared` (`next_case_step`, `_persist_osha_emergency_alert`) are untouched. `_cards` imports
nothing from `_shared` (pulls the two `PRIVACY_CASE_*` constants straight from
`osha_privacy`), so the re-export is a clean one-way `_shared → _cards` with no cycle.
- Extracted by AST (nodes + leading comments), not line ranges. **One miss caught by the test
  suite**: `compose_root_cause_text`/`build_root_cause_text_card` also read
  `ROOT_CAUSE_INTERVIEW_STEPS`, which wasn't in the first move list — 8 root-cause tests failed
  until it moved too. This is exactly why the split needs a bootable test run, not just compile.

**Verification:** `venv` py_compile clean; **446 IR + copilot-smoke tests pass** (0 failures);
app boots at **1858 routes, unchanged** before/after; `copilot`/`crud`/`osha` all import clean.

**NOT done — L2's HTML-builder dedup.** The `REGISTER_PDF_CSS` / `esc()` / `stat_cells()`
consolidation (the ×8 `_esc()` redefinition and the shared register `<style>` block) is a
cosmetic dedup of the HTML *builders*, not the render path — its verification is "render one
PDF per family and diff visually", which can't be done headless here. Left for a follow-up
that can eyeball the output. The render-path conformance (the security-relevant half) is complete.

**Verification:** all touched files `py_compile` clean; invariant greps green (0 raw
genai.Client, 0 raw write_pdf, 0 stray safe_url_fetcher imports); `importlib` of 20 touched
modules across both sweeps → 0 failures. Full pytest not re-run here (env missing local deps
`audioop`/`segno` — same pre-existing baseline).

### C rollout — 5 more (2026-07-20)
Continued the useAsync sweep with 5 clean single-fetch pages (12 → 7 remaining after the
earlier tranche is not the count — this is the broader ~90-candidate pool): `risk/Acord`,
`risk/Coi`, `risk/ManagementLiability`, `broker/client-detail/ControlsTab`,
`broker/client-detail/LimitsTab`. Each dropped its `useState(data)` + `useState(true)` +
fetch-`useEffect` + `.finally(setLoading)` quadruplet for a single `useAsync(fn, deps,
initial)` line; optimistic writers keep working via the hook's `setData`, and `LimitsTab`'s
child `reload` prop is now the hook's `reload`.
- **`broker/client-detail/DefenseTab` deliberately skipped** — it runs two parallel fetches
  under `Promise.allSettled` (each survives the other failing). Folding that into one
  `useAsync` would either lose the independent-failure behavior (`Promise.all`) or need more
  code than it removes. Not a clean single-fetch; left for the god-component pass.

**Verification:** `tsc -p tsconfig.app.json` clean, 154 client tests pass, `npm run build`
clean. These pages have no unit tests (unchanged count); tsc + build is the guard.

### C rollout — 7 more (2026-07-20, same session)
Second tranche of clean single-fetch migrations: `broker/BrokerPropertyPortfolio`,
`widgets/NoteThread`, `er/ERDocumentList`, `admin/company-detail/TokensTab`,
`landing/resources/StateGuides`, `landing/BlogIndex`, `ir/risk/IRLocationScorecards`.
12 useAsync migrations total this session.
- Optimistic writers preserved via `setData` (NoteThread append, ERDocumentList
  append/filter — the hook's `setData` takes a functional updater); `TokensTab`'s
  post-grant refetch is the hook's `reload`; `BrokerPropertyPortfolio`'s bool `error`
  folds into the hook's `error`.
- `StateGuides` kept its `document.title` side effect in its own tiny `useEffect` — only
  the fetch moved to useAsync.
- **`broker/BrokerDashboard` skipped** — 5 parallel fetches into 5 states, same class as
  DefenseTab (not clean single-fetch).

**Verification:** tsc clean, 154 tests pass, build clean.

### C rollout — running total 30 migrations (2026-07-20, one session)
Further tranches after the first 12 (each its own commit, all tsc + 154 tests + build clean):
- risk-assessment {Anomalies,Benchmarks,CohortAnalysis,MonteCarlo}Panel, property/Property,
  broker/client-detail/{LossRatioTab,EplTab}
- admin/GapOverview, marketing/BlogComments, work/channels/JobPostingsPanel
- broker/BrokerExternalClients, admin/jurisdiction/KeyIndexTab, profile/ProfileResumeSection,
  ir/risk/IRIncidentTrendChart, broker/client-detail/LossTriangleTab, admin/Features
- admin/jurisdiction/{IntegrityTab,KeyCoverageDrawer}

**Skipped, each for a real reason** (the remaining pool is increasingly these): multi-fetch
under Promise.all/allSettled (BrokerDashboard, ResidentCare, CompliancePostersTab, WerkLiteHome,
RiskProfile, DefenseTab); parameterized `load(refresh)` that `reload()` can't express
(OutreachDrawer); a `catch` that routes errors to other state (BrokerPipeline →
`setNeedsTerms`); a shared `error` state spanning load + mutations, where useAsync would drop
the load-error into a channel the UI doesn't show (HiringClientPickerModal, InviteManager);
and fetch-then-populate-a-form effects (MatchaLitePricingPanel, MatchaXOnboardingWizard).
The clean single-fetch quadruplet is largely exhausted; what's left needs the god-component /
E2 hook-extraction pass, not a mechanical sweep.
