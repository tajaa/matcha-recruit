import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import type { IRAnalyticsSummary } from '../../../types/ir'

const SLICES = [
  { key: 'critical', label: 'Critical', color: '#ef4444' },
  { key: 'high',     label: 'High',     color: '#f97316' },
  { key: 'medium',   label: 'Medium',   color: '#f59e0b' },
  { key: 'low',      label: 'Low',      color: '#10b981' },
] as const

function DonutTooltip({ active, payload }: any) {
  if (!active || !payload || payload.length === 0) return null
  const p = payload[0]
  return (
    <div className="bg-zinc-900 border border-white/10 px-3 py-2 shadow-xl text-xs rounded-lg">
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.payload.fill }} />
        <span className="text-zinc-300">{p.name}</span>
        <span className="font-mono text-zinc-200 ml-2">{p.value}</span>
      </div>
    </div>
  )
}

export function IRSeverityDonut({ summary }: { summary: IRAnalyticsSummary | null }) {
  const total = summary?.total ?? 0
  const data = SLICES.map((s) => ({
    name: s.label,
    value: summary?.[s.key] ?? 0,
    fill: s.color,
  })).filter((d) => d.value > 0)

  return (
    <div>
      <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3">
        Severity Mix · all incidents
      </h2>
      <div className="bg-zinc-900 border border-white/10 rounded-2xl p-5">
        {total === 0 ? (
          <div className="h-[220px] flex items-center justify-center text-xs text-zinc-500">
            No incidents reported.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center">
            <div className="relative h-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={90}
                    stroke="#18181b"
                    strokeWidth={2}
                  >
                    {data.map((d, i) => <Cell key={i} fill={d.fill} />)}
                  </Pie>
                  <Tooltip content={<DonutTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <span className="text-3xl font-light font-mono text-zinc-100">{total}</span>
                <span className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mt-0.5">
                  total
                </span>
              </div>
            </div>
            <div className="space-y-2">
              {SLICES.map((s) => {
                const v = summary?.[s.key] ?? 0
                const pct = total > 0 ? Math.round((v / total) * 100) : 0
                return (
                  <div key={s.key} className="flex items-center justify-between gap-3 text-[12px]">
                    <span className="flex items-center gap-2 text-zinc-300">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: s.color }} />
                      {s.label}
                    </span>
                    <span className="flex items-center gap-3">
                      <span className="font-mono text-zinc-200 w-6 text-right">{v}</span>
                      <span className="text-[10px] font-mono text-zinc-600 w-9 text-right">{pct}%</span>
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
