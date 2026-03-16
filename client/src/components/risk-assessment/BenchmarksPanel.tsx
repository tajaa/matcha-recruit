import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge } from '../ui'
import { DIMENSION_LABELS } from '../../types/risk-assessment'
import type { BenchmarkResult } from '../../types/risk-assessment'

type Props = {
  qs: string
}

export function BenchmarksPanel({ qs }: Props) {
  const [benchmarks, setBenchmarks] = useState<BenchmarkResult | null>(null)

  useEffect(() => {
    api.get<BenchmarkResult>(`/risk-assessment/benchmarks${qs}`)
      .then(setBenchmarks)
      .catch(() => {})
  }, [qs])

  return (
    <div>
      <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-3">
        Industry Benchmarks
        {benchmarks?.industry_name && (
          <span className="ml-2 normal-case font-normal text-zinc-600">
            — {benchmarks.industry_name}
          </span>
        )}
      </h2>
      {!benchmarks || !benchmarks.dimensions || benchmarks.dimensions.length === 0 ? (
        <p className="text-sm text-zinc-500">No NAICS benchmark data available.</p>
      ) : (
        <div className="border border-zinc-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm text-left">
            <thead className="bg-zinc-900/50 text-zinc-400">
              <tr>
                <th className="px-4 py-2.5 font-medium">Dimension</th>
                <th className="px-4 py-2.5 font-medium text-right">Your Score</th>
                <th className="px-4 py-2.5 font-medium text-right">Industry Median</th>
                <th className="px-4 py-2.5 font-medium text-right">Percentile</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {benchmarks.dimensions.map((row) => (
                <tr key={row.dimension} className="text-zinc-300">
                  <td className="px-4 py-2.5">{DIMENSION_LABELS[row.dimension] ?? row.dimension}</td>
                  <td className="px-4 py-2.5 text-right">{row.company_score}</td>
                  <td className="px-4 py-2.5 text-right text-zinc-400">{row.industry_median}</td>
                  <td className="px-4 py-2.5 text-right">
                    <Badge variant={row.percentile_rank >= 75 ? 'danger' : row.percentile_rank >= 50 ? 'warning' : 'success'}>
                      {row.percentile_rank}th
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
