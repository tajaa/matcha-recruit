# macOS App: Full Feature Parity with Web Client

## Context
The macOS Matcha Work desktop app covers core thread-based chat but is missing 16+ features present in the web client. Goal is full parity using native SwiftUI (no WKWebView). The backend APIs already exist for everything — this is purely a macOS frontend effort.

## Existing macOS Patterns to Reuse
- `APIClient.swift` — auth, refresh, base URL, JSON decode
- `MatchaWorkService.swift` — caching (60s TTL), thread CRUD, SSE streaming
- `ThreadDetailViewModel.swift` — @Observable, streaming state, message handling
- `PreviewPanelView.swift` — task-type-based preview switching
- `ChatPanelView.swift` — image upload pattern (multipart form-data)

---

## Phase 1: Quick Wins (API calls + simple UI)

### 1A. Model Selector
- Add model picker to `ThreadDetailView.swift` toolbar
- Store selection in `@AppStorage("mw-model")`
- Pass `model` param in `sendMessageStream()` request body
- Models: Flash Lite 3.1, Flash 3.0, Pro 3.1 (from `constants.ts`)

### 1B. Token Usage Summary
- Add `fetchUsageSummary(periodDays:)` to `MatchaWorkService.swift`
- Call `GET /matcha-work/usage/summary`
- New `UsageSummaryView.swift` — show totals + by-model breakdown
- Accessible from thread list toolbar or settings area

### 1C. Multi-Format Export
- Add `exportProject(id:format:)` to service (`GET /matcha-work/threads/{id}/project/export/{fmt}`)
- Support `pdf`, `md`, `docx` (currently macOS only does PDF)
- Add export menu in `PreviewPanelView.swift` with format picker
- Use `NSSavePanel` for save location

### 1D. Review Request Sending
- Add `sendReviewRequests(threadId:emails:customMessage:)` to service
- Call `POST /matcha-work/threads/{id}/review-requests/send`
- Add "Send for Review" button in `ReviewPreview` section of `PreviewPanelView.swift`
- Email input field + optional custom message textarea

### 1E. Handbook Upload
- Add `uploadHandbook(threadId:file:callbacks:)` SSE endpoint to service
- Call `POST /matcha-work/threads/{id}/handbook/upload`
- Add file picker button in chat for `.pdf`, `.doc`, `.docx`
- Stream progress events (stage, progress_pct, red_flag_count)

### 1F. Presence & Online Users
- Add `sendHeartbeat()` → `POST /matcha-work/presence/heartbeat`
- Add `fetchOnlineUsers()` → `GET /matcha-work/presence/online`
- Timer-based heartbeat every 30s in `AppState.swift`
- Show online user avatars in thread list header

**Files to create/modify:**
- `MatchaWorkService.swift` — new API methods
- `MatchaWorkModels.swift` — UsageSummary, OnlineUser models
- `ThreadDetailView.swift` — model picker, export menu
- `PreviewPanelView.swift` — review send UI, export formats
- `ThreadListView.swift` — online users display
- New: `UsageSummaryView.swift`

---

## Phase 2: File Handling & Data Panels

### 2A. File Drag-and-Drop in Chat
- Extend `ChatPanelView.swift` to accept `.onDrop` for file types
- Detect resume files (`.pdf`, `.doc`, `.docx`, `.txt`) vs inventory (`.csv`, `.xlsx`, `.xls`)
- Route to appropriate upload endpoint based on extension
- Show upload progress inline

### 2B. Resume Batch Panel
- New: `ResumeBatchPanelView.swift`
- Add `uploadResumes(threadId:files:callbacks:)` SSE to service
- Add `sendCandidateInterviews(threadId:candidateIds:positionTitle:customMessage:)` to service
- Add `syncInterviewStatuses(threadId:)` to service
- UI: Candidate list with search bar, multi-column sorting (name, experience, title, location)
- Expandable candidate detail (skills, education, certifications, flags, strengths)
- Checkbox selection → "Send Interviews" button with position title prompt
- Interview status badges per candidate
- Wire into `PreviewPanelView.swift` as new task_type case

### 2C. Inventory Panel
- New: `InventoryPanelView.swift`
- Add `uploadInventory(threadId:files:callbacks:)` SSE to service
- UI: Item list with category filter (protein, produce, dairy, etc.)
- Search by product name / SKU / vendor
- Sortable columns (name, qty, unit cost, total, vendor)
- Total cost footer
- Wire into `PreviewPanelView.swift`

**Files to create/modify:**
- `ChatPanelView.swift` — file drop handler
- `MatchaWorkService.swift` — resume/inventory upload + interview APIs
- `MatchaWorkModels.swift` — ResumeCandidate, InventoryItem models
- New: `ResumeBatchPanelView.swift`
- New: `InventoryPanelView.swift`
- `PreviewPanelView.swift` — route to new panels

---

## Phase 3: Projects System

