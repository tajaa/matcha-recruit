import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../../api/client'
import { fetchLocations } from '../../../api/compliance/compliance'
import type { BusinessLocation } from '../../../types/compliance'
import { useMe } from '../../../hooks/useMe'
import { renderLogPreview, render300aPreview, renderItaPreview } from './previews'
import type {
  LogEntry,
  PrivacyCaseRow,
  Summary300A,
  ItaProblem,
  ItaSubmissionRow,
  ItaCredentialStatus,
  ItaSubmitResponse,
} from './types'

export function useOshaLogs() {
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

  // ITA direct-submission state (electronic filing via the OSHA API).
  const [itaCredConfigured, setItaCredConfigured] = useState<boolean | null>(null)
  const [itaTokenInput, setItaTokenInput] = useState('')
  const [savingToken, setSavingToken] = useState(false)
  const [showTokenInput, setShowTokenInput] = useState(false)
  const [itaSubmitMsg, setItaSubmitMsg] = useState<{ status: string; text: string } | null>(null)
  const [itaSubmissions, setItaSubmissions] = useState<ItaSubmissionRow[]>([])

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
    loadItaState()
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      promptExport('OSHA ITA Establishment Export', renderItaPreview(year), () =>
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

  // ── ITA direct electronic submission ──────────────────────────────────────
  async function loadItaState() {
    try {
      const status = await api.get<ItaCredentialStatus>('/ir/incidents/osha/ita/credentials')
      setItaCredConfigured(status.configured)
    } catch {
      setItaCredConfigured(null)
    }
    try {
      const res = await api.get<{ submissions: ItaSubmissionRow[] }>('/ir/incidents/osha/ita/submissions')
      setItaSubmissions(res.submissions)
    } catch {
      setItaSubmissions([])
    }
  }

  async function saveItaToken() {
    if (!itaTokenInput.trim()) return
    setSavingToken(true)
    try {
      await api.put('/ir/incidents/osha/ita/credentials', { api_token: itaTokenInput.trim() })
      setItaTokenInput('')
      setShowTokenInput(false)
      setItaCredConfigured(true)
    } catch (e) {
      setItaSubmitMsg({ status: 'error', text: e instanceof Error ? e.message : 'Could not save token' })
    } finally {
      setSavingToken(false)
    }
  }

  async function submitIta() {
    setItaBusy(true)
    setItaProblems(null)
    setItaSubmitMsg(null)
    try {
      const problems = await api.get<ItaProblem[]>(`/ir/incidents/osha/ita/validate?year=${year}`)
      if (problems.length > 0) {
        setItaProblems(problems)
        const blocking = problems.filter((p) => !p.missing.includes('unassigned_location'))
        if (blocking.length > 0) return
      }
      promptExport('Submit to OSHA ITA (electronic filing)', renderItaPreview(year), async () => {
        const res = await api.post<ItaSubmitResponse>('/ir/incidents/osha/ita/submit', {
          year,
          attested: true,
        })
        if (res.status === 'submitted') {
          setItaSubmitMsg({ status: 'ok', text: `Filed ${res.establishment_count} establishment(s) with OSHA${res.submission_id ? ` — confirmation ${res.submission_id}` : ''}.` })
        } else if (res.status === 'not_configured') {
          setItaSubmitMsg({ status: 'warn', text: 'Add your OSHA ITA API token below before filing.' })
          setShowTokenInput(true)
        } else {
          setItaSubmitMsg({ status: 'error', text: res.error || 'OSHA ITA rejected the filing.' })
        }
        await loadItaState()
      })
    } catch {
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

  // Bound export handlers — snapshot the current preview at click time.
  const onExport300Csv = () =>
    promptExport('OSHA 300 Log CSV', renderLogPreview(entries, year), () => runCsv('300'))
  const onExport300aCsv = () =>
    promptExport('OSHA 300A Summary CSV', render300aPreview(summary), () => runCsv('300a'))
  const onExport300aPdf = () =>
    promptExport('OSHA Form 300A PDF', render300aPreview(summary), () => runPdf())

  return {
    navigate,
    canRevealNames,
    year,
    setYear,
    locations,
    locationId,
    setLocationId,
    entries,
    summary,
    loading,
    privacyNames,
    setPrivacyNames,
    revealing,
    hours,
    setHours,
    avgEmp,
    setAvgEmp,
    certBy,
    setCertBy,
    certTitle,
    setCertTitle,
    certDate,
    setCertDate,
    saving,
    saveMsg,
    itaProblems,
    itaBusy,
    itaCredConfigured,
    itaTokenInput,
    setItaTokenInput,
    savingToken,
    showTokenInput,
    setShowTokenInput,
    itaSubmitMsg,
    itaSubmissions,
    attestExport,
    setAttestExport,
    attestChecked,
    setAttestChecked,
    attestBusy,
    confirmExport,
    save300a,
    exportIta,
    saveItaToken,
    submitIta,
    revealConfidentialNames,
    years,
    onExport300Csv,
    onExport300aCsv,
    onExport300aPdf,
  }
}
