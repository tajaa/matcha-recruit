import type { ChannelMessage, ChannelReaction } from './channels'
import type { MWNotification } from './notifications'
import { BaseSocket } from './baseSocket'
import { getAccessToken } from '../../api/authStorage'

type MessageHandler = (msg: ChannelMessage) => void
type TypingHandler = (user: { id: string; name: string }) => void
type OnlineHandler = (users: { id: string; name: string; avatar_url: string | null }[]) => void
type UserEventHandler = (user: { id: string; name: string }) => void
type ChannelActionUpdate = { channel_id: string; action: { kind: string; id: string; status: string } }
type ChannelActionHandler = (update: ChannelActionUpdate) => void
type NotificationHandler = (notification: MWNotification) => void

/** Tab-session outbox for sends attempted while the socket was down. It
 * survives reconnects/reloads but not a closed browser session, so message
 * content is not left in persistent origin storage. Replay is safe because the
 * server INSERT is idempotent on (sender_id, client_message_id). */
type OutboxEntry = {
  channel_id: string
  content: string
  attachments?: { url: string; filename: string; content_type: string; size: number }[]
  client_message_id: string
  reply_to_id?: string
  queued_at: number
}
const OUTBOX_KEY_PREFIX = 'channels_outbox_v1'
const OUTBOX_CAP = 50
// Outbox survived across logins on a shared browser under a single global
// key — user B's login would replay user A's still-queued send under B's
// sender_id. Scope the key to the JWT's `sub` claim (decoded client-side,
// no verification needed — it's a storage namespace, not a security check).
function _outboxKeyForToken(token: string | null): string {
  if (token) {
    try {
      const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
      if (payload?.sub) return `${OUTBOX_KEY_PREFIX}:${payload.sub}`
    } catch { /* fall through to unscoped key */ }
  }
  return OUTBOX_KEY_PREFIX
}
function _currentOutboxKey(): string {
  return _outboxKeyForToken(getAccessToken())
}
/** Called from api/client.ts's logout, with the token that was still valid
 * a moment ago (by the time the lazy import resolves, the token is already
 * cleared, so _currentOutboxKey() would derive the wrong — unscoped — key). */
export function clearChannelOutbox(tokenAtLogout: string | null) {
  try {
    sessionStorage.removeItem(_outboxKeyForToken(tokenAtLogout))
  } catch { /* best-effort */ }
}
/** Drop entries no live socket ever managed to flush past this age — a
 * fresh page load can flush before rejoin() re-establishes room membership,
 * so a message can persist server-side yet never get an echo back (echo is
 * room-scoped) and sit in sessionStorage forever with nothing to remove it. */
const OUTBOX_MAX_AGE_MS = 10 * 60 * 1000

/** Shared add/remove/dispatch boilerplate for a Set-backed listener group.
 * Dispatch swallows per-listener errors so one bad/stale listener can't
 * break the others sharing this socket. */
class ListenerSet<T> {
  private listeners: Set<(arg: T) => void> = new Set()

  add(handler: (arg: T) => void) {
    this.listeners.add(handler)
  }

  remove(handler: (arg: T) => void) {
    this.listeners.delete(handler)
  }

  dispatch(arg: T) {
    for (const fn of this.listeners) {
      try { fn(arg) } catch { /* swallow so one bad listener doesn't kill others */ }
    }
  }
}

export class ChannelSocket extends BaseSocket {
  private joinedRooms: Set<string> = new Set()
  private messageListeners = new ListenerSet<ChannelMessage>()
  private channelActionListeners = new ListenerSet<ChannelActionUpdate>()
  private notificationListeners = new ListenerSet<MWNotification>()

  // Deprecated single-handler; kept for backward compat. Setting this adds
  // the handler to the multi-listener set. Prefer addMessageListener.
  set onMessage(handler: MessageHandler | null) {
    if (handler) this.messageListeners.add(handler)
  }
  get onMessage(): MessageHandler | null {
    return null
  }

  addMessageListener(handler: MessageHandler) {
    this.messageListeners.add(handler)
  }

