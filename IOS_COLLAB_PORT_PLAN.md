# Port Espresso's collab project system to the iOS app (WerkiOS)

## Context

Espresso (macOS, `platforms/desktop/Espresso/Espresso/`) has the full matcha-work collab project system — projects, per-project chat, AI threads, kanban with a deep ticket viewer, files/media, notes. The iOS side of the same codebase (`WerkiOS` target in the same Xcode project) only has channels + DMs + calls, so a user who lives in a collab project on the Mac has no phone client for it.

Goal: make the iOS app essentially a copy of Espresso's collab system. The backend (`/api/matcha-work/*`) already serves both clients — **no backend work**. `platforms/ios/MatchaTutor` is a separate dormant XcodeGen app and stays untouched.

Scope decided with the user:
- **v1 panels**: Overview, Chat, AI Threads, Kanban + full ticket viewer (subtasks, rounds, review, discussion, history), Files, Media, Notes **read-only**.
- **Deferred**: Props, Elements panel, Replay, editable Notes.
- **Project types**: collab only — the iOS list filters `projectType == "collab"`; recruiting/blog/discipline/presentation stay Mac-only.
- **iOS tabs**: Home (assigned-to-me + active projects + recent activity), Projects, Channels, Messages.

The port is cheaper than it looks because ~11k lines of the macOS domain layer (all models, the whole `MatchaWorkService` family, `ProjectWebSocket`) are pure Foundation, and `WorkDetailVMStore` already carries `#if os(macOS)` fences around the project/thread VM caches — someone designed this seam already.

---

## Verified facts (checked against source, not assumed)

1. **WerkiOS does not compile today.** `Espresso/Services/UsageBeaconService.swift:2` has an unconditional `import AppKit` and line 41 calls `NSApplication.shared.isActive`. That file is in the WerkiOS sources phase (`Matcha.xcodeproj/project.pbxproj:1518`).
2. **The pbxproj has drifted from the generator script.** `UsageBeaconService` is in the WerkiOS sources phase but is **not** in `scripts/add_ios_target.rb`'s `shared_basenames`. Its build-file UUIDs (`CA11AB01AB01AB01AB0100F2/F3`) are hand-authored, not gem-generated. Re-running the script would silently drop it. Reconcile before regenerating.
3. **`SafeURL.swift` is already correctly fenced** (`#if os(macOS)` at line 2, `import AppKit` at line 3). It and `UsageBeaconService` are the only AppKit importers among the 20 currently-shared files.
4. **`MatchaWorkService.swift` hard-depends on `JournalService.shared`** (`clearCaches()` + ~25 delegating shims) and on `MWProjectElement` (`projectElementsCache`). So `JournalService` + `JournalModels` + `ProjectElementModels` + `MatchaWorkService+Elements` ship even though those panels are deferred. Surgery costs more than the dead code. `+Recruiting`/`+Productivity`/`+Agent` are genuinely not needed.
5. **`ProjectBizModels.swift` must be shared** — not for `KanbanTemplate` (macOS-view-only) but because it declares `MWAdminSearchUser` (used by `+Collaborators`) and `MWSendInterviewsRequest` (used by `+Threads`). Same for `ReplayModels.swift` → `MWWeeklyReplay` is used by `MatchaWorkService+Tasks.swift:342`.
6. **`PDFKitView` needs no extraction** — it's `NSViewRepresentable` in `Views/MatchaWork/Previews/OfferLetterPreview.swift:16`, referenced only from macOS views. iOS writes its own `UIViewRepresentable` over `PDFKit.PDFView`.
7. **Exactly two symbols must be extracted** out of macOS view files so the shared VMs resolve: `MWProjectTitlePatch` + the `Notification.Name` extension (`Views/MatchaWork/ThreadListView.swift:283-300`), and `WorkToastCenter` (`Views/Components/ChannelToastOverlay.swift:185-229`). With those moved, the proposed shared set has zero unresolved externals.
8. **Only the 6 `ProjectDetailViewModel*.swift` files import AppKit** among the candidate shared VMs/services/models. In 5 of them it is vestigial (`NSError`/`NSURLErrorDomain` are Foundation); only `+Files.swift` has real AppKit.

---

## Step 1 — Source surgery

