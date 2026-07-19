import { useCallback, useEffect, useRef, useState } from 'react'
import {
  MessageCircleQuestion, Loader2, Send, Plus, Trash2, AlertTriangle, LifeBuoy,
} from 'lucide-react'
import Markdown from 'react-markdown'
import { useToast } from '../../components/ui'
import CitationSources, { numberCitations } from '../../components/ui/CitationSources'
import { portalAskHrApi } from '../../api/portal/portalAskHr'
import type { AskHrMessage, AskHrSession } from '../../api/portal/portalAskHr'

function errorMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'message' in err) return String((err as Error).message)
  return 'Something went wrong.'
}

/** A refused turn. Rendered as a distinct notice rather than a chat bubble —
 *  it is not an answer, and it should not read like one. */
function HardStopNotice({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
      <LifeBuoy className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
      <div className="text-sm text-zinc-300 whitespace-pre-line">{text}</div>
    </div>
  )
}

function MessageRow({ m }: { m: AskHrMessage }) {
  if (m.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-lg bg-zinc-700 px-3.5 py-2 text-sm text-white whitespace-pre-wrap">
          {m.content}
        </div>
      </div>
    )
  }

  if (m.metadata?.hard_stop_category) {
    return <HardStopNotice text={m.content} />
  }

  const cited = numberCitations(m.content, m.metadata?.citations)
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-lg border border-zinc-700/50 bg-zinc-800/60 px-3.5 py-2 text-sm text-zinc-200 prose prose-sm prose-invert prose-zinc max-w-none">
        <Markdown>{cited.text}</Markdown>
        <CitationSources citations={cited.ordered} dropped={m.metadata?.dropped_citations} />
        {m.metadata?.open_questions && m.metadata.open_questions.length > 0 && (
          <div className="mt-2 pt-2 border-t border-zinc-800">
            <div className="text-[10px] uppercase tracking-wide text-zinc-500">Worth asking HR</div>
            <ul className="mt-1 space-y-0.5">
              {m.metadata.open_questions.map((q, i) => (
                <li key={i} className="text-[11px] text-zinc-400">· {q}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

export default function AskHR() {
  const { toast } = useToast()
  const [sessions, setSessions] = useState<AskHrSession[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<AskHrMessage[]>([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    portalAskHrApi.listSessions()
      .then(setSessions)
      .catch((err) => setLoadError(errorMessage(err)))
      .finally(() => setLoading(false))
  }, [])

  // Load history when the user switches conversations — but NOT when `activeId`
  // changes because we just created a session mid-send. That refetch races the
  // in-flight POST and wipes the optimistic echo of the question the user is
  // watching. A ref, not `sending` state, because the effect must see the value
  // as of this render, not re-run when it flips back.
  const sendingRef = useRef(false)
  useEffect(() => {
    if (!activeId) { setMessages([]); return }
    if (sendingRef.current) return
    portalAskHrApi.listMessages(activeId)
      .then(setMessages)
      .catch((err) => toast(errorMessage(err), 'error'))
  }, [activeId, toast])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, status])

  const startSession = useCallback(async () => {
    try {
      const s = await portalAskHrApi.createSession()
      setSessions((prev) => [s, ...prev])
      setActiveId(s.id)
      return s.id
    } catch (err) {
      toast(errorMessage(err), 'error')
      return null
    }
  }, [toast])

  const removeSession = useCallback(async (id: string) => {
    try {
      await portalAskHrApi.deleteSession(id)
      setSessions((prev) => prev.filter((s) => s.id !== id))
      setActiveId((cur) => (cur === id ? null : cur))
    } catch (err) {
      toast(errorMessage(err), 'error')
    }
  }, [toast])

  const send = useCallback(async () => {
    const text = draft.trim()
    if (!text || sending) return

    sendingRef.current = true
    setSending(true)
    const sessionId = activeId ?? (await startSession())
    if (!sessionId) {
      sendingRef.current = false
      setSending(false)
      return
    }
    setDraft('')
    // Echo the question immediately; the server persists its own copy.
    setMessages((prev) => [...prev, {
      id: `local-${Date.now()}`, role: 'user', content: text,
      metadata: null, created_at: new Date().toISOString(),
    }])

    try {
      await portalAskHrApi.chat(sessionId, text, (ev) => {
        if (ev.type === 'status') setStatus(ev.message)
        else if (ev.type === 'error') toast(ev.message, 'error')
        else if (ev.type === 'result') {
          setMessages((prev) => [...prev, {
            id: `local-a-${Date.now()}`,
            role: 'assistant',
            content: ev.data.assistant_text,
            metadata: {
              citations: ev.data.citations,
              dropped_citations: ev.data.dropped_citations,
              open_questions: ev.data.open_questions,
              cannot_answer: ev.data.cannot_answer,
              ...(ev.data.hard_stop
                ? { hard_stop_category: ev.data.hard_stop_category ?? 'sensitive' }
                : {}),
            },
            created_at: new Date().toISOString(),
          }])
        }
      })
      // The first question titles the session server-side — refresh the rail.
      portalAskHrApi.listSessions().then(setSessions).catch(() => {})
    } catch (err) {
      toast(errorMessage(err), 'error')
    } finally {
      sendingRef.current = false
      setSending(false)
      setStatus(null)
    }
  }, [draft, sending, activeId, startSession, toast])

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  }

  if (loadError) {
    return (
      <div className="max-w-3xl">
        <div className="flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/5 p-4">
          <AlertTriangle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-medium text-zinc-100">Couldn’t load Ask HR</div>
            <div className="text-sm text-zinc-400 mt-0.5">{loadError}</div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-5 h-[calc(100vh-8rem)]">
      {/* Session rail */}
      <div className="w-56 shrink-0 flex flex-col">
        <button
          onClick={() => setActiveId(null)}
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-zinc-300 border border-zinc-700 hover:bg-zinc-800/60 transition-colors"
        >
          <Plus className="h-4 w-4" /> New question
        </button>
        <div className="mt-2 space-y-1 overflow-auto">
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`group flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs cursor-pointer transition-colors ${
                s.id === activeId ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-800/50'
              }`}
              onClick={() => setActiveId(s.id)}
            >
              <span className="flex-1 truncate">{s.title || 'Untitled'}</span>
              <button
                onClick={(e) => { e.stopPropagation(); removeSession(s.id) }}
                className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400"
                aria-label="Delete conversation"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Conversation */}
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="flex-1 overflow-auto space-y-3 pr-1">
          {messages.length === 0 && (
            <div className="max-w-lg mt-8">
              <div className="flex items-center gap-2 text-zinc-200">
                <MessageCircleQuestion className="h-5 w-5 text-emerald-400" />
                <span className="text-sm font-medium">Ask about your workplace</span>
              </div>
              <p className="mt-2 text-sm text-zinc-400">
                Answers come from your company’s own handbook and policies, and every answer
                shows the sources it used. Try “how much PTO do I get?” or “what’s the
                call-in procedure if I’m running late?”
              </p>
              <p className="mt-2 text-xs text-zinc-500">
                For anything involving harassment, an injury, medical leave, or your job
                being at risk, this will hand you to your HR team directly rather than
                answering.
              </p>
            </div>
          )}
          {messages.map((m) => <MessageRow key={m.id} m={m} />)}
          {status && (
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <Loader2 className="h-3 w-3 animate-spin" /> {status}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="mt-3 flex items-end gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
            }}
            rows={2}
            placeholder="Ask a question about your workplace…"
            className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 resize-none"
          />
          <button
            onClick={send}
            disabled={sending || !draft.trim()}
            className="rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:hover:bg-emerald-600 px-3 py-2.5 text-white transition-colors"
            aria-label="Send"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  )
}