  removeMessageListener(handler: MessageHandler) {
    this.messageListeners.remove(handler)
  }

  addChannelActionListener(handler: ChannelActionHandler) {
    this.channelActionListeners.add(handler)
  }

  removeChannelActionListener(handler: ChannelActionHandler) {
    this.channelActionListeners.remove(handler)
  }

  addNotificationListener(handler: NotificationHandler) {
    this.notificationListeners.add(handler)
  }

  removeNotificationListener(handler: NotificationHandler) {
    this.notificationListeners.remove(handler)
  }

  onTyping: TypingHandler | null = null
  onOnlineUsers: OnlineHandler | null = null
  onUserJoined: UserEventHandler | null = null
  onUserLeft: UserEventHandler | null = null
  onMessageDeleted: ((data: { channel_id: string; message_id: string; deleted_by: string }) => void) | null = null
  onMessageEdited: ((data: { channel_id: string; message_id: string; content: string; edited_at: string | null }) => void) | null = null
  onReactionUpdate: ((data: { channel_id: string; message_id: string; reactions: ChannelReaction[] }) => void) | null = null
  onChannelActionUpdated: ((data: { channel_id: string; action: { kind: string; id: string; status: string } }) => void) | null = null
  // LiveKit SFU call lifecycle callbacks (werk-lite). The server fans these out
  // over the same /ws/channels socket as the call's roster changes; the
  // useLiveKitCall hook drives the join banner + auto-teardown off them.
  onCallStarted: ((data: { channel_id: string; call_id: string; started_by: string; started_at: string; mode: string; max_participants: number }) => void) | null = null
  onCallEnded: ((data: { channel_id: string; call_id: string; reason?: string }) => void) | null = null
  onCallParticipantsChanged: ((data: { channel_id: string; call_id: string; participant_ids: string[]; count: number; max_participants: number }) => void) | null = null
  onCallInvited: ((data: { channel_id: string; call_id: string; invited_by: string }) => void) | null = null
  // Server-side rejection of a join_room/message send (not a member, bad
  // channel id, over 4000 chars, ...) — previously discarded entirely
  // (no 'error' case below), so a message sat as a ghost 'pending' row
  // forever with no user-visible signal of why it never persisted.
  // `channelId`/`clientMessageId` let a listener scope the error to the
  // channel/message it actually concerns — the socket is shared across
  // every joined room, so an unscoped error would otherwise blank
  // whichever channel view happens to be open.
  onServerError: ((message: string, details: { channelId?: string; clientMessageId?: string }) => void) | null = null
  // Cross-device read-state push (Phase 1's mark_read WS frame / Phase 2's
  // GET /channels/{id}) — another of this user's devices marked a channel
  // read; the sidebar badge should zero to match.
  onChannelRead: ((data: { channel_id: string }) => void) | null = null

  protected path() {
    return '/ws/channels'
  }

  protected rejoin() {
    // Rejoin every room we were in. The set survives a reconnect precisely so
    // this can replay it; it's only cleared on an explicit disconnect().
    for (const room of this.joinedRooms) {
      this.send({ type: 'join_room', channel_id: room })
    }
    // After membership is re-established: replay anything queued while down.
    this._flushOutbox()
  }

  private _flushRetryTimeout: ReturnType<typeof setTimeout> | null = null

  private _readOutbox(): OutboxEntry[] {
    try {
      const raw = sessionStorage.getItem(_currentOutboxKey())
      return raw ? (JSON.parse(raw) as OutboxEntry[]) : []
    } catch {
      return []
    }
  }

  private _writeOutbox(entries: OutboxEntry[]) {
    try {
      sessionStorage.setItem(_currentOutboxKey(), JSON.stringify(entries.slice(-OUTBOX_CAP)))
    } catch { /* quota — drop rather than crash the send path */ }
  }

  private _enqueueOutbox(entry: OutboxEntry) {
    const rest = this._readOutbox().filter((e) => e.client_message_id !== entry.client_message_id)
    this._writeOutbox([...rest, entry])
  }

