import { useState } from 'react'
import { AlertTriangle, FileText, Loader2 } from 'lucide-react'
import type { HrCase, HrCaseReviewItem } from '../../../types'

const SOURCE_LABEL: Record<HrCaseReviewItem['source'], string> = {
  compliance: 'Leave and retaliation check',
  ladder: 'Discipline history',
  structure: 'Letter structure',
  ai: 'Wording review',
}

const ACTION_LABEL: Record<string, string> = {
  verbal_warning: 'Verbal warning', written_warning: 'Written warning', final_warning: 'Final warning',
  suspension: 'Suspension', pip: 'PIP', other: 'Other action',
}

function today(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

interface Props {
  hrCase: HrCase
  onOpenDraft: () => Promise<void>
  onDecide: (decision: 'approve' | 'request_changes', reason: string) => Promise<void>
  onDelivered: (deliveredOn: string) => Promise<void>
}

export default function HrCaseReviewSection({ hrCase, onOpenDraft, onDecide, onDelivered }: Props) {
  const [mode, setMode] = useState<'idle' | 'approve' | 'changes'>('idle')
  const [note, setNote] = useState('')
  const [deliveredOn, setDeliveredOn] = useState(today)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const review = hrCase.review
  const canDecide = hrCase.allowed_events.includes('approve')
  const canDeliver = hrCase.allowed_events.includes('delivered')

  async function run(action: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      setMode('idle')
      setNote('')
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'That didn’t work — try again.')
    } finally {
      setBusy(false)
    }
  }

  if (!review && !hrCase.draft_file_id && !canDeliver) return null

  const groups = (['compliance', 'ladder', 'structure', 'ai'] as const)
    .map((source) => ({ source, items: (review?.advisories ?? []).filter((a) => a.source === source) }))
    .filter((g) => g.items.length > 0)

  return (
    <section className="space-y-3">
      <h3 className="text-xs font-medium uppercase tracking-wide text-w-faint">Write-up</h3>
      {(hrCase.action_type || review?.input) && (
        <p className="text-xs text-w-dim">
          {ACTION_LABEL[hrCase.action_type ?? ''] ?? 'Action'}
          {review?.input?.infraction_type && ` · ${review.input.infraction_type.replace(/_/g, ' ')}`}
          {review?.input?.occurrence_dates?.length ? ` · ${review.input.occurrence_dates.join(', ')}` : ''}
        </p>
      )}
      {hrCase.draft_file_id && (
        <button type="button" onClick={() => void run(onOpenDraft)} className="inline-flex items-center gap-1.5 text-sm text-w-accent hover:underline">
          <FileText size={13} /> Open the draft
        </button>
      )}

      {review && review.blocks.length > 0 && (
        <div role="alert" className="space-y-1 rounded-lg border border-red-500/30 bg-red-500/10 p-2.5 text-xs text-red-200">
          <p className="flex items-center gap-1.5 font-medium"><AlertTriangle size={13} /> Can’t be approved as written</p>
          {review.blocks.map((b, i) => <p key={i}>{b.detail}</p>)}
        </div>
      )}

      {groups.map((g) => (
        <div key={g.source} className="space-y-1">
          <p className="text-[11px] font-medium text-w-dim">{SOURCE_LABEL[g.source]}</p>
          <ul className="space-y-1">
            {g.items.map((a, i) => <li key={i} className="rounded-md bg-w-surface2/60 px-2.5 py-1.5 text-xs text-w-text">{a.detail}</li>)}
          </ul>
        </div>
      ))}
      {review && review.blocks.length === 0 && groups.length === 0 && (
        <p className="text-xs text-emerald-300">No issues found in the review.</p>
      )}

      {hrCase.decision === 'changes_requested' && hrCase.decision_reason && (
        <p className="text-xs text-w-dim">Sent back: <span className="text-w-text">{hrCase.decision_reason}</span></p>
      )}

      {canDecide && (
        mode === 'idle' ? (
          <div className="flex gap-2">
            <button type="button" onClick={() => setMode('approve')} className="rounded-lg bg-w-accent px-3 py-1.5 text-sm font-medium text-w-on-accent hover:bg-w-accent-hi">Approve to deliver</button>
            <button type="button" onClick={() => setMode('changes')} className="rounded-lg border border-w-line px-3 py-1.5 text-sm text-w-dim hover:text-w-text">Request changes</button>
          </div>
        ) : (
          <div className="space-y-2">
            <textarea
              autoFocus
              aria-label={mode === 'approve' ? 'Approval note' : 'What should change'}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              placeholder={mode === 'approve' ? 'Optional note for the file' : 'Tell the manager what to change'}
              className="w-full rounded-md border border-w-line bg-w-surface2/60 px-3 py-2 text-sm text-w-text outline-none focus:border-w-accent/50"
            />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => { setMode('idle'); setError(null) }} className="text-sm text-w-dim hover:text-w-text">Cancel</button>
              <button
                type="button"
                disabled={busy || (mode === 'changes' && note.trim().length < 20)}
                onClick={() => void run(() => onDecide(mode === 'approve' ? 'approve' : 'request_changes', note.trim()))}
                className="inline-flex items-center gap-1.5 rounded-lg bg-w-accent px-3 py-1.5 text-sm font-medium text-w-on-accent hover:bg-w-accent-hi disabled:opacity-50"
              >
                {busy && <Loader2 size={13} className="animate-spin" />}
                {mode === 'approve' ? 'Approve' : 'Send back'}
              </button>
            </div>
          </div>
        )
      )}

      {canDeliver && (
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs text-w-dim" htmlFor="hr-delivered-on">Delivered on</label>
          <input
            id="hr-delivered-on"
            type="date"
            value={deliveredOn}
            max={today()}
            onChange={(e) => setDeliveredOn(e.target.value)}
            className="rounded-md border border-w-line bg-w-surface2/60 px-2 py-1 text-sm text-w-text"
          />
          <button
            type="button"
            disabled={busy || !deliveredOn}
            onClick={() => void run(() => onDelivered(deliveredOn))}
            className="rounded-lg border border-w-line px-3 py-1 text-sm text-w-dim hover:text-w-text disabled:opacity-50"
          >
            Mark delivered
          </button>
        </div>
      )}
      {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
    </section>
  )
}
