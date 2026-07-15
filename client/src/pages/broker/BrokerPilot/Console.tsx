import { useEffect, useMemo, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { FileUp, Loader2, Send, ShieldAlert, Sparkles } from 'lucide-react'
import {
  streamPilotChat,
  type ContextPreview, type CorpusRecord, type EvidenceMapItem, type GapSeverity,
  type MissingDoc, type PilotMessage, type PilotSession,
} from '../../../api/brokerPilot'
import { DISCLAIMER, LABEL, missingRequired, startersFor } from './shared'

interface ConsoleProps {
  session: PilotSession
  context: ContextPreview | null
  onTurnComplete: () => void
  onUploadDocs: () => void
}

type LiveMessage = Pick<PilotMessage, 'role' | 'content' | 'metadata'>

/** Analyst console: full-width transcript rows (no chat bubbles), bottom-
 *  anchored, with grounded observations rendered as cited evidence blocks. */
export function Console({ session, context, onTurnComplete, onUploadDocs }: ConsoleProps) {
  const [live, setLive] = useState<LiveMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [view, setView] = useState<'chat' | 'examples'>('chat')
  const [blocked, setBlocked] = useState<MissingDoc[] | null>(null)
  // "Ask anyway", remembered for the rest of this session in this tab: the gate
  // is server-side and stateless, so without this every subsequent turn would
  // re-raise the same 409 and re-nag someone who already answered it.
  const forceRef = useRef(false)
  // Which session already got its auto-kickoff turn — guards against re-firing
  // on every context refetch (doc upload, poll) within the same session.
  const kickoffRef = useRef<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const starters = startersFor(session)

  // cid → corpus record, for citation chips (built from the flat sources).
  const cidIndex = useMemo(() => {
    const map = new Map<string, CorpusRecord>()
    for (const source of Object.values(context?.sources ?? {})) {
      for (const r of source.records) map.set(r.cid, r)
    }
    return map
  }, [context])

  // Persisted transcript + optimistic in-flight turns; reconcile by content so a
  // refetch can't wipe a different in-flight turn.
  const persisted = session.messages ?? []
  useEffect(() => {
    setLive([])
    setBlocked(null)
    forceRef.current = false  // a different session has a different mode + documents
  }, [session.id])
  const persistedKeys = new Set(persisted.map((m) => `${m.role} ${m.content}`))
  const pending = live.filter((m) => !persistedKeys.has(`${m.role} ${m.content}`))
  const messages: LiveMessage[] = [...persisted, ...pending]

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages.length, status])

  function autoGrow() {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }

  const send = async (text?: string) => {
    const message = (text ?? input).trim()
    if (!message || busy) return
    setInput('')
    setBlocked(null)
    if (inputRef.current) inputRef.current.style.height = 'auto'
    setBusy(true)
    const optimistic: LiveMessage = { role: 'user', content: message, metadata: null }
    setLive((prev) => [...prev, optimistic])
    try {
      await streamPilotChat(session.id, message, {
        onStatus: (m) => setStatus(m),
        onResult: (data) => {
          setLive((prev) => [...prev, {
            role: 'assistant',
            content: data.assistant_text,
            metadata: {
              evidence_map: data.evidence_map,
              key_questions: data.key_questions,
              considerations: data.considerations,
              gaps: data.gaps,
              dropped_citations: data.dropped_citations,
            },
          }])
        },
        // The mode's documents aren't in. The server refused BEFORE persisting the
        // turn, so the optimistic row has to come back out and the text goes back
        // in the composer — the question survives the interruption either way.
        onBlocked: (missing) => {
          setLive((prev) => prev.filter((m) => m !== optimistic))
          setInput(message)
          setBlocked(missing)
        },
        onError: (m) => setLive((prev) => [...prev, { role: 'assistant', content: m, metadata: null }]),
      }, { force: forceRef.current })
    } finally {
      setBusy(false)
      setStatus(null)
      onTurnComplete()
    }
  }

  // Auto-kickoff: a moded session with nothing said yet and no outstanding
  // required documents opens with the mode's first starter as a real turn,
  // instead of waiting for someone to type the first question. Fires once
  // required docs clear (upload, "skip", or platform data already covering
  // them) — same path as a typed message, so it persists, streams, and
  // counts against rate limits identically.
  useEffect(() => {
    if (!session.template) return
    if (session.status === 'closed') return
    if ((session.messages?.length ?? 0) > 0 || live.length > 0) return
    if (!context) return
    if (missingRequired(context.doc_requirements).length > 0) return
    if (kickoffRef.current === session.id) return
    const starter = startersFor(session)[0]
    if (!starter) return
    kickoffRef.current = session.id
    void send(starter)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id, session.template, session.status, session.messages, context])

  const askAnyway = () => {
    forceRef.current = true
    setBlocked(null)
    void send()
  }

  const sourceCount = context ? Object.values(deriveNonEmpty(context)).length : 0

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-1 border-b border-white/[0.06] px-5 py-1.5">
        {(['chat', 'examples'] as const).map((v) => (
          <button key={v} onClick={() => setView(v)}
            className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.15em] transition-colors ${
              view === v ? 'bg-white/[0.06] text-zinc-200' : 'text-zinc-500 hover:text-zinc-300'}`}>
            {v === 'chat' ? 'Console' : 'Examples'}
          </button>
        ))}
      </div>
      {view === 'examples' ? (
        <div className="flex-1 overflow-y-auto px-5 py-8">
          <div className={LABEL}>{session.template ? `${session.template.label} · example prompts` : 'Example prompts'}</div>
          <p className="mt-2 max-w-[60ch] text-sm leading-relaxed text-zinc-400">
            Click one to drop it into the composer, then edit or send it as-is.
          </p>
          <div className="mt-4 max-w-[60ch]">
            {starters.map((s) => (
              <button key={s}
                onClick={() => { setInput(s); setView('chat'); inputRef.current?.focus() }}
                className="group flex w-full items-start gap-2.5 border-t border-white/[0.06] py-2.5 text-left text-[13px] text-zinc-500 transition-colors last:border-b last:border-white/[0.06] hover:text-zinc-200"
              >
                <span className="font-mono text-emerald-500/70 transition-colors group-hover:text-emerald-400">›</span>
                {s}
              </button>
            ))}
          </div>
        </div>
      ) : (
      <div className="flex-1 overflow-y-auto">
        <div className="flex min-h-full flex-col justify-end">
          {messages.length === 0 && !status && (
            <div className="px-5 py-8">
              <div className={LABEL}>{session.template ? session.template.label : 'Analyst console'}</div>
              <p className="mt-2 max-w-[60ch] text-sm leading-relaxed text-zinc-400">
                {session.template
                  ? <>{session.template.description}{' '}</>
                  : null}
                {context && context.total > 0
                  ? <>The record is assembled — <span className="font-mono tabular-nums text-zinc-200">{context.total}</span> records across <span className="font-mono tabular-nums text-zinc-200">{sourceCount}</span> systems are in scope.</>
                  : 'The record is being assembled.'}{' '}
                Ask what the record shows — broker-entered data, platform-generated operational
                history, and uploaded documents in one picture; every answer cites the records behind it.
              </p>
              <div className="mt-4 max-w-[60ch]">
                {starters.map((s) => (
                  <button key={s}
                    onClick={() => { setInput(s); inputRef.current?.focus() }}
                    disabled={busy}
                    className="group flex w-full items-start gap-2.5 border-t border-white/[0.06] py-2.5 text-left text-[13px] text-zinc-500 transition-colors last:border-b last:border-white/[0.06] hover:text-zinc-200"
                  >
                    <span className="font-mono text-emerald-500/70 transition-colors group-hover:text-emerald-400">›</span>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            m.role === 'user'
              ? <Entry key={i} role="user" content={m.content} />
              : <AssistantEntry key={i} message={m} cidIndex={cidIndex} />
          ))}

          {status && (
            <div className="border-t border-white/[0.06] bg-white/[0.015] px-5 py-4">
              <RoleMarker role="assistant" />
              <div className="mt-1.5 flex items-center gap-2 text-sm text-zinc-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-400" /> {status ?? 'Analyzing…'}
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>
      )}

      {/* The mode's document gate. Soft by construction: the analyst can answer
          without the paper, it just has to say what it's working without — so the
          escape hatch sits right next to the fix. */}
      {blocked && blocked.length > 0 && (
        <div className="shrink-0 border-t border-amber-500/20 bg-amber-500/[0.06] px-5 py-3">
          <div className="flex items-start gap-2">
            <FileUp className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-amber-200">
                {session.template?.label ?? 'This mode'} analyzes{' '}
                {blocked.map((m) => m.label).join(' and ')} — not provided yet.
              </p>
              <ul className="mt-1 space-y-0.5">
                {blocked.map((m) => (
                  <li key={m.doc_type} className="text-[11px] leading-snug text-amber-200/70">
                    {m.hint}
                  </li>
                ))}
              </ul>
              <div className="mt-2 flex items-center gap-2">
                <button
                  onClick={onUploadDocs}
                  className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-200 transition-colors hover:bg-amber-500/20"
                >
                  Upload documents
                </button>
                <button
                  onClick={askAnyway}
                  className="text-[11px] text-zinc-400 underline-offset-2 transition-colors hover:text-zinc-200 hover:underline"
                >
                  Ask anyway
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Composer */}
      <div className="shrink-0 border-t border-white/[0.06] px-5 pb-2 pt-3">
        <div className="flex items-end gap-2 rounded-md border border-white/[0.08] bg-zinc-900/60 px-3 transition-colors focus-within:border-emerald-500/50">
          <span className="select-none pb-[9px] font-mono text-sm text-emerald-500/80">›</span>
          <textarea
            ref={inputRef}
            value={input}
            rows={1}
            placeholder="Ask what the documents and platform data show…"
            onChange={(e) => { setInput(e.target.value); autoGrow() }}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }}
            className="flex-1 resize-none bg-transparent py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none"
          />
          <button
            onClick={() => void send()}
            disabled={busy || !input.trim()}
            aria-label="Send"
            className="mb-1.5 rounded p-1.5 text-emerald-400 transition-colors hover:bg-emerald-500/10 disabled:text-zinc-700 disabled:hover:bg-transparent"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
        <div className="mt-1 text-[10px] text-zinc-600">Enter to send · Shift+Enter for a new line</div>
      </div>
      <div className="flex shrink-0 items-center gap-2 border-t border-white/[0.06] px-5 py-1.5">
        <ShieldAlert className="h-3 w-3 shrink-0 text-amber-400/70" />
        <p className="text-[10px] leading-snug text-amber-200/60">{DISCLAIMER}</p>
      </div>
    </div>
  )
}

function deriveNonEmpty(context: ContextPreview): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, s] of Object.entries(context.sources)) if (s.records.length) out[k] = s
  return out
}

function RoleMarker({ role }: { role: 'user' | 'assistant' | 'system' }) {
  return role === 'user' ? (
    <span className="text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-500">You</span>
  ) : (
    <span className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.15em] text-emerald-400/90">
      <Sparkles className="h-3 w-3" /> Broker Pilot
    </span>
  )
}

function Entry({ role, content }: { role: 'user' | 'assistant' | 'system'; content: string }) {
  return (
    <div className="border-t border-white/[0.06] px-5 py-4 first:border-t-0">
      <RoleMarker role={role} />
      <p className="mt-1.5 max-w-[65ch] whitespace-pre-wrap text-sm leading-relaxed text-zinc-300">{content}</p>
    </div>
  )
}

const SEVERITY_CHIP: Record<GapSeverity, string> = {
  high: 'bg-red-500/15 text-red-300',
  medium: 'bg-amber-500/15 text-amber-300',
  low: 'bg-zinc-700/60 text-zinc-400',
}

function AssistantEntry({ message, cidIndex }: {
  message: LiveMessage
  cidIndex: Map<string, CorpusRecord>
}) {
  const meta = message.metadata
  const evidence = meta?.evidence_map ?? []
  // `open_questions` is the pre-structured-answer key — old transcripts still render.
  const keyQuestions = meta?.key_questions ?? meta?.open_questions ?? []
  const considerations = meta?.considerations ?? []
  const gaps = meta?.gaps ?? []
  const dropped = meta?.dropped_citations ?? []

  return (
    <div className="border-t border-white/[0.06] bg-white/[0.015] px-5 py-4">
      <RoleMarker role="assistant" />
      <div className="prose prose-sm prose-invert prose-zinc mt-1.5 max-w-[65ch] text-sm leading-relaxed text-zinc-200 prose-p:my-1.5 prose-headings:text-zinc-100">
        <Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown>
      </div>

      {keyQuestions.length > 0 && (
        <div className="mt-3 max-w-[65ch] border-l-2 border-sky-500/30 pl-3">
          <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-sky-400/80">Key questions</div>
          <ul className="mt-1 list-disc pl-4 text-[13px] leading-relaxed text-zinc-400">
            {keyQuestions.map((q, i) => <li key={i}>{q}</li>)}
          </ul>
        </div>
      )}

      {considerations.length > 0 && (
        <div className="mt-3 max-w-[65ch] space-y-2 border-l-2 border-violet-500/30 pl-3">
          <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-violet-400/80">Strategic considerations</div>
          {considerations.map((it, i) => <EvidenceLine key={i} item={it} cidIndex={cidIndex} />)}
        </div>
      )}

      {gaps.length > 0 && (
        <div className="mt-3 max-w-[65ch] space-y-2 border-l-2 border-amber-500/40 pl-3">
          <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-amber-400/80">Gaps identified</div>
          {gaps.map((g, i) => (
            <EvidenceLine key={i} item={g} cidIndex={cidIndex} severity={g.severity ?? null} />
          ))}
        </div>
      )}

      {evidence.length > 0 && (
        <div className="mt-3 max-w-[65ch] space-y-2 border-l-2 border-emerald-500/30 pl-3">
          <div className={LABEL}>Grounded observations</div>
          {evidence.map((it, i) => <EvidenceLine key={i} item={it} cidIndex={cidIndex} />)}
        </div>
      )}

      {dropped.length > 0 && (
        <p className="mt-3 text-[11px] text-zinc-600">
          {dropped.length} ungrounded claim{dropped.length === 1 ? '' : 's'} removed by the citation check.
        </p>
      )}
    </div>
  )
}

function EvidenceLine({ item, cidIndex, severity = null }: {
  item: EvidenceMapItem
  cidIndex: Map<string, CorpusRecord>
  severity?: GapSeverity | null
}) {
  return (
    <div className="text-[13px] leading-relaxed">
      {severity && (
        <span className={`mr-1.5 rounded-sm px-1.5 py-px align-middle font-mono text-[9px] uppercase tracking-wider ${SEVERITY_CHIP[severity]}`}>
          {severity}
        </span>
      )}
      <span className="text-zinc-300">{item.point}</span>
      {item.cited_ids.length > 0 && (
        <span className="ml-1.5 inline-flex flex-wrap gap-1 align-middle">
          {item.cited_ids.map((cid) => {
            const rec = cidIndex.get(cid)
            const label = rec?.ref || cid.split(':')[0]
            return (
              <span key={cid}
                title={rec ? `${rec.ref ? rec.ref + ' — ' : ''}${rec.summary}` : cid}
                className="rounded-sm bg-zinc-800/80 px-1.5 py-px align-baseline font-mono text-[10px] text-zinc-300 underline decoration-zinc-600 decoration-dotted underline-offset-2 transition-colors hover:bg-zinc-700/80 hover:text-emerald-300"
              >
                {label}
              </span>
            )
          })}
        </span>
      )}
    </div>
  )
}
