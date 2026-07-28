import { useState, useEffect } from 'react'
import { Button, Badge } from '../ui'
import { fetchAvailablePosters, fetchPosterOrders, createPosterOrder } from '../../api/compliance'
import type { AvailablePoster, PosterOrder } from '../../types/compliance'

type Props = { locationId: string }

export function CompliancePostersTab({ locationId }: Props) {
  const [posters, setPosters] = useState<AvailablePoster[]>([])
  const [orders, setOrders] = useState<PosterOrder[]>([])
  const [loading, setLoading] = useState(true)
  const [ordering, setOrdering] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetchAvailablePosters().catch(() => []),
      fetchPosterOrders().then((r) => r.orders).catch(() => []),
    ]).then(([p, o]) => {
      setPosters(p)
      setOrders(o)
    }).finally(() => setLoading(false))
  }, [locationId])

  async function handleOrder(poster: AvailablePoster) {
    if (!poster.template_id) return
    setOrdering(poster.location_id)
    try {
      await createPosterOrder({ location_id: poster.location_id, template_ids: [poster.template_id] })
      const [p, o] = await Promise.all([
        fetchAvailablePosters().catch(() => []),
        fetchPosterOrders().then((r) => r.orders).catch(() => []),
      ])
      setPosters(p)
      setOrders(o)
    } finally { setOrdering(null) }
  }

  if (loading) return <p className="text-sm text-zinc-500">Loading posters...</p>

  const locationPosters = posters.filter((p) => p.location_id === locationId)
  const locationOrders = orders.filter((o) => o.location_id === locationId)

  return (
    <div className="space-y-5">
      {locationPosters.length === 0 && locationOrders.length === 0 ? (
        <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
          <p className="text-sm text-zinc-600">No mandatory posters detected for this location.</p>
        </div>
      ) : (
        <>
          {locationPosters.length > 0 && (
            <div>
              <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Available Posters</h3>
              <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                {locationPosters.map((poster, i) => (
                  <div key={i} className="flex items-center justify-between px-4 py-3">
                    <div>
                      <p className="text-sm text-zinc-200">{poster.title}</p>
                      {poster.description && <p className="text-xs text-zinc-500 mt-0.5">{poster.description}</p>}
                      <div className="flex items-center gap-2 mt-1">
                        <Badge variant="neutral">{poster.poster_type}</Badge>
                        <span className="text-[11px] text-zinc-600">{poster.state}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {poster.download_url && (
                        <a href={poster.download_url} target="_blank" rel="noopener noreferrer"
                          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">Download</a>
                      )}
                      {poster.template_id && poster.status === 'available' && (
                        <Button size="sm" variant="ghost" disabled={ordering === poster.location_id}
                          onClick={() => handleOrder(poster)}>
                          {ordering === poster.location_id ? 'Ordering...' : 'Order'}
                        </Button>
                      )}
                      {poster.status === 'ordered' && (
                        <Badge variant="success">Ordered</Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {locationOrders.length > 0 && (
            <div>
              <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Orders</h3>
              <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                {locationOrders.map((order) => (
                  <div key={order.id} className="flex items-center justify-between px-4 py-3">
                    <div>
                      <p className="text-sm text-zinc-200">{order.template_ids.length} poster(s)</p>
                      <span className="text-[11px] text-zinc-600">{new Date(order.created_at).toLocaleDateString()}</span>
                    </div>
                    <Badge variant={order.status === 'delivered' ? 'success' : order.status === 'cancelled' ? 'neutral' : 'warning'}>
                      {order.status}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
