import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Receipt, ChevronDown, ChevronRight } from 'lucide-react'
import { cappeApi } from '../../../api/cappeClient'
import SurfaceShell, { centsToMoney } from '../../../components/cappe/SurfaceShell'
import type { CappeOrder } from '../../../types/cappe'

const STATUSES = ['pending', 'paid', 'fulfilled', 'cancelled', 'refunded'] as const

const statusStyle: Record<string, string> = {
  pending: 'bg-amber-500/15 text-amber-400',
  paid: 'bg-sky-500/15 text-sky-400',
  fulfilled: 'bg-emerald-500/15 text-emerald-400',
  cancelled: 'bg-zinc-800 text-zinc-500',
  refunded: 'bg-red-500/15 text-red-400',
}

export default function Orders() {
  const { siteId } = useParams<{ siteId: string }>()
  const [orders, setOrders] = useState<CappeOrder[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)

  useEffect(() => {
    cappeApi
      .get<CappeOrder[]>(`/sites/${siteId}/orders`)
      .then(setOrders)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load orders'))
  }, [siteId])

  async function toggle(order: CappeOrder) {
    if (openId === order.id) { setOpenId(null); return }
    setOpenId(order.id)
    if (order.items.length === 0) {
      const full = await cappeApi.get<CappeOrder>(`/sites/${siteId}/orders/${order.id}`)
      setOrders((o) => (o || []).map((x) => (x.id === order.id ? full : x)))
    }
  }

  async function setStatus(order: CappeOrder, status: string) {
    const updated = await cappeApi.patch<CappeOrder>(`/sites/${siteId}/orders/${order.id}`, { status })
    setOrders((o) => (o || []).map((x) => (x.id === order.id ? { ...updated, items: x.items } : x)))
  }

  return (
    <SurfaceShell title="Orders" subtitle="Orders placed through your storefront.">
      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}
      {orders === null ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : orders.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
          <Receipt className="mx-auto mb-2 h-7 w-7 text-zinc-300" /> No orders yet.
        </div>
      ) : (
        <div className="divide-y divide-zinc-800 rounded-2xl border border-zinc-800 bg-zinc-900">
          {orders.map((o) => (
            <div key={o.id}>
              <div className="flex items-center gap-4 px-5 py-3">
                <button onClick={() => toggle(o)} className="text-zinc-400 hover:text-zinc-300">
                  {openId === o.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </button>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-zinc-100">{o.customer_email || 'No email'}</div>
                  <div className="text-xs text-zinc-400">{new Date(o.created_at).toLocaleString()}</div>
                </div>
                <div className="text-sm font-medium text-zinc-300">{centsToMoney(o.subtotal_cents, o.currency)}</div>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[o.status]}`}>{o.status}</span>
                <select
                  value={o.status}
                  onChange={(e) => setStatus(o, e.target.value)}
                  className="rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-2 py-1 text-xs"
                >
                  {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              {openId === o.id && (
                <div className="bg-zinc-950 px-12 py-3">
                  {o.items.length === 0 ? (
                    <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
                  ) : (
                    <ul className="space-y-1 text-sm">
                      {o.items.map((it) => (
                        <li key={it.id} className="flex justify-between text-zinc-400">
                          <span>{it.quantity} × {it.title}</span>
                          <span>{centsToMoney(it.unit_price_cents * it.quantity, o.currency)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </SurfaceShell>
  )
}
