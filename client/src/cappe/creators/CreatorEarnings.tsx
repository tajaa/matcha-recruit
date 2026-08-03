import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { cappeApi } from '../api'
import { ui, badgeFor } from '../components/ui'
import { fmtCents, type EarningsRow } from '../types'

const UPCOMING_STATUSES = ['due', 'scheduled', 'processing']

export default function CreatorEarnings() {
  const [rows, setRows] = useState<EarningsRow[] | null>(null)

  useEffect(() => {
    cappeApi.get<EarningsRow[]>('/creators/me/earnings').then(setRows).catch(() => setRows([]))
  }, [])

  if (rows === null) {
    return <div className="flex items-center justify-center py-24"><Loader2 className="h-6 w-6 animate-spin text-zinc-600" /></div>
  }

  const paidOut = rows.filter((r) => r.status === 'paid').reduce((n, r) => n + r.amount_cents - (r.fee_cents ?? 0), 0)
  const upcoming = rows.filter((r) => UPCOMING_STATUSES.includes(r.status)).reduce((n, r) => n + r.amount_cents, 0)

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className={ui.heading}>Earnings</h1>
      <p className={`${ui.subtitle} mb-6`}>Payouts from brand collabs.</p>

      <div className="mb-6 grid grid-cols-2 gap-4 sm:max-w-md">
        <div className={`${ui.card} p-4`}>
          <p className="text-xs uppercase tracking-wide text-zinc-500">Paid out</p>
          <p className="mt-1 text-2xl font-semibold text-emerald-400">{fmtCents(paidOut)}</p>
        </div>
        <div className={`${ui.card} p-4`}>
          <p className="text-xs uppercase tracking-wide text-zinc-500">Upcoming</p>
          <p className="mt-1 text-2xl font-semibold text-zinc-200">{fmtCents(upcoming)}</p>
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="py-12 text-center text-sm text-zinc-500">No earnings yet.</p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-800">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900 text-zinc-500">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Offer</th>
                <th className="px-3 py-2 text-left font-medium">Brand</th>
                <th className="px-3 py-2 text-left font-medium">Installment</th>
                <th className="px-3 py-2 text-left font-medium">Amount</th>
                <th className="px-3 py-2 text-left font-medium">Fee</th>
                <th className="px-3 py-2 text-left font-medium">Status</th>
                <th className="px-3 py-2 text-left font-medium">Paid</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {rows.map((r, i) => (
                <tr key={`${r.offer_id}-${i}`}>
                  <td className="px-3 py-2.5 text-zinc-300">{r.offer_title}</td>
                  <td className="px-3 py-2.5 text-zinc-400">{r.brand_name || '—'}</td>
                  <td className="px-3 py-2.5 text-zinc-400">{r.label}</td>
                  <td className="px-3 py-2.5 text-zinc-300">{fmtCents(r.amount_cents)}</td>
                  <td className="px-3 py-2.5 text-zinc-500">{r.fee_cents != null ? fmtCents(r.fee_cents) : '—'}</td>
                  <td className="px-3 py-2.5"><span className={badgeFor(r.status)}>{r.status}</span></td>
                  <td className="px-3 py-2.5 text-zinc-500">{r.paid_at ? new Date(r.paid_at).toLocaleDateString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
