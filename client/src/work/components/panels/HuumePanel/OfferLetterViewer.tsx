import { useCallback, useEffect, useState } from 'react'
import { Loader2, RotateCw } from 'lucide-react'
import { getOfferLetter, getOfferLetterPreviewHtml } from '../../../api/offerLetters'
import type { HuumeOffer, OfferLetterDetail } from '../../../types'

interface OfferLetterViewerProps {
  offerId: string
  /** Drives the refetch — an accept/decline on the candidate page updates
   * `huume_offer.status`/`.event` in current_state, and the letter itself
   * (signature block) changes once that happens. */
  offer?: HuumeOffer
  lightMode?: boolean
}

const STATUS_LABEL: Record<string, string> = {
  draft: 'Draft', sent: 'Sent — awaiting response', accepted: 'Accepted', rejected: 'Declined', expired: 'Expired',
}

function Field({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide opacity-50">{label}</div>
      <div className="text-xs">{value}</div>
    </div>
  )
}

/** Renders the offer letter as the real document — the same HTML the PDF and
 * the candidate signing page produce (GET /offer-letters/{id}/preview) — in
 * a sandboxed iframe, plus a terms strip above it. This is the fix for the
 * panel that used to show only a raw offer UUID and a Confirm button. */
export default function OfferLetterViewer({ offerId, offer, lightMode }: OfferLetterViewerProps) {
  const [detail, setDetail] = useState<OfferLetterDetail | null>(null)
  const [html, setHtml] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retryNonce, setRetryNonce] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [d, h] = await Promise.all([getOfferLetter(offerId), getOfferLetterPreviewHtml(offerId)])
      setDetail(d)
      setHtml(h)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load the offer letter')
    } finally {
      setLoading(false)
    }
  }, [offerId])

  // offer?.status / offer?.event trigger a refetch even though `load` itself
  // doesn't read them — the letter's signature block changes once the
  // candidate accepts, and that's a status/event flip, not a new offerId.
  useEffect(() => { void load() }, [load, offer?.status, offer?.event, retryNonce])

  const muted = lightMode ? 'text-zinc-500' : 'text-zinc-500'

  if (loading) {
    return (
      <div className="flex w-full flex-1 items-center justify-center">
        <Loader2 size={18} className={`animate-spin ${muted}`} />
      </div>
    )
  }

  if (error || !detail || !html) {
    return (
      <div className="flex w-full flex-1 flex-col items-center justify-center gap-2 px-4 text-center">
        <p className={`text-sm ${muted}`}>{error ?? 'Failed to load the offer letter'}</p>
        <span className="font-mono text-[10px] opacity-50">{offerId.slice(0, 8)}</span>
        <button
          type="button"
          onClick={() => setRetryNonce((n) => n + 1)}
          className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded border ${lightMode ? 'border-zinc-300 hover:bg-zinc-100' : 'border-zinc-700 hover:bg-zinc-800'}`}
        >
          <RotateCw size={12} /> Retry
        </button>
      </div>
    )
  }

  return (
    <div className="flex w-full flex-1 min-h-0 flex-col">
      <div className={`grid grid-cols-2 gap-x-4 gap-y-2 border-b px-3 py-2.5 ${lightMode ? 'border-zinc-200' : 'border-zinc-800'}`}>
        <Field label="Candidate" value={detail.candidate_name} />
        <Field label="Status" value={STATUS_LABEL[detail.status] ?? detail.status} />
        <Field label="Position" value={detail.position_title} />
        <Field label="Salary" value={detail.salary} />
        <Field label="Employment type" value={detail.employment_type} />
        <Field label="Start date" value={detail.start_date} />
        <Field label="Location" value={detail.location} />
        {detail.signed_name && <Field label="Signed by" value={`${detail.signed_name} · ${detail.signed_at ?? ''}`} />}
      </div>
      <iframe
        sandbox=""
        srcDoc={html}
        title="Offer letter"
        className="w-full flex-1 min-h-0 border-0 bg-white"
      />
    </div>
  )
}
