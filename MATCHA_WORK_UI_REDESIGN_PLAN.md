# Matcha-work thread UI + sidebar redesign

## Context

User finds the matcha-work web chat surface crowded/busy/ugly and the sidebar cluttered — wants elegant, simple, work-conducive. Root causes (verified by exploration):

- **ThreadHeader** (`client/src/work/pages/MatchaWorkThread/ThreadHeader.tsx`): one flat `flex-wrap` row holding 9 unrelated things — back, title, collaborators/Invite, task badge, mobile toggle, 9 rainbow mode pills, hand-rolled Agent pill (`#ce9178`), native model `<select>`, token counter, theme toggle.
- **Thread interior ignores the werk design tokens** (`w-*` in `client/src/index.css:38-46`): raw zinc + 9 saturated hues + VS Code palette collide. Theme forks live in `MatchaWorkThread/theme.ts` (`buildThreadTheme`, 15 class-string keys × project/light/dark).
- **MessageBubble** (`client/src/work/components/panels/MessageBubble.tsx`, 316L): 8 stacked bordered metadata sections per assistant bubble.
- **HuumeStepTimeline**: per-step colored bordered boxes, always expanded; rendered live (`ChatMessages.tsx:83`) + persisted (MessageBubble).
- **Duplicate confirm bars**: in-chat `HuumeActionCard.tsx` + `HuumePanel/ConfirmBar.tsx` can show simultaneously.
- **Sidebar** (`client/src/work/components/shell/WorkSidebar.tsx` + `WorkSidebar/`): TABS (localStorage MRU, `useOpenTabs.ts`) fully overlaps THREADS; every thread named "New Chat" forever (no auto-titling exists — `server/app/matcha/routes/matcha_work/threads.py:153` defaults it, only manual rename PATCH); Email nav row vs Inbox footer icon near-dupes; sections default collapsed each reload; sidebar mounted twice in `WorkLayout.tsx` (desktop `hidden md:flex` + mobile `md:hidden` both always in DOM → double fetches + two 60s inbox polls).

**User-approved decisions** (AskUserQuestion): (1) single Tools menu popover replaces pill row; (2) backend auto-title via one-shot flash-lite; (3) steps/metadata collapsed by default; (4) one Chats list sidebar.

## Key facts for implementation

- Tailwind v4, `@theme` in `client/src/index.css`; no tailwind.config.js. `w-*` tokens have NO light overrides; thread light mode is page-local `mw-chat-theme` localStorage boolean in `useThreadController.ts` (~line 489), NOT `html[data-theme]`.
- Popover template to clone: `client/src/work/components/shell/NotificationSettingsMenu.tsx` (ref + mousedown outside-close + `absolute right-0 top-full` panel, w-* styled).
- Flash-lite one-shot template: `server/app/matcha/services/matcha_work/task_summary_service.py` (self-contained client, `gemini-3.1-flash-lite`, never raises).
- `messaging.py`: `_maybe_compact` fire-and-forget via `_track_background_task(asyncio.create_task(...))` at line 203, after `complete` SSE frame. Huume dispatch early-returns at line ~168 — needs its own title dispatch before both `return`s.
- Title PATCH (`threads.py:846`) calls `doc_svc.sync_element_record(thread_id)` after update — auto-titler must too.
- Thread lists order `is_pinned DESC, updated_at DESC` already.
- Sidebar-refresh event precedent: `CHANNELS_CHANGED_EVENT` in `client/src/work/api/channels.ts:168`.
- `WerkLiteSidebar.tsx` self-contained — imports nothing from `WorkSidebar/`; safe to delete SidebarTabs/useOpenTabs/ThreadsSection.
- `constants.ts` consumers: `badgeClass` used by `MatchaWorkList.tsx:227` (keep); `onClass` only by ThreadHeader (delete); `MODEL_OPTIONS` also used by `ProjectView/ChatPane.tsx:107` (leave that select alone).
- New-thread creation pattern: `useMatchaWorkList.ts:72` `handleCreate` → `createThread()` (`work/api/matchaWork/threads.ts:21`).
- `hasFeature` from `useMe`; individuals (`isIndividual`) see no mode pills today — preserve (they still get model picker).

