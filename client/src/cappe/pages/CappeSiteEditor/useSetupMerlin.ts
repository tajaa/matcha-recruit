import { useCallback, useEffect, useRef, useState } from 'react'
import { cappeApi } from '../../api'
import { postCappeSSE } from '../../sse'
import type { CappeReadiness } from '../../types'

// A small sibling of PageEditor/useMerlin.ts, not a reuse of it — that hook is
// built around a page snapshot (blocks/theme/attachments/tier picker), none
// of which this surface has. See CAPPE_MERLIN_SETUP_CONCIERGE_PLAN.md.

export type SetupActionStatus = 'proposed' | 'executed' | 'dismissed' | 'blocked'

export type SetupAction = {
  id: string
  type: string
  summary: string
  payload: Record<string, unknown>
  status: SetupActionStatus
  result?: Record<string, unknown> | null
  message?: string | null
  created_at: string
  executed_at?: string | null
}

export type SetupLink = { target: string; label: string }

export type SetupMessage = {
  role: 'user' | 'assistant'
  content: string
  links?: SetupLink[]
  id?: string
}

type SetupFrame =
  | { type: 'status'; message: string }
  | { type: 'step'; kind: string; label: string }
  | { type: 'staged_action'; action: SetupAction }
  | { type: 'error'; message: string }
  | {
      type: 'result'
      data: {
        message: string
        links?: SetupLink[]
        conversation_id?: string | null
        message_id?: string | null
      }
    }

type StoredMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
}

type ConversationDetail = {
  id: string
  staged_actions?: SetupAction[] | null
  messages: StoredMessage[]
}

const CONVERSATION_KEY_PREFIX = 'cappe:setup-merlin:'

function conversationKey(siteId: string) {
  return `${CONVERSATION_KEY_PREFIX}${siteId}`
}

export function useSetupMerlin(siteId: string | undefined) {
  const [messages, setMessages] = useState<SetupMessage[]>([])
  const [stagedActions, setStagedActions] = useState<SetupAction[]>([])
  const [liveStatus, setLiveStatus] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState(false)
  const [hadPriorConversation, setHadPriorConversation] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  // On mount: resume a persisted conversation for this site, if one exists,
  // so a reload shows the real transcript instead of losing staged cards.
  useEffect(() => {
    if (!siteId) return
    let cancelled = false
    const storedId = localStorage.getItem(conversationKey(siteId))
    if (!storedId) {
      setHydrated(true)
      return
    }
    cappeApi
      .get<ConversationDetail>(`/merlin/setup/conversations/${storedId}`)
      .then((detail) => {
        if (cancelled) return
        setConversationId(detail.id)
        setHadPriorConversation(true)
        setMessages(detail.messages.map((m) => ({ role: m.role, content: m.content, id: m.id })))
        setStagedActions(detail.staged_actions || [])
      })
      .catch(() => {
        // Stale/deleted conversation — drop the pointer, fall back to fresh.
        localStorage.removeItem(conversationKey(siteId))
      })
      .finally(() => {
        if (!cancelled) setHydrated(true)
      })
    return () => {
      cancelled = true
    }
  }, [siteId])

  const send = useCallback(
    async (text: string) => {
      if (!siteId || !text.trim() || sending) return
      setSending(true)
      setError(null)
      setLiveStatus(null)
      setMessages((prev) => [...prev, { role: 'user', content: text }])

      const controller = new AbortController()
      abortRef.current = controller

      try {
        await postCappeSSE(
          `/sites/${siteId}/merlin/setup/agent`,
          { conversation_id: conversationId, message: text, history: [] },
          (frame) => {
            const f = frame as SetupFrame
            if (f.type === 'status') {
              setLiveStatus(f.message)
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
              if (f.data.conversation_id) {
                setConversationId(f.data.conversation_id)
                localStorage.setItem(conversationKey(siteId), f.data.conversation_id)
              }
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
      }
    },
    [siteId, sending, conversationId],
  )

  const approve = useCallback(
    async (actionId: string): Promise<CappeReadiness | null> => {
      if (!conversationId) return null
      try {
        const res = await cappeApi.post<{ action: SetupAction; message: string; readiness: CappeReadiness }>(
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
    messages, stagedActions, liveStatus, sending, error,
    hydrated, hadPriorConversation, conversationId,
    send, approve, dismiss,
  }
}
