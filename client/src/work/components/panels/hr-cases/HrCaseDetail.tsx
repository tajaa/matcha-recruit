import { useState, type FormEvent } from 'react'
import { CheckCircle2, Circle, ExternalLink, Loader2, X } from 'lucide-react'
import type { HrCase } from '../../../types'
import HrCaseReviewSection from './HrCaseReviewSection'
import HrCaseSignedSection from './HrCaseSignedSection'

const ORIGIN_LABEL: Record<HrCase['origin'], string> = {
  intake_triage: 'Flagged when the incident was reported',
  close_check: 'Flagged when the incident was closed',
  gm_draft: 'Opened from a manager’s write-up',
  huume: 'Opened through Huume',
  manual: 'Opened by HR',
}

const EVENT_LABEL: Record<string, string> = {
  opened: 'Case opened',
  dismiss: 'Dismissed',
  intake_check_match: 'Intake check: policy match',
  intake_check_clean: 'Intake check: no match',
  close_check_match: 'Close check: policy match',
  close_check_clean: 'Close check: no match',
  draft_submitted: 'Write-up sent to HR',
  draft_held: 'Write-up held by the leave check',
  approve: 'Approved to deliver',
  request_changes: 'Sent back for changes',
  delivered: 'Delivered to employee',
  signed_uploaded: 'Signed copy uploaded',
  verified: 'Signed copy checked and filed',
  attention: 'Signed copy needs attention',
  acknowledge: 'Closed by HR',
}

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : ''
}

interface Props {
  hrCase: HrCase
  onClose: () => void
  onDismiss: (reason: string) => Promise<void>
  onOpenDraft: () => Promise<void>
  onDecide: (decision: 'approve' | 'request_changes', reason: string) => Promise<void>
  onDelivered: (deliveredOn: string) => Promise<void>
  onOpenSigned: () => Promise<void>
  onUploadSigned: (file: File) => Promise<void>
  onAcknowledge: () => Promise<void>
  onRecheck: () => Promise<void>
}

