# Espresso on the web — rename `/werk` → `/espresso`, then close the desktop parity gap

Companion to `docs/ESPRESSO_WEB_PARITY.md` (the feature inventory). This file is
the execution plan: phase order, exact files, exact endpoints, test cases.

Written to be handed to another model for implementation. Each phase is one PR.

## Verified facts (checked 2026-09-25 — do not re-derive)

| Claim | How it was verified |
|---|---|
| The whole gap is **frontend-only** — no migration, no new table, no new endpoint | `scripts/alembic_graph.py pending <prod heads>` returned empty against the 15 live prod heads read via `scripts/ops-health/prod-query.sh alembic`. `mw_journals`, `mw_journal_folders`, `mw_productivity_boards`, `mw_productivity_cards`, `mw_element_repo_files`, `mw_ticket_drafts` all exist in prod and dev. |
| The backend never emits a `/werk` URL | `grep -rn '/werk' server/app` returns only `/werk-lite` and `/work` (`ems/urgent_notify.py:113`, `huume/record_view.py:56`). The rename touches no Python. |
| Personal (`role='individual'`) users already reach journals + productivity | `require_feature('matcha_work')` special-cases `role == 'individual'` at `server/app/matcha/dependencies.py:432-434`; `require_admin_or_client = require_roles("admin", "client", "individual")` at `dependencies.py:15`. |
| Journals + productivity routers are NOT under `routes/matcha_work/` | They are `server/app/matcha/routes/work/journals.py` and `work/productivity.py`, mounted at `/api/matcha-work` in `routes/__init__.py:282-293`. |
| No edge/nginx change is needed | `grep -rn werk deploy/` is empty; the frontend is a SPA served by a catch-all. |
| `/werk` has zero route tests today | The only `werk` strings under `client/src/**/*.test.*` are `werk_lite` in `featureCatalog.test.ts` and a comment in `systemContent.test.tsx`. |

## Naming

`/werk` (personal) → `/espresso`. `/work` (business) and `/werk-lite` (standalone
business work-chat, own login) are **unchanged** — `werk-lite` is a different
product with its own login route and auth guard, not a surface of this one.

Note the name is now overloaded three ways and that is intentional except for the
third: **Espresso** the macOS app, **Espresso** the web personal surface, and
`@espresso` the repo-question project agent (`services/matcha_work/project_agent/`,
a business-project feature). Do not rename the agent in these PRs; just be aware
that "Espresso" in `server/app/werk/routes/channels_ws.py` means the bot.

## Phase order, and why

The parity doc lists features by size. That order is wrong to execute in, because
**entitlements is load-bearing for most of the list**. Server-side,
`entitlements_service.py` already gates journal kinds, collab projects, Go Live,
email AI and paid channels on a free/lite/pro/business ladder. The web client
today knows only one boolean:

```ts
// client/src/work/components/shell/WorkSidebar/useSidebarData.ts:35-38
getMWSubscription().then((s) => setPlusActive(
  !!s.active && s.pack_id === 'matcha_work_personal'
))
```

So any feature built before entitlements lands has to be re-gated afterwards.
Order:

| Phase | PR | Depends on |
|---|---|---|
| 0 | Rename `/werk` → `/espresso` | — |
| 1 | Entitlements + paywall | 0 |
| 2 | Journals (folders, editor, collaborators) | 1 |
| 3 | Productivity (boards + calendar) | 1 |
| 4 | Home dashboard + Find palette + Stars | 1 |
| 5 | Settings / profile / themes | 1 |
| 6 | Email AI | 1 |
| 7 | Task viewer depth | 1 |
| 8 | Elements + Props | 1 |
| 9 | Broadcast + Replay | 1 |
| 10 | Screenplay | 2 |

Phases 2–10 are independent of each other and can be parallelised across models
once 1 is merged. Phase 10 needs Phase 2's journal shell.

---

# Phase 0 — rename `/werk` → `/espresso`

Mechanical, no behavior change, no new UI. Ship it alone so the diff stays
reviewable and the later phases branch off a settled base path.

## Route + surface

`client/src/work/routes/WorkSurfaceContext.ts` — rename the surface value:

```ts
export type WorkSurface = 'matcha-work' | 'espresso' | 'werk-lite' | 'matcha-ops'

export function useWorkBrand(): 'Espresso' | 'Matcha-Work' | 'Werk Lite' | 'Matcha Ops' {
  const surface = useWorkSurface()
  if (surface === 'espresso') return 'Espresso'
  if (surface === 'werk-lite') return 'Werk Lite'
  if (surface === 'matcha-ops') return 'Matcha Ops'
  return 'Matcha-Work'
}

export function useWorkBase(): '/espresso' | '/work' | '/werk-lite' | '/ops' {
  const surface = useWorkSurface()
  if (surface === 'espresso') return '/espresso'
  if (surface === 'werk-lite') return '/werk-lite'
  if (surface === 'matcha-ops') return '/ops'
  return '/work'
}
```

`git mv client/src/work/routes/WerkRoutes.tsx client/src/work/routes/EspressoRoutes.tsx`
and pass `surface="espresso"`.

`client/src/App.tsx` — rename the lazy import (`:15`) and the route (`:277`):

```tsx
const EspressoRoutes = lazy(() => import("./work/routes/EspressoRoutes"));
...
<Route path="/espresso/*" element={<EspressoRoutes />} />
```

## Identity bounce

`client/src/work/layout/WorkLayout.tsx:278-288`. The prefix-strip regex is already
length-agnostic — extend the alternation and the two surface checks:

```tsx
const tail = pathname.replace(/^\/(?:work|espresso)(?=\/|$)/, '')
if (surface === 'matcha-work' && isPersonal) {
  return <Navigate to={`/espresso${tail}${search}`} replace />
}
if (surface === 'espresso' && !isPersonal) {
  return <Navigate to={`/work${tail}${search}`} replace />
}
```

Keep the comment at `:280` accurate — it currently explains why the old
`slice(5)` was replaced, and `/espresso` is exactly the "base of another length"
it warns about. Update it to say so instead of deleting it.

## Hardcoded navigations

Eight sites, all `'/werk'` → `'/espresso'`:

| File:line | Context |
|---|---|
| `client/src/components/sidebars/ClientSidebar.tsx:106` | `personalNav` entry — also change `label: 'Werk'` → `'Espresso'` |
| `client/src/components/sidebars/ClientSidebar.tsx:196` | `logoTo={isPersonal ? '/werk' : '/app'}` |
| `client/src/layouts/AppLayout.tsx:49` | personal-user bounce out of `/app` |
| `client/src/pages/Login.tsx:21` | `roleRoutes.individual` |
| `client/src/pages/BetaRegister.tsx:51` | post-register navigate |
| `client/src/pages/portal/PortalLayout.tsx:49` | non-employee fallback |
| `client/src/work/pages/ChannelInviteLanding.tsx:46` | personal-surface base |
| `client/src/work/pages/ChannelInviteLanding.tsx:85` | `navigate(\`/werk/channels/${res.channel_id}\`)` |

## Stripe return URLs

`client/src/work/api/matchaWork/billing.ts:19-20` — these are sent to Stripe as
`success_url` / `cancel_url`, so a stale value lands the user on a 404 after
paying:

```ts
const successUrl = `${window.location.origin}/espresso?upgraded=1`
const cancelUrl = `${window.location.origin}/espresso?canceled=1`
```

## Legacy redirect

`/werk/*` must keep working — external links, Stripe receipts, and any bookmarked
path. Add to `client/src/App.tsx`, before the `/espresso` route:

```tsx
<Route path="/werk/*" element={<LegacyOpsRedirect fromPrefix="/werk" toPrefix="/espresso" />} />
```

`LegacyOpsRedirect` (`client/src/work/pages/LegacySurfaceRedirect.tsx:22`) already
does exactly this — prefix swap, query merge, hash preserved — so no new component.
Its name is now wrong for this use; rename it `LegacySurfacePrefixRedirect` and
update the two existing `/work` → `/ops` callers in `WorkRouteTree.tsx`.

