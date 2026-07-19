import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { type CopilotCard, type AcceptPayload } from '../IRCopilotCard'
import { api, ensureFreshToken } from '../../../api/client'
import { reportApiError } from '../../../api/errorReporter'
import { useIRInfoRequests } from '../../../hooks/ir/useIRInfoRequests'
import { BASE } from './helpers'
import { type CopilotMessage, type Transcript, type Props } from './types'

export function useCopilotPanel({
  incidentId, incidentStatus, reportedByName, reportedByEmail, onIncidentChanged, onOpenDocuments,
}: Props) {
  const [messages, setMessages] = useState<CopilotMessage[]>([])
  const [currentCards, setCurrentCards] = useState<CopilotCard[]>([])
  const [openQuestions, setOpenQuestions] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [streaming, setStreaming] = useState(false)
  const [busyCardMessageId, setBusyCardMessageId] = useState<string | null>(null)
  const [busyStage, setBusyStage] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [closingIncident, setClosingIncident] = useState(false)
  const [requestInfoOpen, setRequestInfoOpen] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const incidentIsClosed = incidentStatus === 'closed' || incidentStatus === 'resolved'
  const { requests: infoRequests, refresh: refreshInfoRequests, resend: resendInfoRequest, revoke: revokeInfoRequest } =
    useIRInfoRequests(incidentId)

  const refresh = useCallback(async () => {
    try {
      const t = await api.get<Transcript>(`/ir/incidents/${incidentId}/copilot`)
      setMessages(t.messages)
      setCurrentCards(t.current_cards)
      setOpenQuestions(t.open_questions)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load copilot')
    } finally {
      setLoading(false)
    }
  }, [incidentId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Poll for transcript changes made outside this browser tab — most
  // notably, an outside respondent submitting the "more info" link, which
  // lands a new system event straight in the DB with no push notification
  // to an already-open panel. Skipped while a round/accept is in flight so
  // the poll doesn't clobber their in-progress optimistic UI, and once the
  // incident is closed (nothing left to change).
  useEffect(() => {
    if (incidentIsClosed) return
    const intervalId = window.setInterval(() => {
      if (!streaming && !busyCardMessageId) void refresh()
    }, 15000)
    return () => window.clearInterval(intervalId)
  }, [refresh, streaming, busyCardMessageId, incidentIsClosed])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, currentCards.length])

  // Stream a guidance round (cold start or follow-up message)
  const streamRound = useCallback(async (userMessage: string | null) => {
    setStreaming(true)
    setError(null)
    try {
      const token = await ensureFreshToken()
      const res = await fetch(`${BASE}/ir/incidents/${incidentId}/copilot/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message: userMessage }),
      })
      if (!res.ok || !res.body) {
        // Raw fetch bypasses api/client.ts, so report manually or this is
        // invisible to client-errors.
        let detail: string | undefined
        try { detail = (await res.clone().text()).slice(0, 500) } catch { /* ignore */ }
        reportApiError({
          endpoint: `/ir/incidents/${incidentId}/copilot/stream`,
          status: res.status,
          message: `Copilot stream failed (${res.status})`,
          body: detail,
        })
        throw new Error(`Stream failed (${res.status})`)
      }

      // Optimistic user message in UI
      if (userMessage) {
        setMessages(prev => [...prev, {
          id: `optimistic-${Date.now()}`,
          role: 'user',
          message_type: 'text',
          content: userMessage,
          metadata: null,
          created_by: null,
          created_at: new Date().toISOString(),
        }])
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      const newCards: CopilotCard[] = []
      const newOpenQuestions: string[] = []

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const events = buf.split('\n\n')
        buf = events.pop() || ''
        for (const ev of events) {
          if (!ev.startsWith('data: ')) continue
          try {
            const data = JSON.parse(ev.slice(6))
            if (data.type === 'open_question') {
              newOpenQuestions.push(data.text)
              setOpenQuestions([...newOpenQuestions])
            } else if (data.type === 'card') {
              newCards.push(data.card)
              setCurrentCards([...newCards])
            } else if (data.type === 'error') {
              setError(data.detail)
            }
          } catch {
            // Ignore malformed chunks
          }
        }
      }
      // After the stream, fetch authoritative transcript so we have real DB IDs.
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Stream failed')
    } finally {
      setStreaming(false)
    }
  }, [incidentId, refresh])

  // Cold start once if no prior messages.
  useEffect(() => {
    if (loading) return
    if (messages.length === 0 && currentCards.length === 0 && !streaming) {
      void streamRound(null)
    }
    // streamRound is intentionally omitted (it would re-fire every render);
    // incidentId IS included so switching incidents cold-starts the new one
    // instead of closing over the previous incident's streamRound.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, incidentId])

  async function handleSubmitInput() {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')
    await streamRound(text)
  }

  async function handleAccept(messageId: string, cardId: string, payload?: AcceptPayload) {
    setBusyCardMessageId(messageId)
    setBusyStage('Starting…')
    setError(null)
    try {
      const token = await ensureFreshToken()
      const body: Record<string, unknown> = { message_id: messageId, card_id: cardId }
      if (payload?.selected_value !== undefined) body.selected_value = payload.selected_value
      if (payload?.numeric_value !== undefined) body.numeric_value = payload.numeric_value
      if (payload?.text_value !== undefined) body.text_value = payload.text_value
      if (payload?.notes !== undefined) body.notes = payload.notes
      const res = await fetch(`${BASE}/ir/incidents/${incidentId}/copilot/accept`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      })
      if (!res.ok || !res.body) {
        // Raw fetch bypasses api/client.ts, so report manually or this is
        // invisible to client-errors (this is why the prod 503 never logged).
        let detail: string | undefined
        try { detail = (await res.clone().text()).slice(0, 500) } catch { /* ignore */ }
        reportApiError({
          endpoint: `/ir/incidents/${incidentId}/copilot/accept`,
          status: res.status,
          message: `Copilot accept failed (${res.status})`,
          body: detail,
        })
        throw new Error(`Accept failed (${res.status})`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      let didMutateIncident = false
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const events = buf.split('\n\n')
        buf = events.pop() || ''
        for (const ev of events) {
          if (!ev.startsWith('data: ')) continue
          try {
            const data = JSON.parse(ev.slice(6))
            if (data.type === 'status') {
              if (data.stage === 'starting') setBusyStage('Starting…')
              else if (data.stage === 'running_analysis') setBusyStage(data.label || `Running ${data.analysis_type || 'analysis'}…`)
              else if (data.stage === 'analysis_complete') setBusyStage('Analysis complete — generating guidance…')
              else if (data.stage === 'thinking') setBusyStage('Generating next steps…')
            } else if (data.type === 'event') {
              setBusyStage(data.text)
              // Any action that writes to ir_incidents columns should bubble
              // up so the parent re-fetches the incident header (severity
              // badge, status pill, OSHA recordable indicator, etc.).
              if (
                data.action === 'set_field' ||
                data.action === 'close_incident' ||
                data.action === 'quick_reply' ||
                data.action === 'numeric_input' ||
                data.action === 'text_input' ||
                data.action === 'osha_emergency_alert'
              ) {
                didMutateIncident = true
              }
            } else if (data.type === 'error') {
              setError(data.detail || 'Action failed')
            }
            // We don't render cards/summary inline here — refresh below
            // pulls authoritative transcript with proper IDs.
          } catch {
            // ignore
          }
        }
      }
      await refresh()
      if (didMutateIncident) onIncidentChanged?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Accept failed')
    } finally {
      setBusyCardMessageId(null)
      setBusyStage(null)
    }
  }

  async function handleCloseIncident() {
    if (closingIncident || streaming) return
    if (!window.confirm('Close this incident? Open recommendations will be cleared.')) return
    setClosingIncident(true)
    setError(null)
    try {
      await api.post(`/ir/incidents/${incidentId}/copilot/close`, {})
      await refresh()
      onIncidentChanged?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Close failed')
    } finally {
      setClosingIncident(false)
    }
  }

  async function handleSkip(messageId: string, cardId: string) {
    setBusyCardMessageId(messageId)
    setError(null)
    try {
      await api.post(`/ir/incidents/${incidentId}/copilot/skip`, {
        message_id: messageId,
        card_id: cardId,
      })
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Skip failed')
    } finally {
      setBusyCardMessageId(null)
    }
  }

  async function handleResendInfoRequest(requestId: string) {
    setError(null)
    try {
      await resendInfoRequest(requestId)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Resend failed')
    }
  }

  async function handleRevokeInfoRequest(requestId: string) {
    if (!window.confirm('Revoke this link? It will no longer be answerable.')) return
    setError(null)
    try {
      await revokeInfoRequest(requestId)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Revoke failed')
    }
  }

  const cardsByMessageId = useMemo(() => {
    // Map the most recent message_type='card' rows (one per current_card by id).
    const map = new Map<string, string>() // card_id -> message_id
    for (const m of messages) {
      if (m.message_type === 'card' && m.metadata) {
        const card = (m.metadata as Record<string, unknown>).card as { id?: string } | undefined
        if (card?.id) map.set(card.id, m.id)
      }
    }
    return map
  }, [messages])

  // Emergency block: an un-accepted osha_emergency_alert card pauses intake.
  // Close button + chat input are disabled until the user submits the
  // confirmation-notes textarea on the alert card.
  const emergencyAlertActive = useMemo(
    () => currentCards.some((c) => c.action?.type === 'osha_emergency_alert'),
    [currentCards],
  )

  const acceptedCardIds = useMemo(() => {
    const set = new Set<string>()
    for (const m of messages) {
      if (m.message_type === 'card' && m.metadata) {
        const md = m.metadata as Record<string, unknown>
        if (md.accepted) {
          const card = (md.card as { id?: string }) || {}
          if (card.id) set.add(card.id)
        }
      }
    }
    return set
  }, [messages])

  return {
    incidentId,
    reportedByName,
    reportedByEmail,
    onOpenDocuments,
    messages,
    currentCards,
    openQuestions,
    loading,
    streaming,
    busyCardMessageId,
    busyStage,
    input,
    setInput,
    error,
    closingIncident,
    requestInfoOpen,
    setRequestInfoOpen,
    bottomRef,
    incidentIsClosed,
    infoRequests,
    refreshInfoRequests,
    handleSubmitInput,
    handleAccept,
    handleCloseIncident,
    handleSkip,
    handleResendInfoRequest,
    handleRevokeInfoRequest,
    cardsByMessageId,
    emergencyAlertActive,
    acceptedCardIds,
  }
}
