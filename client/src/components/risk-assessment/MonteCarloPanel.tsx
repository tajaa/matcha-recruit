import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Play, Loader2 } from 'lucide-react'
import { fmtCompact } from '../../types/risk-assessment'
import type { MonteCarloResult } from '../../types/risk-assessment'

type Props = {
  qs: string
  isAdmin: boolean
  companyId: string | null
}

export function MonteCarloPanel({ qs, isAdmin, companyId }: Props) {
  const [mc, setMc] = useState<MonteCarloResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    api.get<MonteCarloResult>(`/risk-assessment/monte-carlo${qs}`)
      .then(setMc)
      .catch(() => setMc(null))
      .finally(() => setLoading(false))
  }, [qs])

  async function handleRun() {
    if (!companyId) return
    setRunning(true)
    setError(null)
    try {
      const result = await api.post<MonteCarloResult>(`/risk-assessment/admin/monte-carlo/${companyId}`, {})
      setMc(result)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Simulation failed')
    } finally {
      setRunning(false)
    }
  }

  const categories = mc ? Object.values(mc.categories).filter(c => c.expected_loss > 0) : []

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Monte Carlo Simulation</div>
          <div className="text-[10px] text-zinc-600 font-mono mt-0.5">10,000 iterations · Annual loss distribution</div>
        </div>
        {isAdmin && companyId && (
          <button
            onClick={handleRun}
            disabled={running}
            className="flex items-center gap-2 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest bg-white/10 text-zinc-300 rounded-lg hover:bg-white/15 disabled:opacity-50 transition-colors"
          >
            {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
            {running ? 'Running...' : mc ? 'Re-run' : 'Run Simulation'}
          </button>
        )}
      </div>

      {error && <div className="text-[10px] text-red-400 font-mono">{error}</div>}

      {loading && <div className="text-[10px] text-zinc-600 animate-pulse font-mono">Loading...</div>}

      {!loading && !mc && !error && (
        <div className="text-[10px] text-zinc-600 font-mono">
          {isAdmin ? 'Click "Run Simulation" to compute loss distribution.' : 'No simulation available yet.'}
        </div>
      )}

      {mc && (
        <>
          {/* Aggregate summary */}
          <div className="grid grid-cols-3 gap-px bg-white/10 rounded-xl overflow-hidden">
            {[
              { label: 'Expected Annual Loss', value: fmtCompact(mc.aggregate.expected_annual_loss), sub: 'mean' },
              { label: 'VaR 95%', value: fmtCompact(mc.aggregate.var_95), sub: '1-in-20 year' },
              { label: 'CVaR 95%', value: fmtCompact(mc.aggregate.cvar_95), sub: 'tail average' },
            ].map(s => (
              <div key={s.label} className="bg-zinc-800 px-4 py-3">
                <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{s.label}</div>
                <div className="text-xl font-mono font-light text-zinc-200 mt-1">{s.value}</div>
                <div className="text-[9px] text-zinc-600 mt-0.5">{s.sub}</div>
              </div>
            ))}
          </div>

          {/* Percentile bar */}
          <div>
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-2">Loss Percentiles (Aggregate)</div>
            <div className="relative h-2 bg-white/10 rounded-full overflow-hidden">
              {(() => {
                const max = mc.aggregate.percentiles.p99
                if (!max) return null
                const p10pct = (mc.aggregate.percentiles.p10 / max) * 100
                const p90pct = (mc.aggregate.percentiles.p90 / max) * 100
                return (
                  <div
                    className="absolute top-0 h-full bg-amber-500/40 rounded-full"
                    style={{ left: `${p10pct}%`, width: `${p90pct - p10pct}%` }}
                  />
                )
              })()}
            </div>
            <div className="flex justify-between mt-1.5 text-[9px] font-mono text-zinc-600">
              {(['p10', 'p25', 'p50', 'p75', 'p90', 'p99'] as const).map(p => (
                <span key={p}><span className="text-zinc-500">{p.toUpperCase()}</span> {fmtCompact(mc.aggregate.percentiles[p])}</span>
              ))}
            </div>
          </div>

          {/* Per-category rows */}
          {categories.length > 0 && (
            <div>
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-2">By Category</div>
              <div className="divide-y divide-white/5">
                {categories.map(cat => (
                  <div key={cat.key} className="py-2.5 flex items-center gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="text-[11px] text-zinc-300 font-medium truncate">{cat.label}</div>
                      <div className="text-[9px] text-zinc-600 font-mono mt-0.5">
                        {cat.frequency_type} · λ={cat.frequency_lambda}
                        {cat.zero_loss_pct > 0 && ` · ${cat.zero_loss_pct}% zero-loss`}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-[11px] font-mono text-zinc-200">{fmtCompact(cat.expected_loss)}<span className="text-zinc-600 text-[9px] ml-1">exp</span></div>
                      <div className="text-[9px] font-mono text-zinc-500">
                        {fmtCompact(cat.percentiles.p10)}–{fmtCompact(cat.percentiles.p90)} <span className="text-zinc-700">P10-P90</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="text-[9px] text-zinc-700 font-mono">
            Computed {new Date(mc.computed_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })} · {mc.iterations.toLocaleString()} iterations
          </div>
        </>
      )}
    </div>
  )
}
