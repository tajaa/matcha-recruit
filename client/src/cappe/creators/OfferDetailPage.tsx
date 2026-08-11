import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams, Link } from 'react-router-dom'
import {
  AlertTriangle, CheckCircle2, Loader2, MessageSquare, Send, ShieldCheck,
} from 'lucide-react'
import { cappeApi, CappeApiError } from '../api'
import { ui, badgeFor } from '../components/ui'
import { creatorPaths, creatorProfilePath } from './creatorPaths'
import StripeConnectCard from '../components/StripeConnectCard'
import TermSheet from './TermSheet'
import CounterSheet from './CounterSheet'
import { fmtCents, type CollabTerms, type DealCheckSeverity, type OfferDetail } from '../types'

function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

const DEAL_CHECK_COLOR: Record<DealCheckSeverity, string> = {
  good: 'border-emerald-500/30 bg-emerald-500/[0.06] text-emerald-300',
  caution: 'border-amber-500/30 bg-amber-500/[0.06] text-amber-200',
  warning: 'border-red-500/30 bg-red-500/[0.06] text-red-200',
}

export default function OfferDetailPage() {
  const { offerId } = useParams<{ offerId: string }>()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()

  const [offer, setOffer] = useState<OfferDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [showCounter, setShowCounter] = useState(false)
  const [payoutsBlocked, setPayoutsBlocked] = useState(false)
  const [message, setMessage] = useState('')
  const [justPaid, setJustPaid] = useState(params.get('paid') === '1')

  const load = useCallback(() => {
    if (!offerId) return
    return cappeApi.get<OfferDetail>(`/collab/offers/${offerId}`)
      .then((d) => { setOffer(d); setError(null) })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [offerId])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!justPaid) return
    const t = setTimeout(() => { load(); setJustPaid(false); const p = new URLSearchParams(params); p.delete('paid'); setParams(p, { replace: true }) }, 3000)
    return () => clearTimeout(t)
  }, [justPaid, load, params, setParams])

  async function act<T>(fn: () => Promise<T>) {
    setBusy(true)
    setError(null)
    try {
      await fn()
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <div className="flex items-center justify-center py-24"><Loader2 className="h-6 w-6 animate-spin text-zinc-600" /></div>
  if (!offer) return <div className="py-24 text-center text-sm text-zinc-500">{error || 'Offer not found.'}</div>

  const side = offer.side
  const isPreAccept = ['sent', 'negotiating'].includes(offer.status)
  // Once accepted, the terms in force are the accepted revision — not
  // necessarily the last row in the table, which a race between accept and
  // a concurrent counter could otherwise leave pointing at superseded terms.
  const acceptedIdx = offer.accepted_revision_id
    ? offer.revisions.findIndex((r) => r.id === offer.accepted_revision_id)
    : -1
  const latestRevisionIdx = acceptedIdx >= 0 ? acceptedIdx : offer.revisions.length - 1
  const latestRevision = offer.revisions[latestRevisionIdx]
  const previousRevision = offer.revisions[latestRevisionIdx - 1]
  const iAmProposer = latestRevision?.proposed_by === side
  const counterpartLabel = side === 'creator' ? (offer.brand_name || 'the brand') : `@${offer.creator_handle}`
  const onAcceptDue = offer.payments.find((p) => p.trigger === 'on_accept' && p.status === 'due')

  async function accept() {
    setPayoutsBlocked(false)
    await act(async () => {
      try {
        await cappeApi.post(`/collab/offers/${offerId}/accept`)
      } catch (e) {
        if (e instanceof CappeApiError && e.code === 'payouts_not_ready') {
          setPayoutsBlocked(true)
          throw new Error('Stripe payout setup is required before this offer can be accepted.')
        }
        throw e
      }
    })
  }

  async function decline() {
    const reason = window.prompt('Reason (optional):') ?? ''
    await act(() => cappeApi.post(`/collab/offers/${offerId}/decline`, { reason: reason || null }))
  }

  async function withdraw() {
    await act(() => cappeApi.post(`/collab/offers/${offerId}/withdraw`))
  }

  async function cancel() {
    const warning = side === 'brand'
      ? 'Cancel this collab? Any due or already-submitted work is still owed — those installments remain payable, and pending deliverables get approved and billed. Paid installments are not refunded automatically.'
      : "Cancel this collab? You'll forfeit any installments that haven't come due yet. Paid installments are not refunded automatically."
    if (!window.confirm(warning)) return
    const reason = window.prompt('Reason for cancelling:')
    if (!reason) return
    await act(() => cappeApi.post(`/collab/offers/${offerId}/cancel`, { reason }))
  }

  async function sendMessage() {
    if (!message.trim()) return
    const body = message.trim()
    setMessage('')
    await act(() => cappeApi.post(`/collab/offers/${offerId}/messages`, { body }))
  }

  async function submitCounter(terms: CollabTerms, counterMessage: string) {
    await act(() => cappeApi.post(`/collab/offers/${offerId}/counter`, { terms, message: counterMessage || null }))
    setShowCounter(false)
  }

  async function submitDeliverable(deliverableId: string, submissionUrl: string, note: string, proofMediaUrl: string | null) {
    await act(() => cappeApi.post(`/collab/offers/${offerId}/deliverables/${deliverableId}/submit`, {
      submission_url: submissionUrl, submission_note: note || null, proof_media_url: proofMediaUrl,
    }))
  }

  async function approveDeliverable(deliverableId: string) {
    await act(() => cappeApi.post(`/collab/offers/${offerId}/deliverables/${deliverableId}/approve`))
  }

  async function requestRevision(deliverableId: string) {
    const note = window.prompt('What needs to change?')
    if (!note) return
    await act(() => cappeApi.post(`/collab/offers/${offerId}/deliverables/${deliverableId}/request-revision`, { review_note: note }))
  }

  async function payNow(paymentId: string) {
    setBusy(true)
    try {
      const { url } = await cappeApi.post<{ url: string }>(`/collab/offers/${offerId}/payments/${paymentId}/checkout`)
      window.location.href = url
    } catch (e) {
      if (e instanceof CappeApiError && e.code === 'payouts_not_ready') {
        setPayoutsBlocked(true)
        setError("The creator hasn't finished their payout setup yet — check back once they have.")
      } else {
        setError(e instanceof Error ? e.message : 'Could not start checkout')
      }
      setBusy(false)
    }
  }

  async function nudge(paymentId: string) {
    await act(() => cappeApi.post(`/collab/offers/${offerId}/payments/${paymentId}/nudge`))
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      {justPaid && (
        <div className="mb-5 flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/[0.08] px-4 py-2.5 text-sm text-emerald-300">
          <CheckCircle2 className="h-4 w-4" /> Payment received — it can take a few seconds to reflect.
        </div>
      )}

      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className={ui.heading}>{offer.title}</h1>
            <span className={badgeFor(offer.status)}>{offer.status.replace('_', ' ')}</span>
          </div>
          <p className="mt-1 text-sm text-zinc-500">
            {side === 'creator' ? (
              <>with {offer.brand_name || 'a brand'}</>
            ) : (
              <>with <Link to={creatorProfilePath(offer.creator_handle)} className={ui.accentText}>@{offer.creator_handle}</Link></>
            )}
            {offer.total_cents != null && <> · {fmtCents(offer.total_cents)}</>}
          </p>
        </div>
        {error && <p className="max-w-xs text-right text-sm text-red-400">{error}</p>}
      </div>

      {offer.status === 'accepted' && onAcceptDue && side === 'creator' && (
        <div className="mb-5 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/[0.06] px-4 py-2.5 text-sm text-amber-200">
          <AlertTriangle className="h-4 w-4" /> Waiting for the brand to fund the first installment before work starts.
        </div>
      )}

      {side === 'creator' && offer.deal_check && offer.deal_check.length > 0 && (() => {
        const order: DealCheckSeverity[] = ['warning', 'caution', 'good']
        const grouped = order.map((sev) => offer.deal_check!.filter((i) => i.severity === sev)).flat()
        const reviewCount = offer.deal_check!.filter((i) => i.severity !== 'good').length
        return (
          <div className="mb-6">
            <div className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-zinc-200">
              <ShieldCheck className="h-4 w-4 text-emerald-400" /> Deal Check
              <span className="font-normal text-zinc-500">
                {reviewCount > 0
                  ? `— ${reviewCount} thing${reviewCount === 1 ? '' : 's'} to review before accepting`
                  : '— looks good'}
              </span>
            </div>
            <div className="space-y-1.5">
              {grouped.map((item) => (
                <div key={item.key} className={`rounded-lg border px-3 py-2 text-sm ${DEAL_CHECK_COLOR[item.severity]}`}>
                  <p className="font-medium">{item.title}</p>
                  <p className="mt-0.5 opacity-90">{item.detail}</p>
                </div>
              ))}
            </div>
          </div>
        )
      })()}

      {side === 'creator' && offer.brand_stats && (
        <div className={`${ui.card} mb-6 flex flex-wrap gap-x-6 gap-y-1 px-4 py-3 text-sm`}>
          <span className="text-zinc-500">Brand track record:</span>
          {offer.brand_stats.completed_collabs === 0 ? (
            <span className="text-zinc-300">New brand — first collab on Gummfit</span>
          ) : (
            <>
              <span className="text-zinc-300">{offer.brand_stats.completed_collabs} completed</span>
              <span className="text-zinc-300">{offer.brand_stats.in_progress} in progress</span>
              <span className="text-zinc-300">{offer.brand_stats.brand_cancelled} cancelled</span>
              {offer.brand_stats.avg_hours_to_pay != null && (
                <span className="text-zinc-300">avg {Math.round(offer.brand_stats.avg_hours_to_pay)}h to pay</span>
              )}
            </>
          )}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <section className={`${ui.card} p-5 lg:col-span-1`}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Terms</h2>
          {latestRevision && <TermSheet terms={latestRevision.terms} previous={previousRevision?.terms} />}

          {payoutsBlocked && side === 'creator' && <div className="mt-3"><StripeConnectCard /></div>}
          {payoutsBlocked && side === 'brand' && (
            <div className={`mt-3 rounded-lg border border-amber-500/30 bg-amber-500/[0.06] p-3 text-sm text-amber-200`}>
              The creator hasn't finished their Stripe payout setup yet — this offer can't be {isPreAccept ? 'accepted' : 'paid'} until they do.
            </div>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            {isPreAccept && !iAmProposer && (
              <button onClick={accept} disabled={busy} className={ui.btnPrimary}>
                {busy && <Loader2 className="h-4 w-4 animate-spin" />} Accept
              </button>
            )}
            {isPreAccept && (
              <button onClick={() => setShowCounter(true)} disabled={busy} className={ui.btnGhost}>Counter</button>
            )}
            {isPreAccept && side === 'creator' && (
              <button onClick={decline} disabled={busy} className={`${ui.btnGhost} ${ui.danger}`}>Decline</button>
            )}
            {isPreAccept && side === 'brand' && (
              <button onClick={withdraw} disabled={busy} className={`${ui.btnGhost} ${ui.danger}`}>Withdraw</button>
            )}
            {(offer.status === 'accepted' || offer.status === 'active') && (
              <button onClick={cancel} disabled={busy} className={`${ui.btnGhost} ${ui.danger}`}>Cancel</button>
            )}
          </div>

          {offer.revisions.length > 1 && (
            <details className="mt-4 text-xs text-zinc-500">
              <summary className="cursor-pointer">Revision history ({offer.revisions.length})</summary>
              <ul className="mt-2 space-y-1">
                {offer.revisions.map((r) => (
                  <li key={r.id}>rev {r.revision_no} by {r.proposed_by} — {new Date(r.created_at).toLocaleString()}{r.message ? `: "${r.message}"` : ''}</li>
                ))}
              </ul>
            </details>
          )}
        </section>

        <section className={`${ui.card} p-5 lg:col-span-1`}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Deliverables</h2>
          <div className="space-y-3">
            {offer.deliverables.map((d) => (
              <div key={d.id} className="rounded-lg border border-zinc-800 p-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-zinc-200">{d.type} · {d.platform}{d.due_date ? ` · due ${d.due_date}` : ''}</p>
                  <span className={badgeFor(d.status)}>{d.status.replace('_', ' ')}</span>
                </div>
                {d.spec && <p className="mt-1 text-xs text-zinc-500">{d.spec}</p>}
                {d.status === 'submitted' && d.submitted_at && (
                  <p className="mt-1 text-xs text-zinc-500">
                    Auto-approves {new Date(new Date(d.submitted_at).getTime() + offer.auto_approve_days * 86_400_000).toLocaleDateString()}
                  </p>
                )}
                {d.review_note && d.status === 'revision_requested' && (
                  <p className="mt-1.5 rounded bg-orange-500/10 px-2 py-1 text-xs text-orange-300">{d.review_note}</p>
                )}
                {d.submission_url && (
                  <a href={d.submission_url} target="_blank" rel="noopener noreferrer" className="mt-1.5 block truncate text-xs text-emerald-400 hover:text-emerald-300">{d.submission_url}</a>
                )}

                {side === 'creator' && ['pending', 'revision_requested'].includes(d.status) && (
                  <DeliverableSubmitForm onSubmit={(url, note, proofMediaUrl) => submitDeliverable(d.id, url, note, proofMediaUrl)} busy={busy} />
                )}
                {side === 'brand' && d.status === 'submitted' && (
                  <div className="mt-2 flex gap-2">
                    <button onClick={() => approveDeliverable(d.id)} disabled={busy} className={`${ui.btnPrimary} px-3 py-1.5 text-xs`}>Approve</button>
                    <button
                      onClick={() => requestRevision(d.id)}
                      disabled={busy || (latestRevision && d.revision_count >= latestRevision.terms.revision_rounds)}
                      title={latestRevision && d.revision_count >= latestRevision.terms.revision_rounds ? 'Revision limit reached' : undefined}
                      className={`${ui.btnGhost} px-3 py-1.5 text-xs`}
                    >
                      Request changes
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        <section className={`${ui.card} p-5 lg:col-span-1`}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Payments</h2>
          <div className="space-y-2">
            {offer.payments.length === 0 && <p className="text-sm text-zinc-500">Gifting collab — no payments.</p>}
            {offer.payments.map((p) => {
              const daysOverdue = p.due_at ? (Date.now() - new Date(p.due_at).getTime()) / 86_400_000 : 0
              const isOverdue = ['due', 'processing'].includes(p.status) && daysOverdue > 3
              return (
                <div key={p.id} className={`rounded-lg border p-3 text-sm ${isOverdue ? 'border-amber-500/40 bg-amber-500/[0.04]' : 'border-zinc-800'}`}>
                  <div className="flex items-center justify-between">
                    <p className="font-medium text-zinc-200">{p.label}</p>
                    <span className={badgeFor(p.status)}>{p.status}</span>
                  </div>
                  <p className="mt-0.5 text-zinc-400">{fmtCents(p.amount_cents)}</p>
                  {p.status === 'paid' && p.fee_cents != null && side === 'creator' && (
                    <p className="mt-0.5 text-xs text-zinc-500">Gummfit fee {fmtCents(p.fee_cents)}</p>
                  )}
                  {p.paid_at && <p className="mt-0.5 text-xs text-zinc-500">Paid {new Date(p.paid_at).toLocaleDateString()}</p>}
                  {isOverdue && <p className="mt-0.5 text-xs font-medium text-amber-400">{Math.floor(daysOverdue)}d overdue</p>}
                  {side === 'brand' && ['due', 'processing'].includes(p.status) && (
                    <button onClick={() => payNow(p.id)} disabled={busy} className={`${ui.btnPrimary} mt-2 px-3 py-1.5 text-xs`}>Pay</button>
                  )}
                  {side === 'creator' && isOverdue && (
                    <button onClick={() => nudge(p.id)} disabled={busy} className={`${ui.btnGhost} mt-2 px-3 py-1.5 text-xs`}>Remind brand</button>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      </div>

      <section className={`${ui.card} mt-6 p-5`}>
        <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-zinc-500">
          <MessageSquare className="h-4 w-4" /> Conversation
        </h2>
        <div className="mb-3 max-h-72 space-y-2 overflow-y-auto">
          {offer.messages.map((m) => (
            <div key={m.id} className={`max-w-[75%] rounded-lg px-3 py-2 text-sm ${m.sender === side ? 'ml-auto bg-emerald-500/15 text-emerald-100' : 'bg-zinc-800 text-zinc-200'}`}>
              <p>{m.body}</p>
              {m.revision_id && <p className="mt-1 text-[11px] opacity-70">proposed new terms</p>}
              <p className="mt-1 text-[10px] opacity-50">{timeAgo(m.created_at)}</p>
            </div>
          ))}
          {offer.messages.length === 0 && <p className="text-sm text-zinc-500">No messages yet.</p>}
        </div>
        {['sent', 'negotiating', 'accepted', 'active'].includes(offer.status) ? (
          <div className="flex gap-2">
            <input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') sendMessage() }}
              placeholder={`Message ${counterpartLabel}…`}
              className={ui.input}
            />
            <button onClick={sendMessage} disabled={busy || !message.trim()} className={ui.btnPrimary}>
              <Send className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <p className="text-sm text-zinc-500">Conversation closed.</p>
        )}
      </section>

      {showCounter && latestRevision && (
        <CounterSheet
          initialTerms={latestRevision.terms}
          onClose={() => setShowCounter(false)}
          onSubmit={submitCounter}
        />
      )}

      <div className="mt-6 text-center">
        <button onClick={() => navigate(side === 'creator' ? creatorPaths.deals : creatorPaths.brandCollabs)} className="text-xs text-zinc-600 hover:text-zinc-400">
          &larr; Back to {side === 'creator' ? 'deals' : 'collabs'}
        </button>
      </div>
    </div>
  )
}

function DeliverableSubmitForm({
  onSubmit, busy,
}: { onSubmit: (url: string, note: string, proofMediaUrl: string | null) => void; busy: boolean }) {
  const [url, setUrl] = useState('')
  const [note, setNote] = useState('')
  const [proofMediaUrl, setProofMediaUrl] = useState<string | null>(null)
  const [proofFileName, setProofFileName] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  async function handleFile(file: File) {
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await cappeApi.upload<{ url: string }>('/creators/me/upload', fd)
      setProofMediaUrl(res.url)
      setProofFileName(file.name)
    } catch (e) {
      setProofMediaUrl(null)
      setProofFileName(null)
      window.alert(e instanceof Error ? e.message : 'Could not upload proof')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="mt-2 space-y-1.5">
      <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Link to the post/content" className={`${ui.input} text-xs`} />
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)" className={`${ui.input} text-xs`} />
      <input
        ref={fileInput} type="file" accept="image/*,video/*" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
      />
      <button
        type="button" onClick={() => fileInput.current?.click()} disabled={uploading}
        className={`${ui.btnGhost} px-3 py-1.5 text-xs`}
      >
        {uploading ? 'Uploading…' : proofFileName ? `Proof: ${proofFileName}` : 'Attach proof (optional)'}
      </button>
      <button
        onClick={() => { if (url.trim()) { onSubmit(url.trim(), note.trim(), proofMediaUrl); setUrl(''); setNote(''); setProofMediaUrl(null); setProofFileName(null) } }}
        disabled={busy || uploading || !url.trim()}
        className={`${ui.btnPrimary} px-3 py-1.5 text-xs`}
      >
        Submit
      </button>
    </div>
  )
}
