import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { DIMENSION_LABELS, DIMENSION_COLORS } from '../../types/risk-assessment'
import type { HistoryEntry } from '../../types/risk-assessment'

type Props = {
  qs: string
  dimensionKeys: string[]
}

export function ScoreHistoryPanel({ qs, dimensionKeys }: Props) {
  const [history, setHistory] = useState<HistoryEntry[]>([])

  useEffect(() => {
    api.get<HistoryEntry[]>(`/risk-assessment/history${qs}`)
      .then(setHistory)
      .catch(() => {})
  }, [qs])

  return (
    <div>
      <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-3">
        Score History
      </h2>
      {history.length === 0 ? (
        <p className="text-sm text-zinc-500">No history yet.</p>
      ) : (
        <div className="border border-zinc-800 rounded-xl p-4">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={history.map((h) => ({
              date: new Date(h.computed_at).toLocaleDateString(),
              overall: h.overall_score,
              ...Object.fromEntries(
                Object.entries(h.dimensions).map(([k, v]) => [k, v])
              ),
            }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis dataKey="date" tick={{ fill: '#71717a', fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fill: '#71717a', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }}
                labelStyle={{ color: '#e4e4e7' }}
                itemStyle={{ color: '#a1a1aa' }}
              />
              <Legend wrapperStyle={{ fontSize: 12, color: '#71717a' }} />
              <Line type="monotone" dataKey="overall" stroke="#e4e4e7" strokeWidth={2} dot={false} name="Overall" />
              {dimensionKeys.map((key) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={DIMENSION_COLORS[key] ?? '#71717a'}
                  strokeWidth={1.5}
                  dot={false}
                  name={DIMENSION_LABELS[key] ?? key}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
