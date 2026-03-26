import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge, Button } from '../ui'
import { Download, Loader2, FileSpreadsheet } from 'lucide-react'

type LogEntry = {
  case_number: string
  employee_name: string
  job_title: string | null
  date_of_injury: string
  location: string | null
  description: string | null
  classification: string | null
  days_away: number
  days_restricted: number
  injury_type: string | null
  incident_id: string
}

type Summary300A = {
  year: number
  establishment_name: string | null
  total_cases: number
  total_deaths: number
  total_days_away_cases: number
  total_restricted_cases: number
  total_other_recordable: number
  total_days_away: number
  total_days_restricted: number
  total_injuries: number
  total_skin_disorders: number
  total_respiratory: number
  total_poisonings: number
  total_hearing_loss: number
  total_other_illnesses: number
  average_employees: number | null
  total_hours_worked: number | null
}

const classificationLabel: Record<string, string> = {
  death: 'Death',
  days_away: 'Days Away',
  restricted_duty: 'Restricted Duty',
  medical_treatment: 'Medical Treatment',
  loss_of_consciousness: 'Loss of Consciousness',
  significant_injury: 'Significant Injury',
}

const classificationBadge: Record<string, 'danger' | 'warning' | 'neutral'> = {
  death: 'danger',
  days_away: 'warning',
  restricted_duty: 'warning',
  medical_treatment: 'neutral',
  loss_of_consciousness: 'warning',
  significant_injury: 'warning',
}

export function OshaLogsPanel() {
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState(currentYear)
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [summary, setSummary] = useState<Summary300A | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.allSettled([
      api.get<LogEntry[]>(`/ir/osha/300-log?year=${year}`).then(setEntries),
      api.get<Summary300A>(`/ir/osha/300a?year=${year}`).then(setSummary),
    ]).finally(() => setLoading(false))
  }, [year])

  function downloadCsv(type: '300' | '300a') {
    const token = localStorage.getItem('matcha_access_token')
    const base = import.meta.env.VITE_API_URL || '/api'
    const url = type === '300'
      ? `${base}/ir/osha/300-log/csv?year=${year}`
      : `${base}/ir/osha/300a/csv?year=${year}`
    window.open(`${url}&_token=${token}`, '_blank')
  }

  const years = Array.from({ length: 5 }, (_, i) => currentYear - i)

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="animate-spin text-zinc-500" size={20} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <FileSpreadsheet size={18} className="text-zinc-400" />
          <h3 className="text-sm font-medium text-zinc-200">OSHA 300/300A Logs</h3>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="bg-zinc-900 border border-zinc-700 rounded text-zinc-300 text-xs px-2 py-1"
          >
            {years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={() => downloadCsv('300')}>
            <Download size={12} className="mr-1" />
            300 CSV
          </Button>
          <Button size="sm" variant="ghost" onClick={() => downloadCsv('300a')}>
            <Download size={12} className="mr-1" />
            300A CSV
          </Button>
        </div>
      </div>

      {/* 300A Summary Card */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
            <p className="text-[10px] text-zinc-500 uppercase">Total Cases</p>
            <p className="text-lg font-semibold text-zinc-100">{summary.total_cases}</p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
            <p className="text-[10px] text-zinc-500 uppercase">Deaths</p>
            <p className={`text-lg font-semibold ${summary.total_deaths > 0 ? 'text-red-400' : 'text-zinc-100'}`}>{summary.total_deaths}</p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
            <p className="text-[10px] text-zinc-500 uppercase">Days Away</p>
            <p className="text-lg font-semibold text-zinc-100">{summary.total_days_away}</p>
            <p className="text-[10px] text-zinc-500">{summary.total_days_away_cases} cases</p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
            <p className="text-[10px] text-zinc-500 uppercase">Restricted Duty</p>
            <p className="text-lg font-semibold text-zinc-100">{summary.total_days_restricted}</p>
            <p className="text-[10px] text-zinc-500">{summary.total_restricted_cases} cases</p>
          </div>
        </div>
      )}

      {/* 300 Log Table */}
      {entries.length === 0 ? (
        <div className="text-center py-12 text-zinc-500 text-sm">
          No OSHA-recordable incidents for {year}.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-zinc-800">
          <table className="w-full text-xs text-left">
            <thead className="bg-zinc-900/50 text-zinc-400">
              <tr>
                <th className="px-3 py-2 font-medium">Case #</th>
                <th className="px-3 py-2 font-medium">Employee</th>
                <th className="px-3 py-2 font-medium">Job Title</th>
                <th className="px-3 py-2 font-medium">Date</th>
                <th className="px-3 py-2 font-medium">Location</th>
                <th className="px-3 py-2 font-medium">Classification</th>
                <th className="px-3 py-2 font-medium text-right">Days Away</th>
                <th className="px-3 py-2 font-medium text-right">Days Restricted</th>
                <th className="px-3 py-2 font-medium">Injury Type</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {entries.map((e) => (
                <tr key={e.incident_id} className="text-zinc-300">
                  <td className="px-3 py-2 font-mono">{e.case_number}</td>
                  <td className="px-3 py-2">{e.employee_name}</td>
                  <td className="px-3 py-2 text-zinc-500">{e.job_title || '—'}</td>
                  <td className="px-3 py-2">{e.date_of_injury}</td>
                  <td className="px-3 py-2 text-zinc-500">{e.location || '—'}</td>
                  <td className="px-3 py-2">
                    {e.classification ? (
                      <Badge variant={classificationBadge[e.classification] ?? 'neutral'}>
                        {classificationLabel[e.classification] ?? e.classification}
                      </Badge>
                    ) : '—'}
                  </td>
                  <td className="px-3 py-2 text-right">{e.days_away || '—'}</td>
                  <td className="px-3 py-2 text-right">{e.days_restricted || '—'}</td>
                  <td className="px-3 py-2 text-zinc-500">{e.injury_type || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
