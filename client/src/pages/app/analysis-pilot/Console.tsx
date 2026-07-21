import { useEffect, useMemo, useState } from 'react'
import { Check, Loader2, Send, X } from 'lucide-react'
import { HelpHint } from '../../../components/ui/HelpHint'
import {
  streamChat, patchDataset,
  type AnalysisSession, type AnalysisMessage, type ProposedEdit,
} from '../../../api/analysis-pilot/analysisPilot'
import { usePilotChat } from '../../../components/pilot/usePilotChat'
import { buildCidIndex, type FocusChip } from './shared'
import { CidChips, CitedMarkdown } from './citations'

// --------------------------------------------------------------------------- //
// Console — grounded chat with citation-aware observations.
// --------------------------------------------------------------------------- //

export function Console({ session, onTurn, focus, onRemoveFocus, onClearFocus, prefill }: {
  session: AnalysisSession; onTurn: () => void
  focus: FocusChip[]; onRemoveFocus: (cid: string) => void; onClearFocus: () => void
  prefill?: { text: string; nonce: number; autoSend?: boolean } | null
}) {
  const {
    messages, setMessages, input, setInput, busy, status, setStatus,
    scrollRef, textareaRef, runTurn,
  } = usePilotChat<AnalysisMessage>({ initialMessages: session.messages ?? [], statusLabel: 'Analyzing…', onTurn })
  // Per-proposal outcome, keyed `${messageIdx}:${editIdx}`.
  const [resolved, setResolved] = useState<Record<string, 'applied' | 'dismissed'>>({})
  const [applying, setApplying] = useState<string | null>(null)
  const cidIndex = useMemo(() => buildCidIndex(session), [session])

  // Examples tab hands off a prompt here. Plain examples just fill the composer
  // and focus it (never auto-send, avoids firing a grounded turn against
  // empty/no data); the live-demo examples set autoSend once their bundled
  // dataset is actually loaded, so the answer is real.
  useEffect(() => {
    if (!prefill) return
    if (prefill.autoSend) {
      void send(prefill.text)
    } else {
      setInput(prefill.text)
      textareaRef.current?.focus()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill?.nonce])

  const send = async (override?: string) => {
    const text = (override ?? input).trim()
    if (!text || busy) return
    const focusCids = focus.map((c) => c.cid)
    setInput('')
    setMessages((m) => [...m, {
      role: 'user', content: text,
      metadata: focusCids.length ? { focus: focusCids } : null,
      created_at: new Date().toISOString(),
    }])
    onClearFocus()
    await runTurn(async (signal, markError) => {
      await streamChat(session.id, text, {
        onStatus: (msg) => setStatus(msg),
        onResult: (data) => {
          setMessages((m) => [...m, {
            role: 'assistant', content: data.assistant_text,
            metadata: {
              evidence_map: data.evidence_map, open_questions: data.open_questions,
              dropped_citations: data.dropped_citations, proposed_edits: data.proposed_edits,
            },
            created_at: new Date().toISOString(),
          }])
        },
        onError: (msg) => { markError(); setStatus(`⚠ ${msg}`) },
      }, signal, focusCids)
    })
  }

  // Apply a chat-proposed correction through the normal confirmed PATCH →
  // recompute path, using the CURRENT stored extraction (never the AI's copy).
  const applyEdit = async (edit: ProposedEdit, key: string) => {
    const ds = (session.datasets ?? []).find((d) => d.id === edit.dataset_id)
    const ext = ds?.extraction
    const idx = ext ? ext.periods.indexOf(edit.period) : -1
    const item = ext?.line_items.find((it) => it.label === edit.label)
    if (!ds || !ext || idx < 0 || !item) {
      setStatus('⚠ That figure no longer matches the stored extraction — review the dataset instead.')
      return
    }
    setApplying(key)
    try {
      await patchDataset(session.id, ds.id, {
        extraction: {
          ...ext,
          line_items: ext.line_items.map((it) =>
            it.label === edit.label
              ? { ...it, values: it.values.map((v, j) => (j === idx ? edit.proposed_value : v)) }
              : it),
        },
      })
      setResolved((r) => ({ ...r, [key]: 'applied' }))
      onTurn()
    } catch (e) {
      setStatus(`⚠ ${e instanceof Error ? e.message : 'Could not apply the correction.'}`)
    } finally {
      setApplying(null)
    }
  }

  const liveCount = messages.filter((m) => m.role !== 'system').length
  const msgLimit = session.message_limit ?? 240
  const nearCap = liveCount >= msgLimit * 0.9

  return (
    <div className="flex flex-col h-full">
      {nearCap && (
        <div className="px-3 py-2 text-[11px] text-amber-300 bg-amber-500/10 border-b border-amber-500/20">
          This session is near its conversation limit ({liveCount}/{msgLimit}). Generate a report to
          capture the analysis, then start a new session.
        </div>
      )}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <p className="text-sm text-zinc-600">
            Ask anything about your data — “Summarize this”, “What’s the trend?”, “Which is highest?”,
            “How volatile is this?”, “Compare the two periods.” Every number the pilot cites was computed
            from your data; anything it can’t trace is dropped. Click a record in the Metrics tab to focus
            the conversation on it.
            <HelpHint text="Each reply carries a “Grounded observations” footnote — one claim per line, with “[N cited]” showing how many real computed records back it. Uncited numbers are dropped, so every figure shown is one that exists." />
          </p>
        )}
        {messages.map((m, i) => (
          // System rows are compaction summaries — internal plumbing, never shown.
          // Return null (not filtered) so `i` stays the stable stored index that
          // `resolved` proposed-edit keys depend on.
          m.role === 'system' ? null : (
          <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
            <div className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm ${
              m.role === 'user' ? 'bg-emerald-600 text-white whitespace-pre-wrap' : 'bg-zinc-800/70 text-zinc-200'
            }`}>
              {m.role === 'assistant'
                ? <CitedMarkdown text={m.content} idx={cidIndex} />
                : m.content}
              {m.role === 'user' && (m.metadata?.focus?.length ?? 0) > 0 && (
                <div className="mt-1.5 text-[10px] text-emerald-200/80">
                  ⌖ focused on {m.metadata!.focus!.length} highlighted record{m.metadata!.focus!.length > 1 ? 's' : ''}
                </div>
              )}
              {m.role === 'assistant' && (m.metadata?.analysis_plan?.length ?? 0) > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-[11px] uppercase tracking-wide text-zinc-500 hover:text-zinc-300">
                    Reasoning ({m.metadata!.analysis_plan!.length} step{m.metadata!.analysis_plan!.length > 1 ? 's' : ''})
                  </summary>
                  <ol className="mt-1.5 space-y-1 list-decimal list-inside text-xs text-zinc-400">
                    {m.metadata!.analysis_plan!.map((s, j) => (
                      <li key={j}>
                        <span className="text-zinc-300">{s.step}</span>
                        {s.finding && <> — {s.finding}</>}{' '}
                        <CidChips cids={s.cited_ids ?? []} idx={cidIndex} />
                      </li>
                    ))}
                  </ol>
                </details>
              )}
              {m.role === 'assistant' && m.metadata?.evidence_map && m.metadata.evidence_map.length > 0 && (
                <div className="mt-2 pt-2 border-t border-zinc-700/60">
                  <div className="text-[11px] uppercase tracking-wide text-emerald-400/80 mb-1">Grounded observations</div>
                  <ul className="text-xs text-zinc-400 space-y-1">
                    {m.metadata.evidence_map.map((ob, j) => (
                      <li key={j}>• {ob.point} <CidChips cids={ob.cited_ids ?? []} idx={cidIndex} /></li>
                    ))}
                  </ul>
                </div>
              )}
              {m.role === 'assistant' && m.metadata?.open_questions && m.metadata.open_questions.length > 0 && (
                <div className="mt-2 pt-2 border-t border-zinc-700/60">
                  <div className="text-[11px] uppercase tracking-wide text-amber-400/80 mb-1">Open questions</div>
                  <ul className="list-disc list-inside text-xs text-zinc-400 space-y-0.5">
                    {m.metadata.open_questions.map((q, j) => <li key={j}>{q}</li>)}
                  </ul>
                </div>
              )}
              {m.role === 'assistant' && (m.metadata?.proposed_edits?.length ?? 0) > 0 && (
                <div className="mt-2 pt-2 border-t border-zinc-700/60 space-y-2">
                  <div className="text-[11px] uppercase tracking-wide text-emerald-400/80">Proposed corrections</div>
                  {m.metadata!.proposed_edits!.map((edit, j) => {
                    const key = `${i}:${j}`
                    const state = resolved[key]
                    return (
                      <div key={j} className="rounded-lg border border-zinc-700/70 bg-zinc-900/50 px-2.5 py-2">
                        <div className="text-xs text-zinc-200">
                          {edit.label} · {edit.period}: <span className="line-through text-zinc-500">{edit.current_value ?? '—'}</span>
                          {' → '}<span className="text-emerald-400 font-medium">{edit.proposed_value}</span>
                        </div>
                        {edit.reason && <div className="text-[11px] text-zinc-500 mt-0.5">{edit.reason}</div>}
                        <div className="flex gap-2 mt-1.5">
                          {state === 'applied' ? (
                            <span className="text-[11px] text-emerald-400 inline-flex items-center gap-1"><Check className="h-3 w-3" /> Applied — metrics recomputed</span>
                          ) : state === 'dismissed' ? (
                            <span className="text-[11px] text-zinc-500">Dismissed</span>
                          ) : (
                            <>
                              <button onClick={() => void applyEdit(edit, key)} disabled={applying === key}
                                className="text-[11px] px-2 py-0.5 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white inline-flex items-center gap-1">
                                {applying === key ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />} Apply
                              </button>
                              <button onClick={() => setResolved((r) => ({ ...r, [key]: 'dismissed' }))}
                                className="text-[11px] px-2 py-0.5 rounded text-zinc-400 hover:text-zinc-200">Dismiss</button>
                            </>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
          )
        ))}
        {status && (
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> {status}
          </div>
        )}
      </div>
      <div className="p-3 border-t border-zinc-800">
        {focus.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 mb-2">
            {focus.map((c) => (
              <span key={c.cid} className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300">
                <span className="truncate max-w-[220px]" title={c.label}>{c.label}</span>
                <button onClick={() => onRemoveFocus(c.cid)} className="text-emerald-400/70 hover:text-emerald-200">
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            <button onClick={onClearFocus} className="text-[11px] text-zinc-500 hover:text-zinc-300">clear</button>
          </div>
        )}
        <div className="flex gap-2">
          <textarea ref={textareaRef} value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }}
            placeholder={focus.length ? 'Ask about the highlighted records…' : 'Ask anything about your data…'} rows={2}
            className="flex-1 resize-none rounded-lg bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-emerald-500" />
          <button onClick={() => void send()} disabled={busy || !input.trim()}
            className="px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white self-stretch flex items-center">
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
