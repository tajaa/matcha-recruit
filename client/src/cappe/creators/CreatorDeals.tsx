import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { cappeApi } from '../api'
import { ui, badgeFor } from '../components/ui'
import { fmtCents, type OfferListItem } from '../types'

const STATUS_CHIPS = ['all', 'sent', 'negotiating', 'accepted', 'active', 'completed', 'declined', 'closed'] as const
type StatusChip = (typeof STATUS_CHIPS)[number]
const CLOSED = ['withdrawn', 'cancelled']

function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 3600) return `${Math.max(1, Math.floor(s / 60))}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export default function CreatorDeals() {
  const [chip, setChip] = useState<StatusChip>('all')
  const [offers, setOffers] = useState<OfferListItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const status = chip === 'all' ? undefined : chip === 'closed' ? CLOSED.join(',') : chip
    const qs = status ? `&status=${encodeURIComponent(status)}` : ''
    cappeApi.get<{ offers: OfferListItem[]; total: number }>(`/collab/offers?side=creator${qs}`)
      .then((res) => setOffers(res.offers))
      .catch(() => setOffers([]))
      .finally(() => setLoading(false))
  }, [chip])

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className={ui.heading}>Deals</h1>
      <p className={`${ui.subtitle} mb-6`}>Offers from brands.</p>

      <div className="mb-4 flex flex-wrap gap-2">
        {STATUS_CHIPS.map((c) => (
          <button
            key={c}
            onClick={() => setChip(c)}
            className={`rounded-full border px-3 py-1 text-xs ${chip === c ? 'border-emerald-500 bg-emerald-500/10 text-emerald-300' : 'border-zinc-700 text-zinc-400'}`}
          >
            {c}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-12 text-sm text-zinc-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
      ) : offers.length === 0 ? (
        <div className="py-12 text-center">
          <p className="text-sm text-zinc-500">No deals yet.</p>
          <Link to="/cappe/creator" className={`${ui.btnPrimary} mt-4 inline-flex`}>Finish your profile to get offers</Link>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-800">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900 text-zinc-500">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Brand</th>
                <th className="px-3 py-2 text-left font-medium">Title</th>
                <th className="px-3 py-2 text-left font-medium">Total</th>
                <th className="px-3 py-2 text-left font-medium">Status</th>
                <th className="px-3 py-2 text-left font-medium">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {offers.map((o) => (
                <tr key={o.id} className="cursor-pointer hover:bg-zinc-900/60" onClick={() => (window.location.href = `/cappe/creator/deals/${o.id}`)}>
                  <td className="px-3 py-2.5 text-zinc-200">{o.brand_name || 'A brand'}</td>
                  <td className="px-3 py-2.5 text-zinc-300">{o.title}</td>
                  <td className="px-3 py-2.5 text-zinc-300">{o.total_cents != null ? fmtCents(o.total_cents, o.currency) : '—'}</td>
                  <td className="px-3 py-2.5"><span className={badgeFor(o.status)}>{o.status.replace('_', ' ')}</span></td>
                  <td className="px-3 py-2.5 text-zinc-500">{timeAgo(o.last_action_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
