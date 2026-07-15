import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2, Send, Play, Check, ArrowRight, AlertTriangle, ExternalLink } from 'lucide-react'
import {
  streamPilotChat, createAction, getAction, approveAction,
  type PilotSession, type PilotMessage, type PilotAction, type Proposal,
  type Citation, type ApproveRowResult,
} from '../../../../api/compliancePilot'
import { libraryLink, coverageLink } from '../utils'

type Props = {
  session: PilotSession
  onRefetch: () => void            // reload this session (messages + actions)
  onSessionsChanged: () => void    // reload the sessions rail (titles/counts)
}

type LiveMsg = { role: 'user' | 'assistant'; content: string; metadata?: PilotMessage['metadata'] }

// Narrow shapes for each action kind's result JSONB (backend-owned; kept loose).
type ResearchResult = { staged?: number; state?: string; city?: string | null; industry_tag?: string }
type ApproveResultBody = { activated?: number; codified?: number; uncodified?: number; already_live?: number; results?: ApproveRowResult[] }
type DeadRow = { id: string; category: string; source_url: string; state: string; city: string }
type CheckResult = { checked?: number; dead?: number; unreachable?: number; missing_citation?: number; dead_rows?: DeadRow[]; state?: string; city?: string | null }

export default function Console({ session, onRefetch, onSessionsChanged }: Props) {
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [live, setLive] = useState<LiveMsg[]>([])
  const [runningAction, setRunningAction] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  const persisted = session.messages ?? []
  const actions = session.actions ?? []
  const starters = session.template?.starters ?? []
  // Research actions whose rows were already committed — hide their approve button.
  const approvedFrom = new Set(
    actions.filter((a) => a.kind === 'approve')
      .map((a) => (a.params && typeof a.params.from_action === 'string' ? a.params.from_action : null))
      .filter((x): x is string => x !== null))

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
    setSending(true); setStatus('Thinking…')
    setLive((p) => [...p, { role: 'user', content: msg }])
    try {
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
      })
    } finally {
      setSending(false); setStatus(null)
      onRefetch(); onSessionsChanged()
    }
  }, [session.id, sending, onRefetch, onSessionsChanged])

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
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> {status}
          </div>
        )}

        {actions.length > 0 && (
          <div className="space-y-2 pt-2">
            <p className="text-[10px] uppercase tracking-wide text-zinc-500">Runs</p>
            {actions.map((a) => (
              <ActionCard key={a.id} action={a} onApproved={onRefetch}
                approved={approvedFrom.has(a.id)} />
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
          <p className="text-[11px] text-zinc-400 mt-1">
            {proposal.category_count} categories · {proposal.coverage.covered} covered ·{' '}
            {proposal.coverage.unchecked} unchecked · {proposal.existing_active_rows} active rows on file
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

function ActionCard({ action, onApproved, approved }: {
  action: PilotAction; onApproved: () => void; approved: boolean
}) {
  const [approving, setApproving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

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
    const r = (action.result ?? {}) as ResearchResult
    const staged = r.staged ?? 0
    return (
      <div className="rounded-lg border border-white/[0.06] px-3 py-2.5">
        <p className="text-xs text-zinc-200">
          Staged <b>{staged}</b> requirement{staged === 1 ? '' : 's'} for {r.city ? `${r.city}, ` : ''}{r.state}
          {r.industry_tag && <span className="text-zinc-500"> · {r.industry_tag}</span>}
        </p>
        <p className="text-[11px] text-zinc-500 mt-0.5">
          Staged rows aren't live or searchable until codified.
        </p>
        {staged > 0 && !approved ? (
          <div className="mt-2 flex items-center gap-2">
            <button disabled={approving}
              onClick={async () => {
                setApproving(true); setErr(null)
                try { await approveAction(action.id); onApproved() }
                catch { setErr('Codify failed — the rows may already be committed.') }
                finally { setApproving(false) }
              }}
              className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1 text-xs text-emerald-200 hover:bg-emerald-500/25 disabled:opacity-40">
              {approving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
              Approve &amp; codify all
            </button>
            <a href="/admin/studio?view=pipeline&section=review"
              className="inline-flex items-center gap-1 text-xs text-cyan-400/80 hover:text-cyan-300">
              Review in Pipeline <ArrowRight className="h-3 w-3" />
            </a>
          </div>
        ) : staged > 0 && approved ? (
          <p className="mt-1 text-[11px] text-emerald-400/70">Committed.</p>
        ) : (
          <p className="mt-1 text-[11px] text-zinc-600">Nothing new — the catalog already covered this.</p>
        )}
        {err && <p className="mt-1 text-[11px] text-red-400">{err}</p>}
      </div>
    )
  }

  if (action.kind === 'approve') {
    const r = (action.result ?? {}) as ApproveResultBody
    const results = r.results ?? []
    const first = results[0]
    return (
      <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.03] px-3 py-2.5">
        <p className="text-xs text-zinc-200">
          Committed <b>{r.activated ?? 0}</b> · codified <b className="text-emerald-300">{r.codified ?? 0}</b>
          {(r.already_live ?? 0) > 0 && <span className="text-zinc-500"> · {r.already_live} already live</span>}
        </p>
        {first && (first.state || first.city) && (
          <a href={libraryLink(first.state, first.city)}
            className="mt-1.5 inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300">
            View in Library <ExternalLink className="h-3 w-3" />
          </a>
        )}
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