## Comments and CSS

Comment-only `/werk` references to update so the tree stays greppable:
`WorkRouteTree.tsx:28`, `WorkRoutes.tsx:5`, `WerkLiteRoutes.tsx:55`,
`WorkSurfaceContext.ts:4`, `useSectionState.ts:10`, `useLiveKitCall.ts:6,29`,
`useChannelNotifications.ts:18`, `LegacySurfaceRedirect.tsx:19`,
`ChannelInviteLanding.tsx:17,20`, `useChannelView.ts:31,112`.

Leave the CSS tokens alone: `html[data-app-shell-bg="werk"]` and `.werk-radial`
(`client/src/index.css:84,91`) are internal class names, renaming them is churn
in a phase that should be behavior-free. Note it as a follow-up.

## Known cosmetic side effect

`useSectionState` keys its localStorage by base path
(`mw-sidebar-sections:${base}`, `useSectionState.ts:15`), so every existing
personal user's sidebar section state resets to the all-open default once. That
is acceptable; do not write a migration for it. Mention it in the PR body.

## Tests (new file — there are none today)

`client/src/work/routes/EspressoRoutes.test.tsx`:

1. `/espresso` renders the work shell with brand `Espresso` for `role='individual'`.
2. `/espresso/channels/:id` renders `ChannelView` (not the business `LegacyChannelRedirect` branch).
3. A `role='client'` user at `/espresso/inbox` is redirected to `/work/inbox` — tail and query preserved.
4. A `role='individual'` user at `/work/projects/abc?tab=chat` is redirected to `/espresso/projects/abc?tab=chat`.
5. `/werk/projects/abc?tab=chat` redirects to `/espresso/projects/abc?tab=chat`.
6. `useWorkBase()` returns `/espresso` under `surface="espresso"`.

Extend `client/src/work/pages/LegacySurfaceRedirect.test.tsx` with the
`/werk` → `/espresso` prefix case.

## Gates

```bash
cd client && npx tsc -p tsconfig.app.json --noEmit   # bare `npx tsc --noEmit` checks NOTHING
cd client && npx vitest run src/work
cd server && ./venv/bin/python -m pytest tests -q     # expected unaffected; run it anyway
```

Then grep for stragglers — `replace_all` misses inline template-literal variants:

```bash
grep -rn "/werk\b" client/src --include="*.ts*" | grep -v werk-lite
```

---

# Phase 1 — entitlements + paywall

The foundation every later phase gates on. Replaces the single `plusActive`
boolean with the real four-tier ladder the backend already resolves.

## Backend: already done, do not touch

`server/app/matcha/services/billing/entitlements_service.py` is the source of
truth. `GET /api/matcha-work/entitlements` returns:

```json
{
  "plan": "free" | "lite" | "pro" | "business",
  "features": {
    "threads_ai": true, "ai_model_pro": false,
    "projects_solo": false, "projects_collab": false,
    "journals_basic": true, "journals_full": false,
    "email_ai": false, "go_live": false,
    "paid_channels": false, "business_modes": false
  },
  "quotas": { "token_limit": 25000, "window_hours": 12,
              "used": 0, "remaining": 25000, "resets_at": "..." }
}
```

Shape source: `features_for_plan()` at `entitlements_service.py:176-192` and
`resolve_entitlements()` at `:195-223`. Plan ranks: free 0, lite 1, pro 2,
business 2 (`_PLAN_RANK`, `:61`). Personal SKUs: `matcha_work_lite` $9
(`LITE_PACK_ID`), `matcha_work_personal` $20 (`PRO_PACK_ID`, grandfathered Plus
subscribers land on Pro automatically).

`require_plan()` (`:226`) raises a **structured** 403 whose detail is
machine-readable specifically so the client can raise a paywall instead of
showing a bare error. Read that function and mirror its detail keys in the client
error handler — that contract is the whole point of this phase.

## Client work

New `client/src/work/api/matchaWork/entitlements.ts`:

```ts
export type WorkPlan = 'free' | 'lite' | 'pro' | 'business'
export interface WorkEntitlements {
  plan: WorkPlan
  features: Record<string, boolean>
  quotas: { token_limit: number; window_hours: number
            used?: number; remaining?: number; resets_at?: string | null }
}
export function getEntitlements() {
  return api.get<WorkEntitlements>('/matcha-work/entitlements')
}
```

New `client/src/work/hooks/useEntitlements.ts` — module-level cache (the value is
read on most screens), exposing `plan`, `can(feature)`, `atLeast(plan)`,
`quotas`, `refetch()`. Refetch on window focus and after a checkout return
(`?upgraded=1`), matching the 60s server-side plan cache
(`_PLAN_CACHE_TTL_SECONDS`, `entitlements_service.py:72`).

**Copy Espresso's two failure-mode rules exactly** — they are the difference
between a paywall and an outage:

- While entitlements are still `null` (first load), gates stay **open**. A slow
  entitlement read must never flash a paywall at a paying user.
- On a fetch **error**, keep the last-known plan rather than falling back to `free`.

Checkout is `POST /matcha-work/billing/checkout/personal`, already wrapped as
`startPersonalCheckout()` in `client/src/work/api/matchaWork/billing.ts:18` — whose
return URLs Phase 0 repointed at `/espresso`.

New `client/src/work/components/shared/PaywallModal.tsx` — port of
`platforms/desktop/Espresso/Espresso/Views/MatchaWork/PaywallSheet.swift` (208
lines). Takes the feature key and required plan from the 403 detail, shows the
tier comparison, and calls the existing checkout helpers in `billing.ts`.

Then delete `plusActive` from `useSidebarData.ts:26,35-39,86` and
`WorkSidebar.tsx:47,371`, and switch `SidebarFooter`'s upgrade CTA to the plan
from `useEntitlements`. `getMWSubscription()` stays — it is still the right call
for the billing page's subscription detail, just not for gating.

## Tests

`client/src/work/hooks/useEntitlements.test.ts`:

1. `can('journals_full')` is false on `plan='free'`, true on `'lite'`.
2. `atLeast('pro')` is true for `'business'` (equal rank, per `_PLAN_RANK`).
3. A structured 403 from a gated call opens the paywall with the right required plan.
4. The cache is shared across two hook consumers — one network call, not two.

---

# Phase 2 — Journals

Espresso source: `platforms/desktop/Espresso/Espresso/Views/Journals/*` (~5.3k Swift
lines, of which ~1.4k is Screenplay — deferred to Phase 10).

## Endpoints (all exist; `server/app/matcha/routes/work/journals.py`)

Every one is `Depends(require_admin_or_client)`, which admits `individual`
(`dependencies.py:15`), mounted at `/api/matcha-work` (`routes/__init__.py:282-287`).

| Method | Path | file:line | Body / params |
|---|---|---|---|
| GET | `/matcha-work/journals` | :80 | `?status` (default `"active"`) |
| POST | `/matcha-work/journals` | :89 | `{title, description?, color?, icon?, kind?, folder_id?}` |
| GET | `/matcha-work/journals/{id}` | :113 | — |
| PATCH | `/matcha-work/journals/{id}` | :124 | `{title?, description?, color?, icon?, kind?, folder_id?}` |
| DELETE | `/matcha-work/journals/{id}` | :138 | 204, archives |
| POST | `/matcha-work/journals/{id}/unarchive` | :149 | — |
| DELETE | `/matcha-work/journals/{id}/permanent` | :161 | 204 |
| GET | `/matcha-work/journal-folders` | :175 | — |
| POST | `/matcha-work/journal-folders` | :185 | `{name, parent_id?, color?}` |
| PATCH | `/matcha-work/journal-folders/{id}` | :202 | `{name?, parent_id?, color?}` |
| DELETE | `/matcha-work/journal-folders/{id}` | :219 | 204 |
| GET | `/matcha-work/journals/{id}/entries` | :236 | `?limit` (1–200, default 50), `?before` (datetime) |
| POST | `/matcha-work/journals/{id}/entries` | :248 | `{title?, content="", entry_date?}` |
| PATCH | `/matcha-work/journals/{id}/entries/{entry_id}` | :266 | `{title?, content?, entry_date?}` — **the markdown save** |
| DELETE | `/matcha-work/journals/{id}/entries/{entry_id}` | :281 | 204 |
| POST | `/matcha-work/journals/{id}/images` | :296 | multipart `file`, `image/*`, ≤10 MB → `{url}` |
| GET | `/matcha-work/journals/{id}/collaborators` | :323 | — |
| POST | `/matcha-work/journals/{id}/collaborators` | :331 | `{user_ids: UUID[]}` → `{added}` |
| DELETE | `/matcha-work/journals/{id}/collaborators/{user_id}` | :347 | 204 |

