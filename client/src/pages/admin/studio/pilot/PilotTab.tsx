import { useCallback, useEffect, useState } from 'react'
import { Bot, Plus, Search, Wrench, Compass, MessageSquare } from 'lucide-react'
import {
  listTemplates, listSessions, getSession, createSession,
  type PilotTemplate, type PilotSession, type PilotMode,
} from '../../../../api/admin/compliancePilot'
import { fmtRelative } from '../utils'
import Console from './Console'

const MODE_ICON: Record<PilotMode, typeof Bot> = {
  research: Search,
  ask: MessageSquare,
  check_sources: Wrench,
  scope: Compass,
}

// Chat-driven compliance-library building. A session runs in a mode; the console
// drives research → codify → commit, catalog Q&A, and source-link checks. Existing
// Studio tabs are untouched.
export default function PilotTab() {
  const [templates, setTemplates] = useState<PilotTemplate[]>([])
  const [sessions, setSessions] = useState<PilotSession[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [active, setActive] = useState<PilotSession | null>(null)
  const [creating, setCreating] = useState(false)

  const refetchSessions = useCallback(async () => {
    try { setSessions(await listSessions()) } catch { setSessions([]) }
  }, [])

  const refetchActive = useCallback(async () => {
    if (!activeId) { setActive(null); return }
    try { setActive(await getSession(activeId)) } catch { setActive(null) }
  }, [activeId])

  useEffect(() => {
    listTemplates().then(setTemplates).catch(() => setTemplates([]))
    refetchSessions()
  }, [refetchSessions])

  useEffect(() => { refetchActive() }, [refetchActive])

  async function startSession(mode: PilotMode) {
    setCreating(true)
    try {
      const s = await createSession(mode)
      await refetchSessions()
      setActiveId(s.id)
    } finally { setCreating(false) }
  }

  return (
    <div className="grid grid-cols-4 gap-4 h-[calc(100vh-13rem)]">
      {/* Sessions rail */}
      <div className="col-span-1 flex flex-col min-h-0">
        <div className="mb-2 flex items-center gap-2">
          <Bot className="h-4 w-4 text-emerald-400" />
          <h2 className="text-sm font-semibold text-zinc-100">Pilot</h2>
        </div>
        <p className="text-[11px] text-zinc-500 mb-2">Start a session</p>
        <div className="grid grid-cols-2 gap-1.5 mb-3">
          {templates.map((t) => {
            const Icon = MODE_ICON[t.key] ?? Bot
            return (
              <button key={t.key} disabled={creating} onClick={() => startSession(t.key)}
                title={t.description}
                className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] px-2 py-2 text-left text-[11px] text-zinc-300 hover:border-emerald-500/40 hover:bg-emerald-500/5 transition-colors disabled:opacity-40">
                <Icon className="h-3.5 w-3.5 shrink-0 text-emerald-400/80" />
                <span className="truncate">{t.label}</span>
              </button>
            )
          })}
        </div>
        <div className="flex items-center justify-between mb-1">
          <p className="text-[10px] uppercase tracking-wide text-zinc-500">Sessions</p>
          <button onClick={refetchSessions} className="text-[10px] text-zinc-500 hover:text-zinc-300">refresh</button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto space-y-1">
          {sessions.length === 0 ? (
            <p className="text-[11px] text-zinc-600 px-1 py-2">No sessions yet.</p>
          ) : sessions.map((s) => (
            <button key={s.id} onClick={() => setActiveId(s.id)}
              className={`w-full text-left rounded-lg px-2.5 py-2 transition-colors ${
                s.id === activeId ? 'bg-zinc-800/70' : 'hover:bg-zinc-800/30'
              }`}>
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs text-zinc-200 truncate">{s.title}</p>
                <span className="text-[9px] uppercase tracking-wide text-emerald-400/70 shrink-0">{s.mode}</span>
              </div>
              <p className="text-[10px] text-zinc-600 mt-0.5">
                {s.message_count ?? 0} msgs · {fmtRelative(s.updated_at)}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* Console */}
      <div className="col-span-3 min-h-0">
        {active ? (
          <Console key={active.id} session={active} onRefetch={refetchActive} onSessionsChanged={refetchSessions} />
        ) : (
          <div className="h-full flex items-center justify-center">
            <div className="max-w-md text-center">
              <Bot className="h-8 w-8 text-zinc-700 mx-auto mb-3" />
              <p className="text-sm text-zinc-400 mb-1">Compliance Pilot</p>
              <p className="text-xs text-zinc-600">
                Pick a mode to start a session. Research an industry × jurisdiction and
                codify it into the catalog, ask the catalog, or check source-link health.
              </p>
              <button disabled={creating} onClick={() => startSession('research')}
                className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-40">
                <Plus className="h-3.5 w-3.5" /> New research session
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
