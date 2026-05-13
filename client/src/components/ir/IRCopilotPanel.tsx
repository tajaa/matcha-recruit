import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Send, Sparkles } from 'lucide-react'
import { Button } from '../ui'
import IRCopilotCard, { type CopilotCard } from './IRCopilotCard'
import { api } from '../../api/client'

const BASE = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/$/, '')

type CopilotMessage = {
  id: string
  role: 'user' | 'assistant' | 'system'
  message_type: 'text' | 'card' | 'event'
  content: string
  metadata: Record<string, unknown> | null
  created_by: string | null
  created_at: string
}

type Transcript = {
  incident_id: string
  messages: CopilotMessage[]
  current_cards: CopilotCard[]
  summary: string | null
  open_questions: string[]
}

interface Props {
  incidentId: string
}

export default function IRCopilotPanel({ incidentId }: Props) {
  const [messages, setMessages] = useState<CopilotMessage[]>([])
  const [currentCards, setCurrentCards] = useState<CopilotCard[]>([])
  const [openQuestions, setOpenQuestions] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [streaming, setStreaming] = useState(false)
  const [busyCardMessageId, setBusyCardMessageId] = useState<string | null>(null)
  const [busyStage, setBusyStage] = useState<string | null>(null)
  const [skippedCards, setSkippedCards] = useState<Set<string>>(new Set())
  const [input, setInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

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

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, currentCards.length])

  // Stream a guidance round (cold start or follow-up message)
  const streamRound = useCallback(async (userMessage: string | null) => {
    setStreaming(true)
    setError(null)
    try {
      const token = localStorage.getItem('matcha_access_token')
      const res = await fetch(`${BASE}/ir/incidents/${incidentId}/copilot/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message: userMessage }),
      })
      if (!res.ok || !res.body) {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading])

  async function handleSubmitInput() {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')
    setSkippedCards(new Set())
    await streamRound(text)
  }

  async function handleAccept(messageId: string, cardId: string) {
    setBusyCardMessageId(messageId)
    setBusyStage('Starting…')
    setError(null)
    try {
      const token = localStorage.getItem('matcha_access_token')
      const res = await fetch(`${BASE}/ir/incidents/${incidentId}/copilot/accept`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message_id: messageId, card_id: cardId }),
      })
      if (!res.ok || !res.body) {
        throw new Error(`Accept failed (${res.status})`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
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
      setSkippedCards(new Set())
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Accept failed')
    } finally {
      setBusyCardMessageId(null)
      setBusyStage(null)
    }
  }

  function handleSkip(messageId: string) {
    setSkippedCards(prev => new Set(prev).add(messageId))
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

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading…
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-2 mb-4">
        <Sparkles className="w-4 h-4 text-emerald-400" />
        <h2 className="text-base font-semibold text-zinc-100">Copilot</h2>
        {streaming && (
          <span className="text-xs text-zinc-500 flex items-center gap-1">
            <Loader2 className="w-3 h-3 animate-spin" /> Thinking…
          </span>
        )}
      </div>

      {busyStage && (
        <div className="mb-4 rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-sm text-emerald-200 flex items-center gap-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
          <span className="leading-snug">{busyStage}</span>
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-md border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Transcript */}
      <div className="space-y-3">
        {messages.map((m) => {
          if (m.message_type === 'text') {
            return (
              <div
                key={m.id}
                className={`rounded-lg p-3 text-sm ${
                  m.role === 'user'
                    ? 'bg-zinc-800/60 text-zinc-100 ml-12'
                    : 'bg-zinc-900 border border-zinc-800 text-zinc-200'
                }`}
              >
                {m.content}
              </div>
            )
          }
          if (m.message_type === 'event') {
            const md = (m.metadata || {}) as Record<string, unknown>
            const action = typeof md.action === 'string' ? md.action : null
            const fieldLabel = typeof md.field_label === 'string' ? md.field_label : null
            const newValue = md.new_value
            const prevValue = md.previous_value
            const note = typeof md.note === 'string' ? md.note : null
            if ((action === 'set_field' || action === 'close_incident') && fieldLabel) {
              const fmt = (v: unknown): string => {
                if (v === null || v === undefined || v === '') return '—'
                if (typeof v === 'string') return v
                return String(v)
              }
              return (
                <div
                  key={m.id}
                  className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-2.5"
                >
                  <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-emerald-400 mb-1">
                    <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M16.704 5.29a1 1 0 010 1.42l-8 8a1 1 0 01-1.42 0l-4-4a1 1 0 011.42-1.42L8 12.585l7.29-7.295a1 1 0 011.414 0z" clipRule="evenodd"/></svg>
                    <span>Updated {fieldLabel}</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm flex-wrap">
                    <span className="text-zinc-500 line-through">{fmt(prevValue)}</span>
                    <span className="text-zinc-500">→</span>
                    <span className="text-emerald-300 font-medium">{fmt(newValue)}</span>
                  </div>
                  {note && <div className="text-[11px] text-zinc-500 mt-1.5">{note}</div>}
                </div>
              )
            }
            return (
              <div key={m.id} className="text-xs text-zinc-500 italic px-3">
                · {m.content}
              </div>
            )
          }
          // card messages: rendered below as part of currentCards if still active
          return null
        })}

        {/* Current actionable cards */}
        {currentCards.length > 0 && (
          <div className="space-y-2">
            {currentCards
              .filter((c) => !skippedCards.has(cardsByMessageId.get(c.id) || ''))
              .map((c) => {
                const mid = cardsByMessageId.get(c.id) || ''
                const accepted = acceptedCardIds.has(c.id)
                return (
                  <IRCopilotCard
                    key={c.id}
                    messageId={mid}
                    card={c}
                    accepted={accepted}
                    busy={busyCardMessageId === mid}
                    onAccept={handleAccept}
                    onSkip={handleSkip}
                  />
                )
              })}
          </div>
        )}

        {openQuestions.length > 0 && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
            <div className="text-xs uppercase tracking-wider text-amber-400 mb-1.5">
              Open questions
            </div>
            <ul className="text-zinc-200 space-y-1 list-disc pl-5">
              {openQuestions.map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="mt-6 sticky bottom-0 bg-zinc-950 pt-3 pb-2 -mx-6 px-6 border-t border-zinc-800">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            disabled={streaming}
            placeholder="Reply to copilot or ask a question…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void handleSubmitInput()
              }
            }}
            className="flex-1 rounded-md bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
          <Button
            variant="primary"
            disabled={streaming || !input.trim()}
            onClick={() => { void handleSubmitInput() }}
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>
        <div className="text-[10px] text-zinc-600 mt-1.5">
          Copilot uses incident details + cached AI analyses. Accept a card to act; type to clarify or ask a follow-up.
        </div>
      </div>
    </div>
  )
}
