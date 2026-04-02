---
name: Inbox messaging system status
description: Current state of inbox feature — working but needs PFP/avatar support and sidebar reorganization
type: project
---

Inbox messaging system was built in this session and is functional.

**What's done:**
- Backend: 8 endpoints under /api/inbox/ (conversations, messages, search, unread count, mute)
- Frontend: Inbox.tsx page, ConversationList, MessageThread, ComposeModal
- DB: inbox_conversations, inbox_participants, inbox_messages, inbox_email_batches tables
- Route: /app/inbox in sidebar nav
- User search: all platform users by name/email ILIKE
- Email notifications: batched at 15min intervals

**Known pending work:**
1. Profile picture / avatar support — users need a way to upload a PFP in settings, stored on users table, displayed in inbox conversation list and message thread
2. Sidebar reorganization — ClientSidebar.tsx needs features grouped by category (e.g., HR Ops, Compliance, Communication, AI Tools)
3. Compose modal Send button may have a state issue — user reported it stays disabled after selecting recipient + typing message. Needs debugging with browser console.

**Why:** User wants inbox to feel personal with avatars, and sidebar is getting long (19 items) and needs categorical organization.

**How to apply:** Check ClientSidebar.tsx for current nav items. Check users table for avatar_url column (may need adding). The inbox components are in client/src/components/inbox/.
