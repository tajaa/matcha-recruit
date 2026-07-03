import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Scale, Send, ShieldAlert } from 'lucide-react'
import type { EvidencePreview, MatterMessage } from '../../../api/legalDefense'
import { DISCLAIMER, LABEL, STARTERS, fmtWhen, type CidInfo } from './shared'

/** Analyst console: full-width transcript rows (no chat bubbles), bottom-
 *  anchored so a short exchange sits next to the composer instead of leaving
 *  a void, with grounded observations rendered as cited evidence blocks. */
export function Console({ messages, status, sending, evidence, onSend }: {
  messages: MatterMessage[]
  status: string | null
  sending: boolean
  evidence: EvidencePreview | null
  onSend: (text: string) => void
}) {
  const [input, setInput] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, status])

  // cid → human ref ("IR-2024-003") for citation chips.
  const cidIndex = useMemo(() => {
    const idx: Record<string, CidInfo> = {}
    if (evidence) {
      for (const s of Object.values(evidence.sources)) {
        for (const r of s.records) idx[r.cid] = { ref: r.ref, label: s.label, summary: r.summary }
      }
    }
    return idx
  }, [evidence])

  function autoGrow() {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }

  function submit() {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    if (inputRef.current) inputRef.current.style.height = 'auto'
    onSend(text)
  }

  const sourceCount = evidence ? Object.keys(evidence.sources).length : 0

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="flex min-h-full flex-col justify-end">
          {messages.length === 0 && !status && (
            <div className="px-5 py-8">
              <div className={LABEL}>Analyst console</div>
              <p className="mt-2 max-w-[60ch] text-sm leading-relaxed text-zinc-400">
                {evidence && evidence.total > 0
                  ? <>The record is assembled — <span className="font-mono tabular-nums text-zinc-200">{evidence.total}</span> records across <span className="font-mono tabular-nums text-zinc-200">{sourceCount}</span> systems are in scope.</>
                  : 'The record is being assembled.'}{' '}
                Describe what's being claimed and the timeframe; the analyst maps your own records to it and flags what counsel should look at.
              </p>
              <div className="mt-4 max-w-[60ch]">
                {STARTERS.map((s) => (
                  <button key={s}
                    onClick={() => { setInput(s); inputRef.current?.focus() }}
                    className="group flex w-full items-start gap-2.5 border-t border-white/[0.06] py-2.5 text-left text-[13px] text-zinc-500 transition-colors last:border-b last:border-white/[0.06] hover:text-zinc-200"
                  >
                    <span className="font-mono text-emerald-500/70 transition-colors group-hover:text-emerald-400">›</span>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => <Entry key={i} m={m} cidIndex={cidIndex} />)}

          {status && (
            <div className="border-t border-white/[0.06] bg-white/[0.015] px-5 py-4">
              <RoleMarker role="assistant" />
              <div className="mt-1.5 flex items-center gap-2 text-sm text-zinc-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-400" /> {status}
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>

      {/* Composer */}
      <div className="shrink-0 border-t border-white/[0.06] px-5 pb-2 pt-3">
        <div className="flex items-end gap-2 rounded-md border border-white/[0.08] bg-zinc-900/60 px-3 transition-colors focus-within:border-emerald-500/50">
          <span className="select-none pb-[9px] font-mono text-sm text-emerald-500/80">›</span>
          <textarea
            ref={inputRef}
            value={input}
            rows={1}
            placeholder="Describe the matter or ask what the records show…"
            onChange={(e) => { setInput(e.target.value); autoGrow() }}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
            className="flex-1 resize-none bg-transparent py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none"
          />
          <button
            onClick={submit}
            disabled={sending || !input.trim()}
            aria-label="Send"
            className="mb-1.5 rounded p-1.5 text-emerald-400 transition-colors hover:bg-emerald-500/10 disabled:text-zinc-700 disabled:hover:bg-transparent"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
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

function RoleMarker({ role, when }: { role: 'user' | 'assistant' | 'system'; when?: string }) {
  return (
    <div className="flex items-baseline gap-3">
      {role === 'user' ? (
        <span className="text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-500">You</span>
      ) : (
        <span className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.15em] text-emerald-400/90">
          <Scale className="h-3 w-3" /> Legal Pilot
        </span>
      )}
      {when && <span className="font-mono text-[10px] tabular-nums text-zinc-600">{fmtWhen(when)}</span>}
    </div>
  )
}

function Entry({ m, cidIndex }: { m: MatterMessage; cidIndex: Record<string, CidInfo> }) {
  const isUser = m.role === 'user'
  const meta = m.metadata
  return (
    <div className={`border-t border-white/[0.06] px-5 py-4 first:border-t-0 ${isUser ? '' : 'bg-white/[0.015]'}`}>
      <RoleMarker role={m.role} when={m.created_at} />
      <p className={`mt-1.5 max-w-[65ch] whitespace-pre-wrap text-sm leading-relaxed ${isUser ? 'text-zinc-300' : 'text-zinc-200'}`}>
        {m.content}
      </p>

      {!isUser && meta?.evidence_map && meta.evidence_map.length > 0 && (
        <div className="mt-3 max-w-[65ch] space-y-2 border-l-2 border-emerald-500/30 pl-3">
          <div className={LABEL}>Grounded observations</div>
          {meta.evidence_map.map((it, i) => (
            <div key={i} className="text-[13px] leading-relaxed">
              <span className="text-zinc-300">{it.point}</span>
              {it.cited_ids.length > 0 && (
                <span className="ml-1.5 inline-flex flex-wrap gap-1 align-middle">
                  {it.cited_ids.map((cid) => {
                    const e = cidIndex[cid]
                    return (
                      <span key={cid} title={e?.summary}
                        className="rounded-sm bg-zinc-800/80 px-1.5 py-px font-mono text-[10px] text-zinc-400">
                        {e?.ref || e?.label || `${cid.slice(0, 15)}…`}
                      </span>
                    )
                  })}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {!isUser && meta?.open_questions && meta.open_questions.length > 0 && (
        <div className="mt-3 max-w-[65ch] border-l-2 border-amber-500/30 pl-3">
          <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-amber-400/80">
            Open questions for counsel
          </div>
          <ul className="mt-1 list-disc pl-4 text-[13px] leading-relaxed text-zinc-400">
            {meta.open_questions.map((q, i) => <li key={i}>{q}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}
