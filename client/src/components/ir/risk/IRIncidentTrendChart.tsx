import { useEffect, useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { TrendingDown, TrendingUp } from 'lucide-react'
import { api } from '../../../api/client'
import type { IRTrendPoint } from '../../../types/ir'

type Mode = 'severity' | 'type' | 'recordable'
type Window = 30 | 90 | 180 | 365

const SEVERITY_KEYS = ['critical', 'high', 'medium', 'low'] as const
const SEVERITY_COLORS: Record<typeof SEVERITY_KEYS[number], string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#f59e0b',
  low: '#10b981',
}

const TYPE_KEYS = ['safety', 'behavioral', 'property', 'near_miss', 'other'] as const
const TYPE_COLORS: Record<typeof TYPE_KEYS[number], string> = {
  safety: '#ef4444',
  behavioral: '#f97316',
  property: '#a855f7',
  near_miss: '#06b6d4',
  other: '#71717a',
}

const TYPE_LABELS: Record<string, string> = {
  safety: 'Safety',
  behavioral: 'Behavioral',
  property: 'Property',
  near_miss: 'Near Miss',
  other: 'Other',
}

function formatBucket(date: string, period: 'weekly' | 'monthly'): string {
  const d = new Date(date)
  if (period === 'monthly') {
    return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
  }
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="bg-zinc-900 border border-white/10 px-4 py-3 shadow-xl text-xs rounded-lg min-w-[160px]">
      <div className="text-zinc-500 font-mono text-[9px] uppercase tracking-widest mb-2">{label}</div>
      {payload
        .filter((p: any) => p.value > 0)
        .reverse()
        .map((entry: any) => (
          <div key={entry.dataKey} className="flex items-center justify-between gap-6">
            <span className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
              <span className="text-zinc-400 capitalize">{(entry.name || entry.dataKey).replace(/_/g, ' ')}</span>
            </span>
            <span className="font-mono text-zinc-200">{entry.value}</span>
          </div>
        ))}
    </div>
  )
}

