import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Loader2, Plus, Sparkles } from 'lucide-react'
import {
  listPilotSessions, getPilotSession, getPilotContext,
  type PilotSession, type ContextPreview, type SubjectKind,
} from '../../../api/brokerPilot'
import { ApiError } from '../../../api/client'
import { Masthead } from './Masthead'
import { Console } from './Console'
import { DocsPanel } from './DocsPanel'
import { ContextPanel } from './ContextPanel'
import { NewSessionModal } from './NewSessionModal'

export default function BrokerPilot() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [sessions, setSessions] = useState<PilotSession[]>([])
  const [active, setActive] = useState<PilotSession | null>(null)
  const [context, setContext] = useState<ContextPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [notPro, setNotPro] = useState(false)
  const [showNew, setShowNew] = useState(false)
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 text-zinc-500 animate-spin" />
      </div>
    )
  }

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
    <div className="flex gap-6 h-[calc(100vh-7rem)] min-h-0">
      {/* Sessions rail */}
      <aside className="w-64 flex-shrink-0 flex flex-col min-h-0">
        <div className="flex items-center justify-between mb-3">
          <h1 className="text-lg font-semibold text-zinc-100 tracking-tight">Broker Pilot</h1>
          <button
            onClick={() => { setPrefill(null); setShowNew(true) }}
            className="p-1.5 rounded-md bg-zinc-800 border border-zinc-700 text-zinc-300 hover:text-zinc-100 hover:border-zinc-600 transition-colors"
            title="New analysis session"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-4 pr-1">
          {sessions.length === 0 && (
            <p className="text-sm text-zinc-500">
              No sessions yet. Start one to analyze a client's documents against their platform data.
            </p>
          )}
          {[...groups.entries()].map(([client, list]) => (
            <div key={client}>
              <p className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1.5">{client}</p>
              <div className="space-y-1">
                {list.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => void openSession(s.id)}
                    className={`w-full text-left px-2.5 py-2 rounded-md border transition-colors ${
                      active?.id === s.id
                        ? 'bg-zinc-800 border-zinc-600 text-zinc-100'
                        : 'bg-transparent border-transparent text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200'
                    }`}
                  >
                    <span className="block text-sm truncate">{s.title}</span>
                    <span className="block text-[11px] text-zinc-500 mt-0.5">
                      {s.document_count ?? 0} doc{(s.document_count ?? 0) === 1 ? '' : 's'} ·{' '}
                      {s.message_count ?? 0} msg{(s.message_count ?? 0) === 1 ? '' : 's'}
                      {s.status === 'closed' ? ' · closed' : ''}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* Workbench */}
      <div className="flex-1 min-w-0 flex flex-col min-h-0">
        {active ? (
          <>
            <Masthead session={active} onChanged={onSessionChanged} />
            <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4">
              <div className="lg:col-span-2 min-h-0 flex flex-col">
                <Console session={active} context={context} onTurnComplete={onTurnComplete} />
              </div>
              <div className="min-h-0 overflow-y-auto space-y-4">
                <DocsPanel session={active} onChanged={onSessionChanged} />
                <ContextPanel
                  context={context}
                  onRefresh={() => { if (activeIdRef.current) void openSession(activeIdRef.current) }}
                />
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <Sparkles className="h-8 w-8 text-zinc-600 mb-3" />
            <p className="text-sm text-zinc-500 max-w-sm">
              Select a session, or start a new one to analyze a client's carrier documents
              alongside their platform data.
            </p>
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
    </div>
  )
}
