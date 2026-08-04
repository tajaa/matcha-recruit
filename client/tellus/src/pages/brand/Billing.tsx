import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { tellusApi } from '../../api/tellusClient'
import { useAccount } from '../../hooks/useAccount'
import { Button, Card, ErrorText, Input, Spinner } from '../../components/ui'
import type { BrandBillingStatus, CheckoutResponse } from '../../api/types'

const dollars = (cents: number) => `$${(cents / 100).toFixed(2)}`

export default function BrandBilling() {
  const { refreshAccount } = useAccount()
  const [params] = useSearchParams()
  const [status, setStatus] = useState<BrandBillingStatus | null>(null)
  const [locationCount, setLocationCount] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [activating, setActivating] = useState(params.get('paid') === '1')

  async function load() {
    const s = await tellusApi.get<BrandBillingStatus>('/billing/status')
    setStatus(s)
    setLocationCount(String(s.location_count))
    return s
  }

  useEffect(() => {
    load().catch((e) => setErr(e instanceof Error ? e.message : 'Failed to load billing status'))
  }, [])

  // On the Stripe success redirect the webhook may not have landed yet —
  // re-poll once after a short delay before giving up on "activating".
  useEffect(() => {
    if (!activating) return
    const t = setTimeout(async () => {
      const s = await load().catch(() => null)
      await refreshAccount()
      if (s?.plan_status === 'active') setActivating(false)
      setActivating(false)
    }, 2500)
    return () => clearTimeout(t)
  }, [activating])

  async function saveLocationCount() {
    const n = parseInt(locationCount, 10)
    if (isNaN(n) || n < 1) return
    setBusy(true); setErr('')
    try {
      const s = await tellusApi.patch<BrandBillingStatus>('/billing/locations', { location_count: n })
      setStatus(s)
    } catch (e) { setErr(e instanceof Error ? e.message : 'Failed to update store count') } finally { setBusy(false) }
  }

  async function checkout() {
    setBusy(true); setErr('')
    try {
      const origin = window.location.origin
      const res = await tellusApi.post<CheckoutResponse>('/billing/checkout', {
        success_url: `${origin}/tellus/brand/billing?paid=1`,
        cancel_url: `${origin}/tellus/brand/billing`,
      })
      window.location.href = res.checkout_url
    } catch (e) { setErr(e instanceof Error ? e.message : 'Failed to open checkout'); setBusy(false) }
  }

  if (!status) return <Spinner />

  if (activating) {
    return (
      <div className="max-w-lg space-y-5">
        <h1 className="text-lg font-bold">Billing</h1>
        <Card className="flex items-center gap-3">
          <Spinner />
          <p className="text-sm text-tu-dim">Activating your subscription…</p>
        </Card>
      </div>
    )
  }

  return (
    <div className="max-w-lg space-y-5">
      <h1 className="text-lg font-bold">Billing</h1>

      {status.plan_status === 'active' && (
        <Card className="space-y-1 border-tu-good/30 bg-tu-good/5">
          <p className="text-sm font-semibold text-tu-good">Subscription active</p>
          <p className="text-xs text-tu-dim">
            {status.location_count} store{status.location_count === 1 ? '' : 's'} · {dollars(status.monthly_total_cents)}/mo
          </p>
        </Card>
      )}

      {status.plan_status === 'past_due' && (
        <Card className="space-y-1 border-tu-bad/30 bg-tu-bad/5">
          <p className="text-sm font-semibold text-tu-bad">Payment failed</p>
          <p className="text-xs text-tu-dim">Update your card in Stripe or contact support to keep your dashboard active.</p>
        </Card>
      )}

      {status.plan_status === 'canceled' && (
        <Card className="space-y-1 border-tu-bad/30 bg-tu-bad/5">
          <p className="text-sm font-semibold text-tu-bad">Subscription canceled</p>
          <p className="text-xs text-tu-dim">Re-subscribe below to regain access to your dashboard.</p>
        </Card>
      )}

      {status.plan_status !== 'active' && (
        <Card className="space-y-4">
          <Input
            label="Number of stores"
            type="number"
            min={1}
            value={locationCount}
            onChange={(e) => setLocationCount(e.target.value)}
            onBlur={saveLocationCount}
          />
          <p className="text-sm text-tu-dim">
            {status.location_count} store{status.location_count === 1 ? '' : 's'} × {dollars(status.price_per_location_cents)}/mo ={' '}
            <span className="font-semibold text-tu-text">{dollars(status.monthly_total_cents)}/mo</span>
          </p>
          <ErrorText>{err}</ErrorText>
          <Button onClick={checkout} loading={busy} className="w-full">Continue to payment</Button>
        </Card>
      )}

      {status.store_count > status.location_count && (
        <p className="text-xs text-tu-bad">
          You have {status.store_count} stores set up but only {status.location_count} on your plan — increase your
          store count above before adding more.
        </p>
      )}
    </div>
  )
}
