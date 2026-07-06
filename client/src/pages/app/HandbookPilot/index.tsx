import { useCallback, useEffect, useRef, useState } from 'react'
import {
  BookOpen, CheckCircle2, FileText, Loader2, Plus, Sparkles, Send, Trash2, Wand2,
} from 'lucide-react'
import {
  listPilotSessions, getPilotSession, getPilotContext, createPilotSession,
  updatePilotDraft, deletePilotDraft, promotePilotDrafts, streamChat,
  type PilotSession, type PilotDraft, type PilotMessage, type ContextPreview,
  type PromoteResult,
} from '../../../api/handbookPilot'

// ---------------------------------------------------------------------------
// Handbook Pilot — conversational, grounded handbook/policy generation.
// Chat with an AI grounded in your profile + applicable law + existing
// policies; it proposes citation-validated drafts you review, edit, and
// promote into the real handbooks / policies tables.
// ---------------------------------------------------------------------------

export default function HandbookPilot() {
  const [sessions, setSessions] = useState<PilotSession[]>([])
  const [active, setActive] = useState<PilotSession | null>(null)
  const [context, setContext] = useState<ContextPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const activeIdRef = useRef<string | null>(null)

  const refreshList = useCallback(async () => {
    const rows = await listPilotSessions()
    setSessions(rows)
    return rows
  }, [])

  const openSession = useCallback(async (id: string) => {
    activeIdRef.current = id
    setContext(null)
    try {
      const [full, ctx] = await Promise.all([
        getPilotSession(id),
        getPilotContext(id).catch(() => null),
      ])
      if (activeIdRef.current !== id) return
      setActive(full)
      setContext(ctx)
    } catch {
      if (activeIdRef.current === id) setActive(null)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const rows = await refreshList()
        if (cancelled) return
        if (rows.length) void openSession(rows[0].id)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const reloadActive = useCallback(async () => {
    const id = activeIdRef.current
    if (!id) return
    try {
      const full = await getPilotSession(id)
      if (activeIdRef.current === id) setActive(full)
    } catch { /* keep current view */ }
    void refreshList()
  }, [refreshList])

  const onCreated = useCallback(async (s: PilotSession) => {
    setShowNew(false)
    await refreshList()
    void openSession(s.id)
  }, [refreshList, openSession])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-72">
        <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-7rem)] gap-4">
      {/* Sessions rail */}
      <aside className="w-64 shrink-0 flex flex-col border border-zinc-800 rounded-xl bg-zinc-950/40">
        <div className="p-3 border-b border-zinc-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-emerald-500" />
            <span className="text-sm font-semibold text-zinc-200">Handbook Pilot</span>
          </div>
          <button
            onClick={() => setShowNew(true)}
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-emerald-400"
            title="New session"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions.length === 0 && (
            <p className="text-xs text-zinc-600 p-3">No sessions yet. Start one to draft a handbook section or policy.</p>
          )}
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => openSession(s.id)}
              className={`w-full text-left px-3 py-2 rounded-lg transition ${
                active?.id === s.id ? 'bg-emerald-500/10 border border-emerald-500/30' : 'hover:bg-zinc-800/60 border border-transparent'
              }`}
            >
              <div className="text-sm text-zinc-200 truncate">{s.title}</div>
              <div className="text-[11px] text-zinc-500 flex gap-2 mt-0.5">
                <span>{s.draft_count ?? 0} drafts</span>
                {(s.promoted_count ?? 0) > 0 && <span className="text-emerald-500">{s.promoted_count} promoted</span>}
              </div>
            </button>
          ))}
        </div>
      </aside>

      {/* Workbench */}
      <main className="flex-1 min-w-0 flex gap-4">
        {active ? (
          <>
            <div className="flex-1 min-w-0 flex flex-col border border-zinc-800 rounded-xl bg-zinc-950/40">
              {/* key by session id → remount (and reset transcript/abort the
                  stream) when the user switches sessions mid-turn */}
              <Console key={active.id} session={active} onTurn={reloadActive} />
            </div>
            <div className="w-80 shrink-0 flex flex-col gap-4 overflow-y-auto">
              <DraftsPanel key={active.id} session={active} onChange={reloadActive} />
              <ContextPanel context={context} />
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <Wand2 className="h-8 w-8 text-emerald-500 mb-3" />
            <h2 className="text-lg font-semibold text-zinc-100">Draft a handbook or policy</h2>
            <p className="text-sm text-zinc-500 mt-2 max-w-md">
              Describe what you need — a meal-and-rest-break policy, an updated anti-harassment
              section — and the pilot drafts it grounded in your profile, the law where you operate,
              and your existing policies. Review, then promote it into your handbooks or policies.
            </p>
            <button
              onClick={() => setShowNew(true)}
              className="mt-5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium inline-flex items-center gap-2"
            >
              <Plus className="h-4 w-4" /> New session
            </button>
          </div>
        )}
      </main>

      {showNew && <NewSessionModal onClose={() => setShowNew(false)} onCreated={onCreated} />}
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Console — transcript + composer with SSE streaming.
// --------------------------------------------------------------------------- //