## Phases (sequencing: 5 → 3a/3b → 1 → 2 → 4 → 5c)

### Phase 1 — ToolsMenu + header slim-down

**`constants.ts`**: add `desc: string` per mode row (one-liner from tipOn); delete `onClass` after ThreadHeader stops using it. Keep `tipOn/tipOff/badgeClass`.

**New `client/src/work/pages/MatchaWorkThread/ToolsMenu.tsx`** (~150L), props `{c, isIndividual}`; clone NotificationSettingsMenu shell:
- Trigger: Huume on → Huume icon+"Huume"; one mode on → that mode; N>1 → "N tools"; none → "Tools". Active: `text-w-accent border-w-accent/40 bg-w-accent/10`; else `text-w-dim border-w-line`.
- Popover `w-72 rounded-lg border-w-line bg-w-surface shadow-xl z-50 max-h-[70vh] overflow-y-auto`: mode rows (feature-filtered, icon + label + desc `text-[11px] text-w-faint` + toggle switch, `handleModeToggle(m.key)`, disabled while `togglingMode`); Huume-on dims others (copy comment block from ThreadHeader:94-100). `!isIndividual` guard around mode list. Agent row own section (replaces hardcoded `#ce9178` pill). Model picker footer (radio rows over `MODEL_OPTIONS`, same `setSelectedModel` + localStorage). Outside-mousedown + Escape close; do NOT close on toggle.

**`ThreadHeader.tsx` rewrite** (~173→~110L): row = back / title+pencil (unchanged handlers) / quiet task badge (`text-[11px] text-w-faint`) / ThreadCollaborators / mobile Chat|Panel toggle (tokens, kill `#ce9178` inline styles) / `<ToolsMenu/>` / HeaderOverflow "⋯" (small local popover: token usage via `formatTokens`, light/dark toggle). Delete pill map, Agent pill, `<select>`, inline counter, standalone theme button. Note: pills were `hidden sm:` — ToolsMenu now visible on phones (test 360px).

### Phase 2 — Density

**`HuumeStepTimeline.tsx`**: add `live?: boolean` prop + `open` state (default false).
- Collapsed persisted: one row `Bot` icon + "N steps" + chevron, `text-[11px] text-w-dim`, no box.
- Collapsed live: "Step k/N · <latest label>" with `animate-pulse`, click to expand mid-stream.
- Expanded: delete `statusColor` filled boxes → status color on icon only (emerald/amber/red/`text-w-faint`), labels `text-w-dim`, single `border-l border-w-line pl-2` rail. Keep per-row payload expand + `PayloadBlock` unchanged. `ChatMessages.tsx:83` passes `live`.

**`MessageBubble.tsx`**: stays inline — markdown, huume_event strip, byline, Add-to-Project. Folds behind one disclosure (`detailsOpen`, default false): ComplianceReasoningPanel, affected employees, policy gaps, enforcement risk, federal thresholds, payer staff, payer sources, CitationSources, HuumeStepTimeline. Summary row only when parts exist: `text-[11px]` chevron + `citations n · steps n · policy gaps n …` (hoist policy-gap `filtered` computation out of JSX IIFE to share the count). Plain messages: zero change. Don't restructure folded sections' internals.

**Confirm dedupe**: keep `HuumeActionCard` (chat-adjacent, mobile-visible, confirm is literally a chat turn); delete `HuumePanel/ConfirmBar.tsx` + its `idOf`. In `HuumePanel/index.tsx:234` replace with passive footer "Awaiting your confirmation in chat · <bannerLabel>" (`text-[11px] text-w-dim border-t border-w-line`). Restyle HuumeActionCard: `bg-w-surface border-w-accent/30`, Confirm `bg-w-accent hover:bg-w-accent-hi`. Send mechanism (literal 'confirm'/'cancel' via handleSend) untouched. Update stale pointer comments in `HuumeActionCard.tsx:20-22`, `utils/huumeActionMeta.tsx:7,21`.

### Phase 3 — Tokens

