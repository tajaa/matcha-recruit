import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, HelpCircle, Loader2 } from 'lucide-react'
import {
  generateReport, downloadPacket,
  type AnalysisSession, type DemoDatasetKey,
} from '../../../api/analysis-pilot/analysisPilot'
import { ANALYSIS_EXAMPLES, type FocusChip } from './shared'
import { DatasetsPanel } from './DatasetsPanel'
import { MetricsTab } from './MetricViews'
import { Console } from './Console'
import { CompareTab } from './CompareTab'
import { ExamplesTab } from './ExamplesTab'

// --------------------------------------------------------------------------- //
// Workbench — datasets rail + tabbed (metrics / chat / compare) center.
// --------------------------------------------------------------------------- //

type Tab = 'metrics' | 'chat' | 'compare' | 'examples'

export function Workbench({ session, onChange, onShowHelp, autoAsk, onRunDemo, demoLoadingKey }: {
  session: AnalysisSession; onChange: () => void; onShowHelp: () => void
  autoAsk?: { text: string; nonce: number } | null
  onRunDemo: (key: DemoDatasetKey, question: string) => void
  demoLoadingKey: DemoDatasetKey | null
}) {
  const [tab, setTab] = useState<Tab>('metrics')
  const [reporting, setReporting] = useState(false)
  // Highlighted records for the next chat turn — adding one jumps to the chat.
  const [focus, setFocus] = useState<FocusChip[]>([])
  const addFocus = useCallback((chip: FocusChip) => {
    setFocus((f) => (f.some((c) => c.cid === chip.cid) || f.length >= 10 ? f : [...f, chip]))
    setTab('chat')
  }, [])
  const removeFocus = useCallback((cid: string) => setFocus((f) => f.filter((c) => c.cid !== cid)), [])
  const clearFocus = useCallback(() => setFocus([]), [])
  // Examples tab hands a prompt to Console via this one-shot signal.
  const [prefill, setPrefill] = useState<{ text: string; nonce: number; autoSend?: boolean } | null>(null)
  const prefillNonceRef = useRef(0)
  const firedAutoAskRef = useRef<number | null>(null)
  const datasets = session.datasets ?? []
  const ready = datasets.filter((d) => d.status === 'ready' || d.status === 'needs_review')

  // A live-demo click sets a nonced autoAsk. Fire it exactly once per nonce —
  // the ref guard survives React StrictMode's double effect-invoke (which was
  // double-sending), and firing on nonce change (not just mount) means a repeat
  // click into the already-active demo session still auto-asks.
  useEffect(() => {
    if (!autoAsk || firedAutoAskRef.current === autoAsk.nonce) return
    firedAutoAskRef.current = autoAsk.nonce
    setTab('chat')
    setPrefill({ text: autoAsk.text, nonce: ++prefillNonceRef.current, autoSend: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoAsk?.nonce])

  const genReport = async () => {
    setReporting(true)
    try {
      const pkt = await generateReport(session.id)
      await downloadPacket(session.id, pkt)
      onChange()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Report generation failed.')
    } finally {
      setReporting(false)
    }
  }

  return (
    <div className="h-full flex gap-4">
      <div className="w-72 shrink-0 overflow-y-auto">
        <DatasetsPanel session={session} onChange={onChange} onFocus={addFocus} />
      </div>
      <div className="flex-1 min-w-0 flex flex-col border border-zinc-800 rounded-xl bg-zinc-950/40">
        <div className="px-4 py-2.5 border-b border-zinc-800 flex items-center justify-between">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-zinc-100 truncate">{session.title}</div>
            {session.goal && <div className="text-xs text-zinc-500 truncate">{session.goal}</div>}
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button onClick={onShowHelp} title="How Analysis Pilot works" aria-label="How Analysis Pilot works"
              className="p-1.5 rounded-lg text-zinc-500 hover:text-emerald-400 hover:bg-zinc-800">
              <HelpCircle className="h-4 w-4" />
            </button>
            <button onClick={() => void genReport()} disabled={reporting || ready.length === 0}
              className="text-xs px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white inline-flex items-center gap-1.5">
              {reporting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
              Report
            </button>
          </div>
        </div>
        <div className="px-3 pt-2 flex gap-1 border-b border-zinc-800">
          {(['metrics', 'chat', 'compare', 'examples'] as Tab[]).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-3 py-1.5 text-xs rounded-t-lg capitalize ${
                tab === t ? 'bg-zinc-800 text-emerald-400' : 'text-zinc-500 hover:text-zinc-300'
              }`}>
              {t === 'metrics' ? 'Metrics' : t === 'chat' ? 'Analyst Chat' : t === 'compare' ? 'Compare' : 'Examples'}
            </button>
          ))}
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto">
          {tab === 'metrics' && <MetricsTab datasets={ready} onFocus={addFocus} />}
          {tab === 'chat' && (
            <Console session={session} onTurn={onChange} focus={focus}
              onRemoveFocus={removeFocus} onClearFocus={clearFocus} prefill={prefill} />
          )}
          {tab === 'compare' && <CompareTab session={session} onChange={onChange} />}
          {tab === 'examples' && (
            <ExamplesTab items={ANALYSIS_EXAMPLES} loadingKey={demoLoadingKey}
              onUse={(item) => onRunDemo(item.key, item.question)} />
          )}
        </div>
      </div>
    </div>
  )
}
