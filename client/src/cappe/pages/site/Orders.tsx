import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Receipt, ChevronDown, ChevronRight, Calendar, Check, X, Clock } from 'lucide-react'
import { cappeApi } from '../../api'
import SurfaceShell, { centsToMoney } from '../../components/SurfaceShell'
import StripeConnectCard from '../../components/StripeConnectCard'
import ImageUpload from '../../components/ImageUpload'
import type { CappeOrder, CappeOrderItem } from '../../types'

const STATUSES = ['pending', 'paid', 'fulfilled', 'cancelled', 'refunded'] as const
const DELIVERABLE_ACCEPT = '.pdf,.zip,.doc,.docx,.xls,.xlsx,.csv,.txt,image/*'

const fulfillBadge: Record<string, string> = {
  physical: 'bg-zinc-800 text-zinc-400',
  digital: 'bg-sky-500/15 text-sky-400',
  service: 'bg-violet-500/15 text-violet-400',
  booking: 'bg-amber-500/15 text-amber-400',
}

const statusStyle: Record<string, string> = {
  pending: 'bg-amber-500/15 text-amber-400',
  paid: 'bg-sky-500/15 text-sky-400',
  fulfilled: 'bg-emerald-500/15 text-emerald-400',
  cancelled: 'bg-zinc-800 text-zinc-500',
  refunded: 'bg-red-500/15 text-red-400',
  declined: 'bg-red-500/15 text-red-400',
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

  async function acceptOrder(order: CappeOrder) {
    const updated = await cappeApi.post<CappeOrder>(`/sites/${siteId}/orders/${order.id}/accept`)
    setOrders((o) => (o || []).map((x) => (x.id === order.id ? { ...updated, items: x.items } : x)))
  }
  async function declineOrder(order: CappeOrder) {
    const reason = window.prompt('Reason for declining (optional, shown to the customer):') ?? undefined
    const updated = await cappeApi.post<CappeOrder>(`/sites/${siteId}/orders/${order.id}/decline`, { reason })
    setOrders((o) => (o || []).map((x) => (x.id === order.id ? { ...updated, items: x.items } : x)))
  }

  async function attachDeliverable(order: CappeOrder, item: CappeOrderItem, url: string) {
    const updated = await cappeApi.patch<CappeOrderItem>(
      `/sites/${siteId}/orders/${order.id}/items/${item.id}`, { deliverable_url: url },
    )
    setOrders((o) => (o || []).map((x) =>
      x.id === order.id ? { ...x, items: x.items.map((i) => (i.id === item.id ? updated : i)) } : x,
    ))
  }

  return (
    <SurfaceShell title="Orders" subtitle="Orders placed through your storefront.">
      <StripeConnectCard />
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
                <div className="text-sm font-medium text-zinc-300">{centsToMoney(o.total_cents ?? o.subtotal_cents, o.currency)}</div>
                {o.requires_approval && o.status === 'pending' && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-400"><Clock className="h-3 w-3" /> needs approval</span>
                )}
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[o.status]}`}>{o.status}</span>
                {(o.status === 'paid' || o.status === 'fulfilled') && (
                  <button
                    onClick={() => cappeApi.openBlob(`/sites/${siteId}/orders/${o.id}/receipt.pdf`).catch((e) => setError(e instanceof Error ? e.message : 'Could not open receipt'))}
                    title="View / print receipt"
                    className="flex items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800"
                  >
                    <Receipt className="h-3.5 w-3.5" /> Receipt
                  </button>
                )}
                {o.requires_approval && o.status === 'pending' ? (
                  <>
                    <button onClick={() => acceptOrder(o)} className="flex items-center gap-1 rounded-lg bg-emerald-500 px-2.5 py-1 text-xs font-semibold text-zinc-950 hover:bg-emerald-400"><Check className="h-3.5 w-3.5" /> Accept</button>
                    <button onClick={() => declineOrder(o)} className="flex items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800"><X className="h-3.5 w-3.5" /> Decline</button>
                  </>
                ) : (
                  <select
                    value={o.status}
                    onChange={(e) => setStatus(o, e.target.value)}
                    className="rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-2 py-1 text-xs"
                  >
                    {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                )}
              </div>
              {openId === o.id && (
                <div className="space-y-2 bg-zinc-950 px-12 py-3">
                  {o.items.length === 0 ? (
                    <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
                  ) : (
                    o.items.map((it) => {
                      const answers = Object.entries(it.intake_answers || {}).filter(([, v]) => v != null && v !== '')
                      const needsDeliverable = it.fulfillment === 'service' || it.fulfillment === 'digital'
                      return (
                        <div key={it.id} className="rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-sm">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="text-zinc-200">{it.quantity} × {it.title}</span>
                              <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${fulfillBadge[it.fulfillment] || fulfillBadge.physical}`}>{it.fulfillment}</span>
                            </div>
                            <span className="text-zinc-300">{centsToMoney(it.unit_price_cents * it.quantity, o.currency)}</span>
                          </div>
                          {it.selected_options?.length > 0 && (
                            <div className="mt-1 text-xs text-zinc-400">{it.selected_options.map((s) => s.name).filter(Boolean).join(', ')}</div>
                          )}
                          {it.booking_id && (
                            <div className="mt-1 flex items-center gap-1 text-xs text-amber-400">
                              <Calendar className="h-3.5 w-3.5" /> Scheduled session — see the Bookings tab
                            </div>
                          )}
                          {answers.length > 0 && (
                            <div className="mt-2 space-y-0.5 border-t border-zinc-800 pt-2 text-xs">
                              {answers.map(([k, v]) => (
                                <div key={k}><span className="text-zinc-500">{k}:</span> <span className="text-zinc-300">{String(v)}</span></div>
                              ))}
                            </div>
                          )}
                          {needsDeliverable && (
                            <div className="mt-2 border-t border-zinc-800 pt-2">
                              <label className="mb-1 block text-xs font-medium text-zinc-400">Deliverable (released to buyer once paid/fulfilled)</label>
                              <ImageUpload
                                siteId={siteId || ''}
                                value={it.deliverable_url || ''}
                                onChange={(url) => attachDeliverable(o, it, url)}
                                placeholder="Deliverable file URL"
                                endpoint="/upload-file"
                                accept={DELIVERABLE_ACCEPT}
                                kind="file"
                              />
                            </div>
                          )}
                        </div>
                      )
                    })
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
