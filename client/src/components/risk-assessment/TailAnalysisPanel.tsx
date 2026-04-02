import { useState, useEffect, useCallback } from 'react'
import { ComposedChart, Line, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, Scatter } from 'recharts'
import { api } from '../../api/client'
import type { AnomalyDetectionResult, MetricTimeSeries } from '../../types/risk-assessment'

type Props = { qs: string }

const METRIC_COLORS: Record<string, string> = {
  overall_score: '#f59e0b',
  compliance_score: '#f59e0b',
  incidents_score: '#ef4444',
  er_cases_score: '#3b82f6',
  monthly_incidents: '#ef4444',
  monthly_er_cases: '#3b82f6',
  monthly_turnover: '#a855f7',
}

export function TailAnalysisPanel({ qs }: Props) {
  const sep = qs ? '&' : '?'
  const [data, setData] = useState<AnomalyDetectionResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedMetric, setSelectedMetric] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api.get<AnomalyDetectionResult>(`/risk-assessment/anomalies${qs}${sep}months=36`)
      setData(result)
      // Auto-select first metric with time series
      const first = result.metrics.find((m) => m.time_series && m.time_series.length > 0)
      if (first) setSelectedMetric(first.metric)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [qs, sep])

  useEffect(() => { load() }, [load])

  if (loading) return <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 text-xs text-zinc-500 animate-pulse">Loading tail analysis...</div>
  if (!data || !data.has_sufficient_data) {
    return (
      <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6">
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-2">Tail Analysis</div>
        <p className="text-xs text-zinc-500">Requires at least 6 months of history data.</p>
      </div>
    )
  }

  const selected: MetricTimeSeries | undefined = data.metrics.find((m) => m.metric === selectedMetric)
  const ts = selected?.time_series ?? []
  const color = selectedMetric ? METRIC_COLORS[selectedMetric] ?? '#71717a' : '#71717a'

  // Mark anomalies in chart data
  const chartData = ts.map((p) => {
    const anomaly = selected?.anomalies.find((a) => a.period === p.period)
    return { ...p, anomalyValue: anomaly ? p.value : undefined, severity: anomaly?.severity }
  })

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Tail Analysis & Anomalies</div>
        <div className="flex gap-2">
          <span className="text-[10px] font-mono text-red-400">{data.alert_count} alerts</span>
          <span className="text-[10px] font-mono text-amber-400">{data.warning_count} warnings</span>
        </div>
      </div>

      {/* Metric selector */}
      <div className="flex flex-wrap gap-1.5">
        {data.metrics
          .filter((m) => m.time_series && m.time_series.length > 0)
          .map((m) => (
            <button
              key={m.metric}
              onClick={() => setSelectedMetric(m.metric)}
              className={`px-2.5 py-1 rounded-md text-[10px] transition-colors ${
                selectedMetric === m.metric
                  ? 'bg-zinc-700 text-zinc-100'
                  : 'bg-zinc-800/60 text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {m.label}
              {m.anomalies.length > 0 && (
                <span className="ml-1 text-red-400">{m.anomalies.length}</span>
              )}
            </button>
          ))}
      </div>

      {/* Time series chart with sigma bands */}
      {ts.length > 0 && (
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 10, right: 15, bottom: 5, left: 5 }}>
              <XAxis
                dataKey="period"
                tick={{ fill: '#71717a', fontSize: 9 }}
                axisLine={{ stroke: '#27272a' }}
                tickLine={false}
                tickFormatter={(v: string) => v.slice(5, 7) + '/' + v.slice(2, 4)}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: '#71717a', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                width={35}
              />
              <Tooltip
                contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8, fontSize: 11 }}
                labelFormatter={(v) => String(v)}
                formatter={(v, name) => {
                  if (v == null) return ['-', name]
                  const labels: Record<string, string> = {
                    value: 'Value', rolling_mean: 'Mean', upper_2s: '+2σ', lower_2s: '-2σ', anomalyValue: 'Anomaly',
                  }
                  return [typeof v === 'number' ? (v as number).toFixed(1) : v, labels[name as string] ?? name]
                }}
              />
              {/* Sigma band */}
              <Area dataKey="upper_2s" stroke="none" fill="#3f3f46" fillOpacity={0.3} dot={false} legendType="none" />
              <Area dataKey="lower_2s" stroke="none" fill="#0c0c0e" fillOpacity={1} dot={false} legendType="none" />
              {/* Rolling mean */}
              <Line dataKey="rolling_mean" stroke="#52525b" strokeDasharray="4 4" strokeWidth={1} dot={false} />
              {/* Actual value */}
              <Line dataKey="value" stroke={color} strokeWidth={1.5} dot={false} />
              {/* Anomaly markers */}
              <Scatter dataKey="anomalyValue" fill="#ef4444" r={4} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Anomaly list */}
      {selected && selected.anomalies.length > 0 && (
        <div className="space-y-1">
          {selected.anomalies.slice(0, 5).map((a, i) => (
            <div key={i} className="flex items-center gap-2 text-[10px]">
              <span className={`px-1.5 py-0.5 rounded ${a.severity === 'alert' ? 'bg-red-500/10 text-red-400' : 'bg-amber-500/10 text-amber-400'}`}>
                {a.severity}
              </span>
              <span className="text-zinc-500 font-mono">{a.period}</span>
              <span className="text-zinc-400">{a.description}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