| File | Line(s) | Change |
|---|---|---|
| `Espresso/Services/UsageBeaconService.swift` | 2 | `import AppKit` → `#if os(macOS)` / `import AppKit` / `#else` / `import UIKit` / `#endif` |
| `Espresso/Services/UsageBeaconService.swift` | 41 | fence the frontmost gate: macOS keeps `NSApplication.shared.isActive`, iOS uses `UIApplication.shared.applicationState == .active` |
| `Espresso/ViewModels/ProjectDetailViewModel.swift` | 2 | delete `import AppKit` (vestigial) |
| `Espresso/ViewModels/ProjectDetailViewModel+Core.swift` | 2 | delete `import AppKit` (vestigial) |
| `Espresso/ViewModels/ProjectDetailViewModel+Tasks.swift` | 2 | delete `import AppKit` (vestigial) |
| `Espresso/ViewModels/ProjectDetailViewModel+Elements.swift` | 2 | delete `import AppKit` (vestigial) |
| `Espresso/ViewModels/ProjectDetailViewModel+Files.swift` | 2 | `import AppKit` → `#if os(macOS) … #endif` |
| `Espresso/ViewModels/ProjectDetailViewModel+Files.swift` | ~210-250 | wrap the export-save-panel block + `presentExportSavePanel(data:format:title:)` in `#if os(macOS)` (real `NSSavePanel`/`NSApp`/`NSAlert`). iOS exports from the view layer via `ShareLink` |
| `Espresso/Services/WorkDetailVMStore.swift` | 27-30, 37-55, 87-90, 111-114 | **remove all four `#if os(macOS)` fences** and update the comment. This is the designed seam — after it, `projectVM(id)`/`threadVM(id)` vend on iOS |
| `Espresso/Views/MatchaWork/ThreadListView.swift` | 283-300 | **cut** the `Notification.Name` extension + `struct MWProjectTitlePatch` into new `Espresso/Models/MatchaWork/WorkNotifications.swift` |
| `Espresso/Views/Components/ChannelToastOverlay.swift` | 185-229 | **cut** `final class WorkToastCenter` into new `Espresso/Views/Components/WorkToastCenter.swift`. Leave `ChannelToastCenter` (line 9), `WorkToastOverlay` (line 231) and the views behind — they read the macOS `AppState` |
| `WerkiOS/Views/Channels/ChannelChatView.swift` | ~8-44 | refactor to `let channelId: String` / `let channelName: String` / `var isEmbedded = false`, keep an `init(channel: ChannelSummary)` convenience for `ChannelListView.swift:35`. Skip `.navigationTitle` when embedded. Only `channel.id`/`.name` are used today |

Register the two new macOS-side files with the macOS target:
```
cd platforms/desktop/Espresso
ruby scripts/add_sources.rb Matcha/Models/MatchaWork WorkNotifications.swift
ruby scripts/add_sources.rb Matcha/Views/Components WorkToastCenter.swift
```

---

## Step 2 — Extend `shared_basenames` and regenerate the iOS target

Edit `scripts/add_ios_target.rb` (array at lines 44-52). **First reconcile the drift**: add `UsageBeaconService.swift` to the list — it is in the pbxproj but not the script, and regenerating without it drops the usage beacon from iOS. Then add 36 more:

- **Models** (`Espresso/Models/MatchaWork/`): `CommonModels`, `DashboardModels`, `ProjectModels`, `ProjectTaskModels`, `ProjectBizModels`, `ProjectElementModels`, `ReplayModels`, `ThreadModels`, `JournalModels`, `WorkNotifications`
- **Services** (`Espresso/Services/`): `MatchaWorkService`, `+Projects`, `+Tasks`, `+Files`, `+Collaborators`, `+Threads`, `+Elements`, `JournalService`, `ProjectWebSocket`, `TicketUpdatesStore`
- **ViewModels** (`Espresso/ViewModels/`): `ProjectDetailViewModel`, `+Core`, `+Tasks`, `+Files`, `+Elements`, `ProjectPresenceViewModel`, `ThreadDetailViewModel`, `ThreadListViewModel` — **not** `+Biz` (recruiting/deals; needs `+Recruiting`)
- **Portable SwiftUI helpers** (`Espresso/Views/MatchaWork/`): `KanbanColumns`, `KanbanSearch`, `KanbanReplay`, `TaskProgressBar`, `TaskHistoryTimeline`, `MarkdownPreviewView`, `PresencePillContent`
- **Extracted**: `WorkToastCenter`

