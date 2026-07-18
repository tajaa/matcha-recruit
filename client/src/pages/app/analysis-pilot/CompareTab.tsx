import { useState } from 'react'
import { BarChart3, GitCompare, Loader2 } from 'lucide-react'
import { HelpHint } from '../../../components/ui/HelpHint'
import { createComparison, type AnalysisSession } from '../../../api/analysis-pilot/analysisPilot'
import { BlockView } from './MetricViews'

// --------------------------------------------------------------------------- //
// Compare tab — build + view saved cross-dataset comparisons.
// --------------------------------------------------------------------------- //

export function CompareTab({ session, onChange }: { session: AnalysisSession; onChange: () => void }) {
  const ready = (session.datasets ?? []).filter((d) => d.status === 'ready' || d.status === 'needs_review')
  const [selected, setSelected] = useState<string[]>([])
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const comparisons = session.comparisons ?? []

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  const build = async () => {
    if (selected.length < 2) return
    setBusy(true)
    try {
      await createComparison(session.id, { title: title.trim() || 'Comparison', dataset_ids: selected })
      setSelected([]); setTitle('')
      onChange()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Comparison failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="p-4">
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 mb-5">
        <div className="text-xs font-medium text-zinc-300 mb-2 inline-flex items-center gap-1.5">
          Compare datasets (select 2+ in order)
          <HelpHint text="Each comparison lines up shared metrics across the selected datasets and shows the delta (absolute change), % (percent change), and CAGR (compound annual growth rate)." />
        </div>
        <div className="space-y-1 mb-3">
          {ready.map((d) => (
            <label key={d.id} className="flex items-center gap-2 text-xs text-zinc-300">
              <input type="checkbox" checked={selected.includes(d.id)} onChange={() => toggle(d.id)} className="accent-emerald-500" />
              {d.filename}{selected.includes(d.id) && <span className="text-emerald-500">#{selected.indexOf(d.id) + 1}</span>}
            </label>
          ))}
          {ready.length < 2 && <p className="text-[11px] text-zinc-600">Add at least two analyzed datasets to compare.</p>}
        </div>
        <div className="flex gap-2">
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Comparison title (e.g. FY22 vs FY23)"
            className="flex-1 rounded bg-zinc-900 border border-zinc-700 px-2.5 py-1.5 text-xs text-zinc-200" />
          <button onClick={() => void build()} disabled={selected.length < 2 || busy}
            className="text-xs px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white inline-flex items-center gap-1.5">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <GitCompare className="h-3.5 w-3.5" />} Compare
          </button>
        </div>
      </div>
      {comparisons.map((c) => (
        <div key={c.id} className="mb-6">
          <div className="text-sm font-semibold text-zinc-200 mb-2 flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-zinc-500" /> {c.title}
          </div>
          <BlockView block={c.result} />
          {c.result.notes?.map((n, i) => <p key={i} className="text-[11px] text-amber-400/70">{n}</p>)}
        </div>
      ))}
    </div>
  )
}