**`index.css`**: add class-scoped light override:
```css
.mw-light {
  --color-w-bg:#f7f7f8; --color-w-surface:#fff; --color-w-surface2:#f1f1f3;
  --color-w-line:#e4e4e7; --color-w-text:#18181b; --color-w-dim:#71717a; --color-w-faint:#a1a1aa;
}
```
Apply `.mw-light` on chat-pane root in `MatchaWorkThread.tsx:90` when `lm`.

**`theme.ts`**: delete project branch entirely (VS Code palette dies; project identity carried by task badge + ProjectPanel + Add-to-Project). KEEP forced-dark rule `lm = isProject ? false : lightMode` (`MatchaWorkThread.tsx:65`). Most keys become static `w-*` strings; only `prose`/`prose-invert` (+ maybe textarea ring) keep `lm` fork. If ≤5 keys remain, inline + delete file (judgment call; prefer keeping file if MessageBubble/ChatComposer churn grows).

**Sweep raw palette** (mechanical class swaps only): `MatchaWorkThread.tsx`, `ChatMessages.tsx`, `ChatComposer.tsx`, `JurisdictionBar.tsx`, `SkillGrid.tsx`, MessageBubble shells (user `bg-w-surface2 text-w-text`, assistant `bg-w-surface border-w-line`). Accent policy: `w-accent` orange only accent in chrome; emerald/amber/red survive only as semantic status inside folded sections.

### Phase 4 — Sidebar

- **Delete** `WorkSidebar/SidebarTabs.tsx`, `WorkSidebar/useOpenTabs.ts`; drop `OpenTab`/`MAX_OPEN_TABS` from `types.ts`.
- **`ThreadsSection.tsx` → `ChatsSection.tsx`**: header "Chats" + right-aligned `Plus` (New chat). Flat recent-first list (backend order already right), drop mine/Shared split → `Users` icon suffix when `collaborator_count>0`. `slice(0,20)` + "Show all" row → `navigate(base)`. Rows become `<Link to={`${base}/${t.id}`}>` (middle-click works); keep rename pencil + `RenameInput`.
- **New chat in `WorkSidebar.tsx`**: clone `useMatchaWorkList.ts:72` mapping — `createThread()` → prepend to threads state → `navigate(`${base}/${res.id}`)`.
- **Section state**: new `WorkSidebar/useSectionState.ts` (~25L) — one localStorage key `mw-sidebar-sections:${base}`, default ALL OPEN; replaces three `useState(false)`. Update `CollapsedRail.tsx` props. Filter keeps force-open behavior.
- **Footer/chrome**: Email → 4th footer icon (`MailOpen`) beside Inbox/People/Billing; delete Email nav row (WorkSidebar.tsx:216-226). Drop 2-letter brand chip (167-169). Type scale sweep: rows `text-[13px]`, section headers `text-[11px] uppercase tracking-wider text-w-faint`, meta `text-[10px]`.
- **Double mount fix** (`WorkLayout.tsx:239-256`): mobile drawer renders `{mobileMenuOpen && <SidebarComp …/>}` inside kept CSS-transitioned wrapper (fresh mount on open acceptable; transform transition still animates). Desktop unchanged. Do NOT lift useSidebarData into WorkLayout (werk-lite has different data contract). WerkLiteSidebar untouched.

### Phase 5 — Backend auto-title

**New `server/app/matcha/services/matcha_work/thread_title_service.py`** (~90L), modeled on `task_summary_service.py` (cite it in docstring): `FLASH_LITE_MODEL = "gemini-3.1-flash-lite"`, lazy `_get_client()`.

`async def maybe_autotitle_thread(thread_id: UUID) -> None` — fire-and-forget, never raises:
1. Fetch title; return unless `== "New Chat"` (user rename wins).
2. First user + assistant messages (`ORDER BY created_at ASC LIMIT 4`), truncate ~1500 chars each.
3. Module-level pure helpers `_build_title_prompt(...)` (3-6 word noun phrase, no quotes/punctuation, Title Case) + `_clean_title(raw)` (strip quotes/markdown/newlines, cap 80, empty→None) — for tests.
4. `generate_content(temperature=0.2, max_output_tokens=30)`, try/except → `logger.warning`.
5. Guarded write: `UPDATE mw_threads SET title=$1, updated_at=NOW() WHERE id=$2 AND title='New Chat'` (concurrent rename wins). If row hit → `doc_svc.sync_element_record(thread_id)` (lazy import, mirror threads.py:872).

