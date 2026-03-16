import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown } from 'lucide-react'
import { api } from '../../api/client'
import {
  AreaChart, Area, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceArea,
} from 'recharts'
import {
  DIMENSION_LABELS, DIMENSION_COLORS, DIMENSION_ORDER,
  type HistoryEntry,
} from '../../types/risk-assessment'

const DIMENSION_META: Record<string, { label: string }> = Object.fromEntries(
  DIMENSION_ORDER.map(k => [k, { label: DIMENSION_LABELS[k] ?? k }])
)

function formatShortDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function TrendTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ dataKey: string; value: number; color: string; payload?: Record<string, unknown> }>; label?: string }) {
  if (!active || !payload || payload.length === 0) return null
  const dataPoint = payload[0]?.payload
  const delta = typeof dataPoint?.delta === 'number' ? dataPoint.delta as number : 0
  const source = typeof dataPoint?.source === 'string' ? dataPoint.source as string : null
  return (
    <div className="bg-zinc-900 border border-white/10 px-4 py-3 shadow-xl text-xs rounded-lg">
      <div className="flex items-center gap-2 mb-2">
        <div className="text-zinc-500 font-mono text-[9px] uppercase tracking-widest">{label}</div>
        {source && (
          <span className="text-[8px] font-mono uppercase tracking-wider text-zinc-600 bg-white/5 px-1.5 py-0.5 rounded">
            {source.replace('_', ' ')}
          </span>
        )}
      </div>
      {payload.filter(e => e.dataKey !== 'delta' && e.dataKey !== 'source').map((entry) => (
        <div key={entry.dataKey} className="flex items-center justify-between gap-6">
          <span className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
            <span className="text-zinc-400 capitalize">{entry.dataKey.replace(/_/g, ' ')}</span>
          </span>
          <span className="font-mono text-zinc-200">{Math.round(entry.value)}</span>
        </div>
      ))}
      {delta !== 0 && (
        <div className={`flex items-center gap-1.5 mt-2 pt-2 border-t border-white/5 font-mono text-[10px] ${
          delta > 0 ? 'text-red-400' : 'text-emerald-400'
        }`}>
          {delta > 0 ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
          <span>{delta > 0 ? '+' : ''}{delta} from previous</span>
        </div>
      )}
    </div>
  )
}

type Props = {
  qs: string
  dimensionKeys: string[]
}

export function ScoreHistoryPanel({ qs }: Props) {
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [months, setMonths] = useState(12)
  const [visibleDimensions, setVisibleDimensions] = useState<Set<string>>(new Set())

  useEffect(() => {
    setLoading(true)
    const sep = qs ? '&' : '?'
    api.get<HistoryEntry[]>(`/risk-assessment/history${qs}${sep}months=${months}`)
      .then(setHistory)
      .catch(() => setHistory([]))
      .finally(() => setLoading(false))
  }, [qs, months])

  const toggleDimension = (dim: string) => {
    setVisibleDimensions(prev => {
      const next = new Set(prev)
      if (next.has(dim)) next.delete(dim)
      else next.add(dim)
      return next
    })
  }

  const sortedHistory = history
    .slice()
    .sort((a, b) => new Date(a.computed_at).getTime() - new Date(b.computed_at).getTime())

  const chartData = sortedHistory.map((entry, i) => {
    const prev = i > 0 ? sortedHistory[i - 1] : null
    const delta = prev ? Math.round(entry.overall_score - prev.overall_score) : 0
    return {
      date: formatShortDate(entry.computed_at),
      overall_score: entry.overall_score,
      delta,
      source: entry.source,
      ...entry.dimensions,
    }
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Risk Trend</h2>
        <div className="flex gap-0 border border-zinc-700 rounded-lg overflow-hidden">
          {([3, 6, 12] as const).map(m => (
            <button
              key={m}
              onClick={() => setMonths(m)}
              className={`px-3 py-1.5 text-[10px] uppercase tracking-widest font-mono transition-colors ${
                months === m
                  ? 'bg-zinc-800 text-zinc-50'
                  : 'bg-zinc-900 text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {m}m
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="border border-zinc-800 rounded-2xl p-8 text-center">
          <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading trend data...</div>
        </div>
      )}

      {!loading && chartData.length === 0 && (
        <div className="border border-zinc-800 rounded-2xl p-8 text-center">
          <div className="text-xs text-zinc-500 uppercase tracking-wider">No history yet</div>
          <div className="text-[10px] text-zinc-600 mt-2 font-mono">Risk assessments will be recorded automatically</div>
        </div>
      )}

      {!loading && chartData.length > 0 && (
        <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6">
          {/* Dimension toggles */}
          <div className="flex flex-wrap gap-2 mb-5">
            {DIMENSION_ORDER.map(dim => {
              const active = visibleDimensions.has(dim)
              const color = DIMENSION_COLORS[dim]
              return (
                <button
                  key={dim}
                  onClick={() => toggleDimension(dim)}
                  className={`px-2.5 py-1 text-[9px] uppercase tracking-widest font-bold rounded-lg border transition-colors ${
                    active
                      ? 'border-white/20 text-zinc-200'
                      : 'border-white/5 text-zinc-600 hover:text-zinc-400 hover:border-white/10'
                  }`}
                  style={active ? { backgroundColor: `${color}20`, borderColor: `${color}40` } : undefined}
                >
                  <span className="inline-block w-1.5 h-1.5 rounded-full mr-1.5" style={{ backgroundColor: active ? color : '#52525b' }} />
                  {DIMENSION_META[dim]?.label ?? dim}
                </button>
              )
            })}
          </div>

          {/* Change-point legend */}
          {chartData.some(d => d.delta !== 0) && (
            <div className="flex items-center gap-4 mb-3 ml-8">
              <span className="flex items-center gap-1.5 text-[9px] text-zinc-500 font-mono uppercase tracking-widest">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500/60 ring-2 ring-red-500/20" />
                Risk increased
              </span>
              <span className="flex items-center gap-1.5 text-[9px] text-zinc-500 font-mono uppercase tracking-widest">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/60 ring-2 ring-emerald-500/20" />
                Risk decreased
              </span>
            </div>
          )}

          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={chartData} margin={{ top: 24, right: 16, bottom: 0, left: 0 }}>
              {/* Risk zone reference bands */}
              <ReferenceArea y1={0} y2={25} fill="#10b981" fillOpacity={0.04} />
              <ReferenceArea y1={25} y2={50} fill="#f59e0b" fillOpacity={0.04} />
              <ReferenceArea y1={50} y2={75} fill="#f97316" fillOpacity={0.04} />
              <ReferenceArea y1={75} y2={100} fill="#ef4444" fillOpacity={0.04} />

              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: '#71717a' }}
                axisLine={{ stroke: 'rgba(255,255,255,0.05)' }}
                tickLine={false}
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fontSize: 10, fill: '#71717a' }}
                axisLine={{ stroke: 'rgba(255,255,255,0.05)' }}
                tickLine={false}
                width={32}
              />
              <Tooltip content={<TrendTooltip />} />

              {/* Overall score — always visible */}
              <Area
                type="monotone"
                dataKey="overall_score"
                stroke="#e4e4e7"
                strokeWidth={2}
                fill="url(#overallGradient)"
                dot={(props: Record<string, unknown>) => {
                  const { cx, cy, index } = props as { cx: number; cy: number; index: number }
                  const d = chartData[index]
                  if (!d) return <circle key={index} cx={cx} cy={cy} r={3} fill="#e4e4e7" stroke="#18181b" strokeWidth={2} />
                  const delta = d.delta
                  const absDelta = Math.abs(delta)

                  if (absDelta < 2) {
                    return <circle key={index} cx={cx} cy={cy} r={3} fill="#e4e4e7" stroke="#18181b" strokeWidth={2} />
                  }

                  const isUp = delta > 0
                  const dotColor = isUp ? '#ef4444' : '#10b981'
                  const ringColor = isUp ? 'rgba(239,68,68,0.2)' : 'rgba(16,185,129,0.2)'
                  const r = Math.min(4 + absDelta * 0.15, 7)

                  return (
                    <g key={index}>
                      {absDelta >= 5 && (
                        <circle cx={cx} cy={cy} r={r + 4} fill="none" stroke={ringColor} strokeWidth={2}>
                          <animate attributeName="r" from={String(r + 2)} to={String(r + 8)} dur="2s" repeatCount="indefinite" />
                          <animate attributeName="opacity" from="0.6" to="0" dur="2s" repeatCount="indefinite" />
                        </circle>
                      )}
                      <circle cx={cx} cy={cy} r={r} fill={dotColor} stroke="#18181b" strokeWidth={2} />
                      <text
                        x={cx}
                        y={cy - r - 6}
                        textAnchor="middle"
                        fill={dotColor}
                        fontSize={9}
                        fontFamily="monospace"
                        fontWeight="bold"
                      >
                        {isUp ? `+${delta}` : `${delta}`}
                      </text>
                    </g>
                  )
                }}
                activeDot={{ r: 6, fill: '#e4e4e7', stroke: '#18181b', strokeWidth: 2 }}
                name="Overall"
              />

              {/* Dimension lines — toggleable */}
              {DIMENSION_ORDER.map(dim => {
                if (!visibleDimensions.has(dim)) return null
                const color = DIMENSION_COLORS[dim]
                return (
                  <Line
                    key={dim}
                    type="monotone"
                    dataKey={dim}
                    stroke={color}
                    strokeWidth={1.5}
                    strokeDasharray="4 2"
                    dot={{ r: 2, fill: color, stroke: '#18181b', strokeWidth: 1 }}
                    activeDot={{ r: 4, fill: color, stroke: '#18181b', strokeWidth: 2 }}
                    name={DIMENSION_META[dim]?.label ?? dim}
                  />
                )
              })}

              <defs>
                <linearGradient id="overallGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#e4e4e7" stopOpacity={0.15} />
                  <stop offset="100%" stopColor="#e4e4e7" stopOpacity={0} />
                </linearGradient>
              </defs>
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
