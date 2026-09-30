import { useEffect, useState, type FormEvent } from 'react'
import { Loader2, X } from 'lucide-react'
import { searchCaseEmployees, searchCaseIncidents, submitWriteUp } from '../../../api/hrCases'
import type { HrCaseEmployee, HrCaseIncident, ManagerCase } from '../../../types'

const ACTIONS: [string, string][] = [
  ['verbal_warning', 'Verbal warning'], ['written_warning', 'Written warning'], ['final_warning', 'Final warning'],
  ['suspension', 'Suspension'], ['pip', 'Performance improvement plan'], ['other', 'Other'],
]
const INFRACTIONS: [string, string][] = [
  ['attendance', 'Attendance'], ['performance', 'Performance'], ['conduct', 'Conduct'],
  ['safety', 'Safety'], ['policy_violation', 'Policy violation'],
]
const GOOGLE_LINK = /^(https?:\/\/)?(docs|drive)\.google\.com\//i

const field = 'w-full rounded-md border border-w-line bg-w-surface2/60 px-3 py-1.5 text-sm text-w-text placeholder:text-w-faint outline-none focus:border-w-accent/50'

function useSearch<T>(query: string, fetcher: (q: string) => Promise<T[]>): T[] {
  const [found, setFound] = useState<{ q: string; items: T[] } | null>(null)
  const q = query.trim()
  useEffect(() => {
    const timer = window.setTimeout(() => {
      fetcher(q).then((items) => setFound({ q, items })).catch(() => setFound({ q, items: [] }))
    }, q ? 250 : 0)
    return () => window.clearTimeout(timer)
  }, [q, fetcher])
  return found?.q === q ? found.items : []
}

const fetchEmployees = (q: string) => searchCaseEmployees(q).then((r) => r.employees)
const fetchIncidents = (q: string) => searchCaseIncidents(q).then((r) => r.incidents)

interface Props {
  /** Revising a case: its id and the employee/incident already on it. */
  existing?: ManagerCase
  onSubmitted: (result: { status: 'submitted' | 'held'; case: ManagerCase }) => void
  onCancel: () => void
}

