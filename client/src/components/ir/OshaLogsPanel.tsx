import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { fetchLocations } from '../../api/compliance'
import type { BusinessLocation } from '../../types/compliance'
import { Badge, Button } from '../ui'
import { Download, Loader2, FileSpreadsheet, FileText, Save, AlertTriangle } from 'lucide-react'

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
  establishment_id: string | null
  ein: string | null
  naics: string | null
  address: string | null
  city: string | null
  state: string | null
  zipcode: string | null
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
  certified_by: string | null
  certified_title: string | null
  certified_date: string | null
}

type ItaProblem = {
  location_id: string
  establishment_name: string
  missing: string[]
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

const missingLabel: Record<string, string> = {
  ein: 'EIN',
  naics: 'NAICS code',
  street_address: 'Street address',
  total_hours_worked: 'Total hours worked',
}

export function OshaLogsPanel() {
  const navigate = useNavigate()
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState(currentYear)
  const [locations, setLocations] = useState<BusinessLocation[]>([])
  const [locationId, setLocationId] = useState<string>('')
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [summary, setSummary] = useState<Summary300A | null>(null)
  const [loading, setLoading] = useState(true)

  // 300A manual / certification form state
  const [hours, setHours] = useState('')
  const [avgEmp, setAvgEmp] = useState('')
  const [certBy, setCertBy] = useState('')
  const [certTitle, setCertTitle] = useState('')
  const [certDate, setCertDate] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  // ITA export state
  const [itaProblems, setItaProblems] = useState<ItaProblem[] | null>(null)
  const [itaBusy, setItaBusy] = useState(false)

  // Load establishments once.
  useEffect(() => {
    fetchLocations()
      .then((locs) => {
        const active = locs.filter((l) => l.is_active)
        setLocations(active)
        if (active.length > 0) setLocationId((prev) => prev || active[0].id)
      })
      .catch(() => {})
  }, [])

  // Load the 300 log + 300A summary whenever year or establishment changes.
  useEffect(() => {
    if (!locationId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setItaProblems(null)
    Promise.allSettled([
      api.get<LogEntry[]>(`/ir/incidents/osha/300-log?year=${year}`).then(setEntries),
      api
        .get<Summary300A>(`/ir/incidents/osha/300a?year=${year}&location_id=${locationId}`)
        .then((s) => {
          setSummary(s)
          setHours(s.total_hours_worked != null ? String(s.total_hours_worked) : '')
          setAvgEmp(s.average_employees != null ? String(s.average_employees) : '')
          setCertBy(s.certified_by ?? '')
          setCertTitle(s.certified_title ?? '')
          setCertDate(s.certified_date ?? '')
        }),
    ]).finally(() => setLoading(false))
  }, [year, locationId])

  function downloadCsv(type: '300' | '300a') {
    // Must go through api.download — the backend CSV endpoints use
    // require_admin_or_client (header JWT). A bare window.open sends no
    // Authorization header, so it 401s with "Not authenticated".
    const path =
      type === '300'
        ? `/ir/incidents/osha/300-log/csv?year=${year}`
        : `/ir/incidents/osha/300a/csv?year=${year}&location_id=${locationId}`
    const filename =
      type === '300' ? `osha_300_log_${year}.csv` : `osha_300a_summary_${year}.csv`
    api.download(path, filename).catch(() => {})
  }

  function downloadPdf() {
    api
      .download(`/ir/incidents/osha/300a/pdf?year=${year}&location_id=${locationId}`, `osha_300a_${year}.pdf`)
      .catch(() => {})
  }

  async function save300a() {
    setSaving(true)
    setSaveMsg(null)
    try {
      await api.put('/ir/incidents/osha/300a/save', {
        location_id: locationId,
        year,
        total_hours_worked: hours.trim() === '' ? null : Number(hours),
        average_employees: avgEmp.trim() === '' ? null : Number(avgEmp),
        certified_by: certBy.trim() || null,
        certified_title: certTitle.trim() || null,
        certified_date: certDate || null,
      })
      // Re-fetch so the persisted snapshot is reflected.
      const s = await api.get<Summary300A>(
        `/ir/incidents/osha/300a?year=${year}&location_id=${locationId}`,
      )
      setSummary(s)
      setSaveMsg('Saved')
    } catch (e) {
      setSaveMsg(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function exportIta() {
    setItaBusy(true)
    setItaProblems(null)
    try {
      const problems = await api.get<ItaProblem[]>(`/ir/incidents/osha/ita/validate?year=${year}`)
      if (problems.length > 0) {
        setItaProblems(problems)
        return
      }
      await api.download(`/ir/incidents/osha/ita/export.csv?year=${year}`, `osha_ita_${year}.csv`)
    } catch {
      // Backend re-validates and may 400 with a structured detail; the validate
      // pre-check above is the primary surface, so just flag a generic failure.
      setItaProblems([])
    } finally {
      setItaBusy(false)
    }
  }

  const years = Array.from({ length: 5 }, (_, i) => currentYear - i)

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="animate-spin text-zinc-500" size={20} />
      </div>
    )
  }

  if (locations.length === 0) {
    return (
      <div className="bg-zinc-900 border border-white/10 rounded-2xl p-12 text-center">
        <p className="text-sm text-zinc-300">No business locations defined.</p>
        <p className="text-[11px] text-zinc-600 mt-1">
          OSHA 300A summaries and ITA filings are per establishment. Add a location under Compliance to begin.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <FileSpreadsheet size={16} className="text-zinc-500" />
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
            OSHA 300/300A Logs
          </span>
          <select
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
            className="bg-zinc-900 border border-white/10 rounded-lg text-zinc-200 text-xs px-2.5 py-1 max-w-[200px]"
          >
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name || `${l.city}, ${l.state}`}
              </option>
            ))}
          </select>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="bg-zinc-900 border border-white/10 rounded-lg text-zinc-200 text-xs px-2.5 py-1 font-mono"
          >
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" onClick={() => downloadCsv('300')}>
            <Download size={12} className="mr-1.5" />
            300 CSV
          </Button>
          <Button size="sm" variant="ghost" onClick={() => downloadCsv('300a')}>
            <Download size={12} className="mr-1.5" />
            300A CSV
          </Button>
          <Button size="sm" variant="ghost" onClick={downloadPdf}>
            <FileText size={12} className="mr-1.5" />
            300A PDF
          </Button>
          <Button size="sm" variant="ghost" onClick={exportIta} disabled={itaBusy}>
            {itaBusy ? (
              <Loader2 size={12} className="mr-1.5 animate-spin" />
            ) : (
              <Download size={12} className="mr-1.5" />
            )}
            ITA Export
          </Button>
        </div>
      </div>

      {/* ITA validation errors */}
      {itaProblems !== null && (
        <div className="bg-amber-950/30 border border-amber-500/30 rounded-2xl p-5">
          <div className="flex items-center gap-2 text-amber-300 text-sm font-semibold">
            <AlertTriangle size={15} />
            {itaProblems.length === 0
              ? 'ITA export failed — check establishment data and retry.'
              : 'Cannot export ITA file — fill these establishment fields first:'}
          </div>
          {itaProblems.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {itaProblems.map((p) => (
                <li key={p.location_id} className="text-[12px] text-amber-200/90">
                  <span className="font-medium">{p.establishment_name || 'Unnamed location'}</span>
                  {' — missing '}
                  {p.missing.map((m) => missingLabel[m] ?? m).join(', ')}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

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

      {/* 300A establishment / hours / certification */}
      {summary && (
        <div className="bg-zinc-900 border border-white/10 rounded-2xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
              300A Establishment Data
            </span>
            <span className="text-[11px] text-zinc-600">
              EIN {summary.ein || '—'} · NAICS {summary.naics || '—'}
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="block">
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
                Total Hours Worked
              </span>
              <input
                type="number"
                value={hours}
                onChange={(e) => setHours(e.target.value)}
                placeholder="e.g. 410000"
                className="mt-1.5 w-full bg-zinc-950 border border-white/10 rounded-lg text-zinc-200 text-sm px-3 py-2 font-mono"
              />
              <span className="text-[10px] text-zinc-600 mt-1 block">
                Manual entry — HRIS does not provide hours worked.
              </span>
            </label>
            <label className="block">
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
                Avg. Employees
              </span>
              <input
                type="number"
                value={avgEmp}
                onChange={(e) => setAvgEmp(e.target.value)}
                className="mt-1.5 w-full bg-zinc-950 border border-white/10 rounded-lg text-zinc-200 text-sm px-3 py-2 font-mono"
              />
              <span className="text-[10px] text-zinc-600 mt-1 block">
                Auto-counted from the active roster; override if needed.
              </span>
            </label>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <label className="block">
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Certified By</span>
              <input
                value={certBy}
                onChange={(e) => setCertBy(e.target.value)}
                className="mt-1.5 w-full bg-zinc-950 border border-white/10 rounded-lg text-zinc-200 text-sm px-3 py-2"
              />
            </label>
            <label className="block">
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Title</span>
              <input
                value={certTitle}
                onChange={(e) => setCertTitle(e.target.value)}
                className="mt-1.5 w-full bg-zinc-950 border border-white/10 rounded-lg text-zinc-200 text-sm px-3 py-2"
              />
            </label>
            <label className="block">
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Date</span>
              <input
                type="date"
                value={certDate}
                onChange={(e) => setCertDate(e.target.value)}
                className="mt-1.5 w-full bg-zinc-950 border border-white/10 rounded-lg text-zinc-200 text-sm px-3 py-2"
              />
            </label>
          </div>
          <div className="flex items-center gap-3">
            <Button size="sm" onClick={save300a} disabled={saving}>
              {saving ? <Loader2 size={12} className="mr-1.5 animate-spin" /> : <Save size={12} className="mr-1.5" />}
              Save 300A
            </Button>
            {saveMsg && <span className="text-[12px] text-zinc-400">{saveMsg}</span>}
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
