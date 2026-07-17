import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { PayEquityAnalysisResult } from '../../types/workforceCompliance'

// Pay-equity visualization, matching the IR/risk recharts chrome so it reads as
// one system. Two modes off the same analysis:
//   • measured protected-class gap by role (when HRIS demographics reach ≥5/class)
//   • otherwise within-role pay spread by role (the dispersion screen)
// Colors reuse the page's own severity triad (emerald / amber / red).

const OK = '#10b981'
const WATCH = '#f59e0b'
const FLAG = '#ef4444'

function spreadColor(sev: string): string {
  return sev === 'flag' ? FLAG : sev === 'watch' ? WATCH : OK
}

function ChartTooltip({ active, payload, unit }: any) {
  if (!active || !payload || payload.length === 0) return null
  const p = payload[0]?.payload
  if (!p) return null
  return (
    <div className="bg-zinc-900 border border-white/10 px-3 py-2 shadow-xl text-xs rounded-lg min-w-[150px]">
      <div className="text-zinc-300 font-medium mb-1">{p.title}</div>
      <div className="flex items-center justify-between gap-4">
        <span className="text-zinc-500">{unit}</span>
        <span className="font-mono text-zinc-200">{p.value}%</span>
      </div>
      {p.detail && <div className="text-zinc-600 text-[10px] mt-1">{p.detail}</div>}
    </div>
  )
}

export function PayEquityGapChart({ a }: { a: PayEquityAnalysisResult }) {
  // Spread across every analyzed role (always ≥1 bar), enriched with the measured
  // protected-class gap in the tooltip where one survived small-cell suppression.
  // The gap headline itself lives in the panel above; this shows the shape.
  const gapByTitle = new Map(a.class_gaps.map((g) => [g.title, g]))
  const data = a.roles.slice(0, 8).map((r) => {
    const g = gapByTitle.get(r.title)
    return {
      title: r.title,
      value: r.spread_pct,
      color: spreadColor(r.severity),
      detail: g
        ? `${g.gap_pct}% gender gap · ${g.reference} highest`
        : `${r.n} employees · median ${r.median.toLocaleString()}`,
    }
  })

  if (data.length === 0) return null
  const threshold = 15  // watch band for spread
  const height = Math.max(120, data.length * 34 + 40)

  return (
    <div className="rounded-2xl border border-white/10 bg-zinc-900 p-5 mb-3">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
          Pay spread by role
        </span>
        <span className="text-[10px] text-zinc-600">within-role dispersion screen</span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="2 4" horizontal={false} />
          <XAxis
            type="number" tick={{ fontSize: 10, fill: '#71717a', fontFamily: 'ui-monospace' }}
            axisLine={{ stroke: 'rgba(255,255,255,0.05)' }} tickLine={false} unit="%"
          />
          <YAxis
            type="category" dataKey="title" width={140}
            tick={{ fontSize: 10, fill: '#a1a1aa' }} axisLine={false} tickLine={false}
          />
          <Tooltip cursor={{ fill: 'rgba(255,255,255,0.03)' }} content={<ChartTooltip unit="Pay spread" />} />
          <ReferenceLine x={threshold} stroke="#52525b" strokeDasharray="3 3" />
          <Bar dataKey="value" radius={[0, 3, 3, 0]} barSize={16}>
            {data.map((d, i) => <Cell key={i} fill={d.color} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
