import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { tellusApi } from '../../api/tellusClient'
import { promoApi } from '../../api/promo'
import { Card, Chip, Empty, Spinner } from '../../components/ui'
import type { PromoCard, Redemption } from '../../api/types'

const STATUS_TONE: Record<string, string> = {
  issued: 'positive', redeemed: 'neutral', pending: 'neutral', expired: 'negative', cancelled: 'negative',
}

export default function Redemptions() {
  const [items, setItems] = useState<Redemption[]>([])
  const [cards, setCards] = useState<PromoCard[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    tellusApi.get<Redemption[]>('/redemptions').then(setItems).finally(() => setLoading(false))
  }, [])

  // Separate from the marketplace fetch so the page's loading gate never waits
  // on this bonus section; a failure just leaves it hidden.
  useEffect(() => {
    promoApi.myCards().then(setCards).catch(() => {})
  }, [])

  if (loading) return <Spinner />

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-bold">My rewards</h1>
      {cards.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-tu-dim">Reward cards</h2>
          {cards.map((c) => (
            <Link key={c.id} to={`/card/${c.card_token}`} className="block">
              <Card className="flex items-center justify-between">
                <div>
                  <p className="font-semibold">{c.campaign_title}</p>
                  <p className="text-xs text-tu-faint">{c.brand_name}</p>
                  <p className="text-xs text-tu-faint">{c.reward_text}</p>
                </div>
                <Chip tone={STATUS_TONE[c.status]}>{c.status}</Chip>
              </Card>
            </Link>
          ))}
        </div>
      )}
      {items.length === 0 ? (
        <Empty>You haven’t redeemed anything yet. Head to the marketplace!</Empty>
      ) : (
        <div className="space-y-3">
          {items.map((r) => (
            <Card key={r.id} className="flex items-center justify-between">
              <div>
                <p className="font-semibold">{r.listing_title || 'Reward'}</p>
                <p className="text-xs text-tu-faint">
                  {[r.brand_name ?? 'Tell-Us reward', [r.listing_city, r.listing_state].filter(Boolean).join(', ')]
                    .filter(Boolean).join(' · ')}
                </p>
                <p className="text-xs text-tu-faint">{r.points_spent} pts · {new Date(r.created_at).toLocaleDateString()}</p>
                {r.status === 'issued' && r.expires_at && (
                  <p className="text-xs text-tu-faint">Expires {new Date(r.expires_at).toLocaleDateString()}</p>
                )}
                {r.code && <p className="mt-1 font-mono text-sm tracking-widest text-tu-accent">{r.code}</p>}
              </div>
              <Chip tone={STATUS_TONE[r.status]}>{r.status}</Chip>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
