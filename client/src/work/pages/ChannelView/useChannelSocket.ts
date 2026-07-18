import { useEffect } from 'react'
import type React from 'react'
import { getChannelMessages } from '../../api/channels'
import type { ChannelMessage } from '../../api/channels'
import { ChannelSocket, getSharedChannelSocket } from '../../api/channelSocket'

type OnlineUser = { id: string; name: string; avatar_url: string | null }

interface UseChannelSocketParams {
  channelId: string | undefined
  isMember: boolean
  userId: string | undefined
  scrollToBottom: () => void
  socketRef: React.MutableRefObject<ChannelSocket | null>
  messagesContainerRef: React.RefObject<HTMLDivElement>
  setMessages: React.Dispatch<React.SetStateAction<ChannelMessage[]>>
  setTypingUsers: React.Dispatch<React.SetStateAction<Map<string, string>>>
  setOnlineUsers: React.Dispatch<React.SetStateAction<OnlineUser[]>>
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
}: UseChannelSocketParams) {
  useEffect(() => {
    if (!channelId || !isMember) return

    const socket = getSharedChannelSocket()
    socketRef.current = socket

    const handleMessage = (msg: ChannelMessage) => {
      if (msg.channel_id !== channelId) return
      setMessages((prev) => {
        // Reconcile optimistic-pending entries first. The sender's own echo
        // carries the client_message_id we generated on send; replace the
        // pending row (whose `id` is the client UUID) with the server-
        // confirmed one so the row keeps its position but flips pending=false
        // and gets the real server id + timestamp.
        if (msg.client_message_id) {
          const idx = prev.findIndex(
            (m) => m.client_message_id === msg.client_message_id && m.pending,
          )
          if (idx >= 0) {
            const next = prev.slice()
            next[idx] = msg
            return next
          }
        }
        // Normal dedup by server id (reconnect replays, other senders).
        return prev.some((m) => m.id === msg.id) ? prev : [...prev, msg]
      })
      // Auto-scroll if near bottom
      const container = messagesContainerRef.current
      if (container) {
        const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 150
        if (nearBottom) setTimeout(scrollToBottom, 50)
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

    // Reconnect catch-up: onopen only fires on a genuine reconnect (not on
    // this effect's initial mount, since the shared socket is usually already
    // open) — refetch and merge by id so messages missed during the drop
    // aren't silently gone. Optimistic-pending sends not yet echoed are kept.
    socket.onConnected = () => {
      getChannelMessages(channelId)
        .then((fetched) => {
          setMessages((prev) => {
            const fetchedIds = new Set(fetched.map((m) => m.id))
            const stillPending = prev.filter((m) => m.pending && !fetchedIds.has(m.id))
            return [...fetched, ...stillPending]
          })
        })
        .catch(() => {})
    }

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
      socket.onConnected = null
      socketRef.current = null
      // Do NOT call disconnect() or leaveRoom() — the shared socket persists.
    }
  }, [channelId, isMember, userId, scrollToBottom])
}