Shapes (`services/matcha_work/journal_service.py`):

```ts
// _parse_journal, journal_service.py:134
interface Journal {
  id: string; title: string; description: string | null
  color: string | null; icon: string | null
  status: string; kind: JournalKind; folder_id: string | null
  created_by: string; owner_name: string | null
  created_at: string; updated_at: string
  entry_count: number; collaborator_count: number
  collaborator_role: string | null   // non-null ⇒ shared WITH me
  preview: string | null
}
// _parse_entry, journal_service.py:164
interface JournalEntry {
  id: string; journal_id: string; author_id: string
  title: string | null; content: string
  entry_date: string | null; created_at: string; updated_at: string
}
// _parse_folder, journal_service.py:689
interface JournalFolder {
  id: string; name: string; parent_id: string | null
  created_by: string; created_at: string; color: string | null
}
```

`kind` ∈ `note | blog | todo | novel | screenplay | journal`.

## Three hard invariants — get these wrong and you ship a bug

1. **`folder_id` omitted ≠ `folder_id: null`.** Omitted files the journal into the
   per-user default "Notes" notebook (`_ensure_default_folder`,
   `journal_service.py:286`); explicit `null` puts it at the hub root. The server
   distinguishes them via `model_fields_set`. A web client that serializes its
   whole model on every PATCH will silently unfile every journal it touches. Build
   the PATCH payload from a dirty-field set, not from the object.
2. **Premium kinds are gated on create only.** `novel | screenplay | blog` are
   `PREMIUM_JOURNAL_KINDS` (`entitlements_service.py:63`) and `POST /journals`
   enforces `require_plan(PLAN_LITE, "journals_full")` at `journals.py:98-99`.
   Read and update are ungated — a user who downgrades keeps editing what they
   made. Mirror that exactly; do not gate the editor.
3. **Journals are personal, not company-shared.** Visibility is own-or-collaborator
   (`list_journals`, `journal_service.py:210`). There is no RLS backing this up —
   `server/app/werk/CLAUDE.md` and the `werk-journal-isolation-no-rls` history
   record that folders and the activity feed were once company-scoped and leaked
   coworkers' notes. Never add a company filter or a company-scoped list here.

## Two things that do NOT exist server-side

- **No starred-journals endpoint.** Pinning exists only for projects
  (`projects.py:219`) and threads (`threads.py:884`). Espresso's journal/file
  stars are client-local (`FileStarStore`, `ChannelStarStore.swift`). Web should
  use `localStorage` per user id, same as Espresso does on disk — see Phase 4.
- **No "shared with me" endpoint.** `GET /journals` already unions own +
  collaborated; filter client-side on `collaborator_role !== null`.

## New web files

```
client/src/work/api/matchaWork/journals.ts        # all 19 calls + the 3 interfaces
client/src/work/pages/Journals.tsx                # route entry
client/src/work/pages/Journals/FolderTree.tsx     # pane 1 — folders, nesting, color
client/src/work/pages/Journals/JournalList.tsx    # pane 2 — list within folder
client/src/work/pages/Journals/JournalEditor.tsx  # pane 3 — markdown editor
client/src/work/pages/Journals/useJournals.ts     # data + dirty-field PATCH builder
client/src/work/pages/Journals/CollaboratorsModal.tsx
```

Route in `WorkRouteTree.tsx`, above the `:threadId` catch-all:

```tsx
<Route path="journals" element={<Journals />} />
<Route path="journals/:journalId" element={<Journals />} />
```

Follow `client/src/work/pages/ProjectView/` for the three-pane shape
(`ProjectSidebar` + `WorkspacePanel` + `ChatPane` is already this layout) rather
than inventing a new one.

Editor: debounce `PATCH …/entries/{entry_id}` at ~800ms plus flush on blur and on
route change. Image paste/drop → `POST …/images`, splice the returned `{url}` into
the markdown as `![](url)`.

Suggested libraries: CodeMirror 6 for the editor, `markdown-it` + `highlight.js` +
`mermaid` + MathJax for the preview (Espresso renders preview in a WebView, so the
web version is the simpler surface here, not the harder one).

## Espresso behavior to port — and three bugs not to copy

Port: folder tree with nesting and per-folder color, slash menu, smart lists, Tab
outlining, collaborators sheet.

**Do not copy these — they are Espresso bugs, fix them on web:**

1. Editing a screenplay **loses dual dialogue** (relevant in Phase 10).
2. The "shot" element type is unreachable in the editor.
3. The workspace's "new journal" menu **does not block premium kinds** — only the
   server does, so the desktop user gets a 403 after choosing. Gate the menu
   client-side from `useEntitlements` *and* keep handling the 403.

**Keyboard clash:** the Espresso editor binds ⌘1–3 (headings) and ⇧⌘T (to-do),
all of which browsers reserve. Pick non-conflicting bindings and document them in
the editor's help affordance rather than fighting the browser.

Dead Swift code, do not port: `NewJournalSheet`, the sidebar `JournalListView`
struct, and the drag-drop image upload handler (all unreferenced).

## Tests

`client/src/work/pages/Journals/useJournals.test.ts`:

1. Renaming a journal PATCHes `{title}` only — `folder_id` is absent from the body.
2. Moving to the hub root PATCHes an explicit `{folder_id: null}`.
3. `kind='screenplay'` create on `plan='free'` opens the paywall and fires no POST.
4. An existing premium journal stays editable on `plan='free'` (no gate on PATCH).
5. "Shared with me" lists exactly the rows with `collaborator_role !== null`.
6. Two edits inside the debounce window issue one PATCH; a route change flushes immediately.

---

# Phase 3 — Productivity (boards + calendar)

Espresso source: `Views/Productivity/ProductivityWorkspace.swift` (~825 lines).

## Endpoints (`server/app/matcha/routes/work/productivity.py`)

All `require_admin_or_client`, all **user-scoped** by `current_user.id` — company
is stored opportunistically and never required, which is why personal users work.

| Method | Path | file:line | Body |
|---|---|---|---|
| GET | `/matcha-work/productivity/boards` | :64 | — |
| POST | `/matcha-work/productivity/boards` | :69 | `{title}` |
| PATCH | `/matcha-work/productivity/boards/{board_id}` | :78 | `{title?, status?}` (`active\|archived`) |
| DELETE | `/matcha-work/productivity/boards/{board_id}` | :90 | 204 |
| GET | `/matcha-work/productivity/boards/{board_id}/cards` | :101 | — |
| POST | `/matcha-work/productivity/boards/{board_id}/cards` | :109 | `{title, notes?, board_column?, due_date?, source_journal_id?, source_excerpt?}` |
| PATCH | `/matcha-work/productivity/cards/{card_id}` | :126 | `{title?, notes?, board_column?, position?, due_date?}` |
| DELETE | `/matcha-work/productivity/cards/{card_id}` | :138 | 204 |
| POST | `/matcha-work/productivity/quick-todo` | :149 | `{title, due_date?, source_journal_id?, source_excerpt?}` → default board |

