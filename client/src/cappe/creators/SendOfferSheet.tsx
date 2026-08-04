import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Plus, Trash2, X } from 'lucide-react'
import { cappeApi } from '../api'
import { ui } from '../components/ui'
import {
  DELIVERABLE_TYPES, PAYMENT_SCHEDULES, SOCIAL_PLATFORMS, fmtCents,
  type Campaign, type CollabTerms, type OfferDetail, type PaymentSchedule,
  type PublicCreatorProfile, type TermsDeliverable,
} from '../types'

type DeliverableRow = TermsDeliverable

function emptyDeliverable(): DeliverableRow {
  return { type: 'post', platform: 'instagram', quantity: 1, spec: null, due_date: null }
}

/** Mirrors services/collab.py:build_payment_rows exactly — first = floor for
 * 50/50, per_deliverable's last row absorbs the remainder — so the brand
 * sees the exact split the backend will materialize on accept. */
function previewInstallments(totalCents: number, schedule: PaymentSchedule, deliverableCount: number) {
  if (totalCents <= 0) return [] as { label: string; amount_cents: number }[]
  if (schedule === 'upfront') return [{ label: 'Full payment', amount_cents: totalCents }]
  if (schedule === 'split_50_50') {
    const first = Math.floor(totalCents / 2)
    return [
      { label: '50% on acceptance', amount_cents: first },
      { label: '50% on completion', amount_cents: totalCents - first },
    ]
  }
  const n = Math.max(1, deliverableCount)
  const base = Math.floor(totalCents / n)
  return Array.from({ length: n }, (_, i) => ({
    label: `Deliverable ${i + 1} of ${n}`,
    amount_cents: i < n - 1 ? base : totalCents - base * (n - 1),
  }))
}

