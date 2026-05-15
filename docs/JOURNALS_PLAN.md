# Journals — Matcha Work macOS

## Context

Top-level "Journals" surface in the macOS Matcha Work app for organising thoughts and ideas across topics. Users create one journal per topic; each journal is a chronological feed of dated entries the user writes manually in markdown. Personal by default; the user can invite collaborators per-journal when a topic should be shared (mirrors the per-channel invite UX shipped earlier).

Decisions (already taken):

- New top-level sidebar section (alongside Channels, Projects, Threads).
- Dated entries per journal — each journal is a container; entries timestamp on creation.
- Pure manual — no AI assistance in v1.
- Personal default, with per-journal collaborator invites.

## Data model

### Migration `zzzz6e7f8g9h0_add_mw_journals.py`

`down_revision = "zzzz5d6e7f8g9"` (current HEAD = `zzzz5d6e7f8g9_add_channel_broadcasts.py`; bump to current HEAD when written).

```sql
CREATE TABLE mw_journals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    title VARCHAR(255) NOT NULL DEFAULT 'Untitled Journal',
    description TEXT,
    color VARCHAR(20),     -- e.g. 'matcha', 'amber', 'blue' for sidebar accent
    icon VARCHAR(64),      -- SF Symbol name (defaults to 'book')
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_mw_journals_created_by ON mw_journals(created_by);
CREATE INDEX idx_mw_journals_company_id ON mw_journals(company_id);

CREATE TABLE mw_journal_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_id UUID NOT NULL REFERENCES mw_journals(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(255),
    content TEXT NOT NULL DEFAULT '',
    entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_mw_journal_entries_journal_date
    ON mw_journal_entries(journal_id, entry_date DESC, created_at DESC);

CREATE TABLE mw_journal_collaborators (
    journal_id UUID NOT NULL REFERENCES mw_journals(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    invited_by UUID REFERENCES users(id),
    role VARCHAR(20) NOT NULL DEFAULT 'collaborator'
        CHECK (role IN ('owner', 'collaborator')),
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'pending', 'removed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (journal_id, user_id)
);
CREATE INDEX idx_mw_journal_collaborators_user
    ON mw_journal_collaborators(user_id, status);
```

Sync the same shape into `server/app/database.py` for fresh installs. Migration NOT auto-run — user runs `alembic upgrade head` per CLAUDE.md.

## Server

### `server/app/matcha/services/journal_service.py` (new)

Pure CRUD + access control. Mirrors `project_service` patterns.

```python
async def list_journals(user_id: UUID, company_id: Optional[UUID]) -> list[dict]
async def get_journal(journal_id: UUID, viewer_id: UUID) -> Optional[dict]
async def create_journal(creator_id: UUID, company_id: UUID, *, title, description, color, icon) -> dict
async def update_journal(journal_id: UUID, viewer_id: UUID, patch: dict) -> dict
async def archive_journal(journal_id: UUID, viewer_id: UUID) -> None

async def list_entries(journal_id: UUID, viewer_id: UUID, *, limit=50, before: Optional[datetime]=None) -> list[dict]
async def create_entry(journal_id: UUID, author_id: UUID, *, title, content, entry_date) -> dict
async def update_entry(entry_id: UUID, viewer_id: UUID, patch: dict) -> dict
async def delete_entry(entry_id: UUID, viewer_id: UUID) -> None

async def list_collaborators(journal_id: UUID, viewer_id: UUID) -> list[dict]
async def add_collaborator(journal_id: UUID, user_id: UUID, invited_by: UUID) -> list[dict]
async def remove_collaborator(journal_id: UUID, user_id: UUID, removed_by: UUID) -> None
```

Visibility rule: a journal is visible to its `created_by` user OR any active row in `mw_journal_collaborators`. All write operations require active membership.

### `server/app/matcha/routes/journals.py` (new)

Mounted under `/matcha-work/journals` (consistent with existing `mw_*` paths).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/journals` | list journals visible to caller |
| POST | `/journals` | create |
| GET | `/journals/{id}` | detail |
| PATCH | `/journals/{id}` | update title/description/color/icon |
| DELETE | `/journals/{id}` | archive |
| GET | `/journals/{id}/entries` | paginated entries (default 50, before=ISO ts) |
| POST | `/journals/{id}/entries` | create entry |
| PATCH | `/journals/{id}/entries/{entry_id}` | update |
| DELETE | `/journals/{id}/entries/{entry_id}` | delete |
| GET | `/journals/{id}/collaborators` | list |
| POST | `/journals/{id}/collaborators` | invite (body `{user_ids: [UUID]}`) |
| DELETE | `/journals/{id}/collaborators/{user_id}` | remove |

Mount in `server/app/matcha/routes/__init__.py`. **Must inherit `require_feature("matcha_work")`** — `matcha_work_router` is mounted at `__init__.py:73–78` with `dependencies=[Depends(require_feature("matcha_work"))]`, and every existing matcha-work route is gated. Either include `journals_router` directly inside `matcha_work_router` (preferred, single source of truth for the gate) or repeat the same `dependencies=[…]` on the new mount.

## Desktop

### Models — `desktop/Werk/Matcha/Models/MatchaWorkModels.swift`

```swift
struct MWJournal: Codable, Identifiable {
    let id: String
    let title: String
    let description: String?
    let color: String?
    let icon: String?
    let status: String
    let createdBy: String
    let createdAt: String
    let updatedAt: String
    let entryCount: Int?
    let collaboratorCount: Int?
    let collaboratorRole: String?

