import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { type CopilotCard, type AcceptPayload } from '../IRCopilotCard'
import { api, ensureFreshToken } from '../../../api/client'
import { consumeSSE } from '../../../api/sse'
import { reportApiError } from '../../../api/errorReporter'
import { useIRInfoRequests } from '../../../hooks/ir/useIRInfoRequests'
import { BASE } from './helpers'
import { type CopilotMessage, type CopilotProgress, type CopilotEvidence, type Transcript, type Props } from './types'

export function useCopilotPanel({
  incidentId, incidentStatus, reportedByName, reportedByEmail, onIncidentChanged, onOpenDocuments,
}: Props) {
  const [messages, setMessages] = useState<CopilotMessage[]>([])
  const [currentCards, setCurrentCards] = useState<CopilotCard[]>([])
  const [openQuestions, setOpenQuestions] = useState<string[]>([])
  const [progress, setProgress] = useState<CopilotProgress | null>(null)
  const [evidence, setEvidence] = useState<CopilotEvidence | null>(null)
  const [loading, setLoading] = useState(true)
  const [streaming, setStreaming] = useState(false)
  const [busyCardMessageId, setBusyCardMessageId] = useState<string | null>(null)
  const [busyStage, setBusyStage] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [closingIncident, setClosingIncident] = useState(false)
  const [requestInfoOpen, setRequestInfoOpen] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const incidentIsClosed = incidentStatus === 'closed' || incidentStatus === 'resolved'
  const { requests: infoRequests, refresh: refreshInfoRequests, resend: resendInfoRequest, revoke: revokeInfoRequest } =
    useIRInfoRequests(incidentId)

  // Monotonic request id. Transcript fetches come from five places (mount, the
  // 15s poll, post-stream, post-accept, post-skip) and they overtake each
  // other: a slow poll issued before a round can land *after* that round's
  // refresh and repaint the pre-turn transcript, making the new turn visibly
  // disappear until the next poll. Only the newest request may write state.
  // Same pattern as hooks/ir/useIRIncident.ts.
  const reqId = useRef(0)
  useEffect(() => () => { reqId.current++ }, [])

  // `silent` suppresses the error banner: a background poll that fails is not
  // something the admin asked for, so it must not paint an error over a
  // transcript that is still perfectly readable. The next poll retries anyway.
  const refresh = useCallback(async (opts?: { silent?: boolean }) => {
    const id = ++reqId.current
    try {
      const t = await api.get<Transcript>(`/ir/incidents/${incidentId}/copilot`)
      if (id !== reqId.current) return
      setMessages(t.messages)
      setCurrentCards(t.current_cards)
      setOpenQuestions(t.open_questions)
      setProgress(t.progress ?? null)
      setEvidence(t.evidence ?? null)
      setLoadFailed(false)
    } catch (e) {
      if (id !== reqId.current) return
      // Tracked separately from `error` so the cold-start effect can tell "this
      // incident really has no transcript" from "we never managed to load it".
      setLoadFailed(true)
      if (!opts?.silent) setError(e instanceof Error ? e.message : 'Failed to load copilot')
    } finally {
      if (id === reqId.current) setLoading(false)
    }
  }, [incidentId])

  // Switching incidents must clear the previous incident's thread synchronously.
  // Leaving it up meant the cold-start effect below saw a non-empty `messages`
  // for the *new* incident and skipped, so an incident with no transcript opened
  // to a dead panel. Bumping reqId also invalidates any refresh still in flight
  // for the old incident so it can't paint into the new one.
  // Every slice belongs here — a leftover busyCardMessageId paints a spinner on
  // a card id that doesn't exist in the new incident, and a leftover `input`
  // carries a half-typed draft across incidents.
  useEffect(() => {
    reqId.current++
    setMessages([])
    setCurrentCards([])
    setOpenQuestions([])
    setProgress(null)
    setEvidence(null)
    setError(null)
    setLoadFailed(false)
    setBusyCardMessageId(null)
    setBusyStage(null)
    setClosingIncident(false)
    setRequestInfoOpen(false)
    setInput('')
    setLoading(true)
  }, [incidentId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Read the in-flight guards through a ref so they don't sit in the poll
  // effect's dep list — keeping them there tore the interval down and rebuilt
  // it on every stream/accept toggle, resetting the 15s clock each time, so a
  // busy admin could go a long stretch without a single poll actually firing.
  const pollGuardRef = useRef({ streaming, busyCardMessageId })
  pollGuardRef.current = { streaming, busyCardMessageId }

  // Poll for transcript changes made outside this browser tab — most
  // notably, an outside respondent submitting the "more info" link, which
  // lands a new system event straight in the DB with no push notification
  // to an already-open panel. Skipped while a round/accept is in flight so
  // the poll doesn't clobber their in-progress optimistic UI, and once the
  // incident is closed (nothing left to change).
  useEffect(() => {
    if (incidentIsClosed) return
    const canPoll = () => {
      const { streaming: isStreaming, busyCardMessageId: busyCard } = pollGuardRef.current
      return !isStreaming && !busyCard
    }
    const intervalId = window.setInterval(() => {
      // A hidden tab has nothing to update — admins keep several incident
      // tabs open, and unconditional ticking meant thousands of transcript
      // fetches a night for UI nobody was looking at.
      if (document.visibilityState === 'hidden') return
      if (canPoll()) void refresh({ silent: true })
    }, 15000)
    // Catch up immediately on return so the tab isn't up to 15s stale.
    const onVisible = () => {
      if (document.visibilityState === 'visible' && canPoll()) void refresh({ silent: true })
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearInterval(intervalId)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [refresh, incidentIsClosed])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, currentCards.length])

  // Stream a guidance round (cold start or follow-up message).
  // Returns whether the round landed — errors are handled here (banner) rather
  // than thrown, so the cold-start caller has no other way to know it failed.
  const streamRound = useCallback(async (userMessage: string | null): Promise<boolean> => {
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

      const newCards: CopilotCard[] = []
      const newOpenQuestions: string[] = []

      await consumeSSE(res, (data) => {
        const ev = data as { type?: string; text?: string; card?: CopilotCard; detail?: string }
        if (ev.type === 'open_question') {
          newOpenQuestions.push(ev.text ?? '')
          setOpenQuestions([...newOpenQuestions])
        } else if (ev.type === 'card' && ev.card) {
          newCards.push(ev.card)
          setCurrentCards([...newCards])
        } else if (ev.type === 'error') {
          setError(ev.detail ?? 'Stream failed')
        }
      })

      // After the stream, fetch authoritative transcript so we have real DB IDs.
      await refresh()
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Stream failed')
      return false
    } finally {
      setStreaming(false)
    }
  }, [incidentId, refresh])

  // Cold start once if no prior messages. The ref — not the `streaming` state —
  // is what makes this once-per-incident: `streaming` is a render-time value, so
  // a second run of this effect before setStreaming(true) commits would fire a
  // duplicate LLM round (StrictMode double-invoke, or any remount of the panel).
  const coldStartedRef = useRef<string | null>(null)
  useEffect(() => {
    if (loading) return
    // An empty transcript because the fetch FAILED is not an incident that needs
    // cold-starting — kicking off a billed LLM round on a network blip was the
    // spurious-trigger half of this bug.
    if (loadFailed) return
    // A closed incident has nothing left to advise on. The poll effect already
    // treats closed as terminal; before the incident-switch reset above this was
    // masked by stale messages happening to be non-empty.
    if (incidentIsClosed) return
    if (coldStartedRef.current === incidentId) return
    if (messages.length === 0 && currentCards.length === 0 && !streaming) {
      const startedFor = incidentId
      coldStartedRef.current = startedFor
      // Clear the marker if the round never landed, or a transient 503 would
      // leave this incident permanently without a cold start — IRDetail no
      // longer remounts the panel, so nothing else would retry it. Guarded on
      // the id so a late failure from the previous incident can't unlock the
      // current one into a duplicate round.
      void streamRound(null).then((ok) => {
        if (!ok && coldStartedRef.current === startedFor) coldStartedRef.current = null
      })
    }
    // streamRound is intentionally omitted (it would re-fire every render);
    // incidentId IS included so switching incidents cold-starts the new one
    // instead of closing over the previous incident's streamRound.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, loadFailed, incidentIsClosed, incidentId])

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

      let didMutateIncident = false
      await consumeSSE(res, (raw) => {
        const data = raw as {
          type?: string; stage?: string; label?: string; analysis_type?: string
          text?: string; action?: string; detail?: string
        }
        if (data.type === 'status') {
          if (data.stage === 'starting') setBusyStage('Starting…')
          else if (data.stage === 'running_analysis') setBusyStage(data.label || `Running ${data.analysis_type || 'analysis'}…`)
          else if (data.stage === 'analysis_complete') setBusyStage('Analysis complete — generating guidance…')
          else if (data.stage === 'thinking') setBusyStage('Generating next steps…')
        } else if (data.type === 'event') {
          setBusyStage(data.text ?? null)
          // Any action that writes to ir_incidents columns should bubble up so
          // the parent re-fetches the incident header (severity badge, status
          // pill, OSHA recordable indicator, etc.).
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
        // Cards/summary aren't rendered inline here — the refresh below pulls
        // the authoritative transcript with proper IDs.
      })
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
    progress,
    evidence,
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