// NB: this component is keyed by session.id in the parent, so it remounts on a
// session switch — `session` is effectively fixed for an instance's lifetime.
function Console({ session, onTurn }: { session: PilotSession; onTurn: () => void }) {
  const [messages, setMessages] = useState<PilotMessage[]>(session.messages ?? [])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Abort any in-flight turn when the user switches sessions (unmount).
  useEffect(() => () => abortRef.current?.abort(), [])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages, status])

  const send = async () => {
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setBusy(true)
    setStatus('Thinking…')
    setMessages((m) => [...m, { role: 'user', content: text, metadata: null, created_at: new Date().toISOString() }])
    const controller = new AbortController()
    abortRef.current = controller
    let hadError = false
    try {
      await streamChat(session.id, text, {
        onStatus: (msg) => setStatus(msg),
        onResult: (data) => {
          setMessages((m) => [...m, {
            role: 'assistant', content: data.assistant_text,
            metadata: { open_questions: data.open_questions, dropped_citations: data.dropped_citations },
            created_at: new Date().toISOString(),
          }])
        },
        onError: (msg) => { hadError = true; setStatus(`⚠ ${msg}`) },
      }, controller.signal)
    } finally {
      if (!controller.signal.aborted) {
        setBusy(false)
        if (!hadError) setStatus(null)  // keep the error visible; clear only on success
        onTurn() // pull persisted drafts
      }
    }
  }

  return (
    <>
      <div className="px-4 py-3 border-b border-zinc-800">
        <div className="text-sm font-semibold text-zinc-100">{session.title}</div>
        {session.goal && <div className="text-xs text-zinc-500 mt-0.5">{session.goal}</div>}
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <p className="text-sm text-zinc-600">
            Ask the pilot to draft or revise a handbook section or policy. Every enforceable clause is grounded in
            your applicable jurisdiction requirements — citations that can't be traced are dropped.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
            <div className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm whitespace-pre-wrap ${
              m.role === 'user' ? 'bg-emerald-600 text-white' : 'bg-zinc-800/70 text-zinc-200'
            }`}>
              {m.content}
              {m.role === 'assistant' && m.metadata?.open_questions && m.metadata.open_questions.length > 0 && (
                <div className="mt-2 pt-2 border-t border-zinc-700/60">
                  <div className="text-[11px] uppercase tracking-wide text-amber-400/80 mb-1">Open questions</div>
                  <ul className="list-disc list-inside text-xs text-zinc-400 space-y-0.5">
                    {m.metadata.open_questions.map((q, j) => <li key={j}>{q}</li>)}
                  </ul>
                </div>
              )}
            </div>
          </div>
        ))}
        {status && (
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> {status}
          </div>
        )}
      </div>
      <div className="p-3 border-t border-zinc-800">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }}
            placeholder="Draft a remote-work policy for our CA and TX locations…"
            rows={2}
            className="flex-1 resize-none rounded-lg bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-emerald-500"
          />
          <button
            onClick={() => void send()}
            disabled={busy || !input.trim()}
            className="px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white self-stretch flex items-center"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </>
  )
}

// --------------------------------------------------------------------------- //
// DraftsPanel — review/edit candidate drafts, select, promote.
// --------------------------------------------------------------------------- //

function DraftsPanel({ session, onChange }: { session: PilotSession; onChange: () => void }) {
  const pending = (session.drafts ?? []).filter((d) => d.status === 'pending')
  const promoted = (session.drafts ?? []).filter((d) => d.status === 'promoted')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<PromoteResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const toggle = (id: string) =>
    setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })

  const promote = async () => {
    if (selected.size === 0 || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await promotePilotDrafts(session.id, { draft_ids: [...selected] })
      setResult(res)
      setSelected(new Set())
      onChange()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Promotion failed — please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="border border-zinc-800 rounded-xl bg-zinc-950/40">
      <div className="px-3 py-2.5 border-b border-zinc-800 flex items-center justify-between">
        <span className="text-sm font-semibold text-zinc-200">Drafts</span>
        {pending.length > 0 && (
          <button
            onClick={() => void promote()}
            disabled={selected.size === 0 || busy}
            className="text-xs px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white inline-flex items-center gap-1"
          >
            {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
            Promote{selected.size ? ` (${selected.size})` : ''}
          </button>
        )}
      </div>
      <div className="p-2 space-y-2 max-h-[42vh] overflow-y-auto">
        {pending.length === 0 && promoted.length === 0 && (
          <p className="text-xs text-zinc-600 p-2">Drafts the pilot proposes will appear here to review and promote.</p>
        )}
        {pending.map((d) => (
          <DraftRow key={d.id} draft={d} selected={selected.has(d.id)} onToggle={() => toggle(d.id)} onChange={onChange} />
        ))}
        {promoted.map((d) => (
          <div key={d.id} className="px-2.5 py-2 rounded-lg bg-zinc-900/40 border border-zinc-800/60 flex items-center gap-2">
            {d.kind === 'policy' ? <FileText className="h-3.5 w-3.5 text-emerald-500" /> : <BookOpen className="h-3.5 w-3.5 text-emerald-500" />}
            <span className="text-xs text-zinc-400 truncate flex-1">{d.title}</span>
            <span className="text-[10px] uppercase tracking-wide text-emerald-500">promoted</span>
          </div>
        ))}
      </div>
      {error && (
        <div className="px-3 py-2 border-t border-zinc-800 text-xs text-amber-400">⚠ {error}</div>
      )}
      {result && (
        <div className="px-3 py-2 border-t border-zinc-800 text-xs text-zinc-400 space-y-1">
          {result.handbook && (
            <a href={`/app/handbook/${result.handbook.id}`} className="text-emerald-400 hover:underline block">
              → Handbook draft created: {result.handbook.title}
            </a>
          )}
          {result.policies.map((p) => (
            <a key={p.id} href="/app/policies" className="text-emerald-400 hover:underline block">→ Policy draft: {p.title}</a>
          ))}
          {result.failed.map((f) => (
            <div key={f.draft_id} className="text-amber-400">⚠ Couldn't promote “{f.title}”: {f.error}</div>
          ))}
        </div>
      )}
    </div>
  )
}

function DraftRow({ draft, selected, onToggle, onChange }: {
  draft: PilotDraft; selected: boolean; onToggle: () => void; onChange: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(draft.title)
  const [content, setContent] = useState(draft.content)
  const [busy, setBusy] = useState(false)

  const save = async () => {
    setBusy(true)
    try {
      await updatePilotDraft(draft.id, { title, content })
      setEditing(false)
      onChange()
    } finally { setBusy(false) }
  }
  const remove = async () => {
    setBusy(true)
    try { await deletePilotDraft(draft.id); onChange() } finally { setBusy(false) }
  }

  return (
    <div className={`rounded-lg border ${selected ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-zinc-800 bg-zinc-900/40'}`}>
      <div className="flex items-center gap-2 px-2.5 py-2">
        <input type="checkbox" checked={selected} onChange={onToggle} className="accent-emerald-500" />
        {draft.kind === 'policy' ? <FileText className="h-3.5 w-3.5 text-zinc-500" /> : <BookOpen className="h-3.5 w-3.5 text-zinc-500" />}
        <span className="text-xs text-zinc-200 truncate flex-1">{draft.title}</span>
        <button onClick={() => setEditing((e) => !e)} className="text-[11px] text-zinc-500 hover:text-emerald-400">{editing ? 'Close' : 'Edit'}</button>
        <button onClick={() => void remove()} disabled={busy} className="text-zinc-600 hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
      </div>
      {editing ? (
        <div className="px-2.5 pb-2.5 space-y-2">
          <input value={title} onChange={(e) => setTitle(e.target.value)} className="w-full rounded bg-zinc-900 border border-zinc-700 px-2 py-1 text-xs text-zinc-200" />
          <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={8} className="w-full rounded bg-zinc-900 border border-zinc-700 px-2 py-1 text-xs text-zinc-300 font-mono leading-relaxed" />
          <button onClick={() => void save()} disabled={busy} className="text-xs px-2 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white">Save</button>
        </div>
      ) : (
        <p className="px-2.5 pb-2.5 text-[11px] text-zinc-500 line-clamp-3 whitespace-pre-wrap">{draft.content}</p>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------- //
// ContextPanel — grounding corpus preview.
// --------------------------------------------------------------------------- //

function ContextPanel({ context }: { context: ContextPreview | null }) {
  if (!context) return null
  return (
    <div className="border border-zinc-800 rounded-xl bg-zinc-950/40">
      <div className="px-3 py-2.5 border-b border-zinc-800">
        <span className="text-sm font-semibold text-zinc-200">Grounding</span>
        <span className="text-xs text-zinc-500 ml-2">{context.total} records</span>
      </div>
      <div className="p-3 space-y-1.5">
        {Object.entries(context.sources).map(([k, s]) => (
          <div key={k} className="flex items-center justify-between text-xs">
            <span className="text-zinc-400">{s.label}</span>
            <span className="text-zinc-500">{s.count}</span>
          </div>
        ))}
        {context.notes.map((n, i) => (
          <p key={i} className="text-[11px] text-amber-400/70 pt-1">{n}</p>
        ))}
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// NewSessionModal
// --------------------------------------------------------------------------- //

function NewSessionModal({ onClose, onCreated }: { onClose: () => void; onCreated: (s: PilotSession) => void }) {
  const [title, setTitle] = useState('')
  const [goal, setGoal] = useState('')
  const [busy, setBusy] = useState(false)

  const create = async () => {
    if (!title.trim() || busy) return
    setBusy(true)
    try {
      const s = await createPilotSession({ title: title.trim(), goal: goal.trim() || undefined })
      onCreated(s)
    } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-zinc-800 bg-zinc-950 p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-semibold text-zinc-100 mb-4 flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-emerald-500" /> New Handbook Pilot session
        </h3>
        <label className="block text-xs text-zinc-400 mb-1">Title</label>
        <input
          autoFocus value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="Meal & rest break policy refresh"
          className="w-full rounded-lg bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-zinc-200 mb-3 focus:outline-none focus:border-emerald-500"
        />
        <label className="block text-xs text-zinc-400 mb-1">What do you want to draft? <span className="text-zinc-600">(optional)</span></label>
        <textarea
          value={goal} onChange={(e) => setGoal(e.target.value)} rows={3}
          placeholder="A compliant meal-and-rest-break policy for our California and Texas hourly staff."
          className="w-full rounded-lg bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-zinc-200 mb-4 focus:outline-none focus:border-emerald-500"
        />
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-2 text-sm text-zinc-400 hover:text-zinc-200">Cancel</button>
          <button
            onClick={() => void create()} disabled={!title.trim() || busy}
            className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm font-medium inline-flex items-center gap-2"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Create
          </button>
        </div>
      </div>
    </div>
  )
}
