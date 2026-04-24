import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList,
} from 'recharts'
import type { ERCaseMetrics } from '../../types/risk-assessment'

const CATEGORY_COLORS = ['#f59e0b', '#ef4444', '#3b82f6', '#10b981', '#a855f7', '#f97316', '#06b6d4', '#6366f1']
const OUTCOME_COLORS = ['#10b981', '#f59e0b', '#3b82f6', '#ef4444', '#a855f7', '#6366f1']

export function ERCaseMetricsPanel() {
  const [metrics, setMetrics] = useState<ERCaseMetrics | null>(null)
  const [loading, setLoading] = useState(false)
  const [days, setDays] = useState(30)

  useEffect(() => {
    setLoading(true)
    api.get<ERCaseMetrics>(`/er/cases/metrics?days=${days}`)
      .then(setMetrics)
      .catch(() => setMetrics(null))
      .finally(() => setLoading(false))
  }, [days])

  if (!loading && metrics && metrics.total_cases === 0) return null

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">ER Case Metrics</div>
        <div className="flex gap-0 border border-zinc-700 rounded-lg overflow-hidden">
          {([30, 60, 90] as const).map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1.5 text-[10px] uppercase tracking-widest font-mono transition-colors ${
                days === d
                  ? 'bg-zinc-800 text-zinc-50'
                  : 'bg-zinc-900 text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="border border-zinc-800 rounded-2xl p-8 text-center">
          <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading metrics...</div>
        </div>
      )}

      {!loading && metrics && metrics.total_cases > 0 && (
        <div className="space-y-4">
          {/* Stat cards */}
          <div className="grid grid-cols-4 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
            {[
              { label: 'Total Cases', value: metrics.total_cases },
              { label: 'Open', value: metrics.by_status['open'] || 0 },
              { label: 'In Review', value: metrics.by_status['in_review'] || 0 },
              { label: 'Closed', value: metrics.by_status['closed'] || 0 },
            ].map(s => (
              <div key={s.label} className="bg-zinc-900 p-5 flex flex-col">
                <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{s.label}</div>
                <div className="text-3xl font-light font-mono text-zinc-200 mt-2">{s.value}</div>
              </div>
            ))}
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Category breakdown */}
            <div className="bg-zinc-900 border border-white/10 rounded-2xl p-5">
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-4">By Category</div>
              {Object.keys(metrics.by_category).length === 0 ? (
                <div className="text-[10px] text-zinc-600 font-mono">No categorized cases yet</div>
              ) : (
                <ResponsiveContainer width="100%" height={Math.max(120, Object.keys(metrics.by_category).length * 28)}>
                  <BarChart
                    data={Object.entries(metrics.by_category).map(([name, value]) => ({ name: name.replace(/_/g, ' '), value }))}
                    layout="vertical"
                    margin={{ top: 0, right: 30, bottom: 0, left: 0 }}
                  >
                    <XAxis type="number" hide />
                    <YAxis type="category" dataKey="name" width={100} tick={{ fontSize: 10, fill: '#71717a' }} axisLine={false} tickLine={false} />
                    <Tooltip
                      contentStyle={{ background: '#18181b', border: '1px solid rgba(255,255,255,0.1)', fontSize: 11, color: '#e4e4e7' }}
                      cursor={{ fill: 'rgba(255,255,255,0.03)' }}
                    />
                    <Bar dataKey="value" radius={[0, 2, 2, 0]} maxBarSize={14}>
                      {Object.entries(metrics.by_category).map((_, i) => (
                        <Cell key={i} fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]} />
                      ))}
                      <LabelList dataKey="value" position="right" style={{ fontSize: 10, fill: '#a1a1aa', fontFamily: 'monospace' }} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Outcome breakdown */}
            <div className="bg-zinc-900 border border-white/10 rounded-2xl p-5">
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-4">By Outcome</div>
              {Object.keys(metrics.by_outcome).length === 0 ? (
                <div className="text-[10px] text-zinc-600 font-mono">No outcomes recorded yet</div>
              ) : (
                <ResponsiveContainer width="100%" height={Math.max(120, Object.keys(metrics.by_outcome).length * 28)}>
                  <BarChart
                    data={Object.entries(metrics.by_outcome).map(([name, value]) => ({ name: name.replace(/_/g, ' '), value }))}
                    layout="vertical"
                    margin={{ top: 0, right: 30, bottom: 0, left: 0 }}
                  >
                    <XAxis type="number" hide />
                    <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10, fill: '#71717a' }} axisLine={false} tickLine={false} />
                    <Tooltip
                      contentStyle={{ background: '#18181b', border: '1px solid rgba(255,255,255,0.1)', fontSize: 11, color: '#e4e4e7' }}
                      cursor={{ fill: 'rgba(255,255,255,0.03)' }}
                    />
                    <Bar dataKey="value" radius={[0, 2, 2, 0]} maxBarSize={14}>
                      {Object.entries(metrics.by_outcome).map((_, i) => (
                        <Cell key={i} fill={OUTCOME_COLORS[i % OUTCOME_COLORS.length]} />
                      ))}
                      <LabelList dataKey="value" position="right" style={{ fontSize: 10, fill: '#a1a1aa', fontFamily: 'monospace' }} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