  removeFromOutbox(clientMessageId: string) {
    const entries = this._readOutbox()
    const rest = entries.filter((e) => e.client_message_id !== clientMessageId)
    if (rest.length !== entries.length) this._writeOutbox(rest)
  }

  private _flushOutbox() {
    if (this._flushRetryTimeout) {
      clearTimeout(this._flushRetryTimeout)
      this._flushRetryTimeout = null
    }
    const now = Date.now()
    const all = this._readOutbox()
    const entries = all.filter((e) => now - e.queued_at < OUTBOX_MAX_AGE_MS)
    if (entries.length !== all.length) this._writeOutbox(entries)
    if (!entries.length) return
    // A queued send's room may not be in joinedRooms yet — on a fresh page
    // load rejoin() runs before useChannelNotifications has resolved
    // listChannels, so joinedRooms is still empty the first time this fires.
    // The message would still persist server-side (membership is DB-checked,
    // not room_members-checked), but the reply echo is room_members-scoped,
    // so without this the entry would never get removed and would replay on
    // every reconnect forever.
    const rooms = new Set(entries.map((e) => e.channel_id))
    for (const room of rooms) {
      if (!this.joinedRooms.has(room)) {
        this.joinedRooms.add(room)
        this.send({ type: 'join_room', channel_id: room })
      }
    }
    // Keep EVERY flushed entry in storage regardless of send()'s return
    // value — a synchronous WebSocket.send() success only means the frame
    // reached the local send buffer, not that the server accepted it (rate
    // limiting is discovered later, async, via an 'error' frame). Dropping
    // an entry here as soon as send() returned true was the actual root
    // cause of HIGH-1: by the time a rate_limited error frame came back for
    // entry #11 of an offline-queued burst, this loop had already removed
    // it from sessionStorage a moment earlier, making the error handler's
    // code branch a no-op. Resolution now happens ONLY via removeFromOutbox,
    // called from the 'message' echo or a permanent 'error' below — a
    // duplicate send on a later retry is safe by design (server INSERT is
    // idempotent on (sender_id, client_message_id)).
    for (const e of entries) {
      this.send({
        type: 'message',
        channel_id: e.channel_id,
        content: e.content,
        ...(e.attachments?.length ? { attachments: e.attachments } : {}),
        client_message_id: e.client_message_id,
        ...(e.reply_to_id ? { reply_to_id: e.reply_to_id } : {}),
      })
    }
  }

  /** Re-drain the outbox at roughly the server's token-bucket refill rate
   * after a rate_limited rejection, instead of bursting the whole queue
   * again immediately (which would just get rate-limited again). */
  private _scheduleOutboxRetry() {
    if (this._flushRetryTimeout) return
    this._flushRetryTimeout = setTimeout(() => {
      this._flushRetryTimeout = null
      this._flushOutbox()
    }, 1200)
  }

  protected clearState() {
    this.joinedRooms.clear()
    if (this._flushRetryTimeout) {
      clearTimeout(this._flushRetryTimeout)
      this._flushRetryTimeout = null
    }
  }

