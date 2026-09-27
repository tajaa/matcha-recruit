import { useCallback, useEffect, useRef, useState } from 'react'
import { getSharedChannelSocket, type SymChatEvent } from '../../api/channelSocket'
import {
  cancelSymChat,
  getSymChat,
  sendSymChatMessage,
  type SymChatDetail,
} from '../../api/matchaWork/symChat'

/** Fallback refresh while a chat is open, for when the WS nudge is missed. */
export const SYM_CHAT_POLL_MS = 15_000

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

type Loaded = { chatId: string; detail: SymChatDetail | null; error: string | null }

/**
 * One sym-chat as the current user sees it. Refetches on the server's
 * `sym_chat.updated` WS nudge (another participant moved the shape) and on a
 * 15 s poll while the chat is still open. State is keyed by chat id, so a
 * response for a chat the page has already navigated away from never shows.
 */
export function useSymChatDetail(chatId: string | undefined) {
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const requestRef = useRef(0)

  const current = loaded && loaded.chatId === chatId ? loaded : null

  const refresh = useCallback((): Promise<void> => {
    if (!chatId) return Promise.resolve()
    const request = ++requestRef.current
    return getSymChat(chatId).then(
      (detail) => {
        if (request === requestRef.current) setLoaded({ chatId, detail, error: null })
      },
      (err) => {
        if (request !== requestRef.current) return
        const error = errorText(err, 'Could not load this sym-chat')
        setLoaded((prev) => ({ chatId, detail: prev?.chatId === chatId ? prev.detail : null, error }))
      },
    )
  }, [chatId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (!chatId) return
    const socket = getSharedChannelSocket()
    const onUpdate = (event: SymChatEvent) => {
      if (event.sym_chat_id === chatId) void refresh()
    }
    socket.addSymChatListener(onUpdate)
    return () => socket.removeSymChatListener(onUpdate)
  }, [chatId, refresh])

  const isOpen = current?.detail?.status === 'open'
  useEffect(() => {
    if (!chatId || !isOpen) return
    const id = window.setInterval(() => { void refresh() }, SYM_CHAT_POLL_MS)
    return () => window.clearInterval(id)
  }, [chatId, isOpen, refresh])

  const send = useCallback(async (content: string) => {
    const text = content.trim()
    if (!chatId || !text || sending) return false
    setSending(true)
    setSendError(null)
    // Optimistic: show my line in the tunnel right away.
    setLoaded((prev) => prev && prev.chatId === chatId && prev.detail
      ? {
          ...prev,
          detail: {
            ...prev.detail,
            messages: [...prev.detail.messages, { id: `pending-${Date.now()}`, role: 'user', content: text, created_at: null }],
          },
        }
      : prev)
    try {
      await sendSymChatMessage(chatId, text)
      return true
    } catch (err) {
      setSendError(errorText(err, 'Message not sent'))
      return false
    } finally {
      setSending(false)
      await refresh()
    }
  }, [chatId, sending, refresh])

  const cancel = useCallback(async () => {
    if (!chatId) return
    try {
      const detail = await cancelSymChat(chatId)
      requestRef.current++
      setLoaded({ chatId, detail, error: null })
    } catch (err) {
      setSendError(errorText(err, 'Could not cancel'))
    }
  }, [chatId])

  return {
    detail: current?.detail ?? null,
    loading: !current,
    error: current?.error ?? null,
    sending,
    sendError,
    send,
    cancel,
    refresh,
  }
}
