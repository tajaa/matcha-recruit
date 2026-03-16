import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Select } from '../ui'
import type { CohortResult } from '../../types/risk-assessment'

type CohortDimension = 'department' | 'location' | 'hire_quarter' | 'tenure'

type Props = {
  qs: string
}

export function CohortAnalysisPanel({ qs }: Props) {
  const [cohorts, setCohorts] = useState<CohortResult[]>([])
  const [cohortDimension, setCohortDimension] = useState<CohortDimension>('department')

  useEffect(() => {
    const sep = qs ? '&' : '?'
    api.get<CohortResult[]>(`/risk-assessment/cohorts${qs}${sep}dimension=${cohortDimension}`)
      .then(setCohorts)
      .catch(() => {})
  }, [cohortDimension, qs])

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
          Cohort Analysis
        </h2>
        <Select
          label=""
          options={[
            { value: 'department', label: 'Department' },
            { value: 'location', label: 'Location' },
            { value: 'hire_quarter', label: 'Hire Quarter' },
            { value: 'tenure', label: 'Tenure' },
          ]}
          value={cohortDimension}
          onChange={(e) => setCohortDimension(e.target.value as CohortDimension)}
        />
      </div>
      {cohorts.length === 0 ? (
        <p className="text-sm text-zinc-500">No cohort data available.</p>
      ) : (
        <div className="border border-zinc-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm text-left">
            <thead className="bg-zinc-900/50 text-zinc-400">
              <tr>
                <th className="px-4 py-2.5 font-medium">Cohort</th>
                <th className="px-4 py-2.5 font-medium text-right">Score</th>
                <th className="px-4 py-2.5 font-medium text-right">Employees</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {[...cohorts].sort((a, b) => b.score - a.score).map((row) => (
                <tr key={row.cohort} className="text-zinc-300">
                  <td className="px-4 py-2.5">{row.cohort}</td>
                  <td className="px-4 py-2.5 text-right">{row.score}</td>
                  <td className="px-4 py-2.5 text-right text-zinc-400">
                    {row.employee_count ?? '—'}
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
