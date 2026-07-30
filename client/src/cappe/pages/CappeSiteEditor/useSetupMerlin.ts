import { useCallback, useEffect, useRef, useState } from 'react'
import { cappeApi } from '../../api'
import { postCappeSSE } from '../../sse'
import type {
  CappeReadiness,
  CappeSetupAction,
  CappeSetupConversationSummary,
  CappeSetupLink,
} from '../../types'

// A small sibling of PageEditor/useMerlin.ts, not a reuse of it — that hook is
// built around a page snapshot (blocks/theme/attachments/tier picker), none
// of which this surface has. See CAPPE_MERLIN_SETUP_CONCIERGE_PLAN.md.

export type SetupMessage = {
  role: 'user' | 'assistant'
  content: string
  links?: CappeSetupLink[]
  id?: string
}

type SetupFrame =
  | { type: 'status'; message: string }
  | { type: 'step'; kind: string; label: string }
  | { type: 'staged_action'; action: CappeSetupAction }
  | { type: 'error'; message: string }
  | {
      type: 'result'
      data: {
        message: string
        links?: CappeSetupLink[]
        conversation_id?: string | null
        message_id?: string | null
        readiness?: CappeReadiness | null
      }
    }

type StoredMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
}

type ConversationDetail = {
  id: string
  staged_actions?: CappeSetupAction[] | null
  messages: StoredMessage[]
}

export function useSetupMerlin(siteId: string | undefined, onReadiness?: (r: CappeReadiness) => void) {
  const [messages, setMessages] = useState<SetupMessage[]>([])
  const [stagedActions, setStagedActions] = useState<CappeSetupAction[]>([])
  const [liveStatus, setLiveStatus] = useState<string | null>(null)
  const [liveSteps, setLiveSteps] = useState<{ kind: string; label: string }[]>([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [conversations, setConversations] = useState<CappeSetupConversationSummary[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const onReadinessRef = useRef(onReadiness)
  onReadinessRef.current = onReadiness

  // Abort any in-flight turn if the editor is navigated away from —
  // the hook itself never unmounts just from closing the panel (the panel
  // stays mounted, collapsed to its launcher button), only on a real route change.
  useEffect(() => () => abortRef.current?.abort(), [])

  const openConversation = useCallback(async (id: string) => {
    const detail = await cappeApi.get<ConversationDetail>(`/merlin/setup/conversations/${id}`)
    setConversationId(detail.id)
    setMessages(detail.messages.map((m) => ({ role: m.role, content: m.content, id: m.id })))
    setStagedActions(detail.staged_actions || [])
  }, [])

  // On mount: load this site's setup conversations and resume the most
  // recent one (server is the source of truth, not localStorage — a
  // reload/different browser must still see the real transcript).
  useEffect(() => {
    if (!siteId) return
    let cancelled = false
    cappeApi
      .get<CappeSetupConversationSummary[]>(`/sites/${siteId}/merlin/setup/conversations`)
      .then(async (list) => {
        if (cancelled) return
        setConversations(list)
        if (list.length > 0) await openConversation(list[0].id)
      })
      .catch(() => {
        // Best-effort — a fresh/empty concierge is a safe fallback.
      })
      .finally(() => {
        if (!cancelled) setHydrated(true)
      })
    return () => {
      cancelled = true
    }
  }, [siteId, openConversation])

  const send = useCallback(
    async (text: string) => {
      if (!siteId || !text.trim() || sending) return
      setSending(true)
      setError(null)
      setLiveStatus(null)
      setLiveSteps([])
      setMessages((prev) => [...prev, { role: 'user', content: text }])

      const controller = new AbortController()
      abortRef.current = controller

      try {
        await postCappeSSE(
          `/sites/${siteId}/merlin/setup/agent`,
          { conversation_id: conversationId, message: text },
          (frame) => {
            const f = frame as SetupFrame
            if (f.type === 'status') {
              setLiveStatus(f.message)
            } else if (f.type === 'step') {
              setLiveSteps((prev) => [...prev, { kind: f.kind, label: f.label }])
            } else if (f.type === 'staged_action') {
              setStagedActions((prev) => {
                const idx = prev.findIndex((a) => a.id === f.action.id)
                if (idx === -1) return [...prev, f.action]
                const next = [...prev]
                next[idx] = f.action
                return next
              })
            } else if (f.type === 'error') {
              setError(f.message)
            } else if (f.type === 'result') {
              setLiveStatus(null)
              setLiveSteps([])
              if (f.data.conversation_id) {
                const newId = f.data.conversation_id
                setConversationId(newId)
                setConversations((prev) =>
                  prev.some((c) => c.id === newId)
                    ? prev
                    : [{ id: newId, title: text.slice(0, 120), created_at: new Date().toISOString(), updated_at: new Date().toISOString() }, ...prev],
                )
              }
              if (f.data.readiness) onReadinessRef.current?.(f.data.readiness)
              setMessages((prev) => [
                ...prev,
                { role: 'assistant', content: f.data.message, links: f.data.links, id: f.data.message_id || undefined },
              ])
            }
          },
          { signal: controller.signal },
        )
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Merlin failed to respond.')
      } finally {
        setSending(false)
        setLiveStatus(null)
        setLiveSteps([])
      }
    },
    [siteId, sending, conversationId],
  )

  const approve = useCallback(
    async (actionId: string): Promise<CappeReadiness | null> => {
      if (!conversationId) return null
      try {
        const res = await cappeApi.post<{ action: CappeSetupAction; message: string; readiness: CappeReadiness }>(
          `/merlin/setup/conversations/${conversationId}/actions/${actionId}/execute`,
        )
        setStagedActions((prev) => prev.map((a) => (a.id === actionId ? res.action : a)))
        return res.readiness
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not run that action.')
        return null
      }
    },
    [conversationId],
  )

  const dismiss = useCallback(
    async (actionId: string) => {
      if (!conversationId) return
      try {
        const res = await cappeApi.post<ConversationDetail>(
          `/merlin/setup/conversations/${conversationId}/actions/${actionId}/dismiss`,
        )
        setStagedActions(res.staged_actions || [])
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not dismiss that action.')
      }
    },
    [conversationId],
  )

  return {
    messages, stagedActions, liveStatus, liveSteps, sending, error,
    hydrated, hadPriorConversation: conversations.length > 0,
    send, approve, dismiss,
  }
}
