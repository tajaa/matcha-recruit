import { useEffect, useState } from 'react'
import { tellusApi } from '../../api/tellusClient'
import { Card, Chip, Empty, Spinner } from '../../components/ui'
import type { Redemption } from '../../api/types'

const STATUS_TONE: Record<string, string> = {
  issued: 'positive', redeemed: 'neutral', pending: 'neutral', expired: 'negative', cancelled: 'negative',
}

export default function Redemptions() {
  const [items, setItems] = useState<Redemption[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    tellusApi.get<Redemption[]>('/redemptions').then(setItems).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-bold">My rewards</h1>
      {items.length === 0 ? (
        <Empty>You haven’t redeemed anything yet. Head to the marketplace!</Empty>
      ) : (
        <div className="space-y-3">
          {items.map((r) => (
            <Card key={r.id} className="flex items-center justify-between">
              <div>
                <p className="font-semibold">{r.listing_title || 'Reward'}</p>
                <p className="text-xs text-tu-faint">{r.points_spent} pts · {new Date(r.created_at).toLocaleDateString()}</p>
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
