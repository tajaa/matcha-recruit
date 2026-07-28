import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2, Send, Play, Check, ArrowRight, AlertTriangle, ExternalLink, Circle, Square, CheckSquare, X } from 'lucide-react'
import {
  streamPilotChat, streamAgentChat, createAction, getAction, approveAction,
  confirmAction, cancelAction,
  type PilotSession, type PilotMessage, type PilotAction, type Proposal,
  type Citation, type CitationRecord, type PilotStep, type ApproveRowResult, type StagedRow,
} from '../../../../api/admin/compliancePilot'
import StepTimeline from '../../../../components/ui/StepTimeline'
import { libraryLink, coverageLink } from '../utils'

type Props = {
  session: PilotSession
  onRefetch: () => void            // reload this session (messages + actions)
  onSessionsChanged: () => void    // reload the sessions rail (titles/counts)
}

type LiveMsg = { role: 'user' | 'assistant'; content: string; metadata?: PilotMessage['metadata'] }

// Narrow shapes for each action kind's result JSONB (backend-owned; kept loose).
type ResearchResult = { staged?: number; codifiable?: number; staged_rows?: StagedRow[]
  state?: string; city?: string | null; industry_tag?: string }
type ApproveResultBody = { activated?: number; codified?: number; uncodified?: number; already_live?: number; results?: ApproveRowResult[] }
type DeadRow = { id: string; category: string; source_url: string; state: string; city: string }
type CheckResult = { checked?: number; dead?: number; unreachable?: number; missing_citation?: number; dead_rows?: DeadRow[]; state?: string; city?: string | null }

