import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
  const navigate = useNavigate()
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState(currentYear)
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [summary, setSummary] = useState<Summary300A | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.allSettled([
      api.get<LogEntry[]>(`/ir/incidents/osha/300-log?year=${year}`).then(setEntries),
      api.get<Summary300A>(`/ir/incidents/osha/300a?year=${year}`).then(setSummary),
    ]).finally(() => setLoading(false))
  }, [year])

  function downloadCsv(type: '300' | '300a') {
    const token = localStorage.getItem('matcha_access_token')
    const base = import.meta.env.VITE_API_URL || '/api'
    const url = type === '300'
      ? `${base}/ir/incidents/osha/300-log/csv?year=${year}`
      : `${base}/ir/incidents/osha/300a/csv?year=${year}`
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
    <div className="space-y-8">
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <FileSpreadsheet size={16} className="text-zinc-500" />
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">OSHA 300/300A Logs</span>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="bg-zinc-900 border border-white/10 rounded-lg text-zinc-200 text-xs px-2.5 py-1 font-mono"
          >
            {years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={() => downloadCsv('300')}>
            <Download size={12} className="mr-1.5" />
            300 CSV
          </Button>
          <Button size="sm" variant="ghost" onClick={() => downloadCsv('300a')}>
            <Download size={12} className="mr-1.5" />
            300A CSV
          </Button>
        </div>
      </div>

      {/* 300A Summary */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
          <div className="bg-zinc-900 px-5 py-5">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Total Cases</div>
            <div className="text-3xl font-light font-mono mt-2 text-zinc-100">{summary.total_cases}</div>
          </div>
          <div className="bg-zinc-900 px-5 py-5">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Deaths</div>
            <div className={`text-3xl font-light font-mono mt-2 ${summary.total_deaths > 0 ? 'text-red-400' : 'text-zinc-700'}`}>{summary.total_deaths}</div>
          </div>
          <div className="bg-zinc-900 px-5 py-5">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Days Away</div>
            <div className="text-3xl font-light font-mono mt-2 text-amber-400">{summary.total_days_away}</div>
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest mt-1 font-mono">{summary.total_days_away_cases} cases</div>
          </div>
          <div className="bg-zinc-900 px-5 py-5">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Restricted Duty</div>
            <div className="text-3xl font-light font-mono mt-2 text-orange-400">{summary.total_days_restricted}</div>
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest mt-1 font-mono">{summary.total_restricted_cases} cases</div>
          </div>
        </div>
      )}

      {/* 300 Log Table */}
      <div className="bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden">
        {entries.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-sm text-zinc-400">No OSHA-recordable incidents for {year}.</p>
            <p className="text-[11px] text-zinc-600 mt-1">Mark an incident OSHA recordable from its detail page.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-zinc-950/50 text-zinc-500">
                <tr>
                  <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Case #</th>
                  <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Employee</th>
                  <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Job Title</th>
                  <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Date</th>
                  <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Location</th>
                  <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Classification</th>
                  <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold text-right">Days Away</th>
                  <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold text-right">Days Restricted</th>
                  <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Injury Type</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr
                    key={e.incident_id}
                    className="border-t border-white/5 text-zinc-300 hover:bg-white/[0.02] transition-colors cursor-pointer"
                    onClick={() => navigate(`/app/ir/${e.incident_id}`)}
                  >
                    <td className="px-4 py-3 font-mono text-[11px] text-zinc-500">{e.case_number}</td>
                    <td className="px-4 py-3 text-[13px] text-zinc-100 font-medium">{e.employee_name}</td>
                    <td className="px-4 py-3 text-[12px] text-zinc-500">{e.job_title || '—'}</td>
                    <td className="px-4 py-3 text-[11px] text-zinc-400 font-mono">{e.date_of_injury}</td>
                    <td className="px-4 py-3 text-[12px] text-zinc-400">{e.location || '—'}</td>
                    <td className="px-4 py-3">
                      {e.classification ? (
                        <Badge variant={classificationBadge[e.classification] ?? 'neutral'}>
                          {classificationLabel[e.classification] ?? e.classification}
                        </Badge>
                      ) : '—'}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-[12px] text-zinc-300">{e.days_away || '—'}</td>
                    <td className="px-4 py-3 text-right font-mono text-[12px] text-zinc-300">{e.days_restricted || '—'}</td>
                    <td className="px-4 py-3 text-[12px] text-zinc-500">{e.injury_type || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
