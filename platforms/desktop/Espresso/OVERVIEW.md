# Werk — Product Overview

Werk is the macOS desktop client for the Matcha collaborative AI workspace. It brings together team messaging, AI-assisted document creation, project management, and shared journals into a single native app — designed for HR, operations, and people teams who need to move fast without switching between tools.

---

## Navigation & Layout

The app is organized around a persistent left sidebar and a detail pane on the right.

**Sidebar** contains four sections — Channels, Projects, Journals, and Threads — each draggable to reorder. Starred items surface at the top for quick access. Inbox and People buttons anchor the footer.

**Tab bar** sits above the detail pane. Pin up to four items (channels, projects, threads, or journals) as persistent tabs for fast switching without losing your place.

**Side pane** keeps a second surface open beside whatever you're working in, such as a thread with your calendar next to it. Open one with ⌘\\ (it brings back the last one), the split button in the toolbar, ⌥-click on a sidebar row, View ▸ Open Beside (⌥⌘1–8), or "Open Beside" on any row's context menu. ⌘F can send any result to the side or bottom pane.
- The pane's dock flips it between Calendar, Journals, Kanban, Espresso, Channels, Threads, Email and Workspaces. Lists open the item in the pane, and Back returns.
- Header buttons swap the pane with the main one, move it to the bottom, pop it out to a window, or close it.
- In a pane each surface uses a narrower layout and never moves the main pane:
  - The calendar puts the day's agenda under the grid.
  - Kanban picks its board from the title.
  - Email opens a message over the list.
  - Pane shortcuts such as ⌘T stay off, so they can't fire while you type next door.

**Themes** — Light, Dark, and Cappuchin (warm brown) — are selectable from Settings.

---

## Channels & Messaging

Channels are real-time chat spaces organized by topic or team.

- Create, browse, and join channels across categories (General, Engineering, Design, Sales, HR, Marketing, Announcements, and more)
- Send messages with attachments, reply to specific messages in threads, react with emoji, edit or delete your messages, and mention teammates by handle
- Pin or star channels to keep important spaces at the top of your sidebar
- Unread counts appear on channel entries and the app icon

**Live Broadcasts** let any channel member start an audio/video stream. Others join as viewers or co-publishers. Weekly broadcast limits apply per subscription tier.

**Notifications** appear as in-app toasts (stacked, auto-dismissed) and as macOS system notifications when the app is in the background.

---

## AI Threads

Threads are AI-assisted conversations where you describe what you need and the assistant produces a structured document or response.

Supported task types:

| Type | What it produces |
|---|---|
| Offer Letter | Drafted offer with candidate name, role, and compensation |
| Employee Handbook | Full or partial handbook sections |
| Presentation | Slide-by-slide outline and content |
| Employee Onboarding | Onboarding plan for one or more employees |
| Resume Batch | Parsed and scored candidates from uploaded resumes |
| Inventory | Structured inventory list |
| HR Workbook | Multi-section workbook |
| Anonymized Review | Performance review with overall rating |
| Policy | Policy document for a given topic |
| Blog | Draft blog post |
| Language Tutor | Language learning conversation |
| Chat | General-purpose AI conversation |

**Compliance mode** layers jurisdiction-aware legal reasoning on top — the AI cites applicable rules by location and flags compliance gaps.

Documents can be exported as PDFs. Every AI reply creates a version, and you can browse the full version history or revert to any prior draft.

---

## Projects

Projects are workspaces for ongoing work. Six project types cover the most common team needs:

**General** — Free-form workspace with editable sections, a kanban board, and task management. Tasks have titles, descriptions, priorities, due dates, assignees, progress notes, and attachments. The board supports category-based templates (Engineering, Sales, Product, Bug, General, Research) with scaffolded columns; a Research card assigned to the AutoPR bot comes back with a report under its attachments instead of a PR.

**Presentation** — Slide-oriented layout for building decks.

