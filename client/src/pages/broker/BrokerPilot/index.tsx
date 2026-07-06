import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { HelpCircle, Loader2, Plus, Sparkles } from 'lucide-react'
import {
  listPilotSessions, getPilotSession, getPilotContext,
  type PilotSession, type ContextPreview, type SubjectKind,
} from '../../../api/brokerPilot'
import { ApiError } from '../../../api/client'
import { LABEL } from './shared'
import { Masthead } from './Masthead'
import { Console } from './Console'
import { DocsPanel } from './DocsPanel'
import { EvidencePanel } from './EvidencePanel'
import { PacketsPanel } from './PacketsPanel'
import { NewSessionModal } from './NewSessionModal'
import { HowItWorksModal } from './HowItWorksModal'

export default function BrokerPilot() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [sessions, setSessions] = useState<PilotSession[]>([])
  const [active, setActive] = useState<PilotSession | null>(null)
  const [context, setContext] = useState<ContextPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [notPro, setNotPro] = useState(false)
  const [showNew, setShowNew] = useState(false)
  const [showHelp, setShowHelp] = useState(false)
  const [prefill, setPrefill] = useState<{ kind: SubjectKind; id: string } | null>(null)
  // Guards a slow getPilotSession response from clobbering a switched session.
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
        // Deep links: ?client=<companyId> / ?external=<clientId> from the
        // client-detail pages — open the newest session for that subject, or
        // start a prefilled new-session modal.
        const client = searchParams.get('client')
        const external = searchParams.get('external')
        const want = client
          ? { kind: 'company' as SubjectKind, id: client }
          : external ? { kind: 'external' as SubjectKind, id: external } : null
        if (want) {
          setSearchParams({}, { replace: true })
          const match = rows.find(
            (s) => s.subject_kind === want.kind && s.subject_id === want.id,
          )
          if (match) void openSession(match.id)
          else {
            setPrefill(want)
            setShowNew(true)
          }
        } else if (rows.length) {
          void openSession(rows[0].id)
        }
      } catch (e) {
        if (!cancelled && e instanceof ApiError && e.status === 403) setNotPro(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onCreated = useCallback(async (session: PilotSession) => {
    setShowNew(false)
    setPrefill(null)
    await refreshList()
    void openSession(session.id)
  }, [refreshList, openSession])

  // Full refresh (session + grounding context) — docs changed, session created.
  const onSessionChanged = useCallback(async () => {
    if (activeIdRef.current) void openSession(activeIdRef.current)
    void refreshList()
  }, [openSession, refreshList])

  // Post-chat-turn refresh: transcript + rail counters only. A chat turn can't
  // change the grounding corpus, so skip the context refetch (it re-runs the
  // whole platform-context pipeline server-side).
  const onTurnComplete = useCallback(async () => {
    const id = activeIdRef.current
    if (id) {
      try {
        const full = await getPilotSession(id)
        if (activeIdRef.current === id) setActive(full)
      } catch { /* keep current view */ }
    }
    void refreshList()
  }, [refreshList])

  if (notPro) {
    return (
      <div className="flex flex-col items-center justify-center h-72 text-center">
        <Sparkles className="h-8 w-8 text-emerald-500 mb-3" />
        <h2 className="text-lg font-semibold text-zinc-100">Broker Pilot is a Broker Pro feature</h2>
        <p className="text-sm text-zinc-500 mt-2 max-w-md">
          Upload carrier documents — loss runs, dec pages, competing quotes — and analyze them
          against the platform data on file for each client. Contact Matcha to enable Broker Pro.
        </p>
      </div>
    )
  }

  // Sessions grouped by client for the rail.
  const groups = new Map<string, PilotSession[]>()
  for (const s of sessions) {
    const key = s.subject_name || 'Unknown client'
    const list = groups.get(key) ?? []
    list.push(s)
    groups.set(key, list)
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
      {/* Sessions rail */}
      <div className="flex w-60 shrink-0 flex-col border-r border-white/[0.06]">
        <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
          <h1 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
            <Sparkles className="h-4 w-4 text-emerald-400" /> Broker Pilot
          </h1>
          <div className="flex items-center gap-0.5">
            <button
              onClick={() => setShowHelp(true)}
              aria-label="How Broker Pilot works"
              title="How Broker Pilot works"
              className="rounded p-1 text-zinc-500 transition-colors hover:bg-white/[0.04] hover:text-zinc-100"
            >
              <HelpCircle className="h-4 w-4" />
            </button>
            <button
              onClick={() => { setPrefill(null); setShowNew(true) }}
              aria-label="New session"
              className="rounded p-1 text-zinc-400 transition-colors hover:bg-white/[0.04] hover:text-zinc-100"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className={`border-b border-white/[0.06] px-4 py-2 ${LABEL}`}>Sessions</div>
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <p className="px-4 py-3 text-xs text-zinc-600">Loading…</p>
          ) : sessions.length === 0 ? (
            <p className="px-4 py-3 text-xs text-zinc-500">
              No sessions yet. Start one to analyze a client's documents against their platform data.
            </p>
          ) : [...groups.entries()].map(([client, list]) => (
            <div key={client}>
              <div className={`px-4 pb-1 pt-3 ${LABEL} truncate`} title={client}>{client}</div>
              {list.map((s) => (
                <button
                  key={s.id}
                  onClick={() => void openSession(s.id)}
                  className={`block w-full border-b border-white/[0.04] border-l-2 px-4 py-2.5 text-left transition-colors ${
                    active?.id === s.id
                      ? 'border-l-emerald-400 bg-white/[0.03]'
                      : 'border-l-transparent hover:bg-white/[0.02]'}`}
                >
                  <div className="truncate text-[13px] font-medium text-zinc-100">{s.title}</div>
                  <div className="mt-0.5 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wide text-zinc-500">
                    <span>{s.document_count ?? 0} doc{(s.document_count ?? 0) === 1 ? '' : 's'}</span>
                    <span>{s.message_count ?? 0} msg{(s.message_count ?? 0) === 1 ? '' : 's'}</span>
                    {s.status === 'closed' && <span className="text-zinc-600">closed</span>}
                  </div>
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Workbench */}
      <div className="min-w-0 flex-1">
        {loading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
          </div>
        ) : !active ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 px-8 text-center">
            <Sparkles className="h-8 w-8 text-zinc-700" />
            <p className="max-w-md text-sm leading-relaxed text-zinc-500">
              Select or start a session. Upload a client's carrier documents — loss runs, dec
              pages, quotes — and the analyst maps them to the platform data on file, citing every record.
            </p>
            <button
              onClick={() => setShowHelp(true)}
              className="inline-flex items-center gap-1.5 text-xs text-emerald-400/90 transition-colors hover:text-emerald-300"
            >
              <HelpCircle className="h-3.5 w-3.5" /> How Broker Pilot works
            </button>
          </div>
        ) : (
          <div className="flex h-full min-h-0 flex-col">
            <Masthead session={active} context={context} onChanged={onSessionChanged} />
            <div className="flex min-h-0 flex-1">
              <div className="flex min-w-0 flex-1 flex-col">
                <Console session={active} context={context} onTurnComplete={onTurnComplete} />
              </div>
              <div className="flex w-80 shrink-0 flex-col overflow-y-auto border-l border-white/[0.06]">
                <EvidencePanel context={context} />
                <DocsPanel session={active} onChanged={onSessionChanged} />
                <PacketsPanel session={active} />
              </div>
            </div>
          </div>
        )}
      </div>

      {showNew && (
        <NewSessionModal
          prefill={prefill}
          onClose={() => { setShowNew(false); setPrefill(null) }}
          onCreated={onCreated}
        />
      )}
      {showHelp && <HowItWorksModal onClose={() => setShowHelp(false)} />}
    </div>
  )
}
