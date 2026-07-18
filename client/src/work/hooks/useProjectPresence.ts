import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ProjectSocket,
  type CaretPayload,
  type CursorPayload,
  type PresenceMember,
} from '../api/projectSocket'

export interface RemoteCursor {
  xPct: number
  yPct: number
}

export interface RemoteCaret {
  sectionId: string
  anchor: number
  head: number
}

export interface UseProjectPresenceResult {
  members: PresenceMember[]
  remoteCursors: Map<string, RemoteCursor>
  remoteCarets: Map<string, RemoteCaret>
  reportCursor: (xPct: number, yPct: number) => void
  reportCaret: (sectionId: string, anchor: number, head: number) => void
}

const CURSOR_THROTTLE_MS = 50
const CARET_THROTTLE_MS = 100

/**
 * Hook for matcha-work project collaborator presence.
 *
 * On mount:
 * - opens a `/ws/projects` WebSocket
 * - sends `join_project` with the current pageKey
 * - subscribes to presence + cursor + caret events
 *
 * When `pageKey` changes (sub-tab switch), sends `page_change`. The server
 * only fans cursors/carets to other users on the same pageKey, so this
 * single hook handles both the cross-tab "who's here" pill and the
 * same-tab cursor/caret rendering.
 *
 * Outgoing cursor/caret reports are throttled here (50ms / 100ms). Server
 * also enforces a 25/sec absolute cap.
 */
export function useProjectPresence(
  projectId: string | null | undefined,
  pageKey: string,
): UseProjectPresenceResult {
  const [members, setMembers] = useState<PresenceMember[]>([])
  const [remoteCursors, setRemoteCursors] = useState<Map<string, RemoteCursor>>(new Map())
  const [remoteCarets, setRemoteCarets] = useState<Map<string, RemoteCaret>>(new Map())

  const socketRef = useRef<ProjectSocket | null>(null)
  // Pageify the latest `pageKey` so the WS event callbacks (registered once
  // per socket) can read the current value instead of a stale closure
  // captured at mount time. Without this, the `onPresenceUpdate` filter that
  // drops a remote cursor when "their page != our page" would compare against
  // our LAST tab, causing cursors to ghost into the new tab.
  const pageKeyRef = useRef(pageKey)
  useEffect(() => {
    pageKeyRef.current = pageKey
  }, [pageKey])

  // Throttle gates: hold the last-sent timestamp + a pending value.
  const cursorGate = useRef<{ lastSent: number; pending: { x: number; y: number } | null; timer: ReturnType<typeof setTimeout> | null }>({
    lastSent: 0,
    pending: null,
    timer: null,
  })
  const caretGate = useRef<{ lastSent: number; pending: { s: string; a: number; h: number } | null; timer: ReturnType<typeof setTimeout> | null }>({
    lastSent: 0,
    pending: null,
    timer: null,
  })

  // Connection lifecycle: open on first project, close on unmount.
  useEffect(() => {
    if (!projectId) return

    const socket = new ProjectSocket()
    socketRef.current = socket

    socket.onPresence = (m) => setMembers(m)

    socket.onPresenceUpdate = (userId, pk) => {
      setMembers((prev) => {
        const idx = prev.findIndex((p) => p.id === userId)
        if (idx === -1) return prev
        const copy = [...prev]
        copy[idx] = { ...copy[idx], page_key: pk }
        return copy
      })
      // Drop remote cursor/caret if the remote user moved off our current
      // sub-tab. Read the live page key from the ref so this callback,
      // registered once per socket, doesn't compare against a stale closure.
      if (pk !== pageKeyRef.current) {
        setRemoteCursors((prev) => {
          if (!prev.has(userId)) return prev
          const next = new Map(prev)
          next.delete(userId)
          return next
        })
        setRemoteCarets((prev) => {
          if (!prev.has(userId)) return prev
          const next = new Map(prev)
          next.delete(userId)
          return next
        })
      }
    }

    socket.onCursor = (p: CursorPayload) => {
      setRemoteCursors((prev) => {
        const next = new Map(prev)
        next.set(p.user_id, { xPct: p.x_pct, yPct: p.y_pct })
        return next
      })
    }

    socket.onCaret = (p: CaretPayload) => {
      setRemoteCarets((prev) => {
        const next = new Map(prev)
        next.set(p.user_id, { sectionId: p.section_id, anchor: p.anchor, head: p.head })
        return next
      })
    }

    socket.onUserJoined = (m) => {
      setMembers((prev) => {
        if (prev.some((p) => p.id === m.id)) return prev
        return [...prev, m as PresenceMember]
      })
    }

    socket.onUserLeft = (m) => {
      setMembers((prev) => prev.filter((p) => p.id !== m.id))
      setRemoteCursors((prev) => {
        if (!prev.has(m.id)) return prev
        const next = new Map(prev)
        next.delete(m.id)
        return next
      })
      setRemoteCarets((prev) => {
        if (!prev.has(m.id)) return prev
        const next = new Map(prev)
        next.delete(m.id)
        return next
      })
    }

    socket.connect()
    socket.joinProject(projectId, pageKeyRef.current)

    return () => {
      socket.disconnect()
      socketRef.current = null
      setMembers([])
      setRemoteCursors(new Map())
      setRemoteCarets(new Map())
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  // Sub-tab switch: send page_change without tearing down the WS.
  useEffect(() => {
    if (!projectId) return
    socketRef.current?.setPageKey(pageKey)
    // When switching tabs we leave the page_rooms of the old tab → drop any
    // cursors / carets we'd cached from there so they don't ghost on the new
    // tab.
    setRemoteCursors(new Map())
    setRemoteCarets(new Map())
  }, [pageKey, projectId])

  const reportCursor = useCallback((xPct: number, yPct: number) => {
    const gate = cursorGate.current
    const now = Date.now()
    const elapsed = now - gate.lastSent
    if (elapsed >= CURSOR_THROTTLE_MS) {
      gate.lastSent = now
      gate.pending = null
      socketRef.current?.sendCursor(xPct, yPct)
    } else {
      gate.pending = { x: xPct, y: yPct }
      if (!gate.timer) {
        gate.timer = setTimeout(() => {
          gate.timer = null
          if (gate.pending) {
            gate.lastSent = Date.now()
            socketRef.current?.sendCursor(gate.pending.x, gate.pending.y)
            gate.pending = null
          }
        }, CURSOR_THROTTLE_MS - elapsed)
      }
    }
  }, [])

  const reportCaret = useCallback((sectionId: string, anchor: number, head: number) => {
    const gate = caretGate.current
    const now = Date.now()
    const elapsed = now - gate.lastSent
    if (elapsed >= CARET_THROTTLE_MS) {
      gate.lastSent = now
      gate.pending = null
      socketRef.current?.sendCaret(sectionId, anchor, head)
    } else {
      gate.pending = { s: sectionId, a: anchor, h: head }
      if (!gate.timer) {
        gate.timer = setTimeout(() => {
          gate.timer = null
          if (gate.pending) {
            gate.lastSent = Date.now()
            socketRef.current?.sendCaret(gate.pending.s, gate.pending.a, gate.pending.h)
            gate.pending = null
          }
        }, CARET_THROTTLE_MS - elapsed)
      }
    }
  }, [])

  return { members, remoteCursors, remoteCarets, reportCursor, reportCaret }
}
