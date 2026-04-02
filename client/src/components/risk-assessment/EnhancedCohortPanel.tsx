import { useState, useEffect, useCallback } from 'react'
import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { api } from '../../api/client'
import type { CohortResult } from '../../types/risk-assessment'

type Props = { qs: string }

const DIMENSIONS = [
  { value: 'department', label: 'Department' },
  { value: 'location', label: 'Location' },
  { value: 'tenure', label: 'Tenure' },
  { value: 'hire_quarter', label: 'Hire Quarter' },
]

function concentrationColor(c: number): string {
  if (c < 1.3) return '#10b981'
  if (c < 2.0) return '#f59e0b'
  return '#ef4444'
}

export function EnhancedCohortPanel({ qs }: Props) {
  const sep = qs ? '&' : '?'
  const [dim, setDim] = useState('department')
  const [data, setData] = useState<CohortResult[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api.get<CohortResult[]>(`/risk-assessment/cohorts${qs}${sep}dimension=${dim}`)
      setData(result)
    } catch {
      setData([])
    } finally {
      setLoading(false)
    }
  }, [qs, sep, dim])

  useEffect(() => { load() }, [load])

  if (loading) return <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 text-xs text-zinc-500 animate-pulse">Loading cohorts...</div>

  const bubbleData = data.map((c) => ({
    x: c.incident_rate,
    y: c.risk_concentration,
    z: c.headcount,
    label: c.label,
    headcount: c.headcount,
    incidents: c.incident_count,
    erCases: c.er_case_count,
    concentration: c.risk_concentration,
  }))

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Cohort Risk Map</div>
        <select
          value={dim}
          onChange={(e) => setDim(e.target.value)}
          className="bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1 text-[10px] text-zinc-200 outline-none"
        >
          {DIMENSIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
        </select>
      </div>

      {data.length === 0 ? (
        <div className="text-xs text-zinc-500 py-8 text-center">No cohort data available</div>
      ) : (
        <>
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 10, right: 15, bottom: 20, left: 5 }}>
                <XAxis
                  type="number"
                  dataKey="x"
                  name="Incident Rate"
                  tick={{ fill: '#71717a', fontSize: 10 }}
                  axisLine={{ stroke: '#27272a' }}
                  tickLine={false}
                  label={{ value: 'Incident Rate / 100', position: 'bottom', fill: '#71717a', fontSize: 10, offset: 0 }}
                />
                <YAxis
                  type="number"
                  dataKey="y"
                  name="Risk Concentration"
                  tick={{ fill: '#71717a', fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  width={35}
                  label={{ value: 'Concentration', angle: -90, position: 'insideLeft', fill: '#71717a', fontSize: 10 }}
                />
                <ZAxis type="number" dataKey="z" range={[40, 400]} />
                <Tooltip
                  contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8, fontSize: 11 }}
                  content={({ payload }) => {
                    if (!payload || !payload.length) return null
                    const d = payload[0].payload
                    return (
                      <div className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs">
                        <div className="font-medium text-zinc-200 mb-1">{d.label}</div>
                        <div className="text-zinc-400">Headcount: {d.headcount}</div>
                        <div className="text-zinc-400">Incidents: {d.incidents}</div>
                        <div className="text-zinc-400">ER Cases: {d.erCases}</div>
                        <div className="text-zinc-400">Concentration: {d.concentration.toFixed(2)}x</div>
                      </div>
                    )
                  }}
                />
                <Scatter data={bubbleData}>
                  {bubbleData.map((entry, i) => (
                    <Cell key={i} fill={concentrationColor(entry.concentration)} fillOpacity={0.7} />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </div>

          {/* Legend */}
          <div className="flex gap-4 text-[10px] text-zinc-500">
            <span><span className="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-1" />Normal (&lt;1.3x)</span>
            <span><span className="inline-block w-2 h-2 rounded-full bg-amber-500 mr-1" />Elevated (1.3-2x)</span>
            <span><span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" />High (&ge;2x)</span>
            <span className="ml-auto">Bubble size = headcount</span>
          </div>
        </>
      )}
    </div>
  )
}