`Board` = `{id, title, is_default, status, created_at, updated_at}`
(`productivity_service.py:65`). `Card` = `{id, board_id, title, notes,
board_column, position, due_date, source_journal_id, source_excerpt, …}` (`:171`).
`board_column` ∈ `todo | in_progress | done`, enforced by a DB CHECK — send
nothing else or you get a 500 from the constraint.

## Notes

- **There is no calendar endpoint.** The month view is a pure client projection of
  `cards[].due_date`; drag-to-reschedule is `PATCH …/cards/{id}` with a new
  `due_date`. Do not go looking for one.
- `due_date` uses `exclude_unset` like journals' `folder_id`: omitted leaves it
  alone, explicit `null` **clears** it. Same dirty-field discipline as Phase 2.
- `POST /productivity/quick-todo` is the journal right-click path — pass
  `source_journal_id` + `source_excerpt` so the card links back.

## New web files

```
client/src/work/api/matchaWork/productivity.ts
client/src/work/pages/Productivity.tsx            # Board / Calendar toggle
client/src/work/pages/Productivity/BoardPane.tsx  # 3-column kanban
client/src/work/pages/Productivity/CalendarPane.tsx
client/src/work/pages/Productivity/useProductivity.ts
```

Reuse the existing drag mechanics in
`client/src/work/components/shell/ProjectKanbanBoard/` rather than adding a
second DnD implementation.

## Espresso behavior to port

Espresso source: `Views/Productivity/ProductivityWorkspace.swift` +
`ProductivityViewModel`. Reached from a sidebar row (user-scoped, not per-project).

Layout: collapsible boards rail (190–280px, per-column counts, `+`, context-menu
rename/delete, **the default board is undeletable**) beside a pane with an inline-
renameable title and a Board/Calendar segmented toggle.

- **Board**: three 280px columns (To Do / In Progress / Done). Column header
  carries icon + count + inline `+`. Card = done circle, title (struck through when
  done), due chip formatted `MMM d`, and a "From journal" backlink whose tooltip is
  `source_excerpt`.
- **Calendar**: `‹ month ›` + Today, an "Add a card on {day}…" bar, weekday row,
  and a 7×6 grid of 42 cells at 94px.

Calendar math, port verbatim:

```
offset    = (weekday(firstOfMonth) - firstWeekday + 7) % 7
gridStart = firstOfMonth - offset          // then 42 consecutive days
```

Weekday symbols rotate by `firstWeekday`; out-of-month cells dim, today is
bold/accent, the selected day gets an accent fill. Each cell shows at most 4 cards
then "+N more". Card colors: todo = accent, in_progress = orange, done = grey +
strikethrough. `cardsOn(day)` matches `due_date == "yyyy-MM-dd"` (POSIX locale)
sorted by `position` — use a fixed-format date key, not a locale-formatted one.

Interaction details: drag payload is the card id; card→column moves, card→day sets
or reschedules the date, and the target highlights. Add and rename commit on Enter
or blur, empty input is dropped, an unchanged rename skips the request. Moves and
date-sets are optimistic and reload cards on error; deletes remove locally. The
done toggle flips `done ↔ todo`. Boards are re-fetched after every card change to
refresh counts. A new board POSTs "New board", selects it, and opens rename mode.
Month, day, and mode are deliberately **not** persisted.

## Tests

1. A card dragged `todo → in_progress` PATCHes `{board_column, position}` and nothing else.
2. Dropping a card on a calendar day PATCHes `{due_date}` only.
3. Clearing a due date sends explicit `{due_date: null}`.
4. Calendar groups by local date — a card due `2026-01-01` does not land in December.
5. Quick-todo from a journal excerpt posts `source_journal_id` + `source_excerpt`.

---

# Phase 4 — Home dashboard, Find palette, Stars

Espresso: `Views/MatchaWork/HomeDashboardView.swift` (765), `App/DetailPanes.swift`
(683, holds the Cmd+F palette), `Services/ChannelStarStore.swift` (173).

## Endpoints (`server/app/matcha/routes/matcha_work/workspace.py`)

| Method | Path | file:line | Notes |
|---|---|---|---|
| GET | `/matcha-work/tasks/open` | :186 | flat list merging tasks **and** subtasks |
| GET | `/matcha-work/activity/recent` | :281 | ≤25, 14-day window |

`/tasks/open` is scoped to `assigned_to = current_user.id` and **deliberately not
by company** (`workspace.py:211-218`) — matcha-work has cross-tenant collaborators,
multi-company admins resolve to one default company, and personal users have no
company at all; a company filter loses assigned work in all three cases. Do not
add one client-side either.

Row shape: `{id, project_id, title, priority, status, due_date, progress_note,
assigned_to, created_by, updated_at, project_title, project_type, is_subtask}`.
Subtask rows add `parent_task_id` + `parent_title` and stub the task-only fields
(`priority: ""`, `status: "pending"`, `due_date: null`, `progress_note: null`) so
one decode shape covers both. Ordering is server-side: tasks first (priority
`critical > high > medium > low`, then `due_date NULLS LAST`, then `updated_at
DESC`), LIMIT 50; then subtasks by `updated_at DESC`, LIMIT 50. Render in the
order received.

`/activity/recent` is company-scoped and returns `[]` when there is no company —
so on `/espresso` it is usually empty. Shape: `{kind, ref_id, project_id, title,
project_type, updated_at}`, `kind` ∈ `project | task | thread | journal`. **The
journal CTE is scoped to `created_by = me` OR an active collaborator row**
(`workspace.py:346-356`) — projects/tasks/threads are company-shared, journals are
not. Do not "simplify" that asymmetry away.

Espresso's real models are `MWOpenTask` / `MWActivityItem` in
`Models/MatchaWork/ProjectModels.swift` — **not** `DashboardModels.swift`, which is
mostly unrelated. `TaskHistoryTimeline.swift` is dead code. Don't mine either.

## Find palette

No endpoint. Client-side match over already-loaded threads, channels, projects,
journals, and project files. Bind **Cmd+K** (web convention; Espresso uses Cmd+F
because Cmd+K is taken in a native app). New
`client/src/work/components/shell/FindPalette.tsx`, mounted in `WorkLayout`.

Espresso's implementation has two flaws worth fixing rather than porting:

1. It **reloads every list on each open, plus one file-list request per project** —
   an N+1 that fires on a keystroke. On web, search what is already in the sidebar
   caches and fetch files only for the project already open.
2. Matching is a case-insensitive substring with **no ranking**. Rank at minimum by
   match position and entity recency, so the palette is useful past ~20 items.

## Stars

No endpoint — client-local. Espresso stores three `UserDefaults` keys:

```
mw-starred-channels:{userId}
mw-starred-journals:{userId}
mw-starred-files:{userId}
```

Keep those exact key names in `localStorage` so a future sync has one shape to
migrate. Note they are **already** user-id-scoped, which matters more on web where
two accounts share a browser profile. Wrap every read and write in try/catch —
private windows throw. Starred items surface as a pinned group at the top of the
sidebar.

Thread and project pins are **server-side** (`threads.py:884`, `projects.py:219`) —
don't reimplement those locally. Channel stars no longer gate notifications; don't
reintroduce that coupling.

Other Espresso state that is `UserDefaults`-only and needs a `localStorage`
equivalent as its feature lands: `kanban-lastseen`, `ticket-updates-viewed`,
broadcast collapse/quality, `review-wizard-seen`.

## Tests

1. Subtask rows render with the parent title and are not mistaken for tasks (`is_subtask`).
2. Server ordering is preserved — no client re-sort.
3. Activity feed renders `[]` without error for a personal user with no company.
4. The palette matches on a substring across all five entity kinds.
5. Stars survive a reload and are scoped per user id.
6. A throwing `localStorage` degrades to "no stars", not a crash.

---

# Phase 5 — Settings, profile, themes