Then:
```
ruby scripts/add_ios_target.rb
```
Idempotent — it drops and rebuilds the WerkiOS target and recursively mirrors `WerkiOS/`, so new iOS files need no pbxproj work. **Never hand-edit pbxproj for WerkiOS** (that drift is finding #2).

---

## Step 3 — New iOS files under `WerkiOS/`

37 files. Naming must stay basename-unique repo-wide (see risks).

**Support (3)** — `Support/PDFViewer.swift` (`UIViewRepresentable` over `PDFKit.PDFView`), `Support/FileImportSupport.swift` (`PhotosPicker` + `.fileImporter` → upload payload), `Support/CollabFormatting.swift` (column labels, priority tint, relative time).

**Projects list + detail shell (7)** — `ViewModels/ProjectsListViewModel.swift` (collab-filtered list, unread counts), `Views/Projects/ProjectsListView.swift`, `ProjectRowView.swift`, `CollabProjectView.swift` (detail host: owns `WorkDetailVMStore.shared.projectVM(id)` + `ProjectPresenceViewModel` + `ProjectWebSocket` join/page_change/leave), `CollabPanelPicker.swift` (scrollable panel bar replacing the macOS 10-tab strip), `CollabOverviewPanel.swift`, `CollabPresenceBar.swift` (reuses shared `PresencePillContent`).

**Chat (1)** — `Views/Projects/CollabChatPanel.swift`: `ensureProjectDiscussionChannel(projectId:)` → embedded `ChannelChatView(channelId:channelName:isEmbedded: true)`. This is why the chat-view refactor is in step 1; `ChannelsWebSocket`'s multi-subscriber fan-out already exists for exactly this.

**Kanban (4)** — `Views/Projects/Kanban/KanbanPanelView.swift` (columns + search via shared `groupedColumns`, realtime task events), `KanbanColumnPager.swift`, `TicketCardView.swift`, `NewTicketSheet.swift`.

**Ticket viewer (8)** — `Views/Projects/Ticket/TicketViewerView.swift` plus `TicketHeaderSection`, `TicketSubtasksSection`, `TicketRoundsSection`, `TicketReviewSection`, `TicketDiscussionSection`, `TicketHistorySection` (wraps shared `TaskHistoryTimeline`), `TicketAttachmentsSection`.

**Files / Media (3)** — `Views/Projects/CollabFilesPanel.swift`, `CollabMediaPanel.swift`, `AttachmentPreviewView.swift` (image / PDF / QuickLook + `ShareLink`, replacing `NSSavePanel`).

**AI Threads (6)** — `Views/Threads/AIThreadListPanel.swift`, `AIThreadChatView.swift` (consumes `ThreadDetailViewModel`'s `URLSession.bytes` SSE stream — already iOS-safe), `AIThreadBubble.swift`, `AIThreadComposer.swift`, `NewAIThreadSheet.swift`, `StandaloneThreadsView.swift`.

**Home (3)** — `ViewModels/HomeViewModel.swift` (parallel `listOpenTasks`/`listProjects`/`listRecentActivity`/`listThreads`), `Views/Home/HomeView.swift`, `HomeTaskRow.swift`.

**Polish (3)** — `Views/Projects/CollabNotesPanel.swift` (read-only, shared `MarkdownPreviewView`), `CollaboratorsSheet.swift`, `Views/Notifications/WorkNotificationsView.swift`.

**Edits to existing WerkiOS files**
- `WerkiOS/Views/MainTabView.swift` — 4 tabs: Home / Projects / Channels / Messages; route `pendingProjectId`/`pendingTaskId` to Projects.
- `WerkiOS/App/AppState.swift` — add `pendingProjectId`/`pendingTaskId`; on login call `MatchaWorkService.shared.updateCacheScope(user.id)`; on logout call `updateCacheScope(nil)` + `WorkDetailVMStore.shared.clearAll()` + `ProjectWebSocket.shared.disconnect()` (mirrors `Espresso/App/AppState+Session.swift`).
- `WerkiOS/WerkApp.swift` — extend the `scenePhase == .active` branch to also reconnect `ProjectWebSocket.shared` when authenticated, alongside the existing `ChannelsWebSocket.shared.connect()`.

---

## Milestones (each independently buildable)

- **M0 — unbreak + share the domain layer.** All of steps 1-2. No UI change. Exit: both schemes build.
- **M1 — Projects tab: list → detail shell + Overview + Chat.** The 7 shell files + `CollabChatPanel` + the `ChannelChatView` refactor + tab/AppState/WS wiring.
- **M2 — Kanban + ticket viewer.** 4 Kanban files + 8 ticket files + `CollabFormatting`.
- **M3 — Files + Media.** `FileImportSupport`, `PDFViewer`, `AttachmentPreviewView`, both panels; wire ticket attachment uploads.
- **M4 — AI Threads + Home.** 6 thread files + 3 Home files + Home tab.
- **M5 — polish.** Read-only Notes, collaborators sheet, notifications, project push deep-link, asset catalog + app icon (see risk 4).

---

## Verification

Per milestone, from `platforms/desktop/Espresso`:
```
xcodebuild -project Matcha.xcodeproj -scheme WerkiOS \
  -destination 'generic/platform=iOS Simulator' build
xcodebuild -project Matcha.xcodeproj -scheme Matcha build   # macOS regression gate
```
The macOS gate matters — the extractions and fences touch shared files.

Then run in Simulator against the local backend. `Espresso/Services/APIClient.swift` picks `http://127.0.0.1:8001/api` under DEBUG and `WerkiOS/Info.plist` already sets `NSAllowsLocalNetworking`, so no plist change. Run the macOS app side-by-side on the same project to exercise realtime: `ProjectWebSocket` task events (M2), `ChannelsWebSocket` multi-subscriber chat (M1), presence (M1).

Run `MatchaTests` (macOS scheme) after the `WorkDetailVMStore` fence removal — `MatchaTests/WorkDetailVMStoreTests.swift` covers that store.

Per-milestone functional checks: M1 — only collab projects listed, Overview counts live, chat round-trips, presence pill shows the Mac client. M2 — board order matches macOS, a ticket moved on the phone lands on the Mac live, subtasks/rounds/review/comments round-trip, unviewed badges clear. M3 — upload from Photos and Files.app, folder CRUD, image + PDF preview, `ShareLink` export. M4 — an AI response streams without stalling, an assigned task opens the right ticket.

---

## Risks / gotchas

1. **`add_ios_target.rb` regenerates the whole target** — any hand pbxproj edit is lost on the next run. Finding #2 is exactly this having already happened. Anyone adding a shared file edits lines 44-52 and re-runs.
2. **Basename uniqueness is load-bearing.** `add_ios_target.rb:56` does `.find` on basename with no ambiguity check — a duplicate binds silently to the wrong ref. All 37 proposed iOS filenames are collision-free; consider adding a duplicate-detection `raise` to the script as cheap hardening.
3. **Elements ships despite the panel being deferred** (finding #4) — ~570 LOC dead on iOS. Don't try to strip it.
4. **WerkiOS has an empty Resources build phase** — no asset catalog, no app icon; it installs blank. Fixing means extending the script with a resources phase + `ASSETCATALOG_COMPILER_APPICON_NAME`. Do it in M5, not at TestFlight time.
5. **`ProjectDetailViewModel+Biz` is excluded on purpose.** Any iOS view touching `recruitingData`/`toggleShortlist`/`savePosting` won't compile — the fix would be sharing `+Biz` + `MatchaWorkService+Recruiting`. Keep collab-only discipline.
6. **Presence scope.** `ProjectPresenceViewModel` exposes `remoteCursors`/`remoteCarets` and throttled `cursor_move`/`caret_move` senders. iOS v1 reads `members` only and sends `join_project`/`page_change`/`leave_project`. Don't call the cursor/caret senders — desktop-pointer concepts that would burn the server's 60 msg/s budget for nothing.
7. **`ProjectWebSocket` lifecycle.** iOS suspends sockets in background; reconnect on `scenePhase == .active`. The class replays `(currentProjectId, currentPageKey)` on reconnect so presence self-heals. `leave_project` on `CollabProjectView.onDisappear`, `page_change` on panel switch.
8. **`TicketUpdatesStore` is per-device `UserDefaults`** — unviewed badges won't match between Mac and phone. Existing v1 design; call it out rather than fixing it here.
9. **`WorkToastCenter` extraction changes macOS layout.** Only the `@Observable` class moves; `WorkToastOverlay` (reads macOS `AppState`) stays. Confirm the macOS build after the cut.
10. **iPad.** `TARGETED_DEVICE_FAMILY = 1,2` already. Ship `NavigationStack` on both; a `NavigationSplitView` iPad variant of list → detail is a clean follow-up since the split point is already the navigation destination boundary.