export default function Console({ session, onRefetch, onSessionsChanged }: Props) {
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [live, setLive] = useState<LiveMsg[]>([])
  const [pendingSteps, setPendingSteps] = useState<PilotStep[]>([])
  const [runningAction, setRunningAction] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const isAgent = session.mode === 'agent'

  // Abort any in-flight turn when the user switches sessions (unmount) —
  // an agent turn can run up to 240s, so leaving it dangling on navigation
  // would keep spending against the shared rate limit for no one watching.
  useEffect(() => () => abortRef.current?.abort(), [])

  const persisted = session.messages ?? []
  const actions = session.actions ?? []
  const starters = session.template?.starters ?? []
  // Requirement ids already committed (across ALL approve actions) — so a research
  // card greys out just those rows and keeps the rest selectable.
  const committedRowIds = new Set<string>()
  for (const a of actions) {
    if (a.kind !== 'approve') continue
    const res = (a.result as { results?: Array<{ id?: string }> } | null)?.results ?? []
    for (const row of res) if (row.id) committedRowIds.add(row.id)
  }

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [persisted.length, live.length, status, actions.length])

  // Reconcile: once a live message lands in the persisted transcript, drop it.
  useEffect(() => {
    if (live.length === 0) return
    setLive((prev) => prev.filter((lm) =>
      !persisted.some((pm) => pm.role === lm.role && pm.content === lm.content)))
  }, [persisted, live.length])

  // Poll any running action until it settles, then refetch the session.
  useEffect(() => {
    const running = actions.filter((a) => a.status === 'running')
    if (running.length === 0) return
    let cancelled = false
    const t = window.setInterval(async () => {
      for (const a of running) {
        try {
          const fresh = await getAction(a.id)
          if (!cancelled && fresh.status !== 'running') { onRefetch(); return }
        } catch { /* keep polling */ }
      }
    }, 3000)
    return () => { cancelled = true; window.clearInterval(t) }
  }, [actions, onRefetch])

  const send = useCallback(async (text: string) => {
    const msg = text.trim()
    if (!msg || sending) return
    setInput('')
    setSending(true); setStatus('Thinking…'); setPendingSteps([])
    setLive((p) => [...p, { role: 'user', content: msg }])
    const controller = new AbortController()
    abortRef.current = controller
    try {
      if (isAgent) {
        await streamAgentChat(session.id, msg, {
          onStatus: (m) => setStatus(m),
          onStep: (s) => setPendingSteps((p) => [...p, s]),
          onResult: (data) => {
            setLive((p) => [...p, {
              role: 'assistant', content: data.message,
              metadata: { steps: data.steps, citation_records: data.citations,
                          proposal_action_ids: data.proposal_action_ids },
            }])
          },
          onError: (m) => setLive((p) => [...p, { role: 'assistant', content: `⚠ ${m}` }]),
        }, controller.signal)
      } else {
        await streamPilotChat(session.id, msg, {
          onStatus: (m) => setStatus(m),
          onResult: (data) => {
            setLive((p) => [...p, {
              role: 'assistant', content: data.assistant_text,
              metadata: { citations: data.citations, proposal: data.proposal,
                          proposal_errors: data.proposal_errors },
            }])
          },
          onError: (m) => setLive((p) => [...p, { role: 'assistant', content: `⚠ ${m}` }]),
        }, controller.signal)
      }
    } finally {
      setSending(false); setStatus(null); setPendingSteps([])
      onRefetch(); onSessionsChanged()
    }
  }, [session.id, sending, isAgent, onRefetch, onSessionsChanged])

  async function runProposal(p: Proposal) {
    setRunningAction('creating')
    try {
      const body = p.kind === 'research'
        ? { kind: 'research' as const, state: p.state, city: p.city,
            industry_tag: p.industry_tag, categories: p.categories }
        : { kind: 'check_sources' as const, state: p.state, city: p.city }
      await createAction(session.id, body)
      onRefetch()
    } catch (e) {
      console.error(e)
    } finally { setRunningAction(null) }
  }

  return (
    <div className="flex flex-col h-full rounded-xl border border-white/[0.06] bg-black">
      <div className="border-b border-white/[0.06] px-4 py-2.5">
        <p className="text-sm font-medium text-zinc-100">{session.title}</p>
        <p className="text-[10px] uppercase tracking-wide text-emerald-400/70">{session.mode}</p>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {persisted.length === 0 && live.length === 0 && (
          <div className="space-y-2">
            <p className="text-xs text-zinc-500">Try:</p>
            {starters.map((s, i) => (
              <button key={i} onClick={() => send(s)}
                className="block w-full text-left rounded-lg border border-white/[0.06] px-3 py-2 text-xs text-zinc-400 hover:border-emerald-500/30 hover:text-zinc-200 transition-colors">
                {s}
              </button>
            ))}
          </div>
        )}

        {persisted.map((m, i) => <MessageRow key={`p${i}`} msg={m} onRun={runProposal} runningAction={runningAction} />)}
        {live.map((m, i) => <MessageRow key={`l${i}`} msg={m} onRun={runProposal} runningAction={runningAction} />)}

        {status && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> {status}
            </div>
            {pendingSteps.length > 0 && <StepTimeline steps={pendingSteps} headerLabel="Pilot" />}
          </div>
        )}

        {actions.length > 0 && (
          <div className="space-y-2 pt-2">
            <p className="text-[10px] uppercase tracking-wide text-zinc-500">Runs</p>
            {actions.map((a) => (
              <ActionCard key={a.id} action={a} onApproved={onRefetch} onChanged={onRefetch}
                committedRowIds={committedRowIds} />
            ))}
          </div>
        )}
      </div>

      <div className="border-t border-white/[0.06] p-3">
        <div className="flex items-end gap-2">
          <textarea
            value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
            rows={1} placeholder="Message the pilot…"
            className="flex-1 resize-none rounded-lg border border-white/[0.08] bg-white/[0.02] px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-white/20 max-h-32" />
          {sending && (
            <button onClick={() => abortRef.current?.abort()} title="Stop"
              className="rounded-lg border border-white/[0.08] p-2 text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-200">
              <Square className="h-4 w-4" />
            </button>
          )}
          <button onClick={() => send(input)} disabled={sending || !input.trim()}
            className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-2 text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-30">
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  )
}