export function IRIncidentTrendChart() {
  const [mode, setMode] = useState<Mode>('severity')
  const [windowDays, setWindowDays] = useState<Window>(90)
  const [points, setPoints] = useState<IRTrendPoint[]>([])
  const [loading, setLoading] = useState(true)

  const period: 'weekly' | 'monthly' = windowDays >= 180 ? 'monthly' : 'weekly'

  useEffect(() => {
    setLoading(true)
    api.get<{ period: string; data: IRTrendPoint[] }>(
      `/ir/incidents/analytics/trends?period=${period}&days=${windowDays}`,
    )
      .then((res) => setPoints(res.data || []))
      .catch(() => setPoints([]))
      .finally(() => setLoading(false))
  }, [period, windowDays])

  const chartData = useMemo(() => {
    return points.map((p) => {
      const row: Record<string, string | number> = { date: formatBucket(p.date, period), total: p.count }
      if (mode === 'severity') {
        for (const k of SEVERITY_KEYS) row[k] = p.by_severity?.[k] ?? 0
      } else if (mode === 'type') {
        for (const k of TYPE_KEYS) row[k] = p.by_type?.[k] ?? 0
      } else {
        row.recordable = p.recordable_count ?? 0
        row.non_recordable = p.count - (p.recordable_count ?? 0)
      }
      return row
    })
  }, [points, mode, period])

  const totalCurrent = points.slice(-Math.ceil(points.length / 2)).reduce((s, p) => s + p.count, 0)
  const totalPrior = points.slice(0, Math.floor(points.length / 2)).reduce((s, p) => s + p.count, 0)
  const trendDelta = totalPrior === 0 ? null : Math.round(((totalCurrent - totalPrior) / totalPrior) * 100)

  return (
    <div>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold flex items-center gap-2">
          Incident Trend
          {trendDelta !== null && (
            <span className={`inline-flex items-center gap-1 text-[10px] font-mono normal-case tracking-normal ${
              trendDelta < -5 ? 'text-emerald-400' : trendDelta > 5 ? 'text-red-400' : 'text-zinc-500'
            }`}>
              {trendDelta < 0 ? <TrendingDown className="w-3 h-3" /> : <TrendingUp className="w-3 h-3" />}
              {trendDelta > 0 ? '+' : ''}{trendDelta}% recent vs prior half
            </span>
          )}
        </h2>
        <div className="flex gap-2">
          <div className="flex gap-0 border border-zinc-700 rounded-lg overflow-hidden">
            {([
              { v: 'severity', l: 'By Severity' },
              { v: 'type', l: 'By Type' },
              { v: 'recordable', l: 'OSHA' },
            ] as const).map(({ v, l }) => (
              <button
                key={v}
                onClick={() => setMode(v)}
                className={`px-3 py-1.5 text-[10px] uppercase tracking-widest font-bold transition-colors ${
                  mode === v ? 'bg-zinc-800 text-zinc-50' : 'bg-zinc-900 text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {l}
              </button>
            ))}
          </div>
          <div className="flex gap-0 border border-zinc-700 rounded-lg overflow-hidden">
            {([30, 90, 180, 365] as Window[]).map((w) => (
              <button
                key={w}
                onClick={() => setWindowDays(w)}
                className={`px-3 py-1.5 text-[10px] uppercase tracking-widest font-mono transition-colors ${
                  windowDays === w ? 'bg-zinc-800 text-zinc-50' : 'bg-zinc-900 text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {w}d
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-zinc-900 border border-white/10 rounded-2xl p-5">
        {loading ? (
          <div className="h-[260px] flex items-center justify-center text-xs text-zinc-500 uppercase tracking-widest font-mono animate-pulse">
            Loading…
          </div>
        ) : chartData.length === 0 ? (
          <div className="h-[260px] flex items-center justify-center text-xs text-zinc-500">
            No incidents in this window.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="2 4" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: '#71717a', fontFamily: 'ui-monospace, monospace' }}
                axisLine={{ stroke: 'rgba(255,255,255,0.05)' }}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 10, fill: '#71717a', fontFamily: 'ui-monospace, monospace' }}
                axisLine={{ stroke: 'rgba(255,255,255,0.05)' }}
                tickLine={false}
                width={32}
                allowDecimals={false}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: 'rgba(255,255,255,0.1)' }} />

              {mode === 'severity' && SEVERITY_KEYS.map((k) => (
                <Area
                  key={k}
                  type="monotone"
                  dataKey={k}
                  name={k.charAt(0).toUpperCase() + k.slice(1)}
                  stackId="1"
                  stroke={SEVERITY_COLORS[k]}
                  fill={SEVERITY_COLORS[k]}
                  fillOpacity={0.45}
                  strokeWidth={1.5}
                />
              ))}

              {mode === 'type' && TYPE_KEYS.map((k) => (
                <Area
                  key={k}
                  type="monotone"
                  dataKey={k}
                  name={TYPE_LABELS[k]}
                  stackId="1"
                  stroke={TYPE_COLORS[k]}
                  fill={TYPE_COLORS[k]}
                  fillOpacity={0.45}
                  strokeWidth={1.5}
                />
              ))}

              {mode === 'recordable' && (
                <>
                  <Area
                    type="monotone"
                    dataKey="non_recordable"
                    name="Non-Recordable"
                    stackId="1"
                    stroke="#52525b"
                    fill="#52525b"
                    fillOpacity={0.25}
                    strokeWidth={1.5}
                  />
                  <Area
                    type="monotone"
                    dataKey="recordable"
                    name="OSHA Recordable"
                    stackId="1"
                    stroke="#ef4444"
                    fill="#ef4444"
                    fillOpacity={0.5}
                    strokeWidth={1.5}
                  />
                </>
              )}
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
