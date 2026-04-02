import { AreaChart, Area, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts'
import type { MonteCarloResult } from '../../types/risk-assessment'
import { fmtCompact } from '../../types/risk-assessment'

type Props = { mc: MonteCarloResult }

export function ExceedanceCurvePanel({ mc }: Props) {
  const curve = mc.aggregate.exceedance_curve
  if (!curve || curve.length === 0) return null

  // Format probability as percentage
  const pctFmt = (p: number) => {
    if (p >= 0.01) return `${(p * 100).toFixed(0)}%`
    if (p >= 0.001) return `${(p * 100).toFixed(1)}%`
    return `${(p * 100).toFixed(2)}%`
  }

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Loss Exceedance Curve</div>
        <div className="text-[10px] text-zinc-600 font-mono">P(Loss &ge; threshold)</div>
      </div>

      <div className="h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={curve} margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
            <defs>
              <linearGradient id="excGrad" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="#3f3f46" stopOpacity={0.6} />
                <stop offset="100%" stopColor="#ef4444" stopOpacity={0.3} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="threshold"
              tickFormatter={fmtCompact}
              tick={{ fill: '#71717a', fontSize: 10 }}
              axisLine={{ stroke: '#27272a' }}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tickFormatter={pctFmt}
              tick={{ fill: '#71717a', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              width={45}
              domain={[0, 1]}
            />
            <Tooltip
              contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8, fontSize: 12 }}
              labelFormatter={(v) => `Loss ≥ ${fmtCompact(v as number)}`}
              formatter={(v: number) => [pctFmt(v), 'Probability']}
            />
            <ReferenceLine y={0.05} stroke="#f59e0b" strokeDasharray="4 4" strokeWidth={1} label={{ value: '5%', position: 'right', fill: '#f59e0b', fontSize: 9 }} />
            <ReferenceLine y={0.01} stroke="#ef4444" strokeDasharray="4 4" strokeWidth={1} label={{ value: '1%', position: 'right', fill: '#ef4444', fontSize: 9 }} />
            <Area type="monotone" dataKey="probability" stroke="#71717a" fill="url(#excGrad)" strokeWidth={1.5} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Key thresholds */}
      <div className="flex gap-4 text-[10px] text-zinc-500">
        {[0.10, 0.05, 0.01].map((p) => {
          const pt = curve.find((c) => c.probability <= p)
          return pt ? (
            <span key={p}>{(p * 100).toFixed(0)}% chance of loss &ge; <span className="text-zinc-300 font-mono">{fmtCompact(pt.threshold)}</span></span>
          ) : null
        })}
      </div>
    </div>
  )
}