export default function WriteUpForm({ existing, onSubmitted, onCancel }: Props) {
  const [employee, setEmployee] = useState<HrCaseEmployee | null>(
    existing?.employee_id ? { id: existing.employee_id, name: existing.employee_name, job_title: null } : null,
  )
  const [employeeQuery, setEmployeeQuery] = useState('')
  const [incident, setIncident] = useState<HrCaseIncident | null>(null)
  const [incidentQuery, setIncidentQuery] = useState('')
  const [actionType, setActionType] = useState(existing?.action_type ?? 'written_warning')
  const [infraction, setInfraction] = useState('attendance')
  const [dates, setDates] = useState<string[]>([])
  const [dateInput, setDateInput] = useState('')
  const [sourceKind, setSourceKind] = useState<'file' | 'google'>('file')
  const [file, setFile] = useState<File | null>(null)
  const [googleUrl, setGoogleUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const employees = useSearch(employeeQuery, fetchEmployees)
  const incidents = useSearch(incidentQuery, fetchIncidents)

  function addDate() {
    if (dateInput && !dates.includes(dateInput)) setDates((d) => [...d, dateInput].sort())
    setDateInput('')
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!employee) return setError('Pick the employee this write-up is for.')
    if (sourceKind === 'file' && !file) return setError('Attach the write-up.')
    if (sourceKind === 'google' && !GOOGLE_LINK.test(googleUrl.trim())) return setError('Paste a Google Doc link.')
    setBusy(true)
    setError(null)
    try {
      const result = await submitWriteUp({
        employeeId: employee.id,
        actionType,
        infractionType: infraction,
        occurrenceDates: dates,
        caseId: existing?.id,
        incidentId: existing ? undefined : incident?.id,
        file: sourceKind === 'file' ? file ?? undefined : undefined,
        googleUrl: sourceKind === 'google' ? googleUrl.trim() : undefined,
      })
      onSubmitted(result)
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Could not send the write-up.')
      setBusy(false)
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-4 rounded-xl border border-w-line bg-w-surface p-4" aria-label="Write-up">
      <h2 className="text-sm font-semibold text-w-text">{existing ? `Send a revised draft for ${existing.case_number}` : 'New write-up'}</h2>

      <div className="space-y-1">
        <label className="text-xs text-w-dim" htmlFor="wu-employee">Employee</label>
        {employee ? (
          <div className="flex items-center justify-between rounded-md bg-w-surface2/60 px-3 py-1.5 text-sm text-w-text">
            {employee.name ?? 'Employee'}
            {!existing && <button type="button" aria-label="Change employee" onClick={() => setEmployee(null)} className="text-w-faint hover:text-w-text"><X size={13} /></button>}
          </div>
        ) : (
          <>
            <input id="wu-employee" className={field} value={employeeQuery} onChange={(e) => setEmployeeQuery(e.target.value)} placeholder="Search by name" />
            {employees.length > 0 && (
              <ul className="max-h-36 overflow-y-auto rounded-md border border-w-line">
                {employees.map((emp) => (
                  <li key={emp.id}>
                    <button type="button" onClick={() => setEmployee(emp)} className="w-full px-3 py-1.5 text-left text-sm text-w-text hover:bg-w-surface2">
                      {emp.name}{emp.job_title && <span className="text-w-faint"> · {emp.job_title}</span>}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>

      {!existing && (
        <div className="space-y-1">
          <label className="text-xs text-w-dim" htmlFor="wu-incident">Incident (optional)</label>
          {incident ? (
            <div className="flex items-center justify-between rounded-md bg-w-surface2/60 px-3 py-1.5 text-sm text-w-text">
              {[incident.incident_number, incident.title].filter(Boolean).join(' · ')}
              <button type="button" aria-label="Clear incident" onClick={() => setIncident(null)} className="text-w-faint hover:text-w-text"><X size={13} /></button>
            </div>
          ) : (
            <>
              <input id="wu-incident" className={field} value={incidentQuery} onChange={(e) => setIncidentQuery(e.target.value)} placeholder="Search incidents" />
              {incidentQuery.trim() && incidents.length > 0 && (
                <ul className="max-h-36 overflow-y-auto rounded-md border border-w-line">
                  {incidents.map((inc) => (
                    <li key={inc.id}>
                      <button type="button" onClick={() => setIncident(inc)} className="w-full px-3 py-1.5 text-left text-sm text-w-text hover:bg-w-surface2">
                        {[inc.incident_number, inc.title].filter(Boolean).join(' · ')}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <label className="text-xs text-w-dim" htmlFor="wu-action">Action</label>
          <select id="wu-action" className={field} value={actionType} onChange={(e) => setActionType(e.target.value)}>
            {ACTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-w-dim" htmlFor="wu-infraction">About</label>
          <select id="wu-infraction" className={field} value={infraction} onChange={(e) => setInfraction(e.target.value)}>
            {INFRACTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-xs text-w-dim" htmlFor="wu-date">When it happened</label>
        <div className="flex gap-2">
          <input id="wu-date" type="date" className={field} value={dateInput} onChange={(e) => setDateInput(e.target.value)} />
          <button type="button" onClick={addDate} disabled={!dateInput} className="rounded-lg border border-w-line px-3 text-sm text-w-dim hover:text-w-text disabled:opacity-50">Add</button>
        </div>
        {dates.length > 0 && (
          <ul className="flex flex-wrap gap-1.5">
            {dates.map((d) => (
              <li key={d} className="flex items-center gap-1 rounded-full bg-w-surface2 px-2 py-0.5 text-xs text-w-text">
                {d}
                <button type="button" aria-label={`Remove ${d}`} onClick={() => setDates((all) => all.filter((x) => x !== d))} className="text-w-faint hover:text-w-text"><X size={11} /></button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex gap-3 text-xs" role="radiogroup" aria-label="Where the write-up is">
          <label className="flex items-center gap-1.5 text-w-dim"><input type="radio" checked={sourceKind === 'file'} onChange={() => setSourceKind('file')} /> Upload a file</label>
          <label className="flex items-center gap-1.5 text-w-dim"><input type="radio" checked={sourceKind === 'google'} onChange={() => setSourceKind('google')} /> Google Doc link</label>
        </div>
        {sourceKind === 'file' ? (
          <input aria-label="Write-up file" type="file" accept=".pdf,.docx,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm text-w-dim" />
        ) : (
          <input aria-label="Google Doc link" className={field} value={googleUrl} onChange={(e) => setGoogleUrl(e.target.value)} placeholder="https://docs.google.com/document/d/…" />
        )}
      </div>

      <p className="text-[11px] text-w-faint">
        Matcha checks the letter against leave protections and your discipline history before HR sees it. The file is saved to HR’s private Drive folder.
      </p>
      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="rounded-lg px-3 py-1.5 text-sm text-w-dim hover:text-w-text">Cancel</button>
        <button type="submit" disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg bg-w-accent px-3 py-1.5 text-sm font-medium text-w-on-accent hover:bg-w-accent-hi disabled:opacity-50">
          {busy && <Loader2 size={13} className="animate-spin" />} Send to HR
        </button>
      </div>
    </form>
  )
}
