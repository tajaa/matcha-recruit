import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { CohortResult } from '../../types/risk-assessment'

type CohortDimension = 'department' | 'location' | 'hire_quarter' | 'tenure'

type Props = {
  qs: string
}

export function CohortAnalysisPanel({ qs }: Props) {
  const [cohorts, setCohorts] = useState<CohortResult[]>([])
  const [loading, setLoading] = useState(true)
  const [dim, setDim] = useState<CohortDimension>('department')

  useEffect(() => {
    setLoading(true)
    const sep = qs ? '&' : '?'
    api.get<CohortResult[]>(`/risk-assessment/cohorts${qs}${sep}dimension=${dim}`)
      .then(setCohorts)
      .catch(() => setCohorts([]))
      .finally(() => setLoading(false))
  }, [dim, qs])

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Cohort Heat Map</div>
        <div className="flex gap-0 border border-white/10 rounded-lg overflow-hidden">
          {(['department', 'location', 'hire_quarter', 'tenure'] as const).map(d => (
            <button
              key={d}
              onClick={() => setDim(d)}
              className={`px-3 py-1.5 text-[9px] uppercase tracking-widest font-mono transition-colors ${
                dim === d ? 'bg-white/15 text-zinc-200' : 'text-zinc-600 hover:text-zinc-400'
              }`}
            >
              {d.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="text-[10px] text-zinc-600 animate-pulse font-mono">Loading...</div>}

      {!loading && cohorts.length === 0 && (
        <div className="text-[10px] text-zinc-600 font-mono">No cohort data available.</div>
      )}

      {!loading && cohorts.length > 0 && (
        <div className="divide-y divide-white/5">
          {/* Header */}
          <div className="grid grid-cols-5 gap-2 pb-2 text-[9px] text-zinc-600 uppercase tracking-widest font-bold">
            <span className="col-span-2">Cohort</span>
            <span className="text-right">Headcount</span>
            <span className="text-right">Incidents</span>
            <span className="text-right">Concentration</span>
          </div>
          {cohorts.map(c => {
            const conc = c.risk_concentration
            const concColor = conc >= 2 ? 'text-red-400' : conc >= 1.3 ? 'text-amber-400' : 'text-zinc-400'
            return (
              <div key={c.label} className="grid grid-cols-5 gap-2 py-2.5 items-center">
                <div className="col-span-2">
                  <div className="text-[11px] text-zinc-200 font-medium truncate">{c.label}</div>
                  {c.flags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {c.flags.map((f, i) => (
                        <span key={i} className="text-[8px] bg-amber-500/10 text-amber-400 border border-amber-500/20 px-1.5 py-0.5 rounded font-mono">{f}</span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="text-right text-[11px] font-mono text-zinc-400">
                  {c.headcount} <span className="text-zinc-700 text-[9px]">{c.headcount_pct}%</span>
                </div>
                <div className="text-right text-[11px] font-mono text-zinc-400">
                  {c.incident_count}
                  {c.incident_rate > 0 && <span className="text-zinc-700 text-[9px] ml-1">{c.incident_rate}/100</span>}
                </div>
                <div className={`text-right text-[11px] font-mono font-bold ${concColor}`}>
                  {conc > 0 ? `${conc.toFixed(1)}x` : '—'}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