  protected handleMessage(data: Record<string, unknown>) {
    switch (data.type) {
      case 'message': {
        const m = data.message as ChannelMessage
        if (m.client_message_id) this.removeFromOutbox(m.client_message_id)
        this.messageListeners.dispatch(m)
        break
      }
      case 'message_deleted':
        this.onMessageDeleted?.({
          channel_id: data.room as string,
          message_id: data.message_id as string,
          deleted_by: data.deleted_by as string,
        })
        break
      case 'message_edited':
        this.onMessageEdited?.({
          channel_id: data.room as string,
          message_id: data.message_id as string,
          content: data.content as string,
          edited_at: (data.edited_at as string) ?? null,
        })
        break
      case 'reaction_update':
        this.onReactionUpdate?.({
          channel_id: data.room as string,
          message_id: data.message_id as string,
          reactions: data.reactions as ChannelReaction[],
        })
        break
      case 'channel_action_updated':
        {
          const update = {
          channel_id: data.channel_id as string,
          action: data.action as { kind: string; id: string; status: string },
          }
          this.onChannelActionUpdated?.(update)
          this.channelActionListeners.dispatch(update)
        }
        break
      case 'notification': {
        const notification = data.notification as MWNotification | undefined
        if (notification) this.notificationListeners.dispatch(notification)
        break
      }
      case 'typing':
        this.onTyping?.(data.user as { id: string; name: string })
        break
      case 'online_users':
        this.onOnlineUsers?.(data.users as { id: string; name: string; avatar_url: string | null }[])
        break
      case 'user_joined':
        this.onUserJoined?.(data.user as { id: string; name: string })
        break
      case 'user_left':
        this.onUserLeft?.(data.user as { id: string; name: string })
        break
      case 'call.started':
        this.onCallStarted?.(data as never)
        break
      case 'call.ended':
        this.onCallEnded?.(data as never)
        break
      case 'call.participants_changed':
        this.onCallParticipantsChanged?.(data as never)
        break
      case 'call.invited':
        this.onCallInvited?.(data as never)
        break
      case 'error': {
        const cmid = data.client_message_id as string | undefined
        const code = data.code as string | undefined
        if (cmid) {
          if (code === 'rate_limited') {
            // NOT permanent — the send was throttled, not rejected. Deleting
            // the entry here (the old behavior) silently and permanently
            // lost any message past the bucket's burst size on outbox
            // replay, which is exactly the scenario the outbox exists for.
            // Leave it queued and re-drain at roughly the refill rate.
            this._scheduleOutboxRetry()
          } else {
            // Permanently rejected (not a member, over the length cap, ...)
            // — don't replay it forever from the outbox.
            this.removeFromOutbox(cmid)
          }
        }
        this.onServerError?.(data.message as string, {
          channelId: data.channel_id as string | undefined,
          clientMessageId: cmid,
        })
        break
      }
      case 'channel_read':
        this.onChannelRead?.({ channel_id: data.channel_id as string })
        break
    }
  }

  joinRoom(channelId: string) {
    if (this.joinedRooms.has(channelId)) return
    this.joinedRooms.add(channelId)
    this.send({ type: 'join_room', channel_id: channelId })
  }

  leaveRoom(channelId: string) {
    this.send({ type: 'leave_room', channel_id: channelId })
    this.joinedRooms.delete(channelId)
  }

  sendMessage(
    channelId: string,
    content: string,
    attachments?: { url: string; filename: string; content_type: string; size: number }[],
    clientMessageId?: string,
    replyToId?: string,
  ): boolean {
    const sent = this.send({
      type: 'message',
      channel_id: channelId,
      content,
      ...(attachments?.length ? { attachments } : {}),
      ...(clientMessageId ? { client_message_id: clientMessageId } : {}),
      ...(replyToId ? { reply_to_id: replyToId } : {}),
    })
    if (!sent && clientMessageId) {
      this._enqueueOutbox({
        channel_id: channelId, content, attachments,
        client_message_id: clientMessageId, reply_to_id: replyToId,
        queued_at: Date.now(),
      })
    }
    return sent
  }

  sendTyping(channelId: string) {
    this.send({ type: 'typing', channel_id: channelId })
  }

  markRead(channelId: string) {
    this.send({ type: 'mark_read', channel_id: channelId })
  }

}

// Process-wide singleton so the global notification listener and individual
// channel views share one WebSocket connection and one set of joined rooms.
let _sharedSocket: ChannelSocket | null = null
export function getSharedChannelSocket(): ChannelSocket {
  if (!_sharedSocket) {
    _sharedSocket = new ChannelSocket()
  }
  // connect() is idempotent: it bails if already open, and retries here
  // cover the case where the very first connect() ran before the auth token
  // was in the tab session and silently returned. Accessing the socket later
  // (e.g. when the user lands on /work after login) will re-attempt.
  if (!_sharedSocket.hasSocket) {
    _sharedSocket.connect()
  }
  return _sharedSocket
}

export function disconnectSharedChannelSocket() {
  _sharedSocket?.disconnect()
  _sharedSocket = null
}
