import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Button } from '../ui'
import { fmtMoney } from '../../types/risk-assessment'
import type { MonteCarloResult } from '../../types/risk-assessment'

type Props = {
  qs: string
  isAdmin: boolean
  companyId: string | null
}

export function MonteCarloPanel({ qs, isAdmin, companyId }: Props) {
  const [monteCarlo, setMonteCarlo] = useState<MonteCarloResult | null>(null)
  const [runningMC, setRunningMC] = useState(false)

  useEffect(() => {
    api.get<MonteCarloResult>(`/risk-assessment/monte-carlo${qs}`)
      .then(setMonteCarlo)
      .catch(() => {})
  }, [qs])

  async function handleRunMonteCarlo() {
    if (!companyId) return
    setRunningMC(true)
    try {
      const result = await api.post<MonteCarloResult>(`/risk-assessment/admin/monte-carlo/${companyId}`, {})
      setMonteCarlo(result)
    } finally {
      setRunningMC(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
          Monte Carlo Simulation
        </h2>
        {isAdmin && companyId && (
          <Button size="sm" variant="ghost" onClick={handleRunMonteCarlo} disabled={runningMC}>
            {runningMC ? 'Running...' : 'Run Simulation'}
          </Button>
        )}
      </div>
      {!monteCarlo ? (
        <p className="text-sm text-zinc-500">Run simulation to see projections.</p>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-4 gap-3">
            {([
              ['Expected Loss', fmtMoney(monteCarlo.expected_loss)],
              ['P50', fmtMoney(monteCarlo.p50)],
              ['P90', fmtMoney(monteCarlo.p90)],
              ['P95', fmtMoney(monteCarlo.p95)],
            ] as const).map(([label, value]) => (
              <div key={label} className="border border-zinc-800 rounded-lg px-3 py-3 text-center">
                <p className="text-lg font-semibold text-zinc-100">{value}</p>
                <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{label}</p>
              </div>
            ))}
          </div>
          {monteCarlo.by_category && monteCarlo.by_category.length > 0 && (
            <div className="border border-zinc-800 rounded-xl overflow-hidden">
              <table className="w-full text-sm text-left">
                <thead className="bg-zinc-900/50 text-zinc-400">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">Category</th>
                    <th className="px-4 py-2.5 font-medium text-right">Expected Loss</th>
                    <th className="px-4 py-2.5 font-medium text-right">P50</th>
                    <th className="px-4 py-2.5 font-medium text-right">P95</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {monteCarlo.by_category.map((row) => (
                    <tr key={row.category} className="text-zinc-300">
                      <td className="px-4 py-2.5">{row.category.replace(/_/g, ' ')}</td>
                      <td className="px-4 py-2.5 text-right">{fmtMoney(row.expected_loss)}</td>
                      <td className="px-4 py-2.5 text-right">{fmtMoney(row.p50)}</td>
                      <td className="px-4 py-2.5 text-right">{fmtMoney(row.p95)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
