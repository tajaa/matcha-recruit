import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { cappeApi } from '../../api'
import StripeConnectCard from '../../components/StripeConnectCard'
import { ui } from '../../components/ui'
import type { CappeMagazineEarnings, CappeMagazineTotals } from '../../types'

const money = (cents: number, currency = 'USD') => {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(cents / 100)
  } catch {
    return `${(cents / 100).toFixed(2)} ${currency}`
  }
}

function Totals({ label, rows }: { label: string; rows: CappeMagazineTotals[] }) {
  return (
    <section className={`${ui.card} p-5`} aria-label={label}>
      <h2 className="mb-3 text-sm font-medium text-zinc-100">{label}</h2>
      {rows.length === 0 ? <p className="text-sm text-zinc-400">No payments yet.</p> : rows.map((t) => (
        <dl key={t.currency} className="grid grid-cols-2 gap-y-1 text-sm sm:grid-cols-4">
          <dt className="text-zinc-500">Readers paid</dt><dd className="text-zinc-100">{money(t.gross_cents, t.currency)}</dd>
          <dt className="text-zinc-500">Gummfit’s share</dt><dd className="text-zinc-100">{money(t.fee_cents, t.currency)}</dd>
          <dt className="text-zinc-500">Refunded</dt><dd className="text-zinc-100">{money(t.refunded_cents, t.currency)}</dd>
          <dt className="text-zinc-500">Yours</dt><dd className="font-semibold text-emerald-300">{money(t.net_cents, t.currency)}</dd>
        </dl>
      ))}
    </section>
  )
}

/** `sites/:siteId/earnings` — what readers have paid, Gummfit's share as
 *  Stripe took it, and the writer's Stripe balance. Stripe's own processing
 *  fee comes out of that balance and isn't shown here. */
export default function Earnings() {
  const { siteId } = useParams<{ siteId: string }>()
  const [data, setData] = useState<CappeMagazineEarnings | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    cappeApi.get<CappeMagazineEarnings>(`/sites/${siteId}/magazine/earnings`)
      .then((d) => { if (live) setData(d) })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : 'Could not load your earnings') })
    return () => { live = false }
  }, [siteId])

  if (data === null && !error) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className={ui.heading}>Earnings</h1>
        <p className={ui.subtitle}>
          {data ? `${data.paying_readers} paying ${data.paying_readers === 1 ? 'reader' : 'readers'}. Gummfit keeps ${data.fee_bps / 100}% of each payment; ` : ''}
          Stripe’s processing fee comes out of your Stripe balance.
        </p>
      </div>
      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      {data && (
        <>
          <StripeConnectCard magazineFeeBps={data.fee_bps} />
          <Totals label="Last 30 days" rows={data.last_30_days} />
          <Totals label="All time" rows={data.all_time} />
          {data.balance && (
            <section className={`${ui.card} p-5 text-sm`} aria-label="Stripe balance">
              <h2 className="mb-2 font-medium text-zinc-100">Your Stripe balance</h2>
              <p className="text-zinc-300">
                Available {data.balance.available.map((b) => money(b.amount_cents, b.currency)).join(', ') || money(0)}
                {' · '}On its way {data.balance.pending.map((b) => money(b.amount_cents, b.currency)).join(', ') || money(0)}
              </p>
            </section>
          )}
          {data.payments.length > 0 && (
            <ul className="divide-y divide-zinc-800 rounded-2xl border border-zinc-800 bg-zinc-900" aria-label="Payments">
              {data.payments.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-2.5 text-sm">
                  <span className="min-w-0 truncate text-zinc-100">{p.email || 'A reader'}</span>
                  <span className="text-xs text-zinc-400">
                    {money(p.amount_cents, p.currency)}{p.refunded_cents ? ` · ${money(p.refunded_cents, p.currency)} refunded` : ''}
                    {' · '}{new Date(p.paid_at).toLocaleDateString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
