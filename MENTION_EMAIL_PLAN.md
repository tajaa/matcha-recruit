# @-Mention Email Notifications (Channels)

## Context

In matcha-work channels, there's currently no way to grab a specific person's attention inside a busy channel. Users want Slack-style `@username` mentions that:

1. Trigger an email to the mentioned user **only when they're offline** (not actively connected to the channels WS).
2. Are scoped to **channels only** — not DMs, not threads, not project chat.
3. Apply to both surfaces: web (`/work/channels/...`) and werk (macOS desktop).

The acquisition / engagement value: a user who returns to the app because they got an email saying "Aaron mentioned you" is one of the highest-quality re-engagement signals. Doubles as a notification path for users who haven't enabled OS push yet.

## Implementation

### Backend

**Mention parsing** — extract from message content server-side; never trust the client.

- New helper `parse_mentions(content: str) -> set[str]` in `server/app/matcha/services/mentions.py` (new file). Regex: `@([a-zA-Z0-9_.\-]{2,32})` (alphanumeric + `_`, `.`, `-`, length-bounded). Returns deduped lowercase handles.
- Resolve handles → user IDs by querying `channel_members` joined to `users.handle` (or `users.email_handle` — TBD per actual schema; check `users` table for the canonical mention-by name field). Only resolve to users who are members of the channel — silently drop mentions of non-members (don't email outsiders).
- Bonus: support `@everyone` and `@here` as reserved handles (skip for v1; flag in out-of-scope).

**Hook into message create** — `server/app/core/routes/channels_ws.py:409` (the INSERT). After the insert succeeds and BEFORE `broadcast_message` at line 454:

```python
mention_user_ids = await resolve_mentions(conn, channel_id, content, exclude_user_id=user_id)
if mention_user_ids:
    # Stamp into the broadcast payload so the live client can render mention
    # styling (bold, badge) without re-parsing.
    message_payload["mentioned_user_ids"] = list(map(str, mention_user_ids))
    # Enqueue offline-email check off the WS hot path.
    from app.workers.tasks.mention_email import enqueue_mention_email
    enqueue_mention_email.delay(
        message_id=str(message_id),
        channel_id=channel_id,
        sender_id=str(user_id),
        mentioned_user_ids=[str(uid) for uid in mention_user_ids],
    )
```

The `exclude_user_id=user_id` argument prevents users from emailing themselves with a self-mention.

**Offline detection + Celery task** — `server/app/workers/tasks/mention_email.py` (new):

```python
@app.task(bind=True, max_retries=3, default_retry_delay=30)
def send_mention_email(self, message_id, channel_id, sender_id, mentioned_user_ids):
    asyncio.run(_send_mention_email_async(...))

async def _send_mention_email_async(...):
    # 1. Pull message + channel + sender details from DB
    # 2. For each mentioned user:
    #    a. Skip if user has disabled mention emails (notif_prefs.mention_email = false)
    #    b. Skip if user is currently online — i.e. `user_id in manager.active_connections`
    #       (need to expose this via a small RPC since the worker is in a separate
    #       process from the WS server. Use Redis: WS server writes a key
    #       `channels_ws:online:{user_id}` with TTL 30s on each connect/heartbeat;
    #       worker checks that key.)
    #    c. Skip if user has received a mention email for this channel within the
    #       throttle window (15 min default, configurable per user).
    #    d. Send email via EmailService.send_mention_notification(...)
    #    e. Stamp throttle key in Redis: `mention_email:throttle:{user_id}:{channel_id}` with 15min TTL
```

**Online presence in Redis** — `server/app/core/routes/channels_ws.py`:

In `connect_user` (~line 60) and on each WS receive (cheap heartbeat), `await redis.setex(f"channels_ws:online:{user_id}", 30, "1")`. In `disconnect_user` (~line 68), `await redis.delete(f"channels_ws:online:{user_id}")`. The worker checks this key — if present, user is "online" and gets no email.

Single key per user (not per WS) — handles the multi-tab/multi-device case correctly via the disconnect cleanup; if the user has any active WS, the key is fresh.

**Email template** — extend `server/app/core/services/email.py` with `send_mention_notification(to_email, sender_name, channel_name, message_excerpt, channel_url)`. Subject: `"[matcha] {sender_name} mentioned you in #{channel_name}"`. Body: short HTML — sender, channel, first ~200 chars of the message, "Open in Matcha" CTA linking to `https://hey-matcha.com/work/channels/{channel_id}` (web client; werk users with the URL handler installed will deep-link automatically).

**User notification preferences** — small migration:

```sql
ALTER TABLE users
ADD COLUMN notification_prefs JSONB NOT NULL DEFAULT '{}'::jsonb;
-- Default keys: {"mention_email": true, "mention_email_throttle_min": 15}
```

Per CLAUDE.md DB rules: write the migration as `server/alembic/versions/XXXX_add_user_notification_prefs.py`, **do not run** — user must execute against prod manually.

User-facing settings UI: `client/src/pages/Settings.tsx` (or wherever profile prefs live — confirm during build) → toggle for "Email me when I'm @-mentioned in a channel and I'm offline". Werk: add to ProfileSheet or a new SettingsView.

**Sender's view: render mentions in the broadcast** — already wired via `mentioned_user_ids` field on the broadcast payload above. Frontend uses this to highlight the mention chip without re-parsing the content.

### Frontend — Web (matcha-work)

- `client/src/components/channels/ChannelMessageInput.tsx` (or equivalent — confirm during build) — add `@`-trigger autocomplete dropdown:
  - On `@` keystroke, open dropdown with channel members (fetch via existing `GET /api/matcha-work/channels/:id/members` — confirm endpoint).
  - Filter as user types after `@`.
  - Insert `@handle ` on selection; track inserted-mention spans for visual rendering.
- `client/src/components/channels/ChannelMessage.tsx` — render `@handle` substrings as styled mention chips (use `mentioned_user_ids` from server payload to confirm valid mentions; unrecognized `@foo` renders as plain text).
- Self-mentions get a distinct highlight (`bg-yellow-500/20`) and trigger an in-app sound + temporary badge in the channel sidebar.

### Frontend — Werk (macOS desktop)

- `desktop/Werk/Matcha/Views/Channels/ChannelDetailView.swift` — extend `inputBar` (search for the existing `inputText` TextEditor binding):
  - Detect `@` keystroke, present a SwiftUI `Popover` anchored to the cursor with a filtered member list.
  - Member list source: `vm.channel?.members` (already in the VM after the recent refactor).
  - On selection: insert `@handle ` into `inputText`.
- `messageRow(_ msg:)` (~line 438 of ChannelDetailView.swift) — parse mention chips from `msg.content` against `msg.mentionedUserIds` (new field on `ChannelMessage` — needs decoding update in `ChannelModels.swift`).
- Self-mention triggers `ChannelNotificationManager.playInAppSound()` + a more prominent badge.

### Critical files

- `server/app/matcha/services/mentions.py` — new, parse + resolve.
- `server/app/core/routes/channels_ws.py:~409-454` — hook between insert and broadcast.
- `server/app/core/routes/channels_ws.py:~60,~68` — Redis online-key set/delete.
- `server/app/workers/tasks/mention_email.py` — new Celery task.
- `server/app/workers/celery_app.py` — register task.
- `server/app/core/services/email.py` — new `send_mention_notification` method.
- `server/alembic/versions/XXXX_add_user_notification_prefs.py` — new migration (do not auto-run).
- `client/src/components/channels/ChannelMessageInput.tsx` — autocomplete.
- `client/src/components/channels/ChannelMessage.tsx` — render chips.
- `desktop/Werk/Matcha/Views/Channels/ChannelDetailView.swift` — popover + chip rendering.
- `desktop/Werk/Matcha/Models/ChannelModels.swift` — add `mentionedUserIds: [String]?` to `ChannelMessage`.

### Reused functions / utilities

- `EmailService.send_email` (email.py:74) — base email sender.
- `manager.active_connections` (channels_ws.py:51) — informs the Redis online key. (Worker can't read in-process dict, so Redis is the bridge.)
- Existing Celery infra (`server/app/workers/celery_app.py`) and Redis connection.
- `vm.channel?.members` on werk — already loaded by `ChannelChatViewModel`, no new fetch needed.

## Out of Scope

- DMs / threads / project chat — channels only per requirement.
- `@everyone` / `@here` group mentions — defer to v2; risk of being abusive without rate-limit logic.
- Push notifications (OS-level) — separate path; `ChannelNotificationManager` already handles starred channels.
- In-app mention badge / inbox surface — useful follow-up but not in scope.
- Rich mention autocomplete with avatars — v1 ships text-only handles; avatars later.
- Editing/deleting messages with mentions does not retroactively trigger emails or undo throttle.
- Web composer full rich-text editing changes — keep current textarea + minimal autocomplete dropdown overlay; defer to ContentEditable / Lexical migration.

## Verification

1. **Mention parses correctly:**
   - Send `Hey @aaron, can you check this?` in a channel where `aaron` is a member. Confirm `mentioned_user_ids` arrives in WS broadcast and renders as a chip on both web and werk.
   - Send `Email @nobody-here` (non-member). Confirm no chip, no email enqueued.
2. **Offline-only email:**
   - Aaron is connected (active WS) → mention him from a different account. Confirm NO email sent (check Celery logs / mail server logs).
   - Aaron disconnects (close all werk + browser tabs) → mention him again. Confirm email arrives within ~30s.
3. **Throttle:**
   - Aaron offline, 5 mentions in same channel within 1 min → confirm only ONE email sent.
   - Wait 16 min, mention again → confirm second email sent.
4. **Self-mention:**
   - Send `@self-handle test` from your own account → confirm no email sent to yourself.
5. **Pref toggle:**
   - Settings → disable mention emails → mention while offline → confirm no email.
   - Re-enable → confirm next mention while offline triggers email.
6. **Multi-device online detection:**
   - Aaron online on werk + offline on web → mention him → confirm NO email (any active connection counts as online).
   - Close werk, web stays closed → wait 30s → mention → confirm email.
7. **Email content:**
   - Subject matches `[matcha] {Sender} mentioned you in #{channel}`.
   - Body shows sender name, channel name, first 200 chars of message, working CTA URL that lands in the right channel.
8. **Tests:**
   - Unit test `parse_mentions` for: empty, single, multiple, deduped, casing, edge characters (`-`, `.`, `_`), too-short handles (`@a` → ignored), too-long handles (>32 chars → ignored).
   - Integration test (manual per CLAUDE.md DB rules): full pipeline from message-send to email arrival in inbox of a test user with throttle-key inspection in Redis.

## Open Questions

- **Username field**: Is `users.handle` the canonical lookup field, or do we use `email_handle`, or first/last name slug? Confirm against the actual schema before coding `resolve_mentions`. Recommend adding a dedicated `users.handle` text column if it doesn't exist (defaulted from email local-part).
- **Online TTL**: 30s ping interval is conservative; could go to 60s if WS heartbeat is reliable. Stick with 30s for v1 — false-positive offline (sending an unwanted email) is worse than the small Redis write cost.
- **CTA URL routing**: web URL `https://hey-matcha.com/work/channels/{id}` — does the werk app's URL scheme handler already deep-link channels? If not, add `matcha://channel/{id}` and parse it in werk's `MatchaApp.swift` URL handler.
- **Throttle window**: 15-min default is sensible; expose as user pref so power users can dial down.
