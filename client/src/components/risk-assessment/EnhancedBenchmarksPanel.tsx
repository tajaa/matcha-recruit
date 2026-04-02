import { useState, useEffect, useCallback } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer, Cell } from 'recharts'
import { api } from '../../api/client'
import type { BenchmarkResult } from '../../types/risk-assessment'

type Props = { qs: string }

const METRIC_LABELS: Record<string, string> = {
  incident_rate_per_100: 'Incident Rate / 100',
  osha_trc_rate: 'OSHA TRC Rate',
  osha_dart_rate: 'OSHA DART Rate',
  er_case_rate_per_1000: 'ER Cases / 1,000',
  eeoc_charge_rate_per_1000: 'EEOC Charges / 1,000',
}

function ratioColor(ratio: number): string {
  if (ratio <= 1.0) return '#10b981'
  if (ratio <= 1.5) return '#f59e0b'
  return '#ef4444'
}

export function EnhancedBenchmarksPanel({ qs }: Props) {
  const [data, setData] = useState<BenchmarkResult | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api.get<BenchmarkResult>(`/risk-assessment/benchmarks${qs}`)
      setData(result)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [qs])

  useEffect(() => { load() }, [load])

  if (loading) return <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 text-xs text-zinc-500 animate-pulse">Loading benchmarks...</div>
  if (!data) return null

  const chartData = data.metrics.map((m) => ({
    name: METRIC_LABELS[m.metric] ?? m.metric,
    company: m.company_value,
    industry: m.industry_median,
    ratio: m.ratio,
    percentile: m.percentile,
  }))

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Industry Benchmarks</div>
        <div className="text-[10px] text-zinc-600 font-mono">{data.naics_label} ({data.naics_code})</div>
      </div>

      <div className="h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 20, bottom: 5, left: 100 }}>
            <XAxis type="number" tick={{ fill: '#71717a', fontSize: 10 }} axisLine={{ stroke: '#27272a' }} tickLine={false} />
            <YAxis type="category" dataKey="name" tick={{ fill: '#a1a1aa', fontSize: 10 }} axisLine={false} tickLine={false} width={95} />
            <Tooltip
              contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8, fontSize: 11 }}
              formatter={(v: number, name: string) => [v.toFixed(2), name === 'company' ? 'Company' : 'Industry Median']}
            />
            <Bar dataKey="industry" fill="#3b82f6" opacity={0.4} barSize={14} radius={[0, 3, 3, 0]} />
            <Bar dataKey="company" barSize={14} radius={[0, 3, 3, 0]}>
              {chartData.map((entry, i) => (
                <Cell key={i} fill={ratioColor(entry.ratio)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Percentile ranks */}
      <div className="flex flex-wrap gap-2">
        {data.metrics.map((m) => (
          <div key={m.metric} className="flex items-center gap-1.5 text-[10px]">
            <span className="text-zinc-500">{METRIC_LABELS[m.metric] ?? m.metric}:</span>
            <span className={`font-mono ${m.percentile > 75 ? 'text-red-400' : m.percentile > 50 ? 'text-amber-400' : 'text-emerald-400'}`}>
              P{m.percentile}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
