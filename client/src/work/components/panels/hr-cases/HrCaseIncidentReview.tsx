import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { searchCaseEmployees } from '../../../api/hrCases'
import type { HrCase, HrCaseEmployee, PolicyViolationReview } from '../../../types'

const field = 'w-full rounded-md border border-w-line bg-w-surface2/60 px-3 py-1.5 text-sm text-w-text outline-none focus:border-w-accent/50'

interface Props {
  hrCase: HrCase
  onStartDraft: () => Promise<void>
  onSuggest: (review: PolicyViolationReview) => Promise<void>
  onAccept: (suggestionId: string, letter: string) => Promise<void>
  onDismissSuggestion: (suggestionId: string, reason: string) => Promise<void>
}

export default function HrCaseIncidentReview({ hrCase, onStartDraft, onSuggest, onAccept, onDismissSuggestion }: Props) {
  const suggestion = hrCase.review?.suggestion
  const [reviewing, setReviewing] = useState(hrCase.stage === 'flagged' && !!hrCase.source_incident_id && !suggestion)
  const [query, setQuery] = useState('')
  const [employees, setEmployees] = useState<HrCaseEmployee[]>([])
  const [employeeId, setEmployeeId] = useState(hrCase.employee_id ?? '')
  const [actionType, setActionType] = useState<PolicyViolationReview['action_type']>('verbal_warning')
  const [infraction, setInfraction] = useState<PolicyViolationReview['infraction_type']>('policy_violation')
  const [dates, setDates] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [letter, setLetter] = useState(suggestion?.letter ?? '')
  const [dismissing, setDismissing] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const draftable = ['flagged', 'drafting'].includes(hrCase.stage) && !hrCase.draft_file_id

  useEffect(() => {
    if (!reviewing) return
    let active = true
    const timer = window.setTimeout(() => {
      searchCaseEmployees(query).then(
        (r) => { if (active) setEmployees(r.employees) },
        () => { if (active) setError('Could not load employees. Try searching again.') },
      )
    }, query ? 250 : 0)
    return () => { active = false; window.clearTimeout(timer) }
  }, [reviewing, query])

  async function run(action: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      setReviewing(false)
      setDismissing(false)
      setReason('')
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Could not save the review.')
    } finally {
      setBusy(false)
    }
  }

  if (!draftable) return null

  return (
    <section className="space-y-3" aria-label="Incident HR review">
      <h3 className="text-xs font-medium uppercase tracking-wide text-w-faint">Draft action for HR review</h3>
      {!suggestion && hrCase.allowed_events.includes('start_draft') && hrCase.gm_user_id && (
        <button type="button" disabled={busy} onClick={() => void run(onStartDraft)} className="w-full rounded-lg border border-w-line px-3 py-1.5 text-sm text-w-text disabled:opacity-50">Request manager write-up</button>
      )}
      {suggestion ? (
        <>
          <p className="text-xs text-w-dim">Suggested write-up for HR to edit. Accepting sends it to HR review; approval to deliver is a separate step.</p>
          <p className="text-xs text-w-dim">{suggestion.input.action_type.replace(/_/g, ' ')} · {suggestion.input.infraction_type.replace(/_/g, ' ')} · {suggestion.input.occurrence_dates.join(', ')}</p>
          <label className="block space-y-1 text-xs text-w-dim">
            <span>Suggested letter</span>
            <textarea aria-label="Suggested letter" className={field} rows={14} maxLength={20_000} value={letter} onChange={(e) => setLetter(e.target.value)} disabled={busy} />
          </label>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy || !letter.trim()} onClick={() => void run(() => onAccept(suggestion.id, letter.trim()))} className="rounded-lg bg-w-accent px-3 py-1.5 text-sm font-medium text-w-on-accent disabled:opacity-50">Accept into HR review</button>
            <button type="button" disabled={busy} onClick={() => setDismissing(true)} className="text-sm text-w-dim hover:text-w-text disabled:opacity-50">Dismiss suggestion</button>
          </div>
          {dismissing && (
            <div className="space-y-2">
              <textarea aria-label="Reason for dismissing suggestion" className={field} rows={3} maxLength={2000} placeholder="Why this suggestion isn't suitable" value={reason} onChange={(e) => setReason(e.target.value)} />
              <button type="button" disabled={busy || reason.trim().length < 10} onClick={() => void run(() => onDismissSuggestion(suggestion.id, reason.trim()))} className="rounded-lg border border-w-line px-3 py-1.5 text-sm text-w-text disabled:opacity-50">Confirm dismissal</button>
            </div>
          )}
        </>
      ) : reviewing ? (
        <form className="space-y-3" onSubmit={(e) => {
          e.preventDefault()
          const occurrenceDates = dates.split(',').map((d) => d.trim()).filter(Boolean)
          void run(() => onSuggest({ classification: 'policy_violation', employee_id: employeeId, action_type: actionType, infraction_type: infraction, occurrence_dates: occurrenceDates }))
        }}>
          <p className="text-xs text-w-dim">Review the incident, choose the proposed action and confirm the employee and dates. Matcha will draft an editable letter for HR review. Nothing is approved or sent to the employee here.</p>
          <label className="block space-y-1 text-xs text-w-dim">
            <span>Search employee</span>
            <input className={field} value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
          <label className="block space-y-1 text-xs text-w-dim">
            <span>Employee for this action</span>
            <select required className={field} value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
              <option value="">Choose employee</option>
              {hrCase.employee_id && !employees.some((e) => e.id === hrCase.employee_id) && <option value={hrCase.employee_id}>{hrCase.employee_name ?? 'Linked employee'}</option>}
              {employees.map((emp) => <option key={emp.id} value={emp.id}>{emp.name ?? emp.id}</option>)}
            </select>
          </label>
          <label className="block space-y-1 text-xs text-w-dim">
            <span>Proposed action</span>
            <select className={field} value={actionType} onChange={(e) => setActionType(e.target.value as PolicyViolationReview['action_type'])}>
              <option value="verbal_warning">Verbal warning</option><option value="written_warning">Written warning</option>
              <option value="final_warning">Final warning</option><option value="suspension">Suspension</option><option value="pip">PIP</option><option value="other">Other</option>
            </select>
          </label>
          <label className="block space-y-1 text-xs text-w-dim">
            <span>Conduct being addressed</span>
            <select className={field} value={infraction} onChange={(e) => setInfraction(e.target.value as PolicyViolationReview['infraction_type'])}>
              <option value="policy_violation">Policy violation</option><option value="attendance">Attendance / absence</option>
              <option value="performance">Performance</option><option value="conduct">Conduct</option><option value="safety">Safety</option>
            </select>
          </label>
          <p className="text-[11px] text-w-faint">Choose Attendance / absence when disciplining an absence so the protected-leave rule applies.</p>
          <label className="block space-y-1 text-xs text-w-dim">
            <span>Occurrence dates (YYYY-MM-DD, separated by commas)</span>
            <input required className={field} value={dates} onChange={(e) => setDates(e.target.value)} placeholder="2026-10-01, 2026-10-02" />
          </label>
          <label className="flex items-start gap-2 text-xs text-w-dim">
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
            <span>I reviewed the incident and confirm a policy violation for this employee.</span>
          </label>
          <div className="flex gap-2">
            <button type="submit" disabled={busy || !confirmed || !employeeId || !dates.trim()} className="rounded-lg bg-w-accent px-3 py-1.5 text-sm font-medium text-w-on-accent disabled:opacity-50">Confirm violation and draft</button>
            <button type="button" disabled={busy} onClick={() => setReviewing(false)} className="text-sm text-w-dim">Cancel</button>
          </div>
        </form>
      ) : (
        <div className="space-y-2">
          <p className="text-xs text-w-dim">Request a manager’s letter, or confirm a policy violation to get an editable suggestion.</p>
          {hrCase.stage === 'drafting' && <p className="text-xs text-w-faint">Waiting on a draft. HR can also prepare one here.</p>}
          {hrCase.source_incident_id && <button type="button" disabled={busy} onClick={() => setReviewing(true)} className="w-full rounded-lg bg-w-accent px-3 py-1.5 text-sm font-medium text-w-on-accent disabled:opacity-50">Draft action for HR review</button>}
        </div>
      )}
      {busy && <p role="status" className="flex items-center gap-2 text-xs text-w-dim"><Loader2 size={13} className="animate-spin" /> Saving review…</p>}
      {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
    </section>
  )
}