export default function SendOfferSheet({ profile, onClose, onSent }: {
  profile: PublicCreatorProfile
  onClose: () => void
  onSent: (offerId: string) => void
}) {
  const navigate = useNavigate()
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [campaignId, setCampaignId] = useState<string>('')
  const [newCampaignTitle, setNewCampaignTitle] = useState('')
  const [creatingCampaign, setCreatingCampaign] = useState(false)

  const [title, setTitle] = useState(`Collab with ${profile.display_name}`)
  const [message, setMessage] = useState('')
  const [deliverables, setDeliverables] = useState<DeliverableRow[]>([emptyDeliverable()])
  const [compDollars, setCompDollars] = useState('')
  const [schedule, setSchedule] = useState<PaymentSchedule>('split_50_50')
  const [scope, setScope] = useState<'organic' | 'paid'>('organic')
  const [usageMonths, setUsageMonths] = useState('3')
  const [whitelisting, setWhitelisting] = useState(false)
  const [exclusive, setExclusive] = useState(false)
  const [exclusiveCategory, setExclusiveCategory] = useState('')
  const [exclusiveMonths, setExclusiveMonths] = useState('3')
  const [revisionRounds, setRevisionRounds] = useState('1')
  const [approvalRequired, setApprovalRequired] = useState(true)
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [notes, setNotes] = useState('')

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    cappeApi.get<Campaign[]>('/collab/campaigns').then(setCampaigns).catch(() => setCampaigns([]))
  }, [])

  async function createCampaign() {
    if (!newCampaignTitle.trim()) return
    setCreatingCampaign(true)
    try {
      const c = await cappeApi.post<Campaign>('/collab/campaigns', { title: newCampaignTitle.trim() })
      setCampaigns((prev) => [c, ...prev])
      setCampaignId(c.id)
      setNewCampaignTitle('')
    } catch {
      // inline campaign create is a convenience — a failure just leaves the field open
    } finally {
      setCreatingCampaign(false)
    }
  }

  function updateDeliverable(i: number, patch: Partial<DeliverableRow>) {
    setDeliverables((prev) => prev.map((d, idx) => (idx === i ? { ...d, ...patch } : d)))
  }

  function addRateCardDeliverable(rate: PublicCreatorProfile['rates'][number]) {
    setDeliverables((prev) => [
      ...prev,
      { type: rate.deliverable_type, platform: rate.platform, quantity: 1, spec: null, due_date: null },
    ])
    setCompDollars((prev) => {
      const current = prev ? Math.round(parseFloat(prev) * 100) : 0
      return (((current + rate.price_cents) / 100)).toString()
    })
  }

  const totalCents = compDollars ? Math.round(parseFloat(compDollars) * 100) : 0
  const deliverableCount = deliverables.reduce((n, d) => n + (d.quantity || 0), 0)
  const installments = previewInstallments(totalCents, schedule, deliverableCount)

  async function submit() {
    setError(null)
    if (!title.trim()) { setError('Title is required'); return }
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
      start_date: startDate || null,
      end_date: endDate || null,
      notes: notes.trim() || null,
    }

    setSubmitting(true)
    try {
      const offer = await cappeApi.post<OfferDetail>('/collab/offers', {
        creator_profile_id: profile.id,
        campaign_id: campaignId || null,
        title: title.trim(),
        terms,
        message: message.trim() || null,
      })
      onSent(offer.id)
      navigate(`/cappe/collabs/${offer.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not send the offer')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60" onClick={onClose}>
      <div className="flex h-full w-full max-w-2xl flex-col overflow-y-auto border-l border-zinc-800 bg-zinc-950 p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-5 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-zinc-50">Send an offer</h2>
            <p className="mt-0.5 text-sm text-zinc-400">to {profile.display_name} (@{profile.handle})</p>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200"><X className="h-5 w-5" /></button>
        </div>

        <div className="grid gap-5 lg:grid-cols-[1fr_240px]">
          <div className="space-y-5">
            <div>
              <label className={ui.label}>Title</label>
              <input value={title} onChange={(e) => setTitle(e.target.value)} className={ui.input} />
            </div>

            <div>
              <label className={ui.label}>Campaign (optional)</label>
              <div className="flex gap-2">
                <select value={campaignId} onChange={(e) => setCampaignId(e.target.value)} className={ui.input}>
                  <option value="">No campaign</option>
                  {campaigns.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
                </select>
              </div>
              <div className="mt-2 flex gap-2">
                <input value={newCampaignTitle} onChange={(e) => setNewCampaignTitle(e.target.value)} placeholder="New campaign title" className={ui.input} />
                <button type="button" onClick={createCampaign} disabled={creatingCampaign} className={ui.btnGhost}>
                  {creatingCampaign ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <div>
              <label className={ui.label}>Deliverables</label>
              <div className="space-y-2">
                {deliverables.map((d, i) => (
                  <div key={i} className="rounded-lg border border-zinc-800 p-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <select value={d.type} onChange={(e) => updateDeliverable(i, { type: e.target.value })} className={`${ui.input} w-auto`}>
                        {DELIVERABLE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                      <select value={d.platform} onChange={(e) => updateDeliverable(i, { platform: e.target.value })} className={`${ui.input} w-auto`}>
                        {SOCIAL_PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
                      </select>
                      <input type="number" min={1} max={20} value={d.quantity} onChange={(e) => updateDeliverable(i, { quantity: Number(e.target.value) || 1 })} className={`${ui.input} w-16`} />
                      <input type="date" value={d.due_date ?? ''} onChange={(e) => updateDeliverable(i, { due_date: e.target.value || null })} className={`${ui.input} w-auto`} />
                      <button type="button" onClick={() => setDeliverables((prev) => prev.filter((_, idx) => idx !== i))} className="ml-auto text-zinc-500 hover:text-red-400">
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                    <input
                      type="text"
                      value={d.spec ?? ''}
                      onChange={(e) => updateDeliverable(i, { spec: e.target.value || null })}
                      placeholder="Spec / brief (optional)"
                      maxLength={2000}
                      className={`${ui.input} mt-2 w-full`}
                    />
                  </div>
                ))}
              </div>
              <button type="button" onClick={() => setDeliverables((prev) => [...prev, emptyDeliverable()])} className={`${ui.btnGhost} mt-2`}>
                <Plus className="h-4 w-4" /> Add deliverable
              </button>
            </div>

            <div>
              <label className={ui.label}>Compensation ($)</label>
              <input type="number" min={0} step="0.01" value={compDollars} onChange={(e) => setCompDollars(e.target.value)} placeholder="0 for gifting" className={ui.input} />
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
              {installments.length > 0 && (
                <p className="mt-2 text-xs text-zinc-500">
                  {installments.map((p) => `${fmtCents(p.amount_cents)} (${p.label})`).join(' · ')}
                </p>
              )}
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
                  <input value={exclusiveCategory} onChange={(e) => setExclusiveCategory(e.target.value)} placeholder="Category (e.g. skincare)" className={ui.input} />
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
              <div className="flex items-end gap-4 pb-2 text-sm">
                <label className="flex items-center gap-1.5 text-zinc-300">
                  <input type="checkbox" checked={approvalRequired} onChange={(e) => setApprovalRequired(e.target.checked)} /> Approval required
                </label>
              </div>
            </div>
            <p className="text-xs text-zinc-500">FTC disclosure is always required and can't be waived.</p>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={ui.label}>Start date</label>
                <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className={ui.input} />
              </div>
              <div>
                <label className={ui.label}>End date</label>
                <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className={ui.input} />
              </div>
            </div>

            <div>
              <label className={ui.label}>Notes</label>
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className={ui.input} />
            </div>

            <div>
              <label className={ui.label}>Message to {profile.display_name}</label>
              <textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={3} className={ui.input} placeholder="Say hi and set the context…" />
            </div>

            {error && <p className="text-sm text-red-400">{error}</p>}

            <button onClick={submit} disabled={submitting} className={`${ui.btnPrimary} w-full`}>
              {submitting && <Loader2 className="h-4 w-4 animate-spin" />} Send offer
            </button>
          </div>

          <div className={`${ui.card} h-fit p-4`}>
            <h3 className="mb-2 text-sm font-semibold text-zinc-200">Their rates</h3>
            {profile.rates.length === 0 ? (
              <p className="text-xs text-zinc-500">No rate card published.</p>
            ) : (
              <ul className="space-y-1.5">
                {profile.rates.map((r) => (
                  <li key={r.id}>
                    <button type="button" onClick={() => addRateCardDeliverable(r)} className="flex w-full items-center justify-between rounded-lg border border-zinc-800 px-2 py-1.5 text-left text-xs hover:border-zinc-600">
                      <span className="text-zinc-300">{r.deliverable_type} · {r.platform}</span>
                      <span className="text-zinc-500">{fmtCents(r.price_cents)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
