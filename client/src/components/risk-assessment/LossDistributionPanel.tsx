import { BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts'
import type { MonteCarloResult } from '../../types/risk-assessment'
import { fmtCompact, fmtMoney } from '../../types/risk-assessment'

type Props = {
  mc: MonteCarloResult
  isAdmin?: boolean
  onRerun?: () => void
  running?: boolean
}

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-zinc-800/60 rounded-xl px-4 py-3">
      <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">{label}</div>
      <div className={`text-lg font-semibold mt-1 ${color ?? 'text-zinc-100'}`}>{value}</div>
    </div>
  )
}

export function LossDistributionPanel({ mc, isAdmin, onRerun, running }: Props) {
  const { aggregate, categories } = mc
  const bins = aggregate.histogram_bins
  const stats = aggregate.distribution_stats

  if (!bins || bins.length === 0) {
    return (
      <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6">
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3">Loss Distribution</div>
        <p className="text-sm text-zinc-500">Re-run the Monte Carlo simulation to generate distribution data.</p>
        {isAdmin && onRerun && (
          <button onClick={onRerun} disabled={running} className="mt-3 text-xs text-zinc-400 hover:text-zinc-200 transition-colors">
            {running ? 'Running...' : 'Run Simulation'}
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Loss Distribution</div>
        <div className="text-[10px] text-zinc-600 font-mono">{mc.iterations.toLocaleString()} iterations</div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Expected Loss" value={fmtCompact(aggregate.expected_annual_loss)} />
        <StatCard label="VaR 95%" value={fmtCompact(aggregate.var_95)} color="text-amber-400" />
        <StatCard label="VaR 99%" value={fmtCompact(aggregate.var_99)} color="text-red-400" />
        <StatCard label="CVaR 95%" value={fmtCompact(aggregate.cvar_95)} color="text-red-300" />
      </div>

      {/* Histogram */}
      <div className="h-[280px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={bins} margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
            <XAxis
              dataKey="x"
              tickFormatter={fmtCompact}
              tick={{ fill: '#71717a', fontSize: 10 }}
              axisLine={{ stroke: '#27272a' }}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: '#71717a', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              width={40}
            />
            <Tooltip
              contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8, fontSize: 12 }}
              labelFormatter={(v) => fmtMoney(v as number)}
              formatter={(v: number | undefined) => [v ?? 0, 'Frequency']}
            />
            <ReferenceLine x={aggregate.var_95} stroke="#f59e0b" strokeDasharray="4 4" strokeWidth={1.5} label={{ value: 'VaR 95%', position: 'top', fill: '#f59e0b', fontSize: 10 }} />
            <ReferenceLine x={aggregate.var_99} stroke="#ef4444" strokeDasharray="4 4" strokeWidth={1.5} label={{ value: 'VaR 99%', position: 'top', fill: '#ef4444', fontSize: 10 }} />
            <ReferenceLine x={aggregate.cvar_95} stroke="#ef4444" strokeWidth={2} label={{ value: 'CVaR', position: 'top', fill: '#ef4444', fontSize: 10 }} />
            <Bar dataKey="count" fill="#52525b" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Distribution stats */}
      {stats && (
        <div className="grid grid-cols-3 lg:grid-cols-7 gap-px bg-white/5 rounded-lg overflow-hidden">
          {[
            { label: 'Mean', value: fmtCompact(stats.mean) },
            { label: 'Median', value: fmtCompact(stats.median) },
            { label: 'Std Dev', value: fmtCompact(stats.std_dev) },
            { label: 'IQR', value: fmtCompact(stats.iqr) },
            { label: 'Skewness', value: stats.skewness.toFixed(2) },
            { label: 'Kurtosis', value: stats.kurtosis.toFixed(2) },
            { label: 'Tail Ratio', value: stats.tail_ratio.toFixed(2) + 'x' },
          ].map((s) => (
            <div key={s.label} className="bg-zinc-800 px-3 py-2">
              <div className="text-[9px] text-zinc-500 uppercase tracking-wider">{s.label}</div>
              <div className="text-xs text-zinc-200 font-mono mt-0.5">{s.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Per-category sparklines */}
      {Object.values(categories).some((c) => c.histogram_bins && c.histogram_bins.length > 0) && (
        <div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-2">Category Distributions</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Object.values(categories)
              .filter((c) => c.expected_loss > 0 && c.histogram_bins && c.histogram_bins.length > 0)
              .sort((a, b) => b.expected_loss - a.expected_loss)
              .map((cat) => (
                <div key={cat.key} className="flex items-center gap-3 bg-zinc-800/40 rounded-lg px-3 py-2">
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-zinc-300 truncate">{cat.label}</div>
                    <div className="text-[10px] text-zinc-500 font-mono">{fmtCompact(cat.expected_loss)} expected</div>
                  </div>
                  <div className="w-24 h-6 shrink-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={cat.histogram_bins!} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                        <Bar dataKey="count" fill="#52525b" radius={[1, 1, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}
