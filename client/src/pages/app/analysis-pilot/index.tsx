import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, HelpCircle, Loader2, Plus, Wand2 } from 'lucide-react'
import { HowItWorksModal } from '../../../components/ui/HowItWorksModal'
import { useShowOnce } from '../../../hooks/useShowOnce'
import {
  listAnalysisSessions, getAnalysisSession, createAnalysisSession, loadDemoDataset,
  type AnalysisSession, type DemoDatasetKey,
} from '../../../api/analysis-pilot/analysisPilot'
import { HOW_IT_WORKS_STEPS } from './howItWorksSteps'
import { Workbench } from './Workbench'
import { NewSessionModal } from './NewSessionModal'

// ---------------------------------------------------------------------------
// Analysis Pilot — general-purpose bring-your-own-data analysis in a chat UI.
// Upload any dataset (CSV/XLSX/financial-document PDF); a deterministic engine
// computes the metrics (descriptive stats, volatility & risk, financial ratios,
// insurance, inventory); a grounded AI answers questions over the computed
// numbers and exports a report. Highlight a record to focus the chat on it —
// the AI can propose corrections to document-extracted figures, which apply
// only through the confirmed review PATCH. Numbers are computed in Python —
// the AI can only cite, never invent.
// ---------------------------------------------------------------------------

// Title of the one shared demo session the Examples tab's live demos load
// their bundled sample datasets into — keeps demo data out of the user's own
// real analysis sessions entirely (a distinct session, not a distinct flag).
const DEMO_SESSION_TITLE = 'Analysis Pilot — Live Demo'

export default function AnalysisPilot() {
  const [sessions, setSessions] = useState<AnalysisSession[]>([])
  const [active, setActive] = useState<AnalysisSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [showHelp, setShowHelp] = useShowOnce('analysis-pilot')
  const [pendingAutoAsk, setPendingAutoAsk] = useState<{ text: string; nonce: number } | null>(null)
  const [demoLoadingKey, setDemoLoadingKey] = useState<DemoDatasetKey | null>(null)
  const activeIdRef = useRef<string | null>(null)
  const autoAskNonceRef = useRef(0)

  const refreshList = useCallback(async () => {
    const rows = await listAnalysisSessions()
    setSessions(rows)
    return rows
  }, [])

  const openSession = useCallback(async (id: string) => {
    activeIdRef.current = id
    try {
      const full = await getAnalysisSession(id)
      if (activeIdRef.current === id) setActive(full)
    } catch {
      if (activeIdRef.current === id) setActive(null)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const rows = await refreshList()
        if (!cancelled && rows.length) void openSession(rows[0].id)
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
      const full = await getAnalysisSession(id)
      if (activeIdRef.current === id) setActive(full)
    } catch { /* keep current */ }
    void refreshList()
  }, [refreshList])

  const onCreated = useCallback(async (s: AnalysisSession) => {
    setShowNew(false)
    await refreshList()
    void openSession(s.id)
  }, [refreshList, openSession])

  // Examples tab's live demo: find-or-create the one shared demo session, load
  // the bundled dataset for this key into it (idempotent server-side), queue
  // the question to auto-ask once Workbench mounts for that session, and
  // switch into it.
  const runDemo = useCallback(async (key: DemoDatasetKey, question: string) => {
    setDemoLoadingKey(key)
    try {
      const rows = await refreshList()
      const existing = rows.find((s) => s.title === DEMO_SESSION_TITLE)
      const demoId = existing ? existing.id : (await createAnalysisSession({ title: DEMO_SESSION_TITLE })).id
      await loadDemoDataset(demoId, key)
      setPendingAutoAsk({ text: question, nonce: ++autoAskNonceRef.current })
      await refreshList()
      void openSession(demoId)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Could not load the demo dataset.')
    } finally {
      setDemoLoadingKey(null)
    }
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
      <aside className="w-60 shrink-0 flex flex-col border border-zinc-800 rounded-xl bg-zinc-950/40">
        <div className="p-3 border-b border-zinc-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-emerald-500" />
            <span className="text-sm font-semibold text-zinc-200">Analysis Pilot</span>
          </div>
          <button onClick={() => setShowNew(true)} title="New session"
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-emerald-400">
            <Plus className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions.length === 0 && (
            <p className="text-xs text-zinc-600 p-3">No analyses yet. Upload any data — financials, loss runs, prices, scores — and ask questions about it.</p>
          )}
          {sessions.map((s) => (
            <button key={s.id} onClick={() => openSession(s.id)}
              className={`w-full text-left px-3 py-2 rounded-lg transition ${
                active?.id === s.id ? 'bg-emerald-500/10 border border-emerald-500/30' : 'hover:bg-zinc-800/60 border border-transparent'
              }`}>
              <div className="text-sm text-zinc-200 truncate">{s.title}</div>
              <div className="text-[11px] text-zinc-500 flex gap-2 mt-0.5">
                <span>{s.dataset_count ?? 0} datasets</span>
                {(s.packet_count ?? 0) > 0 && <span className="text-emerald-500">{s.packet_count} reports</span>}
              </div>
            </button>
          ))}
        </div>
      </aside>

      <main className="flex-1 min-w-0">
        {active ? (
          <Workbench key={active.id} session={active} onChange={reloadActive} onShowHelp={() => setShowHelp(true)}
            autoAsk={pendingAutoAsk} onRunDemo={runDemo} demoLoadingKey={demoLoadingKey} />
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center">
            <Wand2 className="h-8 w-8 text-emerald-500 mb-3" />
            <h2 className="text-lg font-semibold text-zinc-100">Analyze any data in a grounded chat</h2>
            <p className="text-sm text-zinc-500 mt-2 max-w-md">
              Upload a CSV, spreadsheet, or a financial document — a P&L, a loss run, prices, scores,
              inventory. The engine computes the metrics (trends, ratios, volatility & risk); the pilot
              answers your questions citing only those computed numbers.
            </p>
            <button onClick={() => setShowNew(true)}
              className="mt-5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium inline-flex items-center gap-2">
              <Plus className="h-4 w-4" /> New analysis
            </button>
            <button onClick={() => setShowHelp(true)}
              className="mt-3 text-xs text-zinc-500 hover:text-emerald-400 inline-flex items-center gap-1.5">
              <HelpCircle className="h-3.5 w-3.5" /> How Analysis Pilot works
            </button>
          </div>
        )}
      </main>

      {showNew && <NewSessionModal onClose={() => setShowNew(false)} onCreated={onCreated} />}
      {showHelp && <HowItWorksModal title="How Analysis Pilot works" steps={HOW_IT_WORKS_STEPS} onClose={() => setShowHelp(false)} />}
    </div>
  )
}