Espresso: `Views/SettingsView.swift` (359), `Views/Profile/ProfileSheet.swift`
(267), `App/AppState+Theme.swift` (138).

## Endpoints (`server/app/core/routes/auth/profile.py`, mounted at `/api/auth`)

| Method | Path | file:line | Body |
|---|---|---|---|
| GET | `/auth/me` | :61 | — (already consumed by `useMe`) |
| POST | `/auth/avatar` | :465 | multipart `file` — `image/jpeg\|png\|webp` only, ≤5 MB |
| PUT | `/auth/profile` | :499 | `{name?, phone?}` |
| POST | `/auth/work-onboarded` | :547 | — |

`POST /auth/avatar` also refreshes the live channels-WS `manager.users[id].avatar_url`
so messages sent after the upload carry the new avatar without a reconnect. After
it returns, refetch `useMe` so the sidebar updates too.

`PUT /auth/profile` is role-dispatched: `admin` → `admins.name` (**`phone` is
ignored**), `client` → `clients.{name,phone}`, `candidate` → `candidates.{name,phone}`.
There is no branch for `individual` — verify what a personal user's PUT actually
writes before building the form, and if it writes nothing, say so in the PR rather
than shipping a field that silently discards input.

## Notification preferences do not exist

Confirmed absent codebase-wide: no per-type mute, no digest or frequency setting,
no email-notification toggle. What exists is only read/clear
(`server/app/matcha/routes/work/notifications.py`): list (`:61`), unread-count
(`:94`), project-unread-counts (`:104`), mark-read-by (`:114`), mark-read (`:135`),
mark-all-read (`:145`). **Do not add preference endpoints in this phase** — that
is a product decision with a backend cost, not parity work. Ship the settings page
without the toggles and note the gap.

Espresso's Settings is reachable **only** from the ⌘, menu-bar Settings scene,
which has no web analogue — give it a real route (`<base>/settings`) and a sidebar
footer entry. Its four notification `UserDefaults` keys have no server backing (see
above), so they are per-browser preferences at best; prefer omitting them over
shipping toggles that don't survive a device change.

## Themes

Espresso has five, stored in `UserDefaults` under `mw-theme` ∈
`platinum | dark | light | cappuchin | graphite`. Keep that key and those exact
values in `localStorage`. The Matcha accent is amber — `#D9770F` with `#B45309` as
the darker step.

`client/src/index.css` already has the `w-*` token set. Port by adding
`[data-theme="..."]` blocks over those tokens plus a picker. The repo convention
(per the `werk-theme-conventions` history) is that the two color files must stay in
sync and `themeOnAccent` is **computed, not hardcoded** — read that before adding
tokens.

## Tests

1. A >5 MB avatar is rejected client-side before the request.
2. A non-image MIME type is rejected client-side.
3. A successful avatar upload refetches `useMe`.
4. Each theme applies its tokens and survives reload.
5. Settings renders with no notification toggles (guards against re-adding a dead control).

---

# Phase 6 — Email AI

Espresso: `Views/Email/EmailAIActions.swift` (423),
`Views/Email/EmailTicketWizard.swift` (574). Web already has
`client/src/work/pages/WorkEmail.tsx` for connect/fetch/read/send — this phase adds
only the AI layer on top.

## Endpoints (`server/app/matcha/routes/matcha_work/workspace.py`)

**Every AI action is Lite+** via `_require_email_ai` (`:108` →
`require_plan(PLAN_LITE, "email_ai")`). Fetch, read, and send stay free.

| Method | Path | file:line | Body | AI gate |
|---|---|---|---|---|
| POST | `/matcha-work/agent/email/summarize` | :551 | `{email_id}` → `{email_id, summary}` | yes |
| POST | `/matcha-work/agent/email/triage` | :568 | `{email_ids?}` → `{buckets}` | yes |
| POST | `/matcha-work/agent/email/draft` | :598 | `{email_id, instructions?}` | yes |
| POST | `/matcha-work/agent/email/snapshot` | :704 | `{email_ids (1–10), project_id, task_id}` | no |
| POST | `/matcha-work/agent/email/send` | :654 | `{to, subject, body, reply_to_id?, thread_id?, in_reply_to?, draft_id?}` | no |

Error contract, all of which need real UI — not a generic toast:

- `summarize`: an **empty** `summary` string means the model was unavailable. Show
  retry copy. The endpoint deliberately never 500s for this.
- `triage`: omitting `email_ids` triages the current unread list; `[]` returns
  `{buckets: []}`. Buckets are `needs_reply | action | fyi | newsletter`. **Nothing
  is labelled, archived, or marked read in Gmail** — this is in-app only, so don't
  imply otherwise in the copy.
- `draft`: **422** when the original sender has no repliable address (checked
  *before* the model call), **502** when AI drafting is unavailable. Returns
  `{draft_id, to, subject, body, thread_id, in_reply_to}` and saves a real Gmail
  draft in the original thread.
- `send`: **429** on `GmailSendRateLimited`, 400 on a CR/LF-carrying header. Pass
  `draft_id` when sending an AI draft so the server cleans it up.
- `_reply_subject` (`:134`) applies the `Re:` rule server-side and the response
  carries the subject actually saved — **render that, never re-derive it.**
- Gmail ids must fullmatch `[A-Za-z0-9_-]{1,128}` (`_is_message_id`, `:119-131`);
  anything else is a 400 because it would splice into the Gmail API path.

`snapshot` writes `email-<message id>.md` task files, which is what an `email`
AutoPR card reads (the sandbox never touches Gmail). Idempotent on filename;
unreadable messages come back in `skipped` as `{email_id, reason}` rather than
failing the call. `SNAPSHOT_MAX_EMAILS` is 10 and `GET /agent/email/status`
returns it as `snapshot_max_emails` — read it from there, don't hardcode.

Triage buckets live **in memory only** on Espresso — nothing is persisted, so a
reload loses them. That is fine to keep; just don't promise otherwise in the copy.

**OAuth is simpler on web.** Espresso opens the system browser via `NSWorkspace`
and then polls `/agent/email/status` every 2s up to 45 times, because a native app
can't receive the redirect. The web client is the redirect target, so use an
ordinary redirect and read status once on return — do not port the poll loop.

`EmailTicketWizard.swift` (574 lines) is the snapshot→card flow: pick emails, pick
project + task, call `snapshot`. Port it as a modal over the existing
`WorkEmail.tsx` list.

## Tests

1. Every AI action on `plan='free'` opens the paywall and fires no request.
2. An empty `summary` shows retry copy, not an error state.
3. A 422 from `draft` shows "can't reply to this sender", distinct from the 502 path.
4. `triage` with an empty selection renders an empty state without a request.
5. The rendered reply subject comes from the response, not from local `Re:` logic.
6. `snapshot` shows per-email `skipped` reasons alongside the successes.
7. Selecting 11 emails for snapshot is blocked client-side.

---

# Phase 7 — Task viewer depth

Espresso: `Views/.../TaskViewer/*` (~5.3k lines — the largest single area). Web
already has `ProjectKanbanBoard`; this adds rounds, review, agent-draft, and the
history/replay-adjacent views.

**Auth deps are mixed here.** `require_company_member` guards board reads and all
AutoPR endpoints; `require_admin_or_client` guards create/delete/draft. A `client`
token satisfies both, but `employee` and `individual` tokens do not behave the
same across the two sets — check the dep per endpoint, per the table.

## Endpoints (`routes/matcha_work/tasks.py` unless noted)