export default function HrCaseDetail({
  hrCase, onClose, onDismiss, onOpenDraft, onDecide, onDelivered, onOpenSigned, onUploadSigned, onAcknowledge, onRecheck,
}: Props) {
  const [dismissing, setDismissing] = useState(false)
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const canDismiss = hrCase.allowed_events.includes('dismiss')
  const matches = (hrCase.triage?.violations ?? []).filter((v) => v.policy_title)

  async function submitDismiss(e: FormEvent) {
    e.preventDefault()
    if (reason.trim().length < 10) {
      setError('Say briefly why (at least 10 characters).')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onDismiss(reason.trim())
      setDismissing(false)
      setReason('')
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Could not dismiss the case')
    } finally {
      setSaving(false)
    }
  }

  return (
    <aside aria-label={`Case ${hrCase.case_number}`} className="flex h-full w-full flex-col border-l border-w-line bg-w-surface md:w-96">
      <header className="flex items-start justify-between gap-2 border-b border-w-line px-4 py-3">
        <div className="min-w-0">
          <p className="text-xs text-w-faint">{hrCase.case_number}</p>
          <h2 className="truncate text-sm font-semibold text-w-text">{hrCase.incident_title ?? 'HR case'}</h2>
          <p className="mt-0.5 text-xs text-w-dim">{hrCase.stage_label}</p>
        </div>
        <button type="button" aria-label="Close case" onClick={onClose} className="rounded-md p-1 text-w-faint hover:text-w-text">
          <X size={16} />
        </button>
      </header>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4 text-sm">
        <section className="space-y-1 text-xs text-w-dim">
          <p>{ORIGIN_LABEL[hrCase.origin]}</p>
          {hrCase.source_incident_id && (
            <a href={`/app/ir/${hrCase.source_incident_id}`} className="inline-flex items-center gap-1 text-w-accent hover:underline">
              Incident {hrCase.incident_number ?? ''} <ExternalLink size={11} />
            </a>
          )}
          {hrCase.employee_name && <p>Employee: <span className="text-w-text">{hrCase.employee_name}</span></p>}
          {hrCase.gm_name && <p>Reported by: <span className="text-w-text">{hrCase.gm_name}</span></p>}
        </section>

        <section>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-w-faint">Progress</h3>
          <ul className="space-y-1.5">
            {hrCase.checklist.map((item) => (
              <li key={item.key} className="flex items-center gap-2 text-sm">
                {item.done
                  ? <CheckCircle2 size={14} className="shrink-0 text-emerald-400" aria-label="done" />
                  : <Circle size={14} className="shrink-0 text-w-faint" aria-label="not done" />}
                <span className={item.done ? 'text-w-text' : 'text-w-dim'}>{item.label}</span>
              </li>
            ))}
          </ul>
        </section>

        <HrCaseReviewSection hrCase={hrCase} onOpenDraft={onOpenDraft} onDecide={onDecide} onDelivered={onDelivered} />

        <HrCaseSignedSection hrCase={hrCase} onOpenSigned={onOpenSigned} onUploadSigned={onUploadSigned} onAcknowledge={onAcknowledge} onRecheck={onRecheck} />

        {matches.length > 0 && (
          <section>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-w-faint">Possible policy matches</h3>
            <ul className="space-y-1">
              {matches.map((v, i) => (
                <li key={i} className="flex items-center justify-between gap-2 rounded-md bg-w-surface2/60 px-2.5 py-1.5">
                  <span className="truncate text-w-text">{v.policy_title}</span>
                  <span className="shrink-0 text-[11px] text-w-faint">
                    {v.relevance}{v.confidence != null ? ` · ${Math.round(v.confidence * 100)}%` : ''}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-1.5 text-[11px] text-w-faint">These are matches for a person to review, not a finding.</p>
          </section>
        )}

        {hrCase.dismissed_reason && (
          <section>
            <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-w-faint">Dismissed</h3>
            <p className="text-w-dim">{hrCase.dismissed_reason}</p>
          </section>
        )}

        {hrCase.events && hrCase.events.length > 0 && (
          <section>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-w-faint">History</h3>
            <ol className="space-y-1.5 text-xs">
              {hrCase.events.map((ev, i) => (
                <li key={i} className="text-w-dim">
                  <span className="text-w-text">{EVENT_LABEL[ev.event] ?? ev.event.replace(/_/g, ' ')}</span>
                  {ev.actor_name && ` · ${ev.actor_name}`}
                  <span className="block text-[11px] text-w-faint">{when(ev.created_at)}</span>
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>

      {canDismiss && (
        <footer className="border-t border-w-line px-4 py-3">
          {dismissing ? (
            <form onSubmit={(e) => void submitDismiss(e)} className="space-y-2">
              <textarea
                autoFocus
                aria-label="Reason for dismissing"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
                placeholder="Why doesn't this need a write-up?"
                className="w-full rounded-md border border-w-line bg-w-surface2/60 px-3 py-2 text-sm text-w-text outline-none focus:border-w-accent/50"
              />
              {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => { setDismissing(false); setError(null) }} className="text-sm text-w-dim hover:text-w-text">Cancel</button>
                <button type="submit" disabled={saving} className="inline-flex items-center gap-1.5 rounded-lg bg-w-accent px-3 py-1.5 text-sm font-medium text-w-on-accent hover:bg-w-accent-hi disabled:opacity-50">
                  {saving && <Loader2 size={13} className="animate-spin" />} Dismiss case
                </button>
              </div>
            </form>
          ) : (
            <button type="button" onClick={() => setDismissing(true)} className="text-sm text-w-dim hover:text-w-text">
              Dismiss — no write-up needed
            </button>
          )}
        </footer>
      )}
    </aside>
  )
}
