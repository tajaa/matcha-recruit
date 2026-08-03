import { useState } from 'react'
import { Loader2, Plus, Trash2, X } from 'lucide-react'
import { ui } from '../components/ui'
import {
  DELIVERABLE_TYPES, PAYMENT_SCHEDULES, SOCIAL_PLATFORMS,
  type CollabTerms, type PaymentSchedule, type TermsDeliverable,
} from '../types'

// Counter-offer form — same terms shape as SendOfferSheet, seeded from the
// latest revision's terms. POSTs to /collab/offers/{id}/counter (caller owns
// the request; this component only builds the terms object).
export default function CounterSheet({ initialTerms, onClose, onSubmit }: {
  initialTerms: CollabTerms
  onClose: () => void
  onSubmit: (terms: CollabTerms, message: string) => void | Promise<void>
}) {
  const [compDollars, setCompDollars] = useState(String(initialTerms.compensation_cents / 100))
  const [schedule, setSchedule] = useState<PaymentSchedule>(initialTerms.payment_schedule)
  const [deliverables, setDeliverables] = useState<TermsDeliverable[]>(initialTerms.deliverables)
  const [scope, setScope] = useState<'organic' | 'paid'>(initialTerms.usage_rights.scope)
  const [usageMonths, setUsageMonths] = useState(String(initialTerms.usage_rights.duration_months ?? 3))
  const [whitelisting, setWhitelisting] = useState(initialTerms.usage_rights.whitelisting)
  const [exclusive, setExclusive] = useState(!!initialTerms.exclusivity)
  const [exclusiveCategory, setExclusiveCategory] = useState(initialTerms.exclusivity?.category ?? '')
  const [exclusiveMonths, setExclusiveMonths] = useState(String(initialTerms.exclusivity?.duration_months ?? 3))
  const [revisionRounds, setRevisionRounds] = useState(String(initialTerms.revision_rounds))
  const [approvalRequired, setApprovalRequired] = useState(initialTerms.approval_required)
  const [notes, setNotes] = useState(initialTerms.notes ?? '')
  const [message, setMessage] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function updateDeliverable(i: number, patch: Partial<TermsDeliverable>) {
    setDeliverables((prev) => prev.map((d, idx) => (idx === i ? { ...d, ...patch } : d)))
  }

  async function submit() {
    setError(null)
    const totalCents = compDollars ? Math.round(parseFloat(compDollars) * 100) : 0
    if (deliverables.length === 0) { setError('Add at least one deliverable'); return }
    if (exclusive && !exclusiveCategory.trim()) { setError('Exclusivity needs a category'); return }
    if (exclusive && totalCents <= 0) { setError('Exclusivity requires compensation > 0'); return }

    const terms: CollabTerms = {
      compensation_cents: totalCents,
      payment_schedule: schedule,
      deliverables,
      usage_rights: {
        scope,
        duration_months: scope === 'paid' ? Number(usageMonths) || 1 : null,
        whitelisting: scope === 'paid' ? whitelisting : false,
      },
      exclusivity: exclusive ? { category: exclusiveCategory.trim(), duration_months: Number(exclusiveMonths) || 1 } : null,
      revision_rounds: Number(revisionRounds) || 0,
      approval_required: approvalRequired,
      ftc_disclosure: true,
      start_date: initialTerms.start_date,
      end_date: initialTerms.end_date,
      notes: notes.trim() || null,
    }
    setSubmitting(true)
    try {
      await onSubmit(terms, message.trim())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not send counter')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60" onClick={onClose}>
      <div className="flex h-full w-full max-w-lg flex-col overflow-y-auto border-l border-zinc-800 bg-zinc-950 p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-5 flex items-start justify-between">
          <h2 className="text-lg font-semibold text-zinc-50">Propose new terms</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200"><X className="h-5 w-5" /></button>
        </div>

        <div className="space-y-5">
          <div>
            <label className={ui.label}>Deliverables</label>
            <div className="space-y-2">
              {deliverables.map((d, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2 rounded-lg border border-zinc-800 p-2">
                  <select value={d.type} onChange={(e) => updateDeliverable(i, { type: e.target.value })} className={`${ui.input} w-auto`}>
                    {DELIVERABLE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <select value={d.platform} onChange={(e) => updateDeliverable(i, { platform: e.target.value })} className={`${ui.input} w-auto`}>
                    {SOCIAL_PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                  <input type="number" min={1} max={20} value={d.quantity} onChange={(e) => updateDeliverable(i, { quantity: Number(e.target.value) || 1 })} className={`${ui.input} w-16`} />
                  <button type="button" onClick={() => setDeliverables((prev) => prev.filter((_, idx) => idx !== i))} className="ml-auto text-zinc-500 hover:text-red-400">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
            <button type="button" onClick={() => setDeliverables((prev) => [...prev, { type: 'post', platform: 'instagram', quantity: 1, spec: null, due_date: null }])} className={`${ui.btnGhost} mt-2`}>
              <Plus className="h-4 w-4" /> Add deliverable
            </button>
          </div>

          <div>
            <label className={ui.label}>Compensation ($)</label>
            <input type="number" min={0} step="0.01" value={compDollars} onChange={(e) => setCompDollars(e.target.value)} className={ui.input} />
          </div>

          <div>
            <label className={ui.label}>Payment schedule</label>
            <div className="space-y-1.5">
              {PAYMENT_SCHEDULES.map((s) => (
                <label key={s.value} className="flex items-start gap-2 rounded-lg border border-zinc-800 p-2 text-sm">
                  <input type="radio" checked={schedule === s.value} onChange={() => setSchedule(s.value)} className="mt-0.5" />
                  <span><span className="font-medium text-zinc-200">{s.label}</span> — <span className="text-zinc-500">{s.blurb}</span></span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <label className={ui.label}>Usage rights</label>
            <div className="flex items-center gap-4 text-sm">
              <label className="flex items-center gap-1.5"><input type="radio" checked={scope === 'organic'} onChange={() => setScope('organic')} /> Organic only</label>
              <label className="flex items-center gap-1.5"><input type="radio" checked={scope === 'paid'} onChange={() => setScope('paid')} /> Paid usage</label>
            </div>
            {scope === 'paid' && (
              <div className="mt-2 flex items-center gap-3">
                <input type="number" min={1} max={24} value={usageMonths} onChange={(e) => setUsageMonths(e.target.value)} className={`${ui.input} w-20`} />
                <span className="text-sm text-zinc-500">months (max 24)</span>
                <label className="flex items-center gap-1.5 text-sm text-zinc-400">
                  <input type="checkbox" checked={whitelisting} onChange={(e) => setWhitelisting(e.target.checked)} /> Whitelisting / ads
                </label>
              </div>
            )}
          </div>

          <div>
            <label className="flex items-center gap-1.5 text-sm text-zinc-300">
              <input type="checkbox" checked={exclusive} onChange={(e) => setExclusive(e.target.checked)} /> Category exclusivity
            </label>
            {exclusive && (
              <div className="mt-2 flex items-center gap-2">
                <input value={exclusiveCategory} onChange={(e) => setExclusiveCategory(e.target.value)} placeholder="Category" className={ui.input} />
                <input type="number" min={1} max={12} value={exclusiveMonths} onChange={(e) => setExclusiveMonths(e.target.value)} className={`${ui.input} w-20`} />
                <span className="text-sm text-zinc-500">months (max 12)</span>
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={ui.label}>Revision rounds</label>
              <select value={revisionRounds} onChange={(e) => setRevisionRounds(e.target.value)} className={ui.input}>
                {[0, 1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <label className="flex items-end gap-1.5 pb-2 text-sm text-zinc-300">
              <input type="checkbox" checked={approvalRequired} onChange={(e) => setApprovalRequired(e.target.checked)} /> Approval required
            </label>
          </div>

          <div>
            <label className={ui.label}>Notes</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className={ui.input} />
          </div>

          <div>
            <label className={ui.label}>Message</label>
            <textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={2} className={ui.input} placeholder="Explain the change…" />
          </div>

          {error && <p className="text-sm text-red-400">{error}</p>}

          <button onClick={submit} disabled={submitting} className={`${ui.btnPrimary} w-full`}>
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />} Send counter
          </button>
        </div>
      </div>
    </div>
  )
}
