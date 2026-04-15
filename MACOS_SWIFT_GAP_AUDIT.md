# macOS Swift ↔ Web Client matcha-work Gap Audit

## Context

The `client/src` React/TS matcha-work surface has been moving fast and the macOS Swift port at `desktop/Matcha` has fallen behind. This audit compares both apps end-to-end to identify everything the web client has that the Swift app is missing, so porting work can be prioritized.

## Method

Two parallel explorations of:
- **Web client**: `client/src/components/work/`, `client/src/components/matcha-work/`, `client/src/pages/work/`, `client/src/api/matchaWork.ts`, `client/src/types/matcha-work.ts`
- **Swift app**: `desktop/Matcha/Matcha/` (Views, ViewModels, Services, Models)

## Summary

The Swift app covers the **core thread + project + inbox loop** well. It is missing entire **top-level surfaces** (channels, tasks, connections, billing, language tutor, recruiting pipeline, hiring clients) and several **in-thread sub-features** (presentation editor, research tasks, diagram editor, project file attachments, real-time WebSocket collaboration).

---

## ✅ What Swift Already Has (parity)

- Auth (login, refresh, keychain, session restore)
- Thread list + filters (active/finalized/archived) + pin/archive
- Thread chat with SSE streaming
- Markdown message rendering + metadata panels
- Node / Compliance / Payer mode toggles
- Compliance decision tree + reasoning panel (multi-level jurisdiction display)
- Model picker, light/dark theme, version history, finalize, revert
- PDF preview panel (offer letter, review, handbook, workbook, onboarding, presentation)
- Image upload for presentations (up to 4)
- Resume batch panel (upload, sort, search, send/sync interviews)
- Inventory panel (upload, sort, search, category filter)
- Project list + detail + sections (create/edit/delete) + section editor with auto-save
- Project chats + project export (PDF/MD/DOCX)
- Project collaborators (search, add, remove)
- Email Agent (Gmail connect/disconnect/fetch/draft/send)
- Inbox: conversations, messages, compose, attachments, unread count polling, mute, mark-read, user search
- Presence (heartbeat + online list)
- Token usage summary view
- Skills/feature-discovery landing view

---

## ❌ Gaps — Missing in Swift

### 🔴 Tier 1 — Entire Top-Level Surfaces

Whole sidebar sections / pages with no Swift equivalent.

#### 1. Channels (community / paid channels)
**Web files:** `pages/work/ChannelView.tsx`, `pages/work/ChannelBilling.tsx`, `api/channels.ts`
- Free + paid channels (browse, create, join by invite code)
- Real-time WebSocket messaging (`ChannelSocket`), typing indicators, online users
- File uploads in channels
- Members management: join/leave, kick, role assignment (admin/moderator/member)
- Paid channel checkout, tip modal, channel analytics
- Channel job postings, voice calls (`useVoiceCall`)
- APIs: `GET/POST/PATCH /matcha-work/channels`, `.../join`, `.../leave`, `.../members/{id}/kick`, `.../members/{id}/role`, `.../payment-info`, `.../checkout`, `.../files`

#### 2. Task Board
**Web files:** `components/work/TaskBoard.tsx`, tab in `pages/work/MatchaWorkList.tsx`
- Auto-generated + manual tasks
- Fields: title, description, due_date, priority, horizon (today/upcoming/overdue), categories, link
- APIs: `GET/POST/PATCH/DELETE /matcha-work/tasks`, `POST .../tasks/dismiss`

#### 3. Connections / People Panel
**Web files:** `components/work/ConnectionsPanel.tsx`, route `/work/connections`
- Pending connection requests inbox
- API: `GET /matcha-work/pending-connections`

#### 4. Billing & Subscriptions (Personal Plus)
**Web files:** `api/matchaWork.ts` billing helpers, sidebar footer
- Subscription status display (`GET /matcha-work/billing/subscription`)
- "Upgrade to Plus" checkout flow (`POST /matcha-work/billing/checkout/personal`)
- Stripe redirect handling

#### 5. Language Tutor (full task type)
**Web files:** `components/matcha-work/LanguageTutorPanel.tsx`
- Language picker (en, es-mx, fr) + duration picker
- WebSocket real-time voice conversation (Web Audio API mic + speaker)
- Live transcript
- CEFR-level analysis (fluency, vocabulary, grammar) with score visualization
- Inline utterance error detection
- APIs: `POST .../tutor/start`, `GET .../tutor/status`, `POST .../tutor/check`

#### 6. Hiring Clients (Personal recruiting)
**Web files:** `components/matcha-work/HiringClientPickerModal.tsx`
- CRUD for personal-mode hiring clients (name, website, logo, notes)
- Archive/unarchive
- Project sidebar grouping by client
- APIs: `GET/POST/PATCH /matcha-work/recruiting-clients`, `.../archive`, `.../unarchive`

#### 7. Recruiting Pipeline Project Type
**Web files:** `components/matcha-work/RecruitingPipeline.tsx`, `RecruitingWizard.tsx`
- Tabs: status / posting / candidates / interviews / shortlist
- Job posting editor with `[bracketed]` placeholder extraction & guided fill
- Candidate analyze + shortlist + dismiss
- Recruiting wizard (guided setup)
- APIs: `PUT .../posting`, `POST .../posting/from-chat`, `POST .../placeholder-questions`, `POST .../extract-value`, `POST .../resume/analyze`, `POST .../shortlist/{id}`, `POST .../dismiss/{id}`

> Swift's `MatchaWorkService` has stubs for shortlist/posting, but no UI.

---

