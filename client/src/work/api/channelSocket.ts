import type { ChannelMessage, ChannelReaction } from './channels'
import { BaseSocket } from './baseSocket'

type MessageHandler = (msg: ChannelMessage) => void
type TypingHandler = (user: { id: string; name: string }) => void
type OnlineHandler = (users: { id: string; name: string; avatar_url: string | null }[]) => void
type UserEventHandler = (user: { id: string; name: string }) => void

/** Durable outbox for sends attempted while the socket was down. Mirrors
 * Espresso's channels_outbox_v1 (UserDefaults) — safe to blind-replay because
 * the server INSERT is idempotent on (sender_id, client_message_id). */
type OutboxEntry = {
  channel_id: string
  content: string
  attachments?: { url: string; filename: string; content_type: string; size: number }[]
  client_message_id: string
  reply_to_id?: string
  queued_at: number
}
const OUTBOX_KEY = 'channels_outbox_v1'
const OUTBOX_CAP = 50

export class ChannelSocket extends BaseSocket {
  private joinedRooms: Set<string> = new Set()
  private messageListeners: Set<MessageHandler> = new Set()

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
    this.messageListeners.delete(handler)
  }

  private _dispatchMessage(msg: ChannelMessage) {
    for (const fn of this.messageListeners) {
      try { fn(msg) } catch { /* swallow so one bad listener doesn't kill others */ }
    }
  }

  onTyping: TypingHandler | null = null
  onOnlineUsers: OnlineHandler | null = null
  onUserJoined: UserEventHandler | null = null
  onUserLeft: UserEventHandler | null = null
  onMessageDeleted: ((data: { channel_id: string; message_id: string; deleted_by: string }) => void) | null = null
  onMessageEdited: ((data: { channel_id: string; message_id: string; content: string; edited_at: string | null }) => void) | null = null
  onReactionUpdate: ((data: { channel_id: string; message_id: string; reactions: ChannelReaction[] }) => void) | null = null
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

  private _readOutbox(): OutboxEntry[] {
    try {
      const raw = localStorage.getItem(OUTBOX_KEY)
      return raw ? (JSON.parse(raw) as OutboxEntry[]) : []
    } catch {
      return []
    }
  }

  private _writeOutbox(entries: OutboxEntry[]) {
    try {
      localStorage.setItem(OUTBOX_KEY, JSON.stringify(entries.slice(-OUTBOX_CAP)))
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
    const entries = this._readOutbox()
    if (!entries.length) return
    const remaining: OutboxEntry[] = []
    for (const e of entries) {
      const ok = this.send({
        type: 'message',
        channel_id: e.channel_id,
        content: e.content,
        ...(e.attachments?.length ? { attachments: e.attachments } : {}),
        client_message_id: e.client_message_id,
        ...(e.reply_to_id ? { reply_to_id: e.reply_to_id } : {}),
      })
      if (!ok) remaining.push(e)
    }
    this._writeOutbox(remaining)
  }

  protected clearState() {
    this.joinedRooms.clear()
  }

  protected handleMessage(data: Record<string, unknown>) {
    switch (data.type) {
      case 'message': {
        const m = data.message as ChannelMessage
        if (m.client_message_id) this.removeFromOutbox(m.client_message_id)
        this._dispatchMessage(m)
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
        // Permanently rejected (not a member, over the length cap, rate
        // limited) — don't replay it forever from the outbox.
        if (cmid) this.removeFromOutbox(cmid)
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
  // was in localStorage and silently returned. Accessing the socket later
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
