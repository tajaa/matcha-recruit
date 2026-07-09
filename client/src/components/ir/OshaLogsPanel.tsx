import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { fetchLocations } from '../../api/compliance'
import type { BusinessLocation } from '../../types/compliance'
import { Badge, Button, Modal } from '../ui'
import { useMe } from '../../hooks/useMe'
import { Download, Loader2, FileSpreadsheet, FileText, Save, AlertTriangle, Lock, Eye, EyeOff } from 'lucide-react'

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
  is_privacy_case: boolean
  privacy_case_reason: string | null
}

// Confidential privacy-case reference list row (admin/client-only endpoint).
type PrivacyCaseRow = {
  case_number: string
  real_employee_name: string
  privacy_case_reason: string | null
  classification: string | null
  date_of_injury: string
  incident_id: string
}

const privacyReasonLabel: Record<string, string> = {
  intimate_injury: 'Intimate injury',
  sexual_assault: 'Sexual assault',
  mental_illness: 'Mental illness',
  infectious_pathogen: 'HIV / Hepatitis / TB',
  contaminated_sharps: 'Contaminated sharps',
  voluntary_opt_out: 'Employee opt-out',
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
  data_quality_warnings?: string[]
}

type ItaProblem = {
  location_id: string | null
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

// Shown in the pre-export confirm modal. Mirrors the backend EXPORT_DISCLAIMER;
// the server also returns it on a 403 if an un-attested export slips through.
const EXPORT_DISCLAIMER =
  'This OSHA log was prepared with AI-assisted recordability classification, ' +
  'injury-description cleansing, and Privacy Case name masking. These are aids, ' +
  'not a substitute for your review. Before filing with OSHA or any agency you ' +
  'are responsible for verifying every entry — recordability, day counts, ' +
  'Privacy Case masking, and descriptions. Matcha does not guarantee the ' +
  'accuracy or completeness of generated entries. By exporting you confirm you ' +
  'have reviewed this data and accept responsibility for its accuracy and filing.'

const missingLabel: Record<string, string> = {
  ein: 'EIN',
  naics: 'NAICS code',
  street_address: 'Street address',
  total_hours_worked: 'Total hours worked',
  unassigned_location: 'a location (excluded from the filing until assigned)',
}

export function OshaLogsPanel() {
  const navigate = useNavigate()
  const { me } = useMe()
  const canRevealNames = me?.user?.role === 'admin' || me?.user?.role === 'client'
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState(currentYear)
  const [locations, setLocations] = useState<BusinessLocation[]>([])
  const [locationId, setLocationId] = useState<string>('')
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [summary, setSummary] = useState<Summary300A | null>(null)
  const [loading, setLoading] = useState(true)
  // Confidential privacy-case names (revealed on demand; audit-logged server-side).
  const [privacyNames, setPrivacyNames] = useState<PrivacyCaseRow[] | null>(null)
  const [revealing, setRevealing] = useState(false)

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

  // Pre-export reviewer attestation. No file leaves the system until the user
  // confirms they reviewed the (AI-assisted) data; the backend re-checks via
  // ?attested=true and writes the audit record.
  const [attestExport, setAttestExport] = useState<
    { label: string; preview: ReactNode; run: () => Promise<void> } | null
  >(null)
  const [attestChecked, setAttestChecked] = useState(false)
  const [attestBusy, setAttestBusy] = useState(false)

  function promptExport(label: string, preview: ReactNode, run: () => Promise<void>) {
    setAttestChecked(false)
    setAttestExport({ label, preview, run })
  }

  async function confirmExport() {
    if (!attestExport) return
    setAttestBusy(true)
    try {
      await attestExport.run()
      setAttestExport(null)
    } catch {
      // download helper already swallows; keep the modal open on failure.
    } finally {
      setAttestBusy(false)
    }
  }

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
    setPrivacyNames(null)
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

  // Exact export content, rendered inside the attestation modal so the reviewer
  // sees every field that will leave the system — including Description (Column
  // F), the name-cleansed field — before they sign off.
  function renderLogPreview(): ReactNode {
    if (entries.length === 0) {
      return <p className="text-[12px] text-zinc-500">No OSHA-recordable rows for {year}.</p>
    }
    return (
      <table className="w-full text-left text-[11px]">
        <thead className="text-zinc-500">
          <tr>
            <th className="py-1.5 pr-3 uppercase tracking-widest font-bold">Case #</th>
            <th className="py-1.5 pr-3 uppercase tracking-widest font-bold">Employee</th>
            <th className="py-1.5 pr-3 uppercase tracking-widest font-bold">Title</th>
            <th className="py-1.5 pr-3 uppercase tracking-widest font-bold">Date</th>
            <th className="py-1.5 pr-3 uppercase tracking-widest font-bold">Location</th>
            <th className="py-1.5 pr-3 uppercase tracking-widest font-bold">Class</th>
            <th className="py-1.5 pr-3 uppercase tracking-widest font-bold text-right">Away</th>
            <th className="py-1.5 pr-3 uppercase tracking-widest font-bold text-right">Restr.</th>
            <th className="py-1.5 uppercase tracking-widest font-bold">Description (Col. F)</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={`${e.incident_id}-${e.case_number}`} className="border-t border-white/5 text-zinc-300 align-top">
              <td className="py-1.5 pr-3 font-mono text-zinc-500">{e.case_number}</td>
              <td className="py-1.5 pr-3 text-zinc-100">
                {e.is_privacy_case ? 'Privacy Case' : e.employee_name}
              </td>
              <td className="py-1.5 pr-3 text-zinc-400">{e.job_title || '—'}</td>
              <td className="py-1.5 pr-3 font-mono text-zinc-400">{e.date_of_injury}</td>
              <td className="py-1.5 pr-3 text-zinc-400">{e.location || '—'}</td>
              <td className="py-1.5 pr-3 text-zinc-400">
                {e.classification ? classificationLabel[e.classification] ?? e.classification : '—'}
              </td>
              <td className="py-1.5 pr-3 text-right font-mono text-zinc-300">{e.days_away || '—'}</td>
              <td className="py-1.5 pr-3 text-right font-mono text-zinc-300">{e.days_restricted || '—'}</td>
              <td className="py-1.5 text-zinc-300">{e.description || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )
  }

  function render300aPreview(): ReactNode {
    if (!summary) return null
    const rows: [string, string | number][] = [
      ['Establishment', summary.establishment_name || '—'],
      ['Total Cases', summary.total_cases],
      ['Deaths', summary.total_deaths],
      ['Days-Away Cases', summary.total_days_away_cases],
      ['Restricted/Transfer Cases', summary.total_restricted_cases],
      ['Other Recordable Cases', summary.total_other_recordable],
      ['Total Days Away', summary.total_days_away],
      ['Total Days Restricted', summary.total_days_restricted],
      ['Injuries', summary.total_injuries],
      ['Skin Disorders', summary.total_skin_disorders],
      ['Respiratory Conditions', summary.total_respiratory],
      ['Poisonings', summary.total_poisonings],
      ['Hearing Loss', summary.total_hearing_loss],
      ['Other Illnesses', summary.total_other_illnesses],
      ['Avg. Employees', summary.average_employees ?? '—'],
      ['Total Hours Worked', summary.total_hours_worked ?? '—'],
      ['Certified By', summary.certified_by || '—'],
      ['Certified Title', summary.certified_title || '—'],
      ['Certified Date', summary.certified_date || '—'],
    ]
    return (
      <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-[12px]">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between border-b border-white/5 pb-1">
            <dt className="text-zinc-500">{k}</dt>
            <dd className="text-zinc-200 font-mono">{v}</dd>
          </div>
        ))}
      </dl>
    )
  }

  // ITA spans every active establishment (this panel loads one location's 300A
  // at a time), so the modal points the reviewer at the per-establishment 300A
  // rather than re-aggregating all of them here.
  function renderItaPreview(): ReactNode {
    return (
      <p className="text-[12px] text-zinc-400 leading-relaxed">
        The ITA file rolls up the 300A totals for every active establishment for {year}.
        Review each establishment's 300A (switch the location selector above) before exporting —
        the export uses the same figures shown there.
      </p>
    )
  }

  // The actual download runs only after the attestation modal is confirmed, so
  // every path carries &attested=true (the backend gate + audit). Must go
  // through api.download — the CSV/PDF endpoints use require_admin_or_client
  // (header JWT); a bare window.open sends no Authorization header → 401.
  function runCsv(type: '300' | '300a') {
    const path =
      type === '300'
        ? `/ir/incidents/osha/300-log/csv?year=${year}&attested=true`
        : `/ir/incidents/osha/300a/csv?year=${year}&location_id=${locationId}&attested=true`
    const filename =
      type === '300' ? `osha_300_log_${year}.csv` : `osha_300a_summary_${year}.csv`
    return api.download(path, filename)
  }

  function runPdf() {
    return api.download(
      `/ir/incidents/osha/300a/pdf?year=${year}&location_id=${locationId}&attested=true`,
      `osha_300a_${year}.pdf`,
    )
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
        // Missing establishment fields block the export (the backend 400s on
        // them anyway). The unassigned-recordables entry is advisory — those
        // incidents are excluded from the file, but the file itself is valid —
        // so surface it and continue.
        const blocking = problems.filter((p) => !p.missing.includes('unassigned_location'))
        if (blocking.length > 0) return
      }
      promptExport('OSHA ITA Establishment Export', renderItaPreview(), () =>
        api.download(`/ir/incidents/osha/ita/export.csv?year=${year}&attested=true`, `osha_ita_${year}.csv`),
      )
    } catch {
      // Backend re-validates and may 400 with a structured detail; the validate
      // pre-check above is the primary surface, so just flag a generic failure.
      setItaProblems([])
    } finally {
      setItaBusy(false)
    }
  }

  async function revealConfidentialNames() {
    setRevealing(true)
    try {
      const rows = await api.get<PrivacyCaseRow[]>(`/ir/incidents/osha/privacy-cases?year=${year}`)
      setPrivacyNames(rows)
    } catch {
      setPrivacyNames([])
    } finally {
      setRevealing(false)
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
          <Button size="sm" variant="ghost" onClick={() => promptExport('OSHA 300 Log CSV', renderLogPreview(), () => runCsv('300'))}>
            <Download size={12} className="mr-1.5" />
            300 CSV
          </Button>
          <Button size="sm" variant="ghost" onClick={() => promptExport('OSHA 300A Summary CSV', render300aPreview(), () => runCsv('300a'))}>
            <Download size={12} className="mr-1.5" />
            300A CSV
          </Button>
          <Button size="sm" variant="ghost" onClick={() => promptExport('OSHA Form 300A PDF', render300aPreview(), () => runPdf())}>
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
              : itaProblems.every((p) => p.missing.includes('unassigned_location'))
                ? 'Review before filing — these incidents are excluded from the export:'
                : 'Cannot export ITA file — fill these establishment fields first:'}
          </div>
          {itaProblems.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {itaProblems.map((p) => (
                <li key={p.location_id ?? 'unassigned'} className="text-[12px] text-amber-200/90">
                  <span className="font-medium">{p.establishment_name || 'Unnamed location'}</span>
                  {' — missing '}
                  {p.missing.map((m) => missingLabel[m] ?? m).join(', ')}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* 300A data-quality warnings — recordables missing a classification or a
          location won't foot / file correctly. Non-blocking. */}
      {summary && summary.data_quality_warnings && summary.data_quality_warnings.length > 0 && (
        <div className="bg-amber-950/30 border border-amber-500/30 rounded-2xl p-5">
          <div className="flex items-center gap-2 text-amber-300 text-sm font-semibold">
            <AlertTriangle size={15} />
            Data quality — review before filing
          </div>
          <ul className="mt-3 space-y-1.5">
            {summary.data_quality_warnings.map((w, i) => (
              <li key={i} className="text-[12px] text-amber-200/90">{w}</li>
            ))}
          </ul>
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
            <div className="flex flex-col">
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
                300A Establishment Data
              </span>
              <span className="text-[13px] text-zinc-200 font-medium mt-0.5">
                {summary.establishment_name || 'Unnamed establishment'}
                {summary.city && (
                  <span className="text-zinc-500 font-normal"> · {summary.city}, {summary.state}</span>
                )}
              </span>
            </div>
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
                Auto-counted from the active roster (incl. HRIS/Finch-synced employees); override if needed.
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

      {/* Confidential privacy-case reference list (admin/client only). OSHA
          masks the name on the public log; this resolves case # → real name
          (29 CFR 1904.29(b)(9)). Every reveal is audit-logged server-side. */}
      {canRevealNames && entries.some((e) => e.is_privacy_case) && (
        <div className="bg-zinc-900 border border-amber-500/20 rounded-2xl p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Lock size={14} className="text-amber-400" />
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
                Confidential Privacy-Case Names
              </span>
            </div>
            {privacyNames === null ? (
              <Button size="sm" variant="ghost" onClick={revealConfidentialNames} disabled={revealing}>
                {revealing ? <Loader2 size={12} className="mr-1.5 animate-spin" /> : <Eye size={12} className="mr-1.5" />}
                Reveal names
              </Button>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => setPrivacyNames(null)}>
                <EyeOff size={12} className="mr-1.5" />
                Hide
              </Button>
            )}
          </div>
          {privacyNames !== null &&
            (privacyNames.length === 0 ? (
              <p className="text-[12px] text-zinc-500 mt-3">No privacy-case names to show.</p>
            ) : (
              <table className="w-full text-sm text-left mt-3">
                <thead className="text-zinc-500">
                  <tr>
                    <th className="py-1.5 text-[10px] uppercase tracking-widest font-bold">Case #</th>
                    <th className="py-1.5 text-[10px] uppercase tracking-widest font-bold">Employee</th>
                    <th className="py-1.5 text-[10px] uppercase tracking-widest font-bold">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {privacyNames.map((p) => (
                    <tr key={p.incident_id} className="border-t border-white/5 text-zinc-300">
                      <td className="py-2 font-mono text-[11px] text-zinc-500">{p.case_number}</td>
                      <td className="py-2 text-[13px] text-zinc-100">{p.real_employee_name}</td>
                      <td className="py-2 text-[12px] text-zinc-400">
                        {p.privacy_case_reason ? privacyReasonLabel[p.privacy_case_reason] ?? p.privacy_case_reason : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ))}
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
                  <th className="px-4 py-3 text-[10px] uppercase tracking-widest font-bold">Description</th>
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
                    <td className="px-4 py-3 text-[13px] text-zinc-100 font-medium">
                      {e.is_privacy_case ? (
                        <span className="inline-flex items-center gap-1.5">
                          <Lock size={11} className="text-amber-400 shrink-0" />
                          <span>Privacy Case</span>
                          {e.privacy_case_reason && (
                            <Badge variant="neutral">
                              {privacyReasonLabel[e.privacy_case_reason] ?? e.privacy_case_reason}
                            </Badge>
                          )}
                        </span>
                      ) : (
                        e.employee_name
                      )}
                    </td>
                    <td className="px-4 py-3 text-[12px] text-zinc-500">{e.job_title || '—'}</td>
                    <td className="px-4 py-3 text-[11px] text-zinc-400 font-mono">{e.date_of_injury}</td>
                    <td className="px-4 py-3 text-[12px] text-zinc-400">{e.location || '—'}</td>
                    <td className="px-4 py-3 text-[12px] text-zinc-400 max-w-[260px] truncate" title={e.description || ''}>
                      {e.description || '—'}
                    </td>
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

      {/* Pre-export reviewer attestation — absolves the tool, records the human
          sign-off (audit). No OSHA file downloads until this is confirmed. */}
      <Modal
        open={attestExport !== null}
        onClose={() => { if (!attestBusy) setAttestExport(null) }}
        title="Review &amp; confirm export"
        width="xl"
      >
        <div className="space-y-4">
          {attestExport && (
            <div className="flex items-start gap-2 text-amber-300">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              <span className="text-[13px] font-medium">{attestExport.label}</span>
            </div>
          )}
          {/* Exactly what will be exported — review before signing off. */}
          <div className="rounded-xl border border-white/10 bg-zinc-950/50 p-3 max-h-[45vh] overflow-auto">
            {attestExport?.preview}
          </div>
          <p className="text-[13px] text-zinc-300 leading-relaxed">{EXPORT_DISCLAIMER}</p>
          <label className="flex items-start gap-2.5 cursor-pointer">
            <input
              type="checkbox"
              checked={attestChecked}
              onChange={(e) => setAttestChecked(e.target.checked)}
              className="mt-0.5 accent-emerald-500"
            />
            <span className="text-[13px] text-zinc-200">
              I have reviewed this data for accuracy and accept responsibility for the exported records.
            </span>
          </label>
          <div className="flex justify-end gap-2 pt-1">
            <Button size="sm" variant="ghost" onClick={() => setAttestExport(null)} disabled={attestBusy}>
              Cancel
            </Button>
            <Button size="sm" onClick={confirmExport} disabled={!attestChecked || attestBusy}>
              {attestBusy ? <Loader2 size={12} className="mr-1.5 animate-spin" /> : <Download size={12} className="mr-1.5" />}
              Export
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