### 🟡 Tier 2 — Missing Sub-Features Inside Existing Surfaces

#### Threads
- **Real-time WebSocket collaboration** (`ThreadSocket`): online users, typing indicators, live message sync between collaborators. Swift only does SSE for own messages.
- **Thread collaborators UI** (`components/matcha-work/ThreadCollaborators.tsx`): list/add/remove on threads (Swift has it for projects only). APIs: `GET/POST/DELETE /matcha-work/threads/{id}/collaborators`, `.../collaborators/search`
- **Skills selector grid in chat** (icon grid for picking task type, prompt auto-population). Swift has the SkillsView landing page but not the in-chat picker.
- **`agent_mode` toggle** (experimental local)
- **PATCH thread title** edit affordance in UI
- **Thread types not surfaced**: `project`, `language_tutor` task types exist in models but no Swift UI path

#### Projects
- **Section reordering UI** (drag-and-drop). API exists in service, no view.
- **File attachments**: upload/list/delete files on projects (PDF/DOCX/TXT/CSV/XLSX/images/SVG/PPTX/MD). APIs: `GET/POST/DELETE /matcha-work/projects/{id}/files`
- **Diagrams in sections**: SVG diagram embedding + AI-edit + manual-text-edit + save (`DiagramEditor.tsx`). APIs: `POST .../sections/{id}/edit-diagram`, `.../edit-diagram-text`, `.../save-diagram`
- **Research Tasks** (substantial subsystem): create tasks, add URL inputs, run with SSE streaming, retry per-input, follow-up, stop. APIs: `POST/PUT/DELETE .../research-tasks`, `POST .../research-tasks/{id}/run`, `.../inputs/{id}/retry`, `.../inputs/{id}/follow-up`, `.../research-tasks/{id}/stop`
- **Project invitations by email** (separate from search-based collaborators): invite/accept/decline + pending invites list. APIs: `POST .../invite`, `.../invite/accept`, `.../invite/decline`, `GET /matcha-work/project-invites`

#### Presentations
- **Slide-by-slide editor**: cover slide, navigation, speaker notes, theme picker (professional/minimal/bold), edit slide content (web `PresentationPanel.tsx`). Swift only renders the generated PDF.
- **Generate endpoint trigger from UI**: `POST /matcha-work/threads/{id}/presentation/generate`

#### Resume Batch
- **Match scoring display** (`match_score`, `match_summary`) — verify Swift renders
- **Interview review modal** (`InterviewReviewModal.tsx`) for viewing screening analysis (communication_clarity, engagement_energy, critical_thinking, professionalism + recommendation)

#### Compliance Mode
- **Business locations selector**: `GET /compliance/locations` to scope compliance mode. Verify Swift loads + displays.
- **Compliance gaps display** (category, label, status) — confirm Swift renders this metadata.

---

### 🟢 Tier 3 — Polish / Minor Gaps

- Sidebar "Upgrade to Plus" footer (personal users, inactive subscription)
- Thread PDF proxy route handling (`.../pdf/proxy`)
- Markdown-to-HTML renderer parity (`components/matcha-work/markdownToHtml.ts`) — code blocks, syntax highlighting, tables
- Multi-period usage summary display parity

---

## Critical Files — Web Side (reference)

```
client/src/components/work/WorkSidebar.tsx          ← sidebar shape, all top-level surfaces
client/src/components/work/TaskBoard.tsx
client/src/components/work/ConnectionsPanel.tsx
client/src/components/matcha-work/PresentationPanel.tsx
client/src/components/matcha-work/RecruitingPipeline.tsx
client/src/components/matcha-work/RecruitingWizard.tsx
client/src/components/matcha-work/LanguageTutorPanel.tsx
client/src/components/matcha-work/HiringClientPickerModal.tsx
client/src/components/matcha-work/ThreadCollaborators.tsx
client/src/components/matcha-work/InterviewReviewModal.tsx
client/src/components/matcha-work/DiagramEditor.tsx
client/src/pages/work/ChannelView.tsx
client/src/pages/work/ChannelBilling.tsx
client/src/pages/work/ProjectView.tsx               ← research tasks, files, diagrams wiring
client/src/api/matchaWork.ts                        ← canonical API surface
client/src/api/channels.ts
client/src/types/matcha-work.ts                     ← types to mirror in MatchaWorkModels.swift
```

## Critical Files — Swift Side (where ports land)

```
desktop/Matcha/Matcha/Views/MatchaWork/             ← new view files
desktop/Matcha/Matcha/ViewModels/                   ← matching VMs
desktop/Matcha/Matcha/Services/MatchaWorkService.swift  ← extend with new endpoints
desktop/Matcha/Matcha/Models/MatchaWorkModels.swift     ← mirror new types
desktop/Matcha/Matcha/App/ContentView.swift             ← sidebar tab additions
desktop/Matcha/Matcha/App/AppState.swift                ← new global state (channels, tasks)
```

A new `Services/ChannelsService.swift` will likely be needed (parallel to `InboxService.swift`), plus a Swift WebSocket client (`URLSessionWebSocketTask`) for `ThreadSocket` + `ChannelSocket` parity.

---

## Open Questions to Prioritize

1. Which Tier 1 surfaces are **must-have** vs. nice-to-have? (Channels, Tasks, Connections, Billing, Language Tutor, Hiring Clients, Recruiting Pipeline)
2. Do you actively use the **WebSocket real-time collab** features, or is SSE-only fine for Swift?
3. Should the Swift app target **personal mode** features (hiring clients, personal billing) or only **company/HR mode**?
4. Is **Research Tasks** in projects wanted on macOS, or web-only?
