import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, Plus } from 'lucide-react'
import { cappeApi } from '../api'
import { useCappeMe } from '../hooks/useCappeMe'
import { ui, badgeFor } from '../components/ui'
import { fmtCents, type Campaign, type OfferListItem } from '../types'
import { brandCollabPath, creatorPaths } from './creatorPaths'

const STATUS_CHIPS = ['all', 'sent', 'negotiating', 'accepted', 'active', 'completed', 'closed'] as const
type StatusChip = (typeof STATUS_CHIPS)[number]

const CLOSED = ['declined', 'withdrawn', 'cancelled']

function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 3600) return `${Math.max(1, Math.floor(s / 60))}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

function OffersTab() {
  const [chip, setChip] = useState<StatusChip>('all')
  const [offers, setOffers] = useState<OfferListItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const status = chip === 'all' ? undefined : chip === 'closed' ? CLOSED.join(',') : chip
    const qs = status ? `&status=${encodeURIComponent(status)}` : ''
    cappeApi.get<{ offers: OfferListItem[]; total: number }>(`/collab/offers?side=brand${qs}`)
      .then((res) => setOffers(res.offers))
      .catch(() => setOffers([]))
      .finally(() => setLoading(false))
  }, [chip])

  return (
    <div>
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
          <p className="text-sm text-zinc-500">No offers yet.</p>
          <Link to={creatorPaths.directory} className={`${ui.btnPrimary} mt-4 inline-flex`}>Find creators to work with</Link>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-800">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900 text-zinc-500">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Creator</th>
                <th className="px-3 py-2 text-left font-medium">Title</th>
                <th className="px-3 py-2 text-left font-medium">Total</th>
                <th className="px-3 py-2 text-left font-medium">Schedule</th>
                <th className="px-3 py-2 text-left font-medium">Status</th>
                <th className="px-3 py-2 text-left font-medium">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {offers.map((o) => (
                <tr key={o.id} className="cursor-pointer hover:bg-zinc-900/60" onClick={() => (window.location.href = brandCollabPath(o.id))}>
                  <td className="flex items-center gap-2 px-3 py-2.5">
                    <div className="h-6 w-6 overflow-hidden rounded-full bg-zinc-800">
                      {o.creator_avatar_url && <img src={o.creator_avatar_url} alt="" className="h-full w-full object-cover" />}
                    </div>
                    <span className="text-zinc-200">@{o.creator_handle}</span>
                  </td>
                  <td className="px-3 py-2.5 text-zinc-300">{o.title}</td>
                  <td className="px-3 py-2.5 text-zinc-300">{o.total_cents != null ? fmtCents(o.total_cents, o.currency) : '—'}</td>
                  <td className="px-3 py-2.5 text-zinc-400">{o.payment_schedule ?? '—'}</td>
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

function CampaignsTab() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(true)
  const [title, setTitle] = useState('')
  const [creating, setCreating] = useState(false)

  function load() {
    setLoading(true)
    cappeApi.get<Campaign[]>('/collab/campaigns').then(setCampaigns).catch(() => setCampaigns([])).finally(() => setLoading(false))
  }
  useEffect(load, [])

  async function create() {
    if (!title.trim()) return
    setCreating(true)
    try {
      await cappeApi.post('/collab/campaigns', { title: title.trim() })
      setTitle('')
      load()
    } finally {
      setCreating(false)
    }
  }

  async function toggleArchive(c: Campaign) {
    await cappeApi.patch(`/collab/campaigns/${c.id}`, { status: c.status === 'archived' ? 'active' : 'archived' })
    load()
  }

  return (
    <div>
      <div className="mb-4 flex gap-2">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="New campaign title" className={ui.input} />
        <button onClick={create} disabled={creating} className={ui.btnPrimary}>
          {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Create
        </button>
      </div>
      {loading ? (
        <div className="flex items-center gap-2 py-12 text-sm text-zinc-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
      ) : campaigns.length === 0 ? (
        <p className="py-12 text-center text-sm text-zinc-500">No campaigns yet.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {campaigns.map((c) => (
            <div key={c.id} className={`${ui.card} p-4`}>
              <div className="flex items-start justify-between">
                <p className="font-medium text-zinc-100">{c.title}</p>
                <span className={badgeFor(c.status)}>{c.status}</span>
              </div>
              {c.description && <p className="mt-1 text-sm text-zinc-500">{c.description}</p>}
              <p className="mt-2 text-xs text-zinc-500">{c.offer_count} offer{c.offer_count === 1 ? '' : 's'}</p>
              <button onClick={() => toggleArchive(c)} className={`${ui.btnGhost} mt-3 px-3 py-1 text-xs`}>
                {c.status === 'archived' ? 'Reactivate' : 'Archive'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function BrandCollabs() {
  const { account } = useCappeMe()
  const [tab, setTab] = useState<'offers' | 'campaigns'>('offers')

  if (account && account.account_type !== 'business') return null

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className={ui.heading}>Collabs</h1>
      <p className={`${ui.subtitle} mb-6`}>Offers you've sent to creators.</p>

      <div className="mb-6 flex gap-1 border-b border-zinc-800">
        {(['offers', 'campaigns'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize ${tab === t ? 'border-b-2 border-emerald-500 text-zinc-100' : 'text-zinc-500'}`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'offers' ? <OffersTab /> : <CampaignsTab />}
    </div>
  )
}