| Method | Path | file:line | Auth | Notes |
|---|---|---|---|---|
| GET | `…/projects/{id}/tasks` | :57 | company_member | `?done_scope=week\|all` (default `all`) |
| GET | `…/projects/{id}/tasks/done-count` | :45 | company_member | `{total, this_week}` |
| PATCH | `…/projects/{id}/tasks/{task_id}` | :180 | company_member | see body keys below |
| POST | `…/projects/{id}/tasks/{task_id}/approve` | :319 | admin_or_client + `_can_edit_project` | `{note?}`; 400 unless in review |
| POST | `…/projects/{id}/tasks/{task_id}/reject` | :286 | admin_or_client | `{note}` **required non-empty**; emails assignee |
| POST | `…/projects/{id}/tasks/{task_id}/rounds` | :614 | admin_or_client | `{suggested_fix_title (required), body?, attachment_ids?}` |
| POST | `…/projects/{id}/tasks/{task_id}/summarize` | :597 | admin_or_client | Flash Lite, ephemeral, never persisted |
| POST | `…/projects/{id}/tasks/ai-draft` | :345 | admin_or_client | `{prompt}`, no DB write |
| POST | `…/projects/{id}/tasks/agent-draft` | `project_agent_runs.py:29` | admin_or_client + `_can_edit_project` | `{prompt ≤12000}` → **202** `{run_id, status:"queued"}` |
| GET | `…/projects/{id}/tasks/agent-draft/{run_id}` | `project_agent_runs.py:140` | admin_or_client | poll; `Cache-Control: no-store` |
| GET/POST/PATCH/DELETE | `…/tasks/{task_id}/subtasks[/{id}]` | :493/:506/:530/:581 | company_member | checklist |
| GET/POST/DELETE | `…/tasks/{task_id}/files[/{id}]` | `task_files.py:23/46/58` | — | multipart attachments |

`POST …/tasks/agent-draft` returns **412** `{code: "repository_required"}` when the
project has no `github_repo`. Surface that as "connect a repo first", not a generic
failure. Poll the run at 2s; the GET is pinned to project + requester and that
pinning *is* the authorization (the full access check was dropped for the poll
loop), so do not widen it.

### PATCH body keys (`tasks.py:180-230`)

Pass-through: `title, description, priority, board_column, pipeline_column,
status, progress_note, contact_name, contact_company, contact_email, contact_phone,
outcome, loss_reason`. Validated:

- `pr_url` — must match `^https?://` or 400; `null`/`""` clears. Rejected rather
  than sanitized because the card renders it as a clickable link.
- `pr_number` — int.
- `autopr_model`, `autopr_effort`, `autopr_runtime_source` — `null`/`""` means
  "back to auto" and clears the column; a non-string is 400.

Drag-drop sets `board_column`; the checkbox sets `status`.

### Subtask PATCH has a side effect worth knowing

`{reason, is_done: false}` logs a `subtask_rejected` audit event (severity in
metadata) **and** overturns any accepted commit→subtask completion for that
subtask (`cs_svc.dismiss_accepted_for_subtask`, `tasks.py:572-578`) so the card
stops crediting that commit and the same commit won't re-auto-check it. A plain
uncheck does neither. The UI must distinguish "uncheck" from "reject with reason".

### Done-column scoping — do not "fix" the default

`done_scope=all` (the default) returns the most-recently-finished capped at
`DONE_MAX_ROWS`; `week` returns only this Pacific week. The default is `all`
*specifically because* the web board sends no scope and has no "show earlier"
expander, so it keeps a cumulative Done column. The desktop board opens on `week`
and re-requests `all` on expand — that is why `/tasks/done-count` exists, to label
the expander. If you add an expander to web, send the scope explicitly; until
then, leave the default alone.

### "Outreach" is AutoPR staged actions, not a task feature

All in `task_history.py`, all `require_company_member`: staged-actions list
(`:417`), create (`:439`, AutoPR service account + board `outreach` grant),
send (`:481`, per-send human approval, re-checks the grant at `:519`, viewers 403
at `:516`), resolve (`:643`). A missing `outreach` grant is a **spend guard, not a
bug** (`:691`) — render it as "not enabled for this board". Also
`…/autopr/{reconsider,run-now,run-claim,unqueue,run-defer,context-request,
result-notification,pr-closed}` (`:251`–`:815`).

### Use the bundle for project open

`GET …/projects/{id}/bundle` (`projects.py:120`) → `{project, tasks, files,
folders, links, collaborators, elements, done_total}`. Each field comes from the
same service call as its individual endpoint, so decode and cache identically:
access is verified once and six reads run concurrently. Its `tasks` are
`done_scope=week` only — `done_total` carries the real count.

### `POST …/tasks/{id}/complete` does not exist

Completion is `PATCH …/tasks/{task_id}` with `status`/`board_column`.
`POST /matcha-work/projects/{project_id}/complete` (`projects.py:858`) is
project-level and **owner-only** (403 otherwise).

## Tests

1. Reject with an empty note is blocked client-side (the server requires non-empty).
2. Approve on a task not in review surfaces the 400 as "move it to review first".
3. A 412 from agent-draft renders the connect-a-repo prompt.
4. The agent-draft poll stops on terminal status and on unmount.
5. `pr_url` without a scheme is rejected before the request.
6. Clearing `autopr_model` sends `null`, not `""`.
7. Uncheck-with-reason and plain uncheck send different bodies.
8. Board open issues one `/bundle` call, not six.
9. A board without the `outreach` grant renders the not-enabled state, not an error.

---

# Phase 8 — Elements + Props

Espresso: `Views/MatchaWork/ProjectElementsView.swift` (897),
`Views/.../Props/PropsView.swift` (421).

Both live on the **collab-project tab strip** in Espresso
(`ProjectDetailView.swift:95` — collab projects only), which is
`chat 1 · kanban 2 (default) · props 3 · files 4 · media 5 · elements 6 · notes 7 ·
overview 8 · history 0`, icon-only below 760px. Web's `ProjectView` needs the same
two tabs added, gated to collab project types.

## Elements (`routes/matcha_work/elements.py`)

`require_admin_or_client`; mutations additionally need `_can_edit_project(role)`
→ 403.

| Method | Path | file:line | Body |
|---|---|---|---|
| GET | `…/projects/{id}/elements` | :45 | — |
| POST | `…/elements` | :53 | `{name (required), kind?, description?, assigned_to?, repo_paths?, repo_branch?}` |
| PATCH | `…/elements/{element_id}` | :99 | `{name?, kind?, description?, assigned_to?, repo_paths?, repo_branch?, order?}` |
| DELETE | `…/elements/{element_id}` | :171 | — |
| PUT | `…/elements/{element_id}/repo-snapshot` | :189 | `{files: [...]}` |
| GET | `…/elements/{element_id}/repo-snapshot/stats` | :206 | — |
| GET | `…/elements/{element_id}/files` | :225 | — |
| GET/POST | `…/elements/{element_id}/folders` | :239/:253 | `name` + `parent_id` are `Body(..., embed=True)` |
| GET/POST/DELETE | `…/elements/{element_id}/notes[/{note_id}]` | :277/:291/:321 | `{kind?: note\|link, body?, url?}` |

Two traps: **`element_id` is typed `str`, not UUID**, in every elements and github
handler — do not normalize or validate it as a UUID. And the list **excludes** the
hidden `kind='_repository_snapshot'` element (`elements.py:37`), so don't render a
phantom row if you ever read around the list endpoint.

## GitHub + commit suggestions (`routes/matcha_work/github.py`)

| Method | Path | file:line | Body |
|---|---|---|---|
| POST | `…/projects/{id}/commit-scan` | :27 | `{commits: dict[], branch?}` — client-supplied |
| GET | `…/projects/{id}/commit-suggestions` | :48 | `?task_id` — pending only |
| GET | `…/projects/{id}/tasks/{task_id}/commit-completions` | :58 | accepted completions |
| POST | `…/commit-suggestions/{id}/accept` | :70 | atomic claim; 404 if already resolved |
| POST | `…/commit-suggestions/{id}/dismiss` | :94 | — |
| GET | `…/projects/{id}/github/connection` | :119 | `{repo, branch, connected, default_repo, token_present}` |
| PUT | `…/projects/{id}/github/connection` | :135 | `{repo, branch?}`; empty `repo` disconnects + clears the snapshot |
| POST | `…/projects/{id}/github/sync` | :172 | `{repo?, ref?}` → `{repo, total_stored, elements[]}` |
| POST | `…/projects/{id}/github/scan-commits` | :224 | `{repo?, ref?, force?, limit?}` |
| POST | `…/projects/{id}/github/webhook/install` | :267 | 400 unless `GITHUB_WEBHOOK_URL` + `GITHUB_WEBHOOK_SECRET` |