    enum CodingKeys: String, CodingKey {
        case id, title, description, color, icon, status
        case createdBy = "created_by"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case entryCount = "entry_count"
        case collaboratorCount = "collaborator_count"
        case collaboratorRole = "collaborator_role"
    }
}

struct MWJournalEntry: Codable, Identifiable {
    let id: String
    let journalId: String
    let authorId: String
    let title: String?
    let content: String
    let entryDate: String       // YYYY-MM-DD
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, title, content
        case journalId = "journal_id"
        case authorId = "author_id"
        case entryDate = "entry_date"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}
```

### Service — extend `MatchaWorkService.swift`

```swift
// MARK: - Journals
private var journalListCache: [String: MWCacheEntry<[MWJournal]>] = [:]

func listJournals(forceRefresh: Bool = false) async throws -> [MWJournal]
func getJournal(id: String) async throws -> MWJournal
func createJournal(title: String, description: String?, color: String?, icon: String?) async throws -> MWJournal
func updateJournal(id: String, title: String?, description: String?, color: String?, icon: String?) async throws -> MWJournal
func archiveJournal(id: String) async throws

func listJournalEntries(journalId: String, before: String? = nil, limit: Int = 50) async throws -> [MWJournalEntry]
func createJournalEntry(journalId: String, title: String?, content: String, entryDate: String?) async throws -> MWJournalEntry
func updateJournalEntry(entryId: String, journalId: String, title: String?, content: String?) async throws -> MWJournalEntry
func deleteJournalEntry(entryId: String, journalId: String) async throws

func listJournalCollaborators(journalId: String) async throws -> [MWProjectCollaborator]   // reuse same model shape
func addJournalCollaborators(journalId: String, userIds: [String]) async throws
func removeJournalCollaborator(journalId: String, userId: String) async throws

func invalidateJournalLists()
```

### ViewModel — `JournalDetailViewModel.swift` (new)

```swift
@Observable
class JournalDetailViewModel {
    var journal: MWJournal?
    var entries: [MWJournalEntry] = []
    var isLoading = false
    var errorMessage: String?