Runs post-turn on request-path event loop — pool fine, no worker caveats.

**Trigger in `messaging.py`**: small local helper dispatched via `_track_background_task(asyncio.create_task(...))`:
- next to `_maybe_compact` at line 203 (after complete frame),
- AND before both Huume/hard-stop early `return`s (~lines 163, 168) — Huume-first threads otherwise stay "New Chat".
- Guard: first exchange (pre-turn history empty) + `thread["title"] == "New Chat"`. Verify exact variable holding pre-turn count in `turn_pipeline.py`/`messaging.py` at implementation (`tc.msg_dicts` includes current turn; the pre-turn `messages` fetch is in the pipeline — check).
- `create_thread(initial_message=…)` path: no FE caller uses it; note in docstring, skip.

**FE pickup**:
- `work/api/matchaWork/threads.ts`: add `THREADS_CHANGED_EVENT` + `notifyThreadsChanged()` (mirror channels.ts:168).
- `useThreadController.ts` `handleSend` onComplete (~line 199): if `thread?.title === 'New Chat'`, `setTimeout` 2.5s (+one retry at 4s): `getThread(threadId)` → update local title + `notifyThreadsChanged()`. Timer in ref, cleared on unmount/thread-switch (existing `useEffect[threadId]` cleanup ~line 157).
- `useSidebarData.ts`: listen `THREADS_CHANGED_EVENT` → refetch `listThreads('active')` (clone CHANNELS_CHANGED_EVENT block, lines 40-46).

**Tests — new `server/tests/matcha_work/test_thread_autotitle.py`** (normal imports, patch defining module per server/CLAUDE.md):
- `_clean_title` cases (quotes, newlines, empty, overlong); `_build_title_prompt` includes both messages + truncation.
- Guard: stub conn returns renamed title → no Gemini call, no UPDATE.
- Gemini raises → returns without raising, no UPDATE.
- Success: UPDATE SQL carries `AND title='New Chat'`; `sync_element_record` called.

## Risks

- Mobile: ToolsMenu newly visible on phones — `max-h-[70vh] overflow-y-auto`, right-anchor inside `relative`; test 360px. Mobile Chat/Panel toggle must survive header rewrite.
- Project threads deliberately lose VS Code palette; forced-dark rule must survive; `isProjectThread` prop stays (gates Add-to-Project + forced dark), only palette branches die.
- Light mode: `.mw-light` covers only `w-*` utilities — visual pass needed for missed raw zinc; `prose`/`prose-invert` stays lm-forked.
- Confirm dedupe: HuumePanel plan approve/execute buttons are separate REST routes — untouched; only staged-action confirm consolidates.
- Auto-title races: guarded UPDATE handles rename + double-dispatch idempotency.
- Werk-lite: verify `/werk-lite` renders after WorkLayout conditional-mount change.

## Verification

1. `cd client && npx tsc -p tsconfig.app.json --noEmit` (bare `tsc --noEmit` checks nothing).
2. `cd server && ./venv/bin/python -m pytest tests/matcha_work/ -q` — baseline 6 pre-existing `test_blog_pdf_export.py` failures; new autotitle tests pass; no new failures.
3. Manual via dev-remote (already running :5174 — do NOT pkill vite by pattern):
   - New chat from sidebar → first message → title appears ~5s in header + sidebar; manual rename wins.
   - ToolsMenu: toggle each mode + model; Huume-on dims others.
   - Huume turn: live single-line shimmer → expand mid-stream → persisted "N steps"; confirm via chat strip only; panel shows passive footer.
   - Compliance answer: folded summary row → expand shows all sections.
   - Light/dark via ⋯ menu; project thread stays dark.
   - Mobile 360px: drawer fresh-mounts, ToolsMenu fits.
   - `/werk-lite` unchanged; network tab: one set of sidebar fetches, one inbox poll.