function MessageRow({ msg, onRun, runningAction }: {
  msg: LiveMsg | PilotMessage
  onRun: (p: Proposal) => void
  runningAction: string | null
}) {
  const meta = msg.metadata
  const isUser = msg.role === 'user'
  return (
    <div className={isUser ? 'flex justify-end' : ''}>
      <div className={isUser
        ? 'max-w-[80%] rounded-lg bg-zinc-800/60 px-3 py-2 text-sm text-zinc-100'
        : 'max-w-full text-sm text-zinc-200'}>
        <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
        {!isUser && meta?.citations && meta.citations.length > 0 && (
          <div className="mt-2 space-y-1">
            {meta.citations.map((c: Citation, i) => (
              <div key={i} className="text-[11px] text-zinc-500">
                · {c.point}
                {c.cited_ids.length > 0 && (
                  <span className="ml-1 text-emerald-400/60">[{c.cited_ids.length}]</span>
                )}
              </div>
            ))}
          </div>
        )}
        {!isUser && meta?.proposal_errors && meta.proposal_errors.length > 0 && (
          <div className="mt-2 text-[11px] text-amber-400/80">
            {meta.proposal_errors.join(' ')}
          </div>
        )}
        {!isUser && meta?.proposal && (
          <ProposalCard proposal={meta.proposal} onRun={onRun} disabled={runningAction !== null} />
        )}
        {!isUser && meta?.citation_records && meta.citation_records.length > 0 && (
          <div className="mt-2 space-y-1">
            {meta.citation_records.map((c: CitationRecord) => (
              <div key={c.cid} className="text-[11px] text-zinc-500">
                · {c.summary}
                {c.source_url && (
                  <a href={c.source_url} target="_blank" rel="noreferrer"
                    className="ml-1.5 text-cyan-400/60 hover:text-cyan-300 inline-flex items-center gap-0.5">
                    <ExternalLink className="h-2.5 w-2.5" />
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
        {!isUser && meta?.steps && meta.steps.length > 0 && (
          <StepTimeline steps={meta.steps} headerLabel="Pilot" />
        )}
      </div>
    </div>
  )
}

function ProposalCard({ proposal, onRun, disabled }: {
  proposal: Proposal; onRun: (p: Proposal) => void; disabled: boolean
}) {
  const place = `${proposal.city ? proposal.city + ', ' : ''}${proposal.state}`
  return (
    <div className="mt-2.5 rounded-lg border border-emerald-500/25 bg-emerald-500/[0.04] p-3">
      {proposal.kind === 'research' ? (
        <>
          <p className="text-xs font-medium text-emerald-200">
            Research {proposal.industry_tag} × {place}
          </p>
          <p className="text-[11px] text-zinc-300 mt-1">
            {(proposal.category_labels ?? proposal.categories).slice(0, 6).join(', ')}
            {proposal.category_count > 6 && ` +${proposal.category_count - 6} more`}
            <span className="text-zinc-500"> ({proposal.category_count} categor{proposal.category_count === 1 ? 'y' : 'ies'})</span>
          </p>
          <p className="text-[11px] text-zinc-500 mt-0.5">
            {proposal.coverage.covered} covered · {proposal.coverage.unchecked} unchecked ·{' '}
            {proposal.existing_active_rows} active rows on file
            {!proposal.city_found && proposal.city && <span className="text-amber-400/80"> · city not on file (will be created)</span>}
          </p>
        </>
      ) : (
        <>
          <p className="text-xs font-medium text-emerald-200">Check source links · {place}</p>
          <p className="text-[11px] text-zinc-400 mt-1">
            {proposal.source_urls} source URLs across the jurisdiction chain
            {!proposal.city_found && proposal.city && <span className="text-amber-400/80"> · city not on file</span>}
          </p>
        </>
      )}
      <button onClick={() => onRun(proposal)} disabled={disabled}
        className="mt-2.5 inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1 text-xs text-emerald-200 hover:bg-emerald-500/25 disabled:opacity-40">
        <Play className="h-3 w-3" /> {proposal.kind === 'research' ? 'Run research' : 'Check sources'}
      </button>
    </div>
  )
}

// The agentic loop's stage_research/stage_check_sources/stage_approve tools
// INSERT a real action row with status='proposed' — this IS the staged state
// (no separate proposal-metadata shape like the legacy modes). Confirm/cancel
// go through the same REST endpoints the loop's own tools call, so a
// chat-driven and a button-driven confirm/cancel for the same action agree.
function ProposedActionCard({ action, onChanged }: { action: PilotAction; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const params = (action.params ?? {}) as Record<string, unknown>

  let summary: string
  if (action.kind === 'research') {
    const cats = (params.categories as string[] | undefined) ?? []
    const place = [params.city, params.state].filter(Boolean).join(', ')
    summary = `Research ${params.industry_tag ?? '?'} in ${place} — ${cats.length} categor${cats.length === 1 ? 'y' : 'ies'}`
  } else if (action.kind === 'check_sources') {
    const place = [params.city, params.state].filter(Boolean).join(', ')
    summary = `Check source links · ${place}`
  } else if (action.kind === 'approve') {
    const selected = (params.selected as number | undefined) ?? 0
    summary = `Commit ${selected} polic${selected === 1 ? 'y' : 'ies'} (${params.gate_ok ?? 0} pass the codify gate, ${params.gate_blocked ?? 0} would go live uncodified)`
  } else {
    summary = String(action.kind)
  }

  async function run(fn: (id: string) => Promise<unknown>) {
    setBusy(true); setErr(null)
    try { await fn(action.id); onChanged() }
    catch { setErr('That action may already have been actioned — refresh and check.') }
    finally { setBusy(false) }
  }

  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/[0.05] px-3 py-2.5">
      <p className="text-xs text-amber-100">{summary}</p>
      <p className="text-[10px] text-amber-400/70 mt-0.5">Awaiting confirmation</p>
      <div className="mt-2 flex items-center gap-2">
        <button disabled={busy} onClick={() => run(confirmAction)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1 text-xs text-emerald-200 hover:bg-emerald-500/25 disabled:opacity-30">
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />} Confirm
        </button>
        <button disabled={busy} onClick={() => run(cancelAction)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.1] px-2.5 py-1 text-xs text-zinc-400 hover:bg-white/[0.05] disabled:opacity-30">
          <X className="h-3 w-3" /> Cancel
        </button>
      </div>
      {err && <p className="mt-1 text-[11px] text-red-400">{err}</p>}
    </div>
  )
}

function ActionCard({ action, onApproved, onChanged, committedRowIds }: {
  action: PilotAction; onApproved: () => void; onChanged: () => void; committedRowIds: Set<string>
}) {
  if (action.status === 'proposed') {
    return <ProposedActionCard action={action} onChanged={onChanged} />
  }
  if (action.status === 'cancelled') {
    return (
      <div className="rounded-lg border border-white/[0.06] px-3 py-2 opacity-60">
        <p className="text-xs text-zinc-500">Cancelled</p>
      </div>
    )
  }
  if (action.status === 'superseded') {
    return (
      <div className="rounded-lg border border-white/[0.06] px-3 py-2 opacity-50">
        <p className="text-xs text-zinc-600">Superseded by a newer proposal</p>
      </div>
    )
  }
  if (action.status === 'running') {
    const msg = action.progress?.message ?? 'Working…'
    return (
      <div className="rounded-lg border border-white/[0.06] px-3 py-2.5 flex items-center gap-2">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-400" />
        <span className="text-xs text-zinc-400">{msg}</span>
      </div>
    )
  }
  if (action.status === 'failed') {
    const fr = (action.result ?? {}) as { error?: string }
    return (
      <div className="rounded-lg border border-red-500/25 bg-red-500/5 px-3 py-2.5 flex items-center gap-2">
        <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
        <span className="text-xs text-red-300">Run failed{fr.error ? `: ${fr.error}` : ''}</span>
      </div>
    )
  }

  // done
  if (action.kind === 'research') {
    return <ResearchCard action={action} committedRowIds={committedRowIds} onApproved={onApproved} />
  }

  if (action.kind === 'approve') {
    const r = (action.result ?? {}) as ApproveResultBody
    const results = r.results ?? []
    return (
      <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.03] px-3 py-2.5">
        <p className="text-xs text-zinc-200">
          Committed <b>{r.activated ?? 0}</b> · codified <b className="text-emerald-300">{r.codified ?? 0}</b>
          {(r.already_live ?? 0) > 0 && <span className="text-zinc-500"> · {r.already_live} already live</span>}
        </p>
        <div className="mt-1.5 space-y-1">
          {results.map((row) => (
            <div key={row.id} className="text-[11px] flex items-center gap-2">
              {row.codified
                ? <Check className="h-3 w-3 shrink-0 text-emerald-400" />
                : <Circle className="h-3 w-3 shrink-0 text-amber-400/70" />}
              <span className="text-zinc-300 truncate">{row.title}</span>
              {row.codified ? (
                <span className="text-emerald-400/80 shrink-0">
                  {row.citation_url
                    ? <a href={row.citation_url} target="_blank" rel="noreferrer" className="hover:text-emerald-300">{row.statute_citation || 'codified'}</a>
                    : (row.statute_citation || 'codified')}
                </span>
              ) : (
                <span className="text-zinc-500 shrink-0">live · {row.gate_reason || 'not codified'}</span>
              )}
              {(row.state || row.city) && (
                <a href={libraryLink(row.state, row.city, undefined, row.id)}
                  className="text-cyan-400/60 hover:text-cyan-300 shrink-0 inline-flex items-center gap-0.5">
                  Library <ExternalLink className="h-2.5 w-2.5" />
                </a>
              )}
            </div>
          ))}
        </div>
      </div>
    )
  }

  // check_sources
  const r = (action.result ?? {}) as CheckResult
  const deadRows = r.dead_rows ?? []
  return (
    <div className="rounded-lg border border-white/[0.06] px-3 py-2.5">
      <p className="text-xs text-zinc-200">
        Checked {r.checked ?? 0} nodes · <b className="text-red-300">{r.dead ?? 0}</b> dead ·{' '}
        {r.unreachable ?? 0} unreachable · {r.missing_citation ?? 0} missing
        {r.state && (
          <a href={coverageLink(r.state, r.city || undefined)}
            className="ml-2 text-cyan-400/70 hover:text-cyan-300">coverage →</a>
        )}
      </p>
      {deadRows.length > 0 && (
        <div className="mt-1.5 space-y-1">
          {deadRows.slice(0, 8).map((d) => (
            <div key={d.id} className="text-[11px] text-zinc-500 flex items-center gap-2">
              <span className="text-red-400/70">dead</span>
              <span>{d.category}</span>
              <a href={libraryLink(d.state, d.city)} className="text-cyan-400/60 hover:text-cyan-300">in Library →</a>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const DOMAIN_BADGE: Record<string, string> = {
  primary: 'text-emerald-300 bg-emerald-500/10',
  secondary_official: 'text-amber-300 bg-amber-500/10',
  aggregator: 'text-red-300 bg-red-500/10',
  unknown: 'text-zinc-400 bg-zinc-500/10',
  missing: 'text-zinc-500 bg-zinc-500/10',
}

// Research-done card: the discovered policies as a checklist. Tick the one(s) you
// want → commit → each passes the codify gate (primary .gov source + citation) to
// become authoritative, or stays live-but-uncodified with the reason. Already-
// committed rows grey out; the rest stay selectable across multiple commits.
function ResearchCard({ action, committedRowIds, onApproved }: {
  action: PilotAction; committedRowIds: Set<string>; onApproved: () => void
}) {
  const r = (action.result ?? {}) as ResearchResult
  const rows = r.staged_rows ?? []
  const [sel, setSel] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  // Legacy actions (pre-checklist) have staged>0 but no staged_rows — keep the
  // old commit-all path instead of stranding them.
  if (rows.length === 0) {
    const staged = r.staged ?? 0
    if (staged > 0) {
      return (
        <div className="rounded-lg border border-white/[0.06] px-3 py-2.5">
          <p className="text-xs text-zinc-200">Staged <b>{staged}</b> requirement{staged === 1 ? '' : 's'} for {r.city ? `${r.city}, ` : ''}{r.state}.</p>
          <div className="mt-2 flex items-center gap-2">
            <button disabled={busy}
              onClick={async () => {
                setBusy(true); setErr(null)
                try { await approveAction(action.id); onApproved() }
                catch { setErr('Commit failed.') } finally { setBusy(false) }
              }}
              className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1 text-xs text-emerald-200 hover:bg-emerald-500/25 disabled:opacity-30">
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />} Commit all
            </button>
            <a href="/admin/studio?view=pipeline&section=review" className="text-xs text-cyan-400/80 hover:text-cyan-300">Review in Pipeline →</a>
          </div>
          {err && <p className="mt-1 text-[11px] text-red-400">{err}</p>}
        </div>
      )
    }
    return (
      <div className="rounded-lg border border-white/[0.06] px-3 py-2.5">
        <p className="text-xs text-zinc-400">Nothing new for {r.city ? `${r.city}, ` : ''}{r.state} — the catalog already covered this.</p>
      </div>
    )
  }

  const toggle = (id: string) => setSel((p) => {
    const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n
  })
  const uncommitted = rows.filter((row) => !committedRowIds.has(row.id))
  const allDone = uncommitted.length === 0

  return (
    <div className="rounded-lg border border-white/[0.06] px-3 py-2.5">
      <p className="text-xs text-zinc-200">
        Discovered <b>{rows.length}</b> polic{rows.length === 1 ? 'y' : 'ies'} for {r.city ? `${r.city}, ` : ''}{r.state}
        <span className="text-zinc-500"> · {r.codifiable ?? 0} codifiable{allDone ? ' · all committed' : ' · pick which to commit'}</span>
      </p>

      <div className="mt-2 space-y-1.5">
        {rows.map((row: StagedRow) => {
          const done = committedRowIds.has(row.id)
          const on = sel.has(row.id)
          return (
            <div key={row.id} className={`flex items-start gap-2 ${done ? 'opacity-50' : ''}`}>
              {done ? (
                <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
              ) : (
                <button type="button" onClick={() => toggle(row.id)} className="mt-0.5 shrink-0 text-zinc-400 hover:text-emerald-300">
                  {on ? <CheckSquare className="h-3.5 w-3.5 text-emerald-400" /> : <Square className="h-3.5 w-3.5" />}
                </button>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[12px] text-zinc-200">{row.title}</span>
                  <span className="text-[9px] uppercase tracking-wide text-zinc-500">{row.jurisdiction_level}</span>
                  <span className={`text-[9px] px-1 py-0.5 rounded ${DOMAIN_BADGE[row.source_domain_class] ?? DOMAIN_BADGE.unknown}`}>
                    {row.source_domain_class}
                  </span>
                  {done && <span className="text-[9px] text-emerald-400/70">committed</span>}
                </div>
                <div className="text-[10px] text-zinc-500 mt-0.5">
                  {row.research_citation
                    ? (row.source_url
                        ? <a href={row.source_url} target="_blank" rel="noreferrer" className="hover:text-zinc-300">{row.research_citation}</a>
                        : row.research_citation)
                    : <span className="text-zinc-600">no statute citation</span>}
                  {row.gate_ok
                    ? <span className="ml-1.5 text-emerald-400/70">· codifiable</span>
                    : <span className="ml-1.5 text-amber-400/60">· {row.gate_reason}</span>}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {!allDone ? (
        <div className="mt-2.5 flex items-center gap-2">
          <button disabled={busy || sel.size === 0}
            onClick={async () => {
              setBusy(true); setErr(null)
              try { await approveAction(action.id, [...sel]); setSel(new Set()); onApproved() }
              catch { setErr('Commit failed — rows may already be committed.') }
              finally { setBusy(false) }
            }}
            className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1 text-xs text-emerald-200 hover:bg-emerald-500/25 disabled:opacity-30">
            {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
            Commit selected ({sel.size})
          </button>
          <a href="/admin/studio?view=pipeline&section=review"
            className="inline-flex items-center gap-1 text-xs text-cyan-400/80 hover:text-cyan-300">
            Review in Pipeline <ArrowRight className="h-3 w-3" />
          </a>
        </div>
      ) : (
        <p className="mt-2 text-[11px] text-emerald-400/70">All committed — see the outcomes below.</p>
      )}
      {err && <p className="mt-1 text-[11px] text-red-400">{err}</p>}
    </div>
  )
}
