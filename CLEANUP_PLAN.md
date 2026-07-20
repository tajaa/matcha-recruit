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

> **STATUS 2026-07-20 — B1 done, B2 partially done. Resume here.**
>
> Done and committed:
> - `api/sse.ts` exists — `consumeSSE` / `postSSE` / `streamPilotChat` / `SSEHttpError`,
>   plus the E1 shared types (`SessionStatus`, `PilotMessage<TMeta>`, `ChatHandlers<TResult>`).
>   `PilotSession` was NOT hoisted — its shape genuinely differs per pilot, the plan
>   was wrong to list it.
> - **B1 complete** — all 5 pilot api files migrated (`handbookPilot`, `analysisPilot`,
>   `legalDefense`, `brokerPilot`, `compliancePilot`). Broker's 409
>   `missing_required_documents` gate survives via the `onHttpError` escape hatch.
> - **B2 6 of 22 files**: `api/portal/portalAskHr.ts` (also dropped its direct
>   localStorage token read), `api/labor/laborClient.ts`,
>   `work/api/matchaWork/{research,messaging,candidates}.ts`, and a new shared
>   `work/api/matchaWork/_base.ts:uploadFilesStream` that the three multipart
>   uploaders now share (messaging.ts went 368 → 118 lines).
>
> **Remaining B2 (16 files)** — enumerate live with
> `grep -rln "getReader()" client/src --include='*.ts' --include='*.tsx'`:
> `components/shared/HelpAssistant.tsx` (**fixes the real cross-chunk bug** — it
> calls `decoder.decode(value)` with no `{stream:true}` AND keeps no buffer, so
> the trailing partial line of every chunk is discarded outright),
> `components/er/{ERGuidancePanel,EROutcomePanel,ERSimilarCasesPanel}.tsx`,
> `hooks/admin/{useEnrichStream,useResearchGaps}.ts`,
> `hooks/compliance/useComplianceCheck.ts`,
> `pages/admin/studio/{StudioAssistant,LibraryTab,CoverageTab/useCoverage,PipelineTab/usePipeline}`,
> `pages/admin/JurisdictionData.tsx`,
> `components/admin/JurisdictionDetailPanel/helpers.ts`,
> `components/admin/onboarding/StatutoryFitPanel.tsx`,
> `components/matcha-x/onboarding/useMatchaXBuildStream.ts`.
> The two anon streams (`hooks/ir/useIRAnalysisStream.ts`,
> `components/ir/IRCopilotPanel/useCopilotPanel.ts`) keep their own unauthenticated
> fetch and should call `consumeSSE` directly rather than `postSSE`.
>
> **Migration gotcha worth repeating:** before collapsing a loop, check whether it
> treats a bare `[DONE]` as an *error*. `sendMessageStream` does — a `[DONE]` with
> no preceding complete/error means the turn never settled and the composer stays
> stuck on "Thinking…" with the input disabled. `consumeSSE` returns silently on
> `[DONE]`, so that case needs an explicit `settled` flag checked after the await
> (see `messaging.ts`). Losing this is silent and only shows up as a frozen UI.

Two frame families confirmed:
1. **Pilot family** (`{type:'status'|'result'|'error'}` + `data: [DONE]`): handbookPilot, analysisPilot, legalDefense, brokerPilot, compliancePilot — line-identical except URL/body/error handling.
2. **Raw-event family** (`\n` split, per-file event vocab): portalAskHr, laborClient, HelpAssistant, ER panels, studio pages, admin hooks, matcha-x build stream, `work/api/matchaWork/*` (FormData + early-return on `complete`/`error`).

Splitting on `\n` + filtering `data:` lines subsumes both → one parser.

New `api/sse.ts` (next to `client.ts`, builds on `authStreamHeaders`/`ApiError`):
- `consumeSSE(res, onFrame)` — buffers across chunk boundaries, skips malformed JSON, ends on stream end or `[DONE]`; `onFrame` returning `true` stops early (reader cancelled).
- `postSSE(path, body, onFrame, {signal, auth})` — JSON or FormData, auth default on, extracts `detail` from non-ok JSON.
- `streamPilotChat<TResult>(path, body, {onStatus,onResult,onError}, signal)` — standard pilot turn; aborted turns resolve quietly.