**Blog** — Rich text editor with cover image, author metadata, SEO fields (slug, excerpt, audience, tone), tags, word count, read time, and publishing states (draft, scheduled, published).

**Recruiting** — Resume pipeline with parsed candidate profiles (name, contact, experience, skills, education), match scoring, interview scoring, shortlisting, and bulk interview request sending.

**Collab** — Shared team workspace for collaborative writing and planning.

**Discipline** — Structured workflow for employee disciplinary cases.

All project types support:
- File uploads with previews — images, PDFs, CSV tables, text; Markdown opens rendered with a Rendered | Source toggle
- Adding and removing collaborators
- Real-time presence (see who is active in the project)
- Activity feed (task moves, file uploads, collaborator additions)

Repo-connected project discussions also expose **@espresso**, a read-only
repository guide. Mention it with a question about how the app or a feature
works; it completes a background, source-grounded read and posts the answer
back into the project chat without changing code or opening a pull request.

On a repo-connected project board, **Describe a task to draft** uses that same
read-only run lifecycle, but deliberately keeps repository context small:
Espresso reads the root `CLAUDE.md` or `AGENTS.md` architecture guide and then
opens an editable ticket review with a scoped description, checklist, and cited
guidance. Nothing is added to the board until the user reviews the fields and
clicks Create. Projects without a repo keep the simpler one-shot draft fallback.

---

## Journals

Journals are shared writing spaces for teams or individuals.

- The workspace has a journal list and editor. Click the list's folder title to
  browse All Journals, Starred, Shared with me, Uncategorized, or your folders;
  the same picker creates, renames, colors and nests folders.
- Below 760 points of workspace width, **Browse journals** opens the searchable
  list in a popover. The editor stays mounted as the list folds, preserving the
  draft and undo history when opening a side pane or resizing the window.
- **Quick Note** in the window toolbar (⌥⌘N) creates a blank note in your Notes
  folder and opens it beside your current work. It autosaves through the normal
  journal editor and remains available in Journals. **New note** or ⌘N inside
  Journals creates in the selected folder (Uncategorized stays unfiled).
- Create journals with a custom color and icon
- Write entries with a title, date, and rich text content
- Invite collaborators and manage their permissions
- Browse and edit entries from the detail pane

---

## Calendar

The Calendar tab is your own calendar, in a month or week view with the selected day's agenda beside it.

- Create, edit, move (drag to another day) and delete events; timed or all day
- Dated to-dos from your Productivity boards show on their day and can be checked off
- Connect Google (calendar access) and your Google Calendar shows alongside, read-only
- Ask Espresso to put things on it ("lunch with Sam Friday at noon", "add the dinner from Dana's email"); events it adds say so, and its answers link back to the day
- In Email, **Add to calendar** reads the open message and proposes its events. Tell it what you want ("only the dinner"), fix anything it got wrong, and nothing is added until you press Add. Events from an email link back to it

## Inbox

Inbox is the direct message surface for one-on-one and group conversations.

- Start conversations by searching for teammates
- Send messages with attachments
- See unread counts per conversation
- Mute conversations you don't need active alerts for

---

## People & Connections

The People view shows your team directory and lets you manage connection requests. Pending requests surface with a badge count.

---

## Home Dashboard

The Home screen gives a single view across your active work:

- **Active Projects** — top projects currently in progress
- **In-Flight Blogs** — drafts and scheduled posts not yet published
- **Open Tasks** — tasks assigned to or created by you, across all projects
- **Recent Activity** — unified feed of recent threads, projects, and task updates
- **Project Invitations** — pending invites waiting for your response

---

## Settings & Subscription

**Settings** covers theme selection, notification preferences, and account management.

**Matcha Plus** is the premium subscription tier. Upgrading unlocks extended broadcast limits and additional workspace features. Subscription is managed through Stripe and can be started or viewed from within the app.