Repo resolution precedence (`_resolve_github_repo`, `:110`): body override →
`project.github_repo` → `gh_svc.default_repo()`. Sync always maintains one hidden
complete-repository snapshot element (`ensure_repository_snapshot_element`) plus
optional per-element glob scopes. `scan-commits` watermarks
`mw_projects.github_last_scanned_sha`; `force` re-scans recent commits.

`accept` is an atomic claim — two clients racing means one gets a 404. Treat that
as "already handled by someone else" and refresh, not as an error.

**Espresso's local `git log` path has no web equivalent** — `POST /commit-scan`
takes client-supplied commits, which the desktop app gets by shelling out to git.
Web can only use the server-side `github/scan-commits`. Don't build a commit-scan
UI that has no way to produce input.

## Props / ticket-drafts (`routes/matcha_work/ticket_drafts.py`)

`require_admin_or_client` + `_verify_project_access`. Bodies are untyped
`dict = Body(...)`.

| Method | Path | file:line | Body |
|---|---|---|---|
| GET | `…/projects/{id}/ticket-drafts` | :21 | `?status` |
| POST | `…/ticket-drafts` | :31 | `{kind?: feat\|fix (default feat), title?, element_id?}` |
| GET/PATCH/DELETE | `…/ticket-drafts/{draft_id}` | :52/:65/:79 | arbitrary patch dict |
| GET/POST | `…/ticket-drafts/{draft_id}/messages` | :91/:101 | `{content}` required non-empty |
| POST | `…/ticket-drafts/{draft_id}/generate` | :121 | — → AI-filled draft |
| POST | `…/ticket-drafts/{draft_id}/promote` | :135 | `{…overrides}`; needs `_can_edit_project` → 403; 404 if already promoted |

`promote` returns the created **task** row and is one-shot — a second call 404s.

## Espresso behavior to port

**Props** (`Props/PropsView.swift`): a list (kind icon, title, element name,
Promoted badge; New Feat / New Fix buttons) that opens an in-place detail with a
header (back, kind, Promoted badge, "Pick code element" menu = *No grounding* plus
the repo-bound elements), the chat transcript, a draft panel (title persists on
Enter; Generate draft; **Promote disabled until there is a title**; `draft_subtasks`
read-only), and a 1–4-line input.

- The draft chat is **non-streaming and non-optimistic** — the POST returns both the
  user and assistant messages. Don't build an optimistic echo.
- Picking an element PATCHes `{element_id: id ?? ""}` — empty string, not null.
- Promote opens a review sheet seeded with `category = kind` and `column = todo`;
  priorities `critical|high|medium|low`; on confirm it promotes, reloads tasks, and
  flips status to `promoted`.

**Elements** (`ProjectElementsView.swift`): list = header + a GitHub bar
(connect / scan / sync / overflow) + element rows; detail = repository globs +
branch, one-level-deep Files & Folders, Notes & Links, and "Tickets about this". A
4-step wizard shows once while the list is empty.

- Globs parse on newline **or** comma; an empty branch clears it.
- Links get an `https://` prefix and pass an allowlist before being stored.
- Accept/dismiss of a commit suggestion is optimistic (the subtask ticks
  immediately); removes are optimistic too.
- Suggestions group by task; the kanban card badge counts **distinct pending
  subtasks**, not suggestions.
- `loadTasks` runs when a scan reported `scanned > 0`.
- Connecting a repo triggers an immediate sync.

**The GitHub auto-sync cooldown is load-bearing — port it exactly.** Both tabs call
an `autoSyncFromGitHubIfStale` that skips when a sync is already running, when
nothing is connected, or when the last sync was under 600s ago, and **stamps the
timestamp before awaiting** so two concurrent opens can't both fire. A manual scan
deliberately bypasses the cooldown with `force`. Without the stamp-before-await, a
tab switch double-syncs a whole repo.

Elements suggestion hooks also feed surfaces outside the tab, so those need wiring
in the same phase: the kanban card badge (`KanbanBoardView+Columns.swift:269`),
auto-scan on board open (`KanbanBoardView.swift:299`), task-viewer subtask chips
(`TaskViewerSheet+Sections.swift:215`), completions (`TaskViewerSheet.swift:389`),
and the collab Overview card (`CollabOverviewView.swift:219`).

macOS-only pieces needing web substitutes: `NSOpenPanel` and Finder drops → a file
input plus HTML5 drop; `NSItemProvider` drag → dnd-kit or HTML5 DnD; the preview
sheet → a modal; `@AppStorage` → `localStorage`. No local `git` or `FileManager`
use remains in Elements, so there is nothing unportable left.

## Tests

1. `element_id` round-trips as an opaque string (a non-UUID id works).
2. The repo-snapshot element never appears in the elements list UI.
3. Accepting an already-resolved suggestion (404) refreshes instead of erroring.
4. Clearing the repo field sends empty `repo` and reflects the disconnect.
5. `promote` navigates to the created task; a second promote is blocked.
6. Draft chat blocks an empty message client-side.

---

# Phase 9 — Broadcast + Replay

## Broadcast (`server/app/werk/routes/channel_broadcasts.py`)

All `Depends(get_current_user)` plus `_assert_call_access` (`:72` →
`load_channel_access` + `assert_channel_capability(ChannelCapability.CALL)`) —
**the same gate as channel calls, not a separate flag**.

| Method | Path | file:line | Notes |
|---|---|---|---|
| POST | `/channels/{id}/broadcast/start` | :219 | `{title?}`; **Pro-gated**, owner-only |
| POST | `/channels/{id}/broadcast/stop` | :349 | owner-only; 404 if none active |
| GET | `/channels/{id}/broadcast/token` | :396 | subscriber token; any **member** |
| POST | `/channels/{id}/broadcast/refresh-token` | :445 | — |
| POST | `/channels/{id}/broadcast/promote` | :509 | `{user_id}`; target must be a member |
| POST | `/channels/{id}/broadcast/demote` | :583 | `{user_id}` |
| GET | `/channels/{id}/broadcast` | :653 | status |

`start` calls `require_plan(PLAN_PRO, "go_live")` at `:232` — LiveKit is the most
expensive infra feature, so **watching stays free and only starting is gated**.
`start`/`stop`/`promote`/`demote` are owner-only (`_assert_owner`, `:66`).
503 with the LiveKit config error if `_get_lk_config()` raises.

Room name is `channel-{channel_id}` (`_livekit_room_name`, `:90`), sharing the
LiveKit webhook namespace with calls (`call-` prefix) — call and broadcast are
mutually exclusive per channel, so the UI must not offer both at once. Limits:
`BROADCAST_MAX_DURATION_SECONDS`, `BROADCAST_WEEKLY_LIMIT`,
`BROADCAST_TOKEN_TTL_SECONDS`; viewer TTL is clamped to `max(60, TTL - elapsed)`
and promote TTL to `max(30, MAX_DURATION - elapsed)`, and an auto-stop is
scheduled on start.

WS events the web client must handle (`_push_broadcast_event`):

```
broadcast.started            {channel_id, broadcast_id, started_by, started_at, title, max_duration_seconds}
broadcast.ended              {channel_id, broadcast_id}    // skipped if the LiveKit room_finished webhook already pushed it
broadcast.publisher_changed  {channel_id, user_id, can_publish}
broadcast.token_grant        {channel_id, token, livekit_url, can_publish}   // per-user, on promote
```

