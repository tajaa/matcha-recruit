import { useEffect, useRef } from 'react'
import type React from 'react'
import { getChannelMessages } from '../../api/channels'
import type { ChannelMessage } from '../../api/channels'
import { mergeMessages, upsertMessage } from '../../api/channelMessages'
import { ChannelSocket, getSharedChannelSocket } from '../../api/channelSocket'
import { useToast } from '../../../components/ui'

type OnlineUser = { id: string; name: string; avatar_url: string | null }

interface UseChannelSocketParams {
  channelId: string | undefined
  isMember: boolean
  userId: string | undefined
  scrollToBottom: () => void
  socketRef: React.MutableRefObject<ChannelSocket | null>
  messagesContainerRef: React.RefObject<HTMLDivElement | null>
  setMessages: React.Dispatch<React.SetStateAction<ChannelMessage[]>>
  setTypingUsers: React.Dispatch<React.SetStateAction<Map<string, string>>>
  setOnlineUsers: React.Dispatch<React.SetStateAction<OnlineUser[]>>
  setError: React.Dispatch<React.SetStateAction<string>>
}

// WebSocket connection — uses the process-wide shared socket so the global
// notification listener and this view share one connection and one set of
// joined rooms. We only subscribe to events; we don't disconnect on unmount.
export function useChannelSocket({
  channelId,
  isMember,
  userId,
  scrollToBottom,
  socketRef,
  messagesContainerRef,
  setMessages,
  setTypingUsers,
  setOnlineUsers,
  setError,
}: UseChannelSocketParams) {
  const { toast } = useToast()
  const lastMarkReadRef = useRef(0)
  // Throttles the reconnect/wake catch-up refetch (below) — visibilitychange
  // fires this on every alt-tab back to the app, not just genuine
  // reconnects, so without a floor a full 50-row history refetch ran on
  // every single tab focus.
  const lastCatchupFetchRef = useRef(0)

  useEffect(() => {
    if (!channelId || !isMember) return

    const socket = getSharedChannelSocket()
    socketRef.current = socket
    // A ref from a previous channel must not suppress this channel's first
    // debounced mark-read — otherwise switching channels within the 5s
    // window silently skips marking the new channel read until the next
    // inbound message (GET /channels/{id} still covers the initial open,
    // so impact was small, but this closes the gap for good).
    lastMarkReadRef.current = 0
    lastCatchupFetchRef.current = 0

    const handleMessage = (msg: ChannelMessage) => {
      if (msg.channel_id !== channelId) return
      // Reconciles the sender's optimistic-pending row by client_message_id
      // (echo), else dedups by server id (reconnect replays, other
      // senders), always keeping (created_at, id) order — two devices
      // can otherwise render the same messages in different orders (two
      // uvicorn workers, no cross-device ordering guarantee).
      setMessages((prev) => upsertMessage(prev, msg))
      // Auto-scroll if near bottom
      const container = messagesContainerRef.current
      if (container) {
        const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 150
        if (nearBottom) setTimeout(scrollToBottom, 50)
      }
      // Advance last_read_at while actually watching the channel — otherwise
      // unread only zeroes on the next GET /channels/{id} and this open tab
      // accrues phantom unread. Debounced to one frame per 5s.
      if (document.visibilityState === 'visible' && Date.now() - lastMarkReadRef.current > 5000) {
        lastMarkReadRef.current = Date.now()
        socket.markRead(channelId)
      }
    }

    socket.addMessageListener(handleMessage)

    socket.onTyping = (user) => {
      if (user.id === userId) return
      setTypingUsers((prev) => {
        const next = new Map(prev)
        next.set(user.id, user.name)
        return next
      })
      setTimeout(() => {
        setTypingUsers((prev) => {
          const next = new Map(prev)
          next.delete(user.id)
          return next
        })
      }, 3000)
    }

    socket.onOnlineUsers = (users) => setOnlineUsers(users)
    socket.onUserJoined = (user) => {
      setOnlineUsers((prev) => prev.some((u) => u.id === user.id) ? prev : [...prev, { ...user, avatar_url: null }])
    }
    socket.onUserLeft = (user) => {
      setOnlineUsers((prev) => prev.filter((u) => u.id !== user.id))
    }
    socket.onMessageDeleted = (data) => {
      if (data.channel_id !== channelId) return
      setMessages((prev) =>
        prev.map((m) =>
          m.id === data.message_id
            ? { ...m, content: '', attachments: [], deleted_at: new Date().toISOString(), deleted_by: data.deleted_by }
            : m
        )
      )
    }

    socket.onMessageEdited = (data) => {
      if (data.channel_id !== channelId) return
      setMessages((prev) =>
        prev.map((m) =>
          m.id === data.message_id ? { ...m, content: data.content, edited_at: data.edited_at } : m
        )
      )
    }

    socket.onReactionUpdate = (data) => {
      if (data.channel_id !== channelId) return
      setMessages((prev) =>
        prev.map((m) => (m.id === data.message_id ? { ...m, reactions: data.reactions } : m))
      )
    }

    const handleChannelActionUpdated = (data: { channel_id: string; action: { kind: string; id: string; status: string } }) => {
      if (data.channel_id !== channelId) return
      setMessages((prev) =>
        prev.map((message) => {
          const action = message.metadata?.action
          return action?.id === data.action.id && action.kind === data.action.kind
            ? { ...message, metadata: { ...message.metadata, action: { ...action, status: data.action.status } } }
            : message
        })
      )
    }
    socket.addChannelActionListener(handleChannelActionUpdated)

    // Server rejected a join_room/message send (not a member, bad channel,
    // over the length cap) — surface it instead of leaving a pending
    // optimistic row (or a stuck composer) with no explanation.
    //
    // The socket is shared across every joined room (global notification
    // listener + whichever channel view is open), so an error scoped to a
    // DIFFERENT channel (e.g. a stale join_room replay for a channel this
    // user was removed from) must not blank the channel actually being
    // viewed — only act on errors for this channel, or unscoped ones
    // (bad-channel-id parse failures carry no id to compare).
    socket.onServerError = (message, details) => {
      if (details.channelId && details.channelId !== channelId) return

      if (details.clientMessageId) {
        // A rejected send (not a member, over the length cap) — drop the
        // ghost pending row and surface a transient toast instead of the
        // full-screen error gate, which would otherwise replace a working
        // channel view over one failed message.
        setMessages((prev) => prev.filter((m) => m.client_message_id !== details.clientMessageId))
        toast(message || 'Message failed to send', 'error')
        return
      }

      setError(message || 'Something went wrong sending that message')
    }

    // Reconnect catch-up: onopen only fires on a genuine reconnect (not on
    // this effect's initial mount, since the shared socket is usually
    // already open) — refetch and UNION (never replace) so a WS message
    // that lands while this fetch is in flight survives. The old
    // replace-the-array version erased it on THIS device only, which was
    // the reported cross-device divergence. Pending rows reconcile by
    // client_message_id, which REST now returns.
    const offConnected = socket.addConnectedListener(() => {
      // baseSocket's wake handler fires this on every visibilitychange to
      // 'visible' even when the socket never actually dropped (an already-
      // open — possibly zombie — socket still emits, so the catch-up path
      // covers that case too) — so a plain alt-tab back to the app was
      // refetching the full history on every focus with no floor.
      const now = Date.now()
      if (now - lastCatchupFetchRef.current < 15_000) return
      lastCatchupFetchRef.current = now
      getChannelMessages(channelId)
        .then((fetched) => {
          setMessages((prev) => mergeMessages(prev, fetched))
        })
        .catch(() => {})
    })

    // Global hook should already have joined this room, but joinRoom is
    // idempotent on the client and the server allows duplicate joins.
    socket.joinRoom(channelId)

    return () => {
      socket.removeMessageListener(handleMessage)
      // Null the singular handlers on the shared socket so this unmounted
      // component's state setters aren't held in stale closures.
      socket.onTyping = null
      socket.onOnlineUsers = null
      socket.onUserJoined = null
      socket.onUserLeft = null
      socket.onMessageDeleted = null
      socket.onMessageEdited = null
      socket.onReactionUpdate = null
      socket.removeChannelActionListener(handleChannelActionUpdated)
      socket.onServerError = null
      // Unsubscribe rather than nulling a shared slot: useChannelNotifications
      // and useLiveKitCall hold the same singleton, and `= null` used to remove
      // whichever handler happened to be registered, not just this one.
      offConnected()
      socketRef.current = null
      // Do NOT call disconnect() or leaveRoom() — the shared socket persists.
    }
  }, [channelId, isMember, userId, scrollToBottom, toast])
}
