import { useEffect, useState } from 'react'
import { Loader2, CreditCard, CheckCircle2, ExternalLink } from 'lucide-react'
import { cappeApi } from '../api'

// Stripe Connect onboarding card for the dashboard. Shows the business's payout
// status and a button to connect/finish their Stripe account. Until charges are
// enabled, storefront orders can't take card payment (they fall back to manual
// pending). Account-level (not per-site) — same connected account across sites.
type Status = { connected: boolean; charges_enabled: boolean; details_submitted: boolean }

export default function StripeConnectCard() {
  const [status, setStatus] = useState<Status | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    cappeApi.get<Status>('/payments/status').then(setStatus).catch(() => setStatus({ connected: false, charges_enabled: false, details_submitted: false }))
  }, [])

  async function connect() {
    setBusy(true)
    setError(null)
    try {
      const { url } = await cappeApi.post<{ url: string }>('/payments/connect', { return_url: window.location.href })
      window.location.href = url
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start Stripe onboarding')
      setBusy(false)
    }
  }

  if (status === null) return null

  if (status.charges_enabled) {
    return (
      <div className="mb-5 flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/[0.06] px-4 py-2.5 text-sm text-emerald-300">
        <CheckCircle2 className="h-4 w-4" /> Card payments active — customer purchases pay out to your Stripe account (Gummfit takes 2%).
      </div>
    )
  }

  return (
    <div className="mb-5 rounded-xl border border-amber-600/40 bg-amber-500/[0.06] px-4 py-3.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <CreditCard className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" />
          <div>
            <p className="text-sm font-medium text-amber-100">
              {status.connected ? 'Finish connecting Stripe to accept payments' : 'Connect Stripe to sell on your storefront'}
            </p>
            <p className="mt-0.5 text-xs text-amber-200/70">
              Customers pay by card; the money goes straight to your Stripe account. Gummfit takes a 2% fee. Until then, orders stay pending for you to handle manually.
            </p>
          </div>
        </div>
        <button
          onClick={connect}
          disabled={busy}
          className="flex items-center gap-1.5 rounded-lg bg-amber-400 px-3.5 py-2 text-sm font-semibold text-zinc-950 hover:bg-amber-300 disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ExternalLink className="h-4 w-4" />}
          {status.connected ? 'Finish setup' : 'Connect Stripe'}
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
    </div>
  )
}