Status: inactive ⇒ `{active: false, max_duration_seconds, weekly_limit,
weekly_used, weekly_remaining}`; active ⇒ adds `{broadcast_id, started_at,
started_by, title, publisher_user_ids, elapsed_seconds}`. `publisher_user_ids`
comes from `list_participant_identities` and falls back to `[started_by]` on
failure — so treat a single-element list as possibly incomplete.

Web already has `client/src/work/hooks/useLiveKitCall.ts` and `livekit-client` as a
dependency; extend that rather than adding a second LiveKit client.

Note Espresso **never implements** `POST …/broadcast/refresh-token` even though the
endpoint exists — so a desktop broadcast dies at token expiry. Web should call it,
which means this phase is a small improvement over the desktop behavior, not a
straight port. `BroadcastPanelView.swift` (396 lines) is the UI reference.

## Replay (`routes/matcha_work/task_history.py`)

| Method | Path | file:line | Auth | Params |
|---|---|---|---|---|
| GET | `…/projects/{id}/history/replay` | :78 | company_member | `?week_start` (datetime, **required**) |
| GET | `…/projects/{id}/tasks/{task_id}/history` | :51 | company_member | — |
| GET | `…/projects/{id}/activity` | :876 | company_member | — |

`week_end` is always `week_start + 7 days`. **`week_start` is Monday 00:00 Pacific
and is computed client-side** — get the timezone right or the week is off by hours.

```ts
starting_state: { task_id, title, column, assignee_name, assignee_avatar_url }[]
events: { id, task_id, event_type, from_column, to_column,
          actor_id, actor_name, actor_avatar_url, title, created_at }[]
```

Invariants (`task_history.py:78-200`):

- Column-mutating events are exactly `created | column_change | review_rejected |
  review_approved` (+ `deleted`). Other events are still returned for flavor text
  and the replay engine ignores them.
- Grouping key is `COALESCE(h.task_id_text, h.task_id::text)` — `task_id_text`
  survives hard deletes, and rows with both null are excluded because they would
  collapse into one phantom card.
- `done` cards are deliberately **not** seeded into `starting_state` (`:163-171`):
  the Done column resets each week, and a card reopened out of Done mid-week
  materializes from its move event instead.

Two computations are client-side in Espresso and **must agree with the backend** —
they are the likeliest source of a web/desktop divergence:

- The replay fold (applying `events` onto `starting_state` to get each frame).
- Round derivation: `round_index = 1 + count(round_started events ≤ timestamp)`.
  There is no `round_index` column; per the `werk-round-index-derivation` history it
  is derived at read time, and the kickoff-attachment ordering is the known trap.

Pacific is hardcoded as the replay week timezone on Espresso. Match it explicitly
(`America/Los_Angeles`), don't use the viewer's local zone.

## Tests

1. A non-Pro user sees Go Live disabled with the paywall; watching still works.
2. A non-owner sees no stop/promote controls.
3. `broadcast.ended` arriving twice (WS + webhook) tears down once.
4. `broadcast.token_grant` promotes the local participant to publisher.
5. A channel with an active call does not offer Go Live.
6. `week_start` is Monday 00:00 Pacific for a viewer in a non-Pacific timezone.
7. Replay ignores non-column events and renders no phantom card for a deleted task.
8. Cards in Done at week start are absent from `starting_state` and appear on their move event.

---

# Phase 10 — Screenplay

Depends on Phase 2. Espresso source (~1.4k lines):
`Views/Journals/Screenplay.swift` (363), `ScreenplayEditorView.swift` (730),
`ScreenplayPaginator.swift` (197), `ScreenplayPDF.swift` (99).

No new endpoints — a screenplay is a journal with `kind='screenplay'`, its text
stored as Fountain in the single entry's `content`. Gated on create by
`journals_full` (Lite+), per Phase 2.

Three pieces to port:

1. **Element editor** — Final-Draft-style WYSIWYG where Tab/Return cycle element
   types (scene heading → action → character → dialogue → parenthetical). Espresso
   tracks the type in a `.spElement` text attribute; web needs an equivalent per
   block, and a contenteditable or a block-model editor rather than a textarea.
2. **US-Letter paginator** — `ScreenplayPaginator.swift` computes page breaks on
   industry line counts. Port the arithmetic verbatim; it is the part that must
   agree between surfaces or the page count differs between web and desktop.
3. **PDF** — Espresso uses Core Text, which has no web equivalent. Two options:
   client-side (`pdf-lib` or `jsPDF`, 12pt Courier) or a server endpoint reusing the
   existing WeasyPrint path (`routes/matcha_work/pdf_export.py`). **Prefer
   server-side** — it keeps one renderer for both surfaces, and root `CLAUDE.md`
   already notes WeasyPrint render is the dominant memory consumer in the backend
   container, so size it there deliberately rather than discovering the difference
   later. This is the one place in the whole plan that may need a new endpoint;
   call it out explicitly in the PR rather than slipping it in.

Per the `werk-screenplay-module` history, dual dialogue is sequential in v1 — keep
that simplification.

## Tests

1. Tab/Return cycles element types in the documented order.
2. Fountain round-trips: parse → edit → serialize is stable.
3. The paginator's page count matches a known fixture (shared with the Swift fixture if one exists).
4. PDF export produces a non-empty file with the expected page count.
5. Creating a screenplay on `plan='free'` opens the paywall.

---

---

# Explicitly out of scope

- **`SkillsView.swift`** (247 lines) — the parity doc lists it as "not inspected".
  It is a static help page of five skill cards plus a Tips section, and it is
  **unreachable**: the only thing that sets `showSkills = true` is `ThreadListView`,
  which is never instantiated. Don't port it; delete it from the parity doc's
  open-questions list.
- **Notification preference endpoints** — none exist (Phase 5). Adding them is a
  product decision with backend work, not parity.
- **Espresso's local `git log` commit scan** — web has no way to produce the input
  (Phase 8).
- **Web-only features Espresso lacks** (Ops/Events/Protocol/Inventory, Huume panel,
  Assets, thread side panels, channel tips/job-postings/analytics, work permissions,
  onboarding wizard). Those are the *other* direction of the gap and belong in a
  separate plan.

## The open question from the parity doc, answered

> `/werk` personal users are gated by feature flags on web but by entitlements on
> macOS — which should win?

**Entitlements win.** The server already enforces the entitlement ladder on every
gated path (`journals.py:98`, `projects.py:76-79`, `workspace.py:108`,
`channel_broadcasts.py:232`), so a feature-flag-only client gate is decorative:
it can hide a button but cannot stop a 403, and it cannot express the free/lite
tier split at all. Company feature flags stay meaningful for the **business**
surfaces (`/work`, `/ops`, `/werk-lite`) where a company admin provisions them.
That is why Phase 1 comes before everything else.

## Cross-cutting notes for every later phase

- **Never hardcode a base path in a shared page.** Use `useWorkBase()`. This is
  the rule that makes one tree serve four surfaces (`client/src/work/CLAUDE.md`).
- **Feature gating stays keyed on identity, not surface** — `isPersonal` /
  `role === 'individual'`, plus the Phase 1 entitlements. Surface drives only
  branding strings and nav base paths (`WorkSurfaceContext.ts:11-17`).
- **New top-level routes go before `<Route path=":threadId">`** in
  `WorkRouteTree.tsx:95`. React Router v6 ranks static above dynamic so it works
  either way, but keeping them above the catch-all keeps the file readable.
- **The sidebar's nav buttons are copy-pasted** — `WorkSidebar.tsx:230-308` has
  the same 8-line button repeated for Home / Events / Protocol / Inventory /
  Waste / Assets. Extract a `SidebarNavButton` in the first phase that adds an
  entry, rather than adding a seventh copy.
- **Multi-pane precedent**: `client/src/work/pages/ProjectView/` is already
  sidebar + `WorkspacePanel` + `ChatPane`. Journals' three-pane workspace should
  follow that shape, not invent a new one.
- Per-phase gates are the same three commands as Phase 0, plus
  `cd client && npx vitest run src/work` scoped to the new files.
