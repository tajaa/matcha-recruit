import { useEffect, useRef, useState } from 'react'
import type { MWMessage } from '../../types'
import { ThreadSocket } from '../../api/threadSocket'

// Real-time collaboration over the thread WebSocket: online-user presence,
// typing indicators, and dedup-merging of messages pushed by other clients.
export function useThreadCollaboration(
  threadId: string | undefined,
  setMessages: React.Dispatch<React.SetStateAction<MWMessage[]>>,
) {
  const [onlineUsers, setOnlineUsers] = useState<{ id: string; name: string }[]>([])
  const [typingUsers, setTypingUsers] = useState<Map<string, string>>(new Map())
  const threadSocketRef = useRef<ThreadSocket | null>(null)
  const typingTimeoutsRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())
  const lastTypingSentRef = useRef(0)

  useEffect(() => {
    if (!threadId) return

    const sock = new ThreadSocket()
    threadSocketRef.current = sock

    sock.onNewMessage = (newMessages) => {
      setMessages((prev) => {
        const existingIds = new Set(prev.map(m => m.id))
        const deduped = newMessages.filter(m => !existingIds.has(m.id))
        return deduped.length > 0 ? [...prev, ...deduped] : prev
      })
    }

    sock.onTyping = (user) => {
      setTypingUsers((prev) => {
        const next = new Map(prev)
        next.set(user.id, user.name)
        return next
      })
      // Clear after 3 seconds
      const existing = typingTimeoutsRef.current.get(user.id)
      if (existing) clearTimeout(existing)
      typingTimeoutsRef.current.set(
        user.id,
        setTimeout(() => {
          setTypingUsers((prev) => {
            const next = new Map(prev)
            next.delete(user.id)
            return next
          })
          typingTimeoutsRef.current.delete(user.id)
        }, 3000)
      )
    }

    sock.onOnlineUsers = (users) => {
      setOnlineUsers(users)
    }

    sock.onUserJoined = (user) => {
      setOnlineUsers((prev) => {
        if (prev.some((u) => u.id === user.id)) return prev
        return [...prev, user]
      })
    }

    sock.onUserLeft = (user) => {
      setOnlineUsers((prev) => prev.filter((u) => u.id !== user.id))
      // Clear typing state for the user who left
      setTypingUsers((prev) => {
        if (!prev.has(user.id)) return prev
        const next = new Map(prev)
        next.delete(user.id)
        return next
      })
    }

    sock.connect()
    sock.joinThread(threadId)

    return () => {
      sock.leaveThread(threadId)
      sock.disconnect()
      threadSocketRef.current = null
      // Clean up typing timeouts
      typingTimeoutsRef.current.forEach((t) => clearTimeout(t))
      typingTimeoutsRef.current.clear()
    }
  }, [threadId])

  return { onlineUsers, typingUsers, threadSocketRef, lastTypingSentRef }
}
