import { useState, useEffect, useCallback } from 'react'
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, Line, ComposedChart } from 'recharts'
import { api } from '../../api/client'
import { DIMENSION_LABELS, DIMENSION_ORDER, DIMENSION_COLORS } from '../../types/risk-assessment'
import type { CorrelationResult } from '../../types/risk-assessment'

type Props = { qs: string }

const DIMS = [...DIMENSION_ORDER, 'overall'] as const

export function DimensionCorrelationPanel({ qs }: Props) {
  const [dimX, setDimX] = useState('compliance')
  const [dimY, setDimY] = useState('incidents')
  const [data, setData] = useState<CorrelationResult | null>(null)
  const [loading, setLoading] = useState(false)

  const sep = qs ? '&' : '?'

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api.get<CorrelationResult>(
        `/risk-assessment/correlations${qs}${sep}dim_x=${dimX}&dim_y=${dimY}`,
      )
      setData(result)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [qs, sep, dimX, dimY])

  useEffect(() => { load() }, [load])

  const labelFor = (d: string) => d === 'overall' ? 'Overall' : DIMENSION_LABELS[d] ?? d

  // Compute trend line points for chart
  const trendData = data ? [
    { x: 0, y: data.trend_line.intercept },
    { x: 100, y: data.trend_line.slope * 100 + data.trend_line.intercept },
  ] : []

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 space-y-4">
      <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Dimension Correlation</div>

      {/* Selectors */}
      <div className="flex items-center gap-3">
        <select
          value={dimX}
          onChange={(e) => setDimX(e.target.value)}
          className="bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 text-xs text-zinc-200 outline-none"
        >
          {DIMS.map((d) => <option key={d} value={d}>{labelFor(d)}</option>)}
        </select>
        <span className="text-xs text-zinc-500">vs</span>
        <select
          value={dimY}
          onChange={(e) => setDimY(e.target.value)}
          className="bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 text-xs text-zinc-200 outline-none"
        >
          {DIMS.map((d) => <option key={d} value={d}>{labelFor(d)}</option>)}
        </select>
      </div>

      {loading && <div className="text-xs text-zinc-500 animate-pulse py-8 text-center">Loading...</div>}

      {!loading && !data && (
        <div className="text-xs text-zinc-500 py-8 text-center">Not enough history for correlation analysis</div>
      )}

      {!loading && data && (
        <>
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart margin={{ top: 10, right: 15, bottom: 5, left: 5 }}>
                <XAxis
                  type="number"
                  dataKey="x"
                  domain={[0, 100]}
                  tick={{ fill: '#71717a', fontSize: 10 }}
                  axisLine={{ stroke: '#27272a' }}
                  tickLine={false}
                  label={{ value: labelFor(dimX), position: 'bottom', fill: '#71717a', fontSize: 10, offset: -2 }}
                />
                <YAxis
                  type="number"
                  dataKey="y"
                  domain={[0, 100]}
                  tick={{ fill: '#71717a', fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  width={30}
                  label={{ value: labelFor(dimY), angle: -90, position: 'insideLeft', fill: '#71717a', fontSize: 10 }}
                />
                <Tooltip
                  contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8, fontSize: 11 }}
                  formatter={(v: number, name: string) => [v, name === 'x' ? labelFor(dimX) : labelFor(dimY)]}
                />
                <Scatter
                  data={data.points}
                  fill={DIMENSION_COLORS[dimX] ?? '#71717a'}
                  opacity={0.7}
                  r={4}
                />
                <Line
                  data={trendData}
                  dataKey="y"
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                  strokeDasharray="6 3"
                  dot={false}
                  legendType="none"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Stats */}
          <div className="flex gap-4 text-[10px]">
            <span className="text-zinc-500">
              r = <span className={`font-mono ${Math.abs(data.correlation) >= 0.5 ? 'text-amber-400' : 'text-zinc-300'}`}>
                {data.correlation.toFixed(3)}
              </span>
            </span>
            <span className="text-zinc-500">
              R² = <span className="text-zinc-300 font-mono">{data.r_squared.toFixed(3)}</span>
            </span>
            <span className="text-zinc-500">
              n = <span className="text-zinc-300 font-mono">{data.n}</span>
            </span>
          </div>
        </>
      )}
    </div>
  )
}