### 3A. Project Models & Service
- Add to `MatchaWorkModels.swift`: MWProject, ProjectSection, ProjectCollaborator, ProjectType enum
- Add to `MatchaWorkService.swift`:
  - `listProjects(status:)` → `GET /matcha-work/projects`
  - `createProject(title:projectType:)` → `POST /matcha-work/projects`
  - `getProjectDetail(id:)` → `GET /matcha-work/projects/{id}`
  - `updateProjectMeta(id:updates:)` → `PATCH /matcha-work/projects/{id}`
  - `archiveProject(id:)` → `DELETE /matcha-work/projects/{id}`
  - Section CRUD: add, update, delete, reorder
  - `exportProject(id:format:)` → `GET /matcha-work/projects/{id}/export/{fmt}`
  - `createProjectChat(projectId:title:)` → `POST /matcha-work/projects/{id}/chats`

### 3B. Project List View
- New: `ProjectListView.swift`
- Shown as tab/section in `ThreadListView.swift` (alongside thread list)
- Project cards: title, type badge, section count, chat count, collaborator avatars
- Create project button with type picker (general / presentation / recruiting)
- Pin/archive actions

### 3C. Project Detail View
- New: `ProjectDetailView.swift`
- NavigationSplitView: sidebar (chats list) + detail (active chat or section editor)
- Multi-chat support — chat list with create/rename
- Chat panel reuses existing `ChatPanelView` pattern
- Section list sidebar with add/reorder/delete
- Model selector + token usage in toolbar

### 3D. Native Section Editor
- New: `SectionEditorView.swift`
- Built on SwiftUI `TextEditor` with `AttributedString`
- Formatting toolbar: bold, italic, headings (H2/H3), bullet/numbered lists
- Keyboard shortcuts: Cmd+B, Cmd+I, Cmd+Shift+H
- Image insertion via file picker → upload to S3 → insert URL
- Debounced auto-save (1s) calling `updateProjectSection()`
- Markdown import/export for round-tripping with web client

### 3E. Project Export
- Export menu: PDF, Markdown, DOCX
- Uses `NSSavePanel` for file save
- Calls `GET /matcha-work/projects/{id}/export/{fmt}`

**Files to create/modify:**
- `MatchaWorkModels.swift` — project models
- `MatchaWorkService.swift` — project API methods
- New: `ProjectListView.swift`
- New: `ProjectDetailView.swift`
- New: `ProjectDetailViewModel.swift`
- New: `SectionEditorView.swift`
- `ContentView.swift` — add project navigation
- `ThreadListView.swift` — add Projects tab

---

## Phase 4: Collaboration

### 4A. Collaborator Panel
- New: `CollaboratorPanelView.swift`
- Add `listCollaborators(projectId:)`, `addCollaborator()`, `removeCollaborator()`, `searchAdminUsers()` to service
- List collaborators with avatar, name, role badge
- Search field (2+ chars) to find admin users
- Add/remove buttons (owner only)
- Popover or sheet presentation from project detail toolbar

### 4B. Multi-Chat per Project
- Chat list in project sidebar
- Create new chat within project context
- Each chat is a separate thread linked to the project
- Reuse existing `ChatPanelView` + `ThreadDetailViewModel` pattern

**Files to create/modify:**
- `MatchaWorkService.swift` — collaborator + search APIs
- `MatchaWorkModels.swift` — ProjectCollaborator model (may already exist)
- New: `CollaboratorPanelView.swift`
- `ProjectDetailView.swift` — chat list sidebar, collaborator button

---

## Phase 5: Recruiting Pipeline

### 5A. Pipeline View
- New: `RecruitingPipelineView.swift`
- Tabbed interface: Status, Posting, Candidates, Interviews, Shortlist
- Shown in `ProjectDetailView` when `project_type == "recruiting"`

### 5B. Job Posting Editor
- New: `JobPostingEditorView.swift`
- Edit title, description, requirements, compensation, location, employment type
- `[Placeholder]` detection and highlighting (orange attributed text)
- Placeholder fill workflow: generate questions → extract values from chat
- Finalize button (disabled until all placeholders filled)
- Add service calls: `updateProjectPosting()`, `populatePostingFromChat()`, `generatePlaceholderQuestions()`, `extractPlaceholderValue()`

### 5C. Candidate Management
- Reuse `ResumeBatchPanelView` pattern but project-scoped
- Add `uploadProjectResumes()`, `analyzeProjectCandidates()` SSE endpoints
- Search/sort/filter candidates
- Expandable detail cards

### 5D. Shortlist & Interviews
- Shortlist toggle per candidate → `POST /matcha-work/projects/{id}/shortlist/{candidateId}`
- Interview tab: status tracking, scores, summaries
- Send interviews from candidate selection
- Sync interview statuses

