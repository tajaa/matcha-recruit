import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, FileText, CheckCircle2, XCircle, Download, Sparkles } from 'lucide-react'
import { Logo } from '../../components/ui'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

type PageState = 'loading' | 'sign' | 'range' | 'accepted' | 'declined' | 'already_done' | 'not_found' | 'expired' | 'error'

interface OfferDocument {
  id: string
  mode: 'sign' | 'range'
  status: string
  position_title: string
  company_name: string
  company_logo_url?: string | null
  employment_type?: string | null
  location?: string | null
  salary?: string | null
  bonus?: string | null
  stock_options?: string | null
  start_date?: string | null
  manager_name?: string | null
  benefits_medical: boolean
  benefits_dental: boolean
  benefits_vision: boolean
  benefits_401k: boolean
  benefits_pto_vacation: boolean
  benefits_pto_sick: boolean
  benefits_holidays: boolean
  benefits_other?: string | null
  signed_name?: string | null
  signed_at?: string | null
  declined_at?: string | null
  salary_range_min?: number | null
  salary_range_max?: number | null
  range_match_status?: string | null
  matched_salary?: number | null
}

function formatDate(value?: string | null) {
  if (!value) return 'TBD'
  try {
    return new Date(value).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
  } catch {
    return value
  }
}

export default function OfferSign() {
  const { token } = useParams<{ token: string }>()
  const [state, setState] = useState<PageState>('loading')
  const [offer, setOffer] = useState<OfferDocument | null>(null)
  const [error, setError] = useState('')
  const [signedName, setSignedName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [showDecline, setShowDecline] = useState(false)
  const [declineReason, setDeclineReason] = useState('')

  // Range-mode fields
  const [rangeMin, setRangeMin] = useState('')
  const [rangeMax, setRangeMax] = useState('')
  const [rangeResult, setRangeResult] = useState<{ result: string; matched_salary: number | null } | null>(null)

  useEffect(() => {
    if (!token) { setState('not_found'); return }
    fetch(`${BASE}/offer-letters/candidate/${token}/document`)
      .then(async (res) => {
        if (res.status === 404) { setState('not_found'); return }
        if (res.status === 410) { setState('expired'); return }
        if (!res.ok) { setState('error'); setError(`Unexpected error (${res.status})`); return }
        const data: OfferDocument = await res.json()
        setOffer(data)
        if (data.status === 'accepted') setState('accepted')
        else if (data.status === 'rejected') setState('declined')
        else setState(data.mode === 'range' ? 'range' : 'sign')
      })
      .catch(() => { setState('error'); setError('Network error. Please check your connection.') })
  }, [token])

  async function handleAccept() {
    if (!token || !signedName.trim()) return
    setSubmitting(true)
    setError('')
    try {
      const res = await fetch(`${BASE}/offer-letters/candidate/${token}/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signed_name: signedName.trim() }),
      })
      if (res.status === 409) {
        setState('already_done')
        return
      }
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        setError(body?.detail || `Failed to accept (${res.status})`)
        return
      }
      const data = await res.json()
      setOffer((prev) => (prev ? { ...prev, status: 'accepted', signed_name: data.signed_name, signed_at: data.signed_at } : prev))
      setState('accepted')
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDecline() {
    if (!token) return
    setSubmitting(true)
    setError('')
    try {
      const res = await fetch(`${BASE}/offer-letters/candidate/${token}/decline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: declineReason.trim() || undefined }),
      })
      if (res.status === 409) {
        setState('already_done')
        return
      }
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        setError(body?.detail || `Failed to decline (${res.status})`)
        return
      }
      setState('declined')
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleSubmitRange() {
    if (!token) return
    const min = parseFloat(rangeMin)
    const max = parseFloat(rangeMax)
    if (Number.isNaN(min) || Number.isNaN(max) || min > max) {
      setError('Enter a valid range (min ≤ max).')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const res = await fetch(`${BASE}/offer-letters/candidate/${token}/submit-range`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ range_min: min, range_max: max }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        setError(body?.detail || `Failed to submit (${res.status})`)
        return
      }
      const data = await res.json()
      setRangeResult(data)
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-900 flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-lg">
        <Logo className="justify-center mb-8 grayscale" />

        <div className="border border-zinc-800 rounded-xl p-6">
          {state === 'loading' && (
            <div className="flex flex-col items-center py-6 gap-3">
              <Loader2 size={24} className="animate-spin text-zinc-500" />
              <p className="text-sm text-zinc-500">Loading your offer...</p>
            </div>
          )}

          {state === 'not_found' && (
            <div className="flex flex-col items-center py-6 gap-3 text-center">
              <XCircle size={28} className="text-zinc-600" />
              <p className="text-sm text-zinc-400">We couldn't find this offer. The link may be incorrect.</p>
            </div>
          )}

          {state === 'expired' && (
            <div className="flex flex-col items-center py-6 gap-3 text-center">
              <XCircle size={28} className="text-amber-500" />
              <p className="text-sm text-zinc-400">This offer link has expired. Please reach out to your hiring contact for a new one.</p>
            </div>
          )}

          {state === 'error' && (
            <div className="flex flex-col items-center py-6 gap-3 text-center">
              <XCircle size={28} className="text-red-500" />
              <p className="text-sm text-zinc-400">{error || 'Something went wrong.'}</p>
            </div>
          )}

          {state === 'already_done' && (
            <div className="flex flex-col items-center py-6 gap-3 text-center">
              <CheckCircle2 size={28} className="text-emerald-400" />
              <p className="text-sm text-zinc-400">This offer has already been responded to.</p>
            </div>
          )}

          {state === 'accepted' && offer && (
            <div className="flex flex-col items-center py-6 gap-3 text-center">
              <CheckCircle2 size={32} className="text-emerald-400" />
              <h1 className="text-lg font-semibold text-zinc-100">Offer Accepted</h1>
              <p className="text-sm text-zinc-400">
                You've accepted the offer for <span className="text-zinc-200 font-medium">{offer.position_title}</span> at{' '}
                <span className="text-zinc-200 font-medium">{offer.company_name}</span>
                {offer.signed_name ? <> as <span className="text-zinc-200">{offer.signed_name}</span></> : null}.
              </p>
              <a
                href={`${BASE}/offer-letters/candidate/${token}/pdf`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 mt-2 text-xs text-emerald-400 hover:text-emerald-300"
              >
                <Download size={12} /> Download signed offer (PDF)
              </a>
              <p className="text-xs text-zinc-600 mt-4">Your new employer will be in touch about next steps.</p>
            </div>
          )}

          {state === 'declined' && offer && (
            <div className="flex flex-col items-center py-6 gap-3 text-center">
              <XCircle size={28} className="text-zinc-500" />
              <h1 className="text-lg font-semibold text-zinc-100">Offer Declined</h1>
              <p className="text-sm text-zinc-400">
                You've declined the offer for {offer.position_title} at {offer.company_name}.
              </p>
            </div>
          )}

          {state === 'sign' && offer && !showDecline && (
            <>
              <div className="flex items-center gap-2 mb-4">
                <FileText size={18} className="text-emerald-400" />
                <h1 className="text-lg font-semibold text-zinc-100">Offer of Employment</h1>
              </div>
              <div className="space-y-1 mb-4">
                <p className="text-sm text-zinc-300">
                  {offer.company_name} would like to offer you the position of{' '}
                  <span className="font-medium text-zinc-100">{offer.position_title}</span>.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm bg-zinc-800/50 border border-zinc-800 rounded-lg p-4 mb-4">
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500">Salary</div>
                  <div className="text-zinc-200 font-medium">{offer.salary || 'TBD'}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500">Start Date</div>
                  <div className="text-zinc-200 font-medium">{formatDate(offer.start_date)}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500">Employment Type</div>
                  <div className="text-zinc-200 font-medium">{offer.employment_type || 'Full-Time'}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500">Location</div>
                  <div className="text-zinc-200 font-medium">{offer.location || 'Remote'}</div>
                </div>
              </div>
              <a
                href={`${BASE}/offer-letters/candidate/${token}/pdf`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 mb-5 text-xs text-zinc-400 hover:text-zinc-200"
              >
                <Download size={12} /> View full offer letter (PDF)
              </a>

              <label className="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">
                Type your full legal name to electronically sign
              </label>
              <input
                type="text"
                value={signedName}
                onChange={(e) => setSignedName(e.target.value)}
                placeholder="Jane Doe"
                className="w-full px-3 py-2 mb-3 text-sm bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
              {error && <p className="text-xs text-red-400 mb-3">{error}</p>}
              <div className="flex gap-2">
                <button
                  onClick={handleAccept}
                  disabled={!signedName.trim() || submitting}
                  className="flex-1 py-2.5 text-sm font-medium rounded-lg transition-colors bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-800 disabled:text-zinc-600 text-white"
                >
                  {submitting ? <Loader2 size={16} className="animate-spin mx-auto" /> : 'Accept Offer'}
                </button>
                <button
                  onClick={() => setShowDecline(true)}
                  disabled={submitting}
                  className="px-4 py-2.5 text-sm font-medium rounded-lg border border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600"
                >
                  Decline
                </button>
              </div>
              <p className="text-xs text-zinc-600 mt-3">
                By clicking "Accept Offer" you are electronically signing this document. Your name, the time, and your
                IP address will be recorded as your signature.
              </p>
            </>
          )}

          {state === 'sign' && offer && showDecline && (
            <>
              <h1 className="text-lg font-semibold text-zinc-100 mb-3">Decline Offer</h1>
              <p className="text-sm text-zinc-400 mb-3">
                Are you sure you want to decline the offer for {offer.position_title} at {offer.company_name}?
              </p>
              <textarea
                value={declineReason}
                onChange={(e) => setDeclineReason(e.target.value)}
                placeholder="Reason (optional)"
                rows={3}
                className="w-full px-3 py-2 mb-3 text-sm bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500 resize-none"
              />
              {error && <p className="text-xs text-red-400 mb-3">{error}</p>}
              <div className="flex gap-2">
                <button
                  onClick={handleDecline}
                  disabled={submitting}
                  className="flex-1 py-2.5 text-sm font-medium rounded-lg bg-red-600 hover:bg-red-500 text-white"
                >
                  {submitting ? <Loader2 size={16} className="animate-spin mx-auto" /> : 'Confirm Decline'}
                </button>
                <button
                  onClick={() => setShowDecline(false)}
                  disabled={submitting}
                  className="px-4 py-2.5 text-sm font-medium rounded-lg border border-zinc-700 text-zinc-400 hover:text-zinc-200"
                >
                  Back
                </button>
              </div>
            </>
          )}

          {state === 'range' && offer && !rangeResult && (
            <>
              <div className="flex items-center gap-2 mb-4">
                <Sparkles size={18} className="text-emerald-400" />
                <h1 className="text-lg font-semibold text-zinc-100">Salary Range Offer</h1>
              </div>
              <p className="text-sm text-zinc-400 mb-4">
                {offer.company_name} has invited you to submit your salary range for{' '}
                <span className="text-zinc-200 font-medium">{offer.position_title}</span>. This uses blind range
                matching — neither side sees the other's exact numbers; the system finds the overlap automatically.
              </p>
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div>
                  <label className="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Minimum</label>
                  <input
                    type="number"
                    value={rangeMin}
                    onChange={(e) => setRangeMin(e.target.value)}
                    placeholder="80000"
                    className="w-full px-3 py-2 text-sm bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Maximum</label>
                  <input
                    type="number"
                    value={rangeMax}
                    onChange={(e) => setRangeMax(e.target.value)}
                    placeholder="95000"
                    className="w-full px-3 py-2 text-sm bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                </div>
              </div>
              {error && <p className="text-xs text-red-400 mb-3">{error}</p>}
              <button
                onClick={handleSubmitRange}
                disabled={!rangeMin || !rangeMax || submitting}
                className="w-full py-2.5 text-sm font-medium rounded-lg transition-colors bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-800 disabled:text-zinc-600 text-white"
              >
                {submitting ? <Loader2 size={16} className="animate-spin mx-auto" /> : 'Submit Range'}
              </button>
            </>
          )}

          {state === 'range' && rangeResult && (
            <div className="flex flex-col items-center py-6 gap-3 text-center">
              {rangeResult.result === 'matched' ? (
                <>
                  <CheckCircle2 size={32} className="text-emerald-400" />
                  <h1 className="text-lg font-semibold text-zinc-100">It's a Match!</h1>
                  <p className="text-sm text-zinc-400">
                    Your range overlapped with the offer. Matched salary:{' '}
                    <span className="text-zinc-200 font-medium">
                      ${rangeResult.matched_salary?.toLocaleString()}
                    </span>
                    . Your new employer will be in touch.
                  </p>
                </>
              ) : (
                <>
                  <XCircle size={28} className="text-amber-500" />
                  <h1 className="text-lg font-semibold text-zinc-100">No Overlap Yet</h1>
                  <p className="text-sm text-zinc-400">
                    Your range didn't overlap with the current offer this round. The employer may follow up with a
                    revised range.
                  </p>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
