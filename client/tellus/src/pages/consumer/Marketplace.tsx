import { useEffect, useState } from 'react'
import { Gift, MapPin } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { useAccount } from '../../hooks/useAccount'
import { Button, Card, Empty, ErrorText, Input, Spinner } from '../../components/ui'
import type { Listing, PointsBalance, Redemption } from '../../api/types'

export default function Marketplace() {
  const { account } = useAccount()
  const [listings, setListings] = useState<Listing[]>([])
  const [balance, setBalance] = useState<number>(0)
  const [city, setCity] = useState(account?.city ?? '')
  const [loading, setLoading] = useState(true)
  const [redeeming, setRedeeming] = useState<string | null>(null)
  const [err, setErr] = useState('')
  const [done, setDone] = useState<Redemption | null>(null)

  async function load(searchCity?: string) {
    setLoading(true)
    try {
      const q = searchCity ? `?city=${encodeURIComponent(searchCity)}` : ''
      const [l, b] = await Promise.all([
        tellusApi.get<Listing[]>(`/marketplace${q}`),
        tellusApi.get<PointsBalance>('/rewards/balance'),
      ])
      setListings(l); setBalance(b.points_balance)
    } finally { setLoading(false) }
  }

  useEffect(() => { void load(account?.city ?? undefined) }, [account?.city])

  async function redeem(listing: Listing) {
    setErr(''); setRedeeming(listing.id)
    try {
      const r = await tellusApi.post<Redemption>('/redeem', { listing_id: listing.id })
      setDone(r)
      await load(city || undefined)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not redeem')
    } finally { setRedeeming(null) }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold">Marketplace</h1>
          <p className="text-sm text-tu-faint">Spend points on local perks.</p>
        </div>
        <div className="rounded-lg bg-tu-accent/10 px-3 py-1.5 text-sm font-bold text-tu-accent">{balance.toLocaleString()} pts</div>
      </div>

      <form onSubmit={(e) => { e.preventDefault(); void load(city || undefined) }} className="flex gap-2">
        <div className="flex-1"><Input placeholder="Filter by city" value={city} onChange={(e) => setCity(e.target.value)} /></div>
        <Button type="submit" variant="soft">Search</Button>
      </form>

      <ErrorText>{err}</ErrorText>

      {done && (
        <Card className="border-tu-good/40 bg-tu-good/5">
          <p className="text-sm font-semibold text-tu-good">Redeemed: {done.listing_title}</p>
          {done.code && <p className="mt-1 font-mono text-lg tracking-widest">{done.code}</p>}
          <p className="mt-1 text-xs text-tu-faint">Show this at the store. Find it again under “My rewards”.</p>
        </Card>
      )}

      {loading ? <Spinner /> : listings.length === 0 ? (
        <Empty>No rewards in this area yet. Try another city.</Empty>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {listings.map((l) => {
            const affordable = balance >= l.points_cost
            return (
              <Card key={l.id} className="flex flex-col">
                {l.image_url ? (
                  <img src={l.image_url} alt="" className="mb-3 h-32 w-full rounded-lg object-cover" />
                ) : (
                  <div className="mb-3 flex h-32 w-full items-center justify-center rounded-lg bg-tu-panel2 text-tu-faint"><Gift className="h-8 w-8" /></div>
                )}
                <div className="flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-semibold">{l.title}</h3>
                    <span className="whitespace-nowrap rounded-full bg-tu-accent/10 px-2 py-0.5 text-xs font-bold text-tu-accent">{l.points_cost} pts</span>
                  </div>
                  {l.brand_name && <p className="text-xs text-tu-faint">{l.brand_name}</p>}
                  {l.description && <p className="mt-1 text-sm text-tu-dim">{l.description}</p>}
                  {(l.city || l.state) && (
                    <p className="mt-2 flex items-center gap-1 text-xs text-tu-faint"><MapPin className="h-3 w-3" />{[l.city, l.state].filter(Boolean).join(', ')}</p>
                  )}
                  {l.quantity_remaining != null && <p className="mt-1 text-xs text-tu-faint">{l.quantity_remaining} left</p>}
                </div>
                <Button className="mt-4" disabled={!affordable} loading={redeeming === l.id} onClick={() => redeem(l)}>
                  {affordable ? 'Redeem' : 'Not enough points'}
                </Button>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