**Files to create/modify:**
- New: `RecruitingPipelineView.swift`
- New: `JobPostingEditorView.swift`
- `MatchaWorkService.swift` — posting, shortlist, placeholder APIs
- `MatchaWorkModels.swift` — RecruitingPosting, RecruitingData
- `ProjectDetailView.swift` — route recruiting projects to pipeline

---

## Phase 6: Email Agent

### 6A. Gmail OAuth on macOS
- Use `ASWebAuthenticationSession` for OAuth popup (macOS native)
- Call `POST /matcha-work/agent/email/connect` to get auth URL
- Handle callback, store connection status
- Add `agentEmailStatus()`, `agentConnectGmail()`, `agentDisconnectGmail()` to service

### 6B. Agent Panel View
- New: `AgentPanelView.swift`
- Gmail connect/disconnect button with status indicator
- Email list (fetch from Gmail via `POST /matcha-work/agent/email/fetch`)
- Email detail view (subject, from, date, body)
- Draft reply: instruction input → AI generates draft → editable text
- Send button (with Re: prefix for replies)
- Add to thread detail toolbar as toggleable panel

**Files to create/modify:**
- New: `AgentPanelView.swift`
- `MatchaWorkService.swift` — email agent APIs
- `MatchaWorkModels.swift` — AgentEmail model
- `ThreadDetailView.swift` — agent panel toggle

---

## Phase 7: Compliance Decision Tree (Native)

### 7A. Native DAG Visualization
- New: `ComplianceDecisionTreeView.swift`
- Since React Flow is web-only, build a native SwiftUI canvas visualization
- Use `Canvas` view or `Path` drawing for node connections
- Question nodes: expandable cards showing answer, conclusion, sources
- Jurisdiction level nodes: color-coded by precedence (floor/ceiling/supersede/additive)
- Governing jurisdiction highlight (cyan border)
- Layout algorithm: simple top-down tree using manual positioning or `Layout` protocol
- Expandable inline in `MessageBubbleView.swift` where compliance reasoning exists

**Files to create/modify:**
- New: `ComplianceDecisionTreeView.swift`
- `MessageBubbleView.swift` — add tree toggle button in compliance section

---

## Phase 8: Inbox

### 8A. Inbox Service & Models
- New: `InboxService.swift`
- Models: InboxConversation, InboxMessage, InboxParticipant, InboxAttachment
- API calls: listConversations, getConversation, createConversation, sendMessage (FormData with files), markRead, toggleMute, getUnreadCount, searchUsers

### 8B. Inbox Views
- New: `InboxView.swift` — main inbox with NavigationSplitView (conversation list + thread)
- New: `InboxConversationListView.swift` — conversation cards with unread badges
- New: `InboxMessageThreadView.swift` — message bubbles, auto-scroll, date dividers
- New: `InboxComposeView.swift` — sheet/modal with recipient search, message, file attachment
- Attachment display: inline images, file download chips (same as web)
- File picker for attachments (10MB limit, same allowed types)

### 8C. Unread Count & Notifications
- Poll unread count every 60s from `AppState.swift`
- Show badge on Inbox tab/sidebar item
- Optional: native macOS `UNUserNotificationCenter` notifications for new messages

### 8D. Integration
- Add Inbox as top-level navigation item in `ContentView.swift`
- Also embed in `ProjectDetailView.swift` sidebar (matching web's ProjectView)

**Files to create/modify:**
- New: `InboxService.swift`
- New: `InboxModels.swift`
- New: `InboxView.swift`
- New: `InboxConversationListView.swift`
- New: `InboxMessageThreadView.swift`
- New: `InboxComposeView.swift`
- `ContentView.swift` — add inbox navigation
- `AppState.swift` — unread count polling
- `ProjectDetailView.swift` — inbox sidebar mode

---

## Phase Summary

| Phase | Features | New Files | Complexity |
|-------|----------|-----------|------------|
| 1 | Model selector, usage summary, export, review sending, handbook upload, presence | ~2 new, ~5 modified | Low |
| 2 | File drag-drop, resume panel, inventory panel | ~2 new, ~4 modified | Medium |
| 3 | Projects (models, list, detail, section editor, export) | ~5 new, ~4 modified | High |
| 4 | Collaborators, multi-chat | ~1 new, ~3 modified | Medium |
| 5 | Recruiting pipeline (posting, candidates, shortlist, interviews) | ~2 new, ~4 modified | High |
| 6 | Email agent (OAuth, email list, draft, send) | ~1 new, ~3 modified | Medium |
| 7 | Compliance decision tree (native canvas) | ~1 new, ~1 modified | Medium-High |
| 8 | Inbox (conversations, messages, compose, attachments, notifications) | ~6 new, ~3 modified | High |

**Total: ~20 new Swift files, ~15 modified files**

## Verification
After each phase:
1. Build in Xcode (`Cmd+B`) — zero warnings/errors
2. Run the app, log in, verify the new feature end-to-end
3. Test against the live backend APIs
4. Compare behavior side-by-side with the web client
5. Test edge cases: empty states, error handling, streaming interrupts
