# Espresso vs Web — Parity

As of 2026-09-23.

Web Espresso = `client/src/work/*`, mounted at `/work` (business), `/werk` (personal), `/werk-lite` (business work-chat, own login).
Same backend as macOS (`server/app/matcha/routes/matcha_work/`, `/channels`, `/inbox`) + same `mw_*` tables.
Every endpoint Espresso calls already exists → closing gaps is frontend work.

## Have on both

| Feature | Web | Espresso |
|---|---|---|
| Threads (AI chat, files, PDF, modes, pins) | `pages/MatchaWorkThread/*` | `ThreadDetailView.swift` |
| Projects / workspaces (sections, files, collaborators, invites, discussion channel, presence) | `pages/ProjectView/*` | `ProjectDetailView*.swift` |
| Kanban + subtasks + AI draft | `components/shell/ProjectKanbanBoard/*` | `KanbanBoardView*.swift` |
| Recruiting pipeline / resume batch | `components/panels/RecruitingPipeline/*` | `RecruitingPipelineView.swift` |
| Channels (messages, members, invites, discover, paid) | `pages/ChannelView/*` | `Views/Channels/*` |
| Channel audio calls (LiveKit) | `hooks/useLiveKitCall.ts` | `CallService.swift` |
| Inbox / DMs | `pages/Inbox.tsx` | `Views/Inbox/*` |
| Notifications + presence | `components/shell/NotificationBell.tsx` | `NotificationsPopoverView.swift` |
| Gmail (connect, fetch, draft, send) | `pages/WorkEmail.tsx` | `Views/Email/*` |
| People / connections | `components/shell/ConnectionsPanel.tsx` | `Views/People/PeopleView.swift` |
| Billing / usage | `api/matchaWork/{billing,usage}.ts` | `UsageSummaryView.swift` |

## Missing on web (Espresso-only)

| Feature | Espresso source | Endpoints | Size |
|---|---|---|---|
| Journals (folders, starred/shared, markdown editor, slash menu, collaborators) | `Views/Journals/*` | `/matcha-work/journals/*`, `/journal-folders` | L |
| Screenplay (journal kind, local pagination + PDF) | `Screenplay*.swift` | journal endpoints | L |
| Productivity boards + calendar | `Views/Productivity/ProductivityWorkspace.swift` | `/matcha-work/productivity/*` | M |
| Props (repo-grounded draft chat → ticket) | `Props/PropsView.swift` | `/projects/{id}/ticket-drafts/*` | M |
| Elements / GitHub sync / commit suggestions | `ProjectElementsView.swift` | `/projects/{id}/elements`, `/github/*`, `/commit-suggestions` | M |
| Entitlements + paywall (free/lite/pro/business) | `PaywallSheet.swift` | `/matcha-work/entitlements` | M |
| Weekly replay / history | `Replay/*` | `/projects/{id}/history/replay` | M |
| Task viewer depth (rounds, graph, outreach, review, agent-draft) | `TaskViewer/*` | `/tasks/agent-draft`, `/done-count`, `/complete` | M |
| Broadcast (go-live, promote/demote) | `BroadcastPanelView.swift` | `/channels/{id}/broadcast/*` | M |
| Home dashboard (recent activity, open tasks) | `HomeDashboardView.swift` | `/activity/recent`, `/tasks/open` | S |
| Email AI (summarize, triage, snapshot→board, ticket wizard) | `EmailAIActions.swift`, `EmailTicketWizard.swift` | `/agent/email/{summarize,triage,snapshot}` | S–M |
| Find palette (threads/channels/projects/journals/files) | `DetailPanes.swift` | none | S |
| Stars (channels, journals) | `ChannelStarStore.swift` | none (local) | S |
| Themes (light/dark/cappuchin/platinum/graphite) | `AppState+Theme.swift` | none | S–M |
| Settings / profile (avatar, notification toggles) | `SettingsView.swift`, `ProfileSheet.swift` | `/auth/profile`, `/auth/avatar` | S |
| Project extras: media tab, links, folders, thread versions/revert/finalize, blog editor, discipline bar | various | exist | verify |

## Web-only (Espresso missing)

- Ops: Events, Protocol, Inventory (audit/forecast/buying/waste) — `pages/EventsHub.tsx`, `pages/Inventory*.tsx`
- Huume panel + Assets — `components/panels/HuumePanel/*`, `pages/AssetsHub.tsx`
- Thread side panels: presentation, language tutor, diagram editor, compliance reasoning
- Channel tips, job postings, analytics
- Work permissions + onboarding wizard

## Open / verify

- Project extras row: check each item against web ProjectView before scoping.

## Resolved (2026-09-25)

Execution plan: `docs/plans/ESPRESSO_WEB_PLAN.md` — phase order, endpoint tables, test cases.

- The whole gap is **frontend-only**. Prod has zero pending migrations and every
  backing table (`mw_journals`, `mw_journal_folders`, `mw_productivity_boards`,
  `mw_productivity_cards`, `mw_element_repo_files`, `mw_ticket_drafts`) is live.
  The one possible exception is a server-side screenplay PDF endpoint.
- **Entitlements win** over feature flags for personal users. The server already
  enforces the ladder (`journals.py:98`, `projects.py:76-79`, `workspace.py:108`,
  `channel_broadcasts.py:232`), so a flag-only client gate can hide a button but
  can't prevent a 403 or express the free/lite split. Company flags stay meaningful
  for the business surfaces. This is why entitlements is the first feature phase.
- `SkillsView.swift` is a static help page and is **unreachable** — the only setter
  of `showSkills` lives in `ThreadListView`, which is never instantiated. Not
  ported.
- `/werk` is being renamed `/espresso` (Phase 0 of the plan); `/werk-lite` is a
  separate product and is unaffected.