Migration:
- **B1** — 5 pilot api files: `api/handbook-pilot/handbookPilot.ts`, `api/analysis-pilot/analysisPilot.ts`, `api/legal-defense/legalDefense.ts`, `api/broker/brokerPilot.ts`, `api/admin/compliancePilot.ts`. Each `streamChat` shrinks ~55→~8 lines, public signatures unchanged (no console edits).
- **B2** — raw-event consumers → `postSSE`/`consumeSSE`: `api/portal/portalAskHr.ts` (also removes its direct localStorage token read), `api/labor/laborClient.ts`, `components/shared/HelpAssistant.tsx`, `components/er/{ERGuidancePanel,EROutcomePanel,ERSimilarCasesPanel}.tsx`, `pages/admin/studio/*`, `pages/admin/JurisdictionData.tsx`, `hooks/admin/{useEnrichStream,useResearchGaps}.ts`, `hooks/compliance/useComplianceCheck.ts`, `components/admin/onboarding/StatutoryFitPanel.tsx`, `components/admin/JurisdictionDetailPanel/helpers.ts`, `components/matcha-x/onboarding/useMatchaXBuildStream.ts`, `work/api/matchaWork/{candidates,messaging,research}.ts`. Anon streams (`hooks/ir/useIRAnalysisStream.ts`, `components/ir/IRCopilotPanel/useCopilotPanel.ts`) keep own fetch, call `consumeSSE` directly. `candidates.ts` keeps its timeout/FormData wrapper, early-stops via `return true`.

Behavior deltas (flag in PR): analysisPilot's `detail` extraction becomes shared default (better errors for other 4 pilots); fixes `HelpAssistant.tsx:45` latent bug (`decoder.decode` without `{stream:true}`, no cross-chunk buffer — frames split across network chunks are silently dropped); portalAskHr now returns on `[DONE]` (terminal server-side, safe).

Verify: tsc; one turn each in Handbook/Analysis/Broker Pilot, Legal Defense chat, portal Ask HR, help widget, ER outcome gen; abort via session-switch mid-stream.

## Phase C — `hooks/useAsync.ts` (hook + 15-file tranche; ~250 now, 1,500+ full rollout)

No shared async hook exists: 213 files carry the `try/catch/finally` + `setLoading`/`setError` triad, 287 combine `useState`+`useEffect`. A hand-rolled hook stays compatible with the house rule against React Query/SWR.

New `hooks/useAsync.ts` (~90 LOC):
- `useAsync<T>(fn, deps)` → `{data, loading, error, reload, setData}`. `reload()` refetches WITHOUT clearing data (matches prevailing pattern, no flash); out-of-order responses discarded via run counter; `fn` in a ref so inline closures are fine; `setData` exposed for optimistic updates; `error` is a string (`e.message`). Guarded params: `fn: () => id ? fetch(id) : Promise.resolve(null)`.
- `useAsyncAction<A,R>(fn)` → `{run, busy, error, reset}`; `run()` resolves `undefined` on failure (keeps the `const r = await run(); if (!r) return` shape).

Tranche rule: a file qualifies with the full quadruplet (data `useState`, `useState(true)` loading, fetch-in-`useEffect`, `.finally(() => setLoading(false))`). Enumerate: `grep -rln "finally(() => setLoading(false))" pages components | xargs grep -ln "useState(true)"`. Tranche 1 = top 15 by fetch-effect count, seeded with `pages/admin/Individuals.tsx`, `pages/admin/Companies.tsx`, `pages/broker/BrokerExternalClientDetail.tsx`, plus `PayerData`/`DealFlow`/`ServerErrors` (D2 touches them anyway — same diff, avoid double churn). Later tranches: opportunistic in files already being touched, plus dedicated ~15-file PRs; never mix a useAsync sweep with behavior changes.

Verify: tsc; each converted page renders, a filter change refetches, one mutation (token grant on Individuals) refreshes.

## Phase D — UI consolidation

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