    func load(id: String) async
    func refresh() async
    func createEntry(title: String?, content: String) async
    func updateEntry(_ entry: MWJournalEntry, title: String?, content: String) async
    func deleteEntry(_ entry: MWJournalEntry) async
    func updateJournalMeta(title: String?, description: String?, color: String?, icon: String?) async
}
```

### Views

- `Views/Journals/JournalListView.swift` — sidebar list of journals with title + colour dot/icon. `+` opens `NewJournalSheet`. Star/archive via context menu.
- `Views/Journals/JournalDetailView.swift` — right-pane: header (title + collaborators + invite button), composer at top ("New entry today…" → expands), then a chronological timeline of entries grouped by date. **Markdown rendering**: `MarkdownPreviewView` is project-specific (`init(sections: [MWProjectSection], title: String)`) and won't accept a single string. Mirror `BlogEditorView`'s plain-markdown render path instead — likely an `AttributedString(markdown:)` cell. Hover on an entry surfaces edit/delete. Entry editor reuses `MarkdownTextEditor` already in `Views/MatchaWork/`. Composer exposes a date picker so users can backdate entries; default is today.
- `Views/Journals/NewJournalSheet.swift` — title + optional description + colour picker (3-5 preset colours) + icon picker (subset of SF Symbols).
- `Views/Journals/InviteToJournalSheet.swift` — mirrors `InviteToChannelSheet` exactly. Props: `journalId: String`, `journalTitle: String`, `onInvited: (Int) -> Void`. State: `query`, `users: [ChannelsService.InvitableUser]` (or new `MatchaWorkService.InvitableUser` if scope diverges), `selectedIds: Set<String>`, `loading`, `inviting`, `error`, `searchTask`. Add `MatchaWorkService.searchInvitableUsersForJournal(query:)` — same debounce + multi-select pattern as channels.

### Sidebar wiring — `App/ContentView.swift`

Add a new `sidebarSection(title: "Journals", icon: "book.closed", isOpen: $journalsSectionOpen)` between Projects and Threads. `@AppStorage("mw-sidebar-journals-open") = true`. Gate the entire section behind `appState.mwBetaLite` (matches the rest of the matcha-work surface — no new beta key).

```
Channels
Consultations    (existing toggle)
Projects
Journals         (NEW)
Threads
```

`JournalListView(showHeader: false)` is the body. The `+` trailing button opens `NewJournalSheet`.

### AppState — `App/AppState.swift`

```swift
var selectedJournalId: String? = nil
var journalsListGeneration: Int = 0
```

`didLogout()` resets both. Selecting a journal clears `selectedThreadId` / `selectedProjectId` / `selectedChannelId` (mirror existing exclusivity).

### App router — `App/MatchaApp.swift` / `ContentView.swift`

Right pane shows `JournalDetailView` when `selectedJournalId != nil`, falling back to existing thread/project/channel routing.

### Project membership — `project.pbxproj`

Register all new Swift files in the Xcode project (same pattern as the past few rounds — direct PBXBuildFile + PBXFileReference inserts).

## Out of scope (v1)

- AI assist on entries (pure manual decision).
- Per-user starring of journals (same deferred scope as channel pin).
- Realtime collab — entries are list-based; no WebSocket push, callers refetch on entry create. Fine for solo / small-team use; a v2 can layer Channels-style WS.
- Tags, full-text search, attachments — entries are markdown only for now.
- Cross-linking entries to projects/threads.

## Critical files

| File | Change |
|------|--------|
| `server/alembic/versions/zzzk7l8m9n0o1_add_mw_journals.py` | Migration (manual run) |
| `server/app/database.py` | Sync schema for fresh installs |
| `server/app/matcha/services/journal_service.py` | New service module |
| `server/app/matcha/routes/journals.py` | New router |
| `server/app/matcha/routes/__init__.py` | Mount router under `/matcha-work` |
| `desktop/Werk/Matcha/Models/MatchaWorkModels.swift` | `MWJournal`, `MWJournalEntry` |
| `desktop/Werk/Matcha/Services/MatchaWorkService.swift` | Journal API methods + cache |
| `desktop/Werk/Matcha/ViewModels/JournalDetailViewModel.swift` | New |
| `desktop/Werk/Matcha/Views/Journals/JournalListView.swift` | New (sidebar list) |
| `desktop/Werk/Matcha/Views/Journals/JournalDetailView.swift` | New (entry timeline) |
| `desktop/Werk/Matcha/Views/Journals/NewJournalSheet.swift` | New |
| `desktop/Werk/Matcha/Views/Journals/InviteToJournalSheet.swift` | New (mirror of InviteToChannelSheet) |
| `desktop/Werk/Matcha/App/AppState.swift` | `selectedJournalId`, `journalsListGeneration` |
| `desktop/Werk/Matcha/App/ContentView.swift` | Sidebar section + main pane routing |
| `desktop/Werk/Matcha.xcodeproj/project.pbxproj` | Register new Swift files |

## Build order

1. Migration (NOT run). User runs `alembic upgrade head`.
2. `database.py` schema sync.
3. `journal_service.py` + `server/tests/matcha_work/test_journal_service.py` (mocked deps; mirrors `test_project_task_toggle.py` shape). Visibility cases: creator, active collaborator, non-member; write paths gated on active membership. Skip a real-DB variant per CLAUDE.md DB-test rule.
4. `journals.py` router + mount.
5. Desktop models + service methods + cache.
6. `NewJournalSheet` + sidebar section + `JournalListView`.
7. `JournalDetailViewModel` + `JournalDetailView` (timeline + composer + entry editor).
8. `InviteToJournalSheet` + collaborator endpoints.
9. `pbxproj` register; `xcodebuild` verify.

## Verification

- Create a journal → appears in sidebar instantly.
- Add 3 entries on different dates → timeline groups by date, newest first.
- Edit / delete an entry from hover button → list updates without flicker (existing refresh pattern).
- Invite a second user from a personal-mode account → other user sees the journal in their sidebar after refresh; can write entries; can be removed by owner.
- Sign out / sign in: sidebar shows journals correctly. Cache scope (`MatchaWorkService.updateCacheScope`) resets the journal cache on user switch.
- Archive a journal → disappears from default list (active filter).
- Company without `enabled_features.matcha_work` → 403 from `/matcha-work/journals` (proves feature gate inherited from parent router).
- `mwBetaLite=false` user → sidebar Journals section hidden (proves desktop beta gate).
- Migration applies clean: `alembic upgrade head` after pulling — `alembic history` shows new revision after `zzzz5d6e7f8g9`.
