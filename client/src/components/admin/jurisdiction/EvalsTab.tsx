import { useCallback, useEffect, useState } from 'react'
import { api } from '../../../api/client'
import { Button } from '../../ui'
import { BaselinePanel } from './EvalsTab/BaselinePanel'
import { SUITES } from './EvalsTab/constants'
import type { Suite } from './EvalsTab/constants'
import { FindingsTable } from './EvalsTab/FindingsTable'
import { GoldenPanel } from './EvalsTab/GoldenPanel'
import { ReadinessWidget } from './EvalsTab/ReadinessWidget'
import { Scorecard } from './EvalsTab/Scorecard'
import type { EvalRun, RunDetail, ScorecardCell, View } from './EvalsTab/types'

// ── Main ──────────────────────────────────────────────────────────────────────

export default function EvalsTab() {
  const [view, setView] = useState<View>('scorecard')
  const [cells, setCells] = useState<ScorecardCell[]>([])
  const [runs, setRuns] = useState<EvalRun[]>([])
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null)
  const [suites, setSuites] = useState<Suite[]>(['completeness', 'tagging', 'golden'])
  const [triggering, setTriggering] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadScorecard = useCallback(() => {
    api.get<{ cells: ScorecardCell[] }>('/admin/jurisdictions/evals/scorecard')
      .then((r) => setCells(r.cells))
      .catch(() => {})
  }, [])

  const loadRuns = useCallback(() => {
    api.get<{ runs: EvalRun[] }>('/admin/jurisdictions/evals/runs')
      .then((r) => setRuns(r.runs))
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadScorecard()
    loadRuns()
  }, [loadScorecard, loadRuns])

  const openRun = async (id: string) => {
    setSelectedRun(await api.get<RunDetail>(`/admin/jurisdictions/evals/runs/${id}`))
  }

  const trigger = async () => {
    setTriggering(true)
    setError(null)
    try {
      await api.post('/admin/jurisdictions/evals/run', { suites })
      // The run is async on both paths; poll the run list rather than block.
      setTimeout(() => { loadRuns(); loadScorecard() }, 2500)
      setView('runs')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to trigger run')
    } finally {
      setTriggering(false)
    }
  }

  const toggleSuite = (s: Suite) =>
    setSuites((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]))

  return (
    <div className="space-y-5">
      <ReadinessWidget />

      <div className="border border-zinc-800 rounded-lg p-4">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div>
            <h3 className="text-sm font-semibold text-zinc-200">Run evals</h3>
            <p className="text-xs text-zinc-500">
              Read-only over the catalog. `authority` fetches every distinct citation URL and runs on the
              worker.
            </p>
          </div>
          <Button size="sm" onClick={trigger} disabled={triggering || !suites.length}>
            {triggering ? 'Starting…' : 'Run'}
          </Button>
        </div>
        <div className="flex flex-wrap gap-2">
          {SUITES.map((s) => (
            <button
              key={s}
              onClick={() => toggleSuite(s)}
              className={`px-2.5 py-1 rounded text-xs border ${
                suites.includes(s)
                  ? 'border-emerald-600/50 bg-emerald-500/10 text-emerald-300'
                  : 'border-zinc-700 text-zinc-500'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
      </div>

      <div className="flex gap-1">
        {(['scorecard', 'runs', 'golden', 'baseline'] as View[]).map((v) => (
          <Button key={v} variant={view === v ? 'secondary' : 'ghost'} size="sm" onClick={() => setView(v)}>
            {v[0].toUpperCase() + v.slice(1)}
          </Button>
        ))}
      </div>

      {view === 'scorecard' && <Scorecard cells={cells} />}

      {view === 'golden' && <GoldenPanel />}

      {view === 'baseline' && <BaselinePanel />}

      {view === 'runs' && (
        <div className="space-y-4">
          <div className="border border-zinc-800 rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-zinc-900/50">
                <tr>
                  {['Started', 'Suites', 'Status', 'Findings', ''].map((h) => (
                    <th key={h} className="text-left px-3 py-2 text-[10px] uppercase tracking-wider text-zinc-500">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="border-t border-zinc-900">
                    <td className="px-3 py-2 text-zinc-400">{r.started_at?.slice(0, 16).replace('T', ' ')}</td>
                    <td className="px-3 py-2 text-zinc-500">{r.suites.join(', ')}</td>
                    <td className="px-3 py-2">
                      <span
                        className={
                          r.status === 'completed'
                            ? 'text-emerald-400'
                            : r.status === 'failed'
                              ? 'text-red-400'
                              : 'text-amber-400'
                        }
                      >
                        {r.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-zinc-300">
                      {(r.totals?.findings as number | undefined) ?? '—'}
                    </td>
                    <td className="px-3 py-2">
                      <Button variant="ghost" size="sm" onClick={() => openRun(r.id)}>View</Button>
                    </td>
                  </tr>
                ))}
                {!runs.length && (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center text-zinc-600">No runs yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {selectedRun && (
            <FindingsTable detail={selectedRun} onResolved={() => openRun(selectedRun.run.id)} />
          )}
        </div>
      )}
    </div>
  )
}
