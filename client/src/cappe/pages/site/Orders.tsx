import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Receipt, ChevronDown, ChevronRight, Calendar, Check, X, Clock, Truck, Undo2, AlertTriangle, Search, PackageCheck } from 'lucide-react'
import { cappeApi } from '../../api'
import SurfaceShell, { centsToMoney } from '../../components/SurfaceShell'
import StripeConnectCard from '../../components/StripeConnectCard'
import ImageUpload from '../../components/ImageUpload'
import type { CappeOrder, CappeOrderItem, CappeRefundBody } from '../../types'
import { parseMoneyCents } from '../../utils/money'

// What an owner may move an order to by hand. Mirrors the server's
// `order_lifecycle.ALLOWED_TRANSITIONS` — the server is the authority and
// refuses anything else with a reason; this only keeps impossible choices out
// of the menu. `refunded` is deliberately absent everywhere: it is reached
// through the Refund button, which actually returns the money.
const NEXT_STATUSES: Record<string, string[]> = {
  pending: ['paid', 'cancelled'],
  paid: ['fulfilled'],
  fulfilled: ['paid'],
}
const STATUS_ACTION_LABEL: Record<string, string> = {
  paid: 'Mark paid',
  cancelled: 'Cancel order',
  fulfilled: 'Mark fulfilled',
}
const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: '', label: 'All orders' },
  { value: 'pending', label: 'Pending' },
  { value: 'paid', label: 'Paid — to fulfil' },
  { value: 'fulfilled', label: 'Fulfilled' },
  { value: 'refunded', label: 'Refunded' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'declined', label: 'Declined' },
]
/** Orders fetched per page. The list used to load every order ever taken. */
const ORDERS_PAGE = 50
/** Paid by card through the storefront — the refund goes back through Stripe. */
const paidByCard = (o: CappeOrder) => (o.payment_ref || '').startsWith('pi_')
/** Statuses that hold goods on their way to (or with) the customer. */
const shipping = (o: CappeOrder) => o.status === 'paid' || o.status === 'fulfilled'
/** What can still be refunded: the total less every refund so far. */
const refundableLeft = (o: CappeOrder) => Math.max(0, (o.total_cents ?? o.subtotal_cents) - (o.refunded_cents ?? 0))
const REFUND_SOURCE: Record<string, string> = {
  dashboard: 'Refunded here', manual: 'Recorded here (paid outside Stripe)', stripe: 'Refunded in Stripe',
  dispute: 'Lost dispute', legacy: 'Refunded',
}
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

function ordersPath(siteId: string, status: string, q: string, offset: number) {
  const params = new URLSearchParams({ limit: String(ORDERS_PAGE), offset: String(offset) })
  if (status) params.set('status', status)
  if (q) params.set('q', q)
  return `/sites/${siteId}/orders?${params.toString()}`
}

export default function Orders() {
  const { siteId } = useParams<{ siteId: string }>()
  // The list is stored with the filter it was loaded for, so changing the
  // filter shows the spinner (a stale key reads as "not loaded") without the
  // effect having to reset anything itself.
  const [page, setPage] = useState<{ key: string; orders: CappeOrder[] } | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')       // `search`, debounced
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [refunding, setRefunding] = useState<string | null>(null)
  const [refundTarget, setRefundTarget] = useState<CappeOrder | null>(null)
  // Each load is numbered so a slow answer for an old filter can't overwrite
  // the list for the current one.
  const loadSeq = useRef(0)
  const key = `${statusFilter}|${query}`
  const orders = page && page.key === key ? page.orders : null
  function setOrders(update: (os: CappeOrder[]) => CappeOrder[]) {
    setPage((p) => (p ? { ...p, orders: update(p.orders) } : p))
  }

  useEffect(() => {
    const t = setTimeout(() => setQuery(search.trim()), 300)
    return () => clearTimeout(t)
  }, [search])

  useEffect(() => {
    const seq = ++loadSeq.current
    const loading = `${statusFilter}|${query}`
    cappeApi
      .get<CappeOrder[]>(ordersPath(siteId || '', statusFilter, query, 0))
      .then((rows) => {
        if (seq !== loadSeq.current) return
        setPage({ key: loading, orders: rows })
        setHasMore(rows.length === ORDERS_PAGE)
      })
      .catch((e) => {
        if (seq !== loadSeq.current) return
        setPage({ key: loading, orders: [] })
        setError(e instanceof Error ? e.message : 'Failed to load orders')
      })
  }, [siteId, statusFilter, query])

  async function loadMore() {
    if (!orders) return
    const seq = loadSeq.current
    setLoadingMore(true)
    try {
      const more = await cappeApi.get<CappeOrder[]>(ordersPath(siteId || '', statusFilter, query, orders.length))
      if (seq !== loadSeq.current) return
      // An order that moved up the list between pages must not show twice.
      setOrders((os) => {
        const seen = new Set(os.map((o) => o.id))
        return [...os, ...more.filter((o) => !seen.has(o.id))]
      })
      setHasMore(more.length === ORDERS_PAGE)
    } catch (e) {
      fail(e, 'Could not load more orders')
    } finally {
      setLoadingMore(false)
    }
  }

  // Every mutation below moves real money or a customer's order. An unhandled
  // rejection here left the row showing its old status with nothing on screen
  // to say the change never reached the server — the owner walks away believing
  // they accepted an order they did not. Failures land in the banner at the top
  // of the page (same `error` state the initial load uses).
  function fail(e: unknown, fallback: string) {
    setError(e instanceof Error ? e.message : fallback)
  }

  /** Replace one order in place, keeping the lines already loaded for it. */
  function replace(updated: CappeOrder) {
    setOrders((os) => os.map((x) => (x.id === updated.id
      ? { ...updated, items: updated.items?.length ? updated.items : x.items, items_summary: x.items_summary, item_count: x.item_count }
      : x)))
  }

  async function toggle(order: CappeOrder) {
    if (openId === order.id) { setOpenId(null); return }
    setOpenId(order.id)
    if (order.items.length === 0) {
      try {
        const full = await cappeApi.get<CappeOrder>(`/sites/${siteId}/orders/${order.id}`)
        replace(full)
      } catch (e) {
        setOpenId(null)  // otherwise the row stays open on a permanent spinner
        fail(e, 'Could not load this order')
      }
    }
  }

  async function setStatus(order: CappeOrder, status: string) {
    if (!status || status === order.status) return
    if (status === 'paid' && order.status === 'pending' && !window.confirm(
      'Mark this order as paid?\n\nUse this only for money you collected yourself (cash, invoice). '
      + "The customer's card payment page will be closed.",
    )) return
    if (status === 'cancelled' && !window.confirm(
      'Cancel this order? Its stock and any booked time slots are released.',
    )) return
    setError(null)
    try {
      replace(await cappeApi.patch<CappeOrder>(`/sites/${siteId}/orders/${order.id}`, { status }))
    } catch (e) {
      fail(e, 'Could not change the order status')
    }
  }

  async function refundOrder(order: CappeOrder, body: CappeRefundBody) {
    setRefundTarget(null)
    setError(null)
    setRefunding(order.id)
    try {
      replace(await cappeApi.post<CappeOrder>(`/sites/${siteId}/orders/${order.id}/refund`, body))
    } catch (e) {
      fail(e, 'Could not refund this order')
    } finally {
      setRefunding(null)
    }
  }

  async function acceptOrder(order: CappeOrder) {
    setError(null)
    try {
      replace(await cappeApi.post<CappeOrder>(`/sites/${siteId}/orders/${order.id}/accept`))
    } catch (e) {
      fail(e, 'Could not accept this order')
    }
  }
  async function declineOrder(order: CappeOrder) {
    // prompt() returns null on Cancel and '' on an empty OK. Only Cancel backs
    // out — `?? undefined` used to fold it into "no reason" and decline anyway.
    const answer = window.prompt('Reason for declining (optional, shown to the customer):')
    if (answer === null) return
    const reason = answer.trim() || undefined
    setError(null)
    try {
      replace(await cappeApi.post<CappeOrder>(`/sites/${siteId}/orders/${order.id}/decline`, { reason }))
    } catch (e) {
      fail(e, 'Could not decline this order')
    }
  }

  async function attachDeliverable(order: CappeOrder, item: CappeOrderItem, url: string) {
    setError(null)
    try {
      const updated = await cappeApi.patch<CappeOrderItem>(
        `/sites/${siteId}/orders/${order.id}/items/${item.id}`, { deliverable_url: url },
      )
      setOrders((os) => os.map((x) =>
        x.id === order.id ? { ...x, items: x.items.map((i) => (i.id === item.id ? updated : i)) } : x,
      ))
    } catch (e) {
      fail(e, 'Could not attach the deliverable')
    }
  }

  const filtered = Boolean(statusFilter || query)

  return (
    <SurfaceShell title="Orders" subtitle="Orders placed through your storefront.">
      <StripeConnectCard />
      {error && <p role="alert" className="mb-4 text-sm text-red-400">{error}</p>}

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-400 focus-within:border-emerald-500">
          <Search className="h-4 w-4 shrink-0" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by customer, email or receipt number"
            aria-label="Search orders"
            className="w-full bg-transparent text-zinc-100 placeholder:text-zinc-500 outline-none"
          />
        </label>
        <select
          value={statusFilter}
          onChange={(e) => { setError(null); setOpenId(null); setStatusFilter(e.target.value) }}
          aria-label="Show orders"
          className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100"
        >
          {STATUS_FILTERS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
        </select>
      </div>

      {orders === null ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : orders.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
          <Receipt className="mx-auto mb-2 h-7 w-7 text-zinc-300" /> {filtered ? 'No orders match.' : 'No orders yet.'}
        </div>
      ) : (
        <div className="divide-y divide-zinc-800 rounded-2xl border border-zinc-800 bg-zinc-900">
          {orders.map((o) => (
            <div key={o.id}>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3">
                <button onClick={() => toggle(o)} aria-label={openId === o.id ? 'Hide order details' : 'Show order details'} className="text-zinc-400 hover:text-zinc-300">
                  {openId === o.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </button>
                <div className="min-w-0 flex-1 basis-48">
                  <div className="truncate text-sm font-medium text-zinc-100">
                    {o.customer_name || o.customer_email || 'No email'}
                    {o.customer_name && o.customer_email && <span className="ml-2 font-normal text-zinc-500">{o.customer_email}</span>}
                  </div>
                  {o.items_summary && (
                    <div className="truncate text-xs text-zinc-300">
                      {o.items_summary}
                      {(o.item_count ?? 0) > 3 && <span className="text-zinc-500"> · {o.item_count} items</span>}
                    </div>
                  )}
                  <div className="text-xs text-zinc-400">
                    {new Date(o.created_at).toLocaleString()}{o.receipt_number ? ` · ${o.receipt_number}` : ''}
                  </div>
                </div>
                <div className="text-sm font-medium text-zinc-300">{centsToMoney(o.total_cents ?? o.subtotal_cents, o.currency)}</div>
                {o.requires_approval && o.status === 'pending' && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-400"><Clock className="h-3 w-3" /> needs approval</span>
                )}
                {!o.requires_approval && o.status === 'pending' && o.pay_by && (
                  <span
                    title="You accepted this order. The customer was emailed a link to pay; if they don't by then, it's released and its stock returned."
                    className="inline-flex items-center gap-1 rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase text-sky-400"
                  >
                    <Clock className="h-3 w-3" /> awaiting payment until {new Date(o.pay_by).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                  </span>
                )}
                {o.dispute_status && (
                  <span title="A chargeback was opened against this order — respond in your Stripe dashboard." className="inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase text-red-400"><AlertTriangle className="h-3 w-3" /> dispute: {o.dispute_status.replace(/_/g, ' ')}</span>
                )}
                {o.status !== 'refunded' && (o.refunded_cents ?? 0) > 0 && (
                  <span className="rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-red-300">{centsToMoney(o.refunded_cents ?? 0, o.currency)} refunded</span>
                )}
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[o.status]}`}>{o.status}</span>
                {shipping(o) && (
                  <button
                    onClick={() => cappeApi.openBlob(`/sites/${siteId}/orders/${o.id}/receipt.pdf`, `${o.receipt_number || `receipt-${o.id}`}.pdf`).catch((e) => setError(e instanceof Error ? e.message : 'Could not open receipt'))}
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
                  <>
                    {(NEXT_STATUSES[o.status] || []).length > 0 && (
                      <select
                        value=""
                        aria-label={`Change status of order from ${o.customer_email || 'customer'}`}
                        onChange={(e) => setStatus(o, e.target.value)}
                        className="rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-2 py-1 text-xs"
                      >
                        <option value="">Change status…</option>
                        {NEXT_STATUSES[o.status].map((s) => <option key={s} value={s}>{STATUS_ACTION_LABEL[s] || s}</option>)}
                      </select>
                    )}
                    {/* A renewal order paid through Stripe now carries its payment
                        intent and is refunded like any card order; one without
                        it (recorded before that) is refunded in Stripe. */}
                    {shipping(o) && (!o.subscription_id || paidByCard(o)) && refundableLeft(o) > 0 && (
                      <button
                        onClick={() => setRefundTarget(o)}
                        disabled={refunding === o.id}
                        title={paidByCard(o) ? "Return all or part of the money to the customer's card" : 'Record a refund you made yourself'}
                        className="flex items-center gap-1 rounded-lg border border-red-500/40 px-2.5 py-1 text-xs font-medium text-red-300 hover:bg-red-500/10 disabled:opacity-60"
                      >
                        {refunding === o.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Undo2 className="h-3.5 w-3.5" />} Refund
                      </button>
                    )}
                  </>
                )}
              </div>
              {openId === o.id && (
                <div className="space-y-2 bg-zinc-950 px-5 py-3 sm:px-12">
                  {o.subscription_id && <span className="rounded bg-emerald-500/15 px-2 py-1 text-xs text-emerald-400">Subscription</span>}
                  {o.note && (
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-xs text-zinc-300">
                      <div className="mb-1 font-medium text-zinc-400">Customer note</div>
                      <p className="whitespace-pre-wrap">{o.note}</p>
                    </div>
                  )}
                  {o.shipping_address && (
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-xs text-zinc-300">
                      <div className="mb-1 flex items-center gap-1.5 font-medium text-zinc-400"><Truck className="h-3.5 w-3.5" /> Ship to</div>
                      {o.shipping_address.name && <div>{o.shipping_address.name}</div>}
                      {o.shipping_address.address?.line1 && <div>{o.shipping_address.address.line1}</div>}
                      {o.shipping_address.address?.line2 && <div>{o.shipping_address.address.line2}</div>}
                      <div>
                        {[o.shipping_address.address?.city, o.shipping_address.address?.state].filter(Boolean).join(', ')}{' '}
                        {o.shipping_address.address?.postal_code || ''}
                      </div>
                      {o.shipping_address.address?.country && <div>{o.shipping_address.address.country}</div>}
                    </div>
                  )}
                  {shipping(o) && (o.shipping_address != null || o.items.some((i) => i.fulfillment === 'physical')) ? (
                    <TrackingEditor siteId={siteId || ''} order={o} onSaved={replace} />
                  ) : (o.carrier || o.tracking_number) ? (
                    <p className="text-xs text-zinc-400">Tracking: {[o.carrier, o.tracking_number].filter(Boolean).join(' ')}</p>
                  ) : null}
                  {o.items.length === 0 ? (
                    <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
                  ) : (
                    o.items.map((it) => {
                      const answers = Object.entries(it.intake_answers || {}).filter(([, v]) => v != null && v !== '')
                      const needsDeliverable = it.fulfillment === 'service' || it.fulfillment === 'digital'
                      return (
                        <div key={it.id} className="rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-sm">
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex min-w-0 items-center gap-2">
                              <span className="truncate text-zinc-200">{it.quantity} × {it.title}</span>
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
                  {o.items.length > 0 && <Totals order={o} />}
                  {(o.refunds?.length ?? 0) > 0 && <RefundHistory order={o} />}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {orders && hasMore && (
        <div className="mt-4 flex justify-center">
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60"
          >
            {loadingMore && <Loader2 className="h-4 w-4 animate-spin" />} Load more orders
          </button>
        </div>
      )}
      {refundTarget && (
        <RefundDialog
          order={refundTarget}
          onCancel={() => setRefundTarget(null)}
          onConfirm={(body) => refundOrder(refundTarget, body)}
          loadOrder={async () => {
            const full = await cappeApi.get<CappeOrder>(`/sites/${siteId}/orders/${refundTarget.id}`)
            replace(full)
            return full
          }}
        />
      )}
    </SurfaceShell>
  )
}

/** Subtotal → total as the customer was charged, plus anything refunded. */
function Totals({ order: o }: { order: CappeOrder }) {
  // `subtotal_cents` is after a promo code; show the goods before it, then the code.
  const discount = o.discount_cents ?? 0
  const rows: [string, number][] = [['Subtotal', o.subtotal_cents + discount]]
  if (discount) rows.push([o.promo_code ? `Discount (${o.promo_code})` : 'Discount', -discount])
  if (o.tax_cents) rows.push(['Tax', o.tax_cents])
  if (o.shipping_cents) rows.push(['Shipping', o.shipping_cents])
  return (
    <dl className="ml-auto max-w-xs space-y-0.5 pt-1 text-xs">
      {rows.map(([label, cents]) => (
        <div key={label} className="flex justify-between gap-6 text-zinc-400"><dt>{label}</dt><dd>{cents < 0 ? '−' : ''}{centsToMoney(Math.abs(cents), o.currency)}</dd></div>
      ))}
      <div className="flex justify-between gap-6 border-t border-zinc-800 pt-1 font-medium text-zinc-200">
        <dt>Total</dt><dd>{centsToMoney(o.total_cents ?? o.subtotal_cents, o.currency)}</dd>
      </div>
      {(o.refunded_cents ?? 0) > 0 && (
        <div className="flex justify-between gap-6 text-red-300"><dt>Refunded</dt><dd>−{centsToMoney(o.refunded_cents ?? 0, o.currency)}</dd></div>
      )}
    </dl>
  )
}

/** The order's refunds, oldest first: how much, where it was made, why. */
function RefundHistory({ order: o }: { order: CappeOrder }) {
  return (
    <div className="ml-auto max-w-sm rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-xs">
      <div className="mb-1 font-medium text-zinc-400">Refunds</div>
      <ul className="space-y-1">
        {(o.refunds ?? []).map((r) => (
          <li key={r.id} className="flex flex-wrap justify-between gap-x-4 text-zinc-300">
            <span>
              {new Date(r.created_at).toLocaleDateString()} · {REFUND_SOURCE[r.source] ?? r.source}
              {r.status === 'pending' && <span className="text-amber-300"> · processing</span>}
              {r.status === 'failed' && <span className="text-red-300"> · failed{r.failure ? `: ${r.failure}` : ''}</span>}
              {r.reason && <span className="block text-zinc-500">{r.reason}</span>}
            </span>
            <span className={r.status === 'succeeded' ? 'text-red-300' : 'text-zinc-500 line-through'}>
              −{centsToMoney(r.amount_cents, o.currency)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Confirm a refund — all of what's left, or part of it — and say which goods
 *  come back to the shelf. A full refund's default matches the server's: back
 *  in stock unless the order was already fulfilled (a refund for a parcel that
 *  was lost or kept used to add stock that was never coming back). A part
 *  refund restocks exactly the units chosen, nothing else. */
function RefundDialog({ order, onCancel, onConfirm, loadOrder }: {
  order: CappeOrder
  onCancel: () => void
  onConfirm: (body: CappeRefundBody) => void
  /** The order with its lines, for choosing which units come back. */
  loadOrder: () => Promise<CappeOrder>
}) {
  const left = refundableLeft(order)
  const [part, setPart] = useState(false)
  const [restock, setRestock] = useState(order.status !== 'fulfilled')
  const [amount, setAmount] = useState((left / 100).toFixed(2))
  const [reason, setReason] = useState('')
  const [lines, setLines] = useState<CappeOrder['items'] | null>(order.items.length ? order.items : null)
  const [back, setBack] = useState<Record<string, string>>({})
  const [loadError, setLoadError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const card = paidByCard(order)
  const fullText = centsToMoney(left, order.currency)
  const partCents = parseMoneyCents(amount)
  const label = part && partCents !== null ? centsToMoney(partCents, order.currency) : fullText
  const physical = (lines ?? []).filter((it) => it.fulfillment === 'physical'
    && it.quantity - (it.restocked_quantity ?? 0) > 0)

  function choosePart() {
    setPart(true)
    if (lines === null) {
      loadOrder().then((full) => setLines(full.items)).catch(() => setLoadError('Couldn’t load the items, so none can be restocked from here.'))
    }
  }

  function confirm() {
    setError(null)
    const why = reason.trim() || undefined
    if (!part) { onConfirm({ restock, ...(why ? { reason: why } : {}) }); return }
    if (partCents === null || partCents <= 0) { setError('Enter the amount to refund, e.g. 12.50'); return }
    if (partCents > left) { setError(`At most ${fullText} is left to refund.`); return }
    const chosen = []
    for (const it of physical) {
      const raw = (back[it.id] ?? '').trim()
      if (!raw) continue
      const n = Number(raw)
      const max = it.quantity - (it.restocked_quantity ?? 0)
      if (!Number.isInteger(n) || n < 0 || n > max) { setError(`Return between 0 and ${max} of “${it.title}”.`); return }
      if (n > 0) chosen.push({ item_id: it.id, quantity: n })
    }
    onConfirm({ amount_cents: partCents, lines: chosen, ...(why ? { reason: why } : {}) })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onCancel}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="refund-title"
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl border border-zinc-700 bg-zinc-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="refund-title" className="text-lg font-semibold text-zinc-50">
          {card ? `Refund ${label}?` : 'Record a refund?'}
        </h2>
        <p className="mt-2 text-sm text-zinc-400">
          {card
            ? "It goes back to the customer's card through Stripe. This can't be undone."
            : `It wasn't paid by card here, so no money moves — return ${label} to the customer yourself. This only updates your records.`}
        </p>
        <div className="mt-4 flex gap-1 rounded-lg border border-zinc-700 p-0.5 text-xs">
          <button type="button" onClick={() => setPart(false)} aria-pressed={!part}
            className={`flex-1 rounded-md px-2 py-1.5 ${!part ? 'bg-zinc-100 font-semibold text-zinc-900' : 'text-zinc-400 hover:text-zinc-200'}`}>
            Everything left ({fullText})
          </button>
          <button type="button" onClick={choosePart} aria-pressed={part}
            className={`flex-1 rounded-md px-2 py-1.5 ${part ? 'bg-zinc-100 font-semibold text-zinc-900' : 'text-zinc-400 hover:text-zinc-200'}`}>
            Part of it
          </button>
        </div>
        {!part ? (
          <label className="mt-4 flex items-start gap-2 text-sm text-zinc-300">
            <input
              type="checkbox"
              checked={restock}
              onChange={(e) => setRestock(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-zinc-600 bg-zinc-950 text-emerald-500"
            />
            <span>
              Put the items back in stock
              <span className="block text-xs text-zinc-500">
                {order.status === 'fulfilled'
                  ? 'This order was fulfilled. Tick this only if the goods were returned to you.'
                  : 'Untick if the goods are not coming back. Items that don’t track stock are unaffected.'}
              </span>
            </span>
          </label>
        ) : (
          <div className="mt-4 space-y-3">
            <label className="block text-xs text-zinc-400">
              Amount ({order.currency})
              <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal"
                className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500" />
            </label>
            {loadError && <p className="text-xs text-amber-300">{loadError}</p>}
            {lines === null && !loadError && <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />}
            {physical.length > 0 && (
              <fieldset className="space-y-1.5">
                <legend className="mb-1 text-xs text-zinc-400">Back in stock (only what was returned to you)</legend>
                {physical.map((it) => {
                  const max = it.quantity - (it.restocked_quantity ?? 0)
                  return (
                    <label key={it.id} className="flex items-center justify-between gap-3 text-sm text-zinc-300">
                      <span className="truncate">{it.title}</span>
                      <span className="flex items-center gap-1.5 text-xs text-zinc-500">
                        <input value={back[it.id] ?? ''} onChange={(e) => setBack({ ...back, [it.id]: e.target.value })}
                          inputMode="numeric" placeholder="0" aria-label={`Units of ${it.title} back in stock`}
                          className="w-14 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-right text-sm text-zinc-100 outline-none focus:border-emerald-500" />
                        of {max}
                      </span>
                    </label>
                  )
                })}
              </fieldset>
            )}
          </div>
        )}
        <label className="mt-4 block text-xs text-zinc-400">
          Reason (optional, for your records)
          <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} placeholder="e.g. Arrived damaged"
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500" />
        </label>
        {error && <p role="alert" className="mt-3 text-xs text-red-400">{error}</p>}
        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onCancel} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800">Keep order</button>
          <button
            onClick={confirm}
            className="flex items-center gap-1.5 rounded-lg bg-red-500 px-4 py-2 text-sm font-semibold text-white hover:bg-red-400"
          >
            <Undo2 className="h-4 w-4" /> {card ? `Refund ${label}` : 'Mark refunded'}
          </button>
        </div>
      </div>
    </div>
  )
}

function TrackingEditor({ siteId, order, onSaved }: {
  siteId: string
  order: CappeOrder
  onSaved: (o: CappeOrder) => void
}) {
  const [carrier, setCarrier] = useState(order.carrier || '')
  const [tracking, setTracking] = useState(order.tracking_number || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // `fulfil` saves the tracking AND marks a paid order fulfilled in one PATCH
  // — the usual moment a parcel gets its tracking number.
  async function save(fulfil: boolean) {
    setSaving(true); setError(null)
    try {
      const updated = await cappeApi.patch<CappeOrder>(
        `/sites/${siteId}/orders/${order.id}`,
        {
          carrier: carrier.trim() || null,
          tracking_number: tracking.trim() || null,
          ...(fulfil ? { status: 'fulfilled' } : {}),
        },
      )
      onSaved({ ...updated, items: order.items })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save tracking')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 p-3">
      <input
        value={carrier}
        onChange={(e) => setCarrier(e.target.value)}
        maxLength={40}
        placeholder="Carrier — e.g. USPS"
        aria-label="Carrier"
        className="w-36 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100 placeholder:text-zinc-500"
      />
      <input
        value={tracking}
        onChange={(e) => setTracking(e.target.value)}
        maxLength={120}
        placeholder="Tracking number"
        aria-label="Tracking number"
        className="min-w-0 flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100 placeholder:text-zinc-500"
      />
      <button
        onClick={() => save(false)}
        disabled={saving}
        className="flex items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60"
      >
        {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Save
      </button>
      {order.status === 'paid' && (
        <button
          onClick={() => save(true)}
          disabled={saving}
          className="flex items-center gap-1 rounded-lg bg-emerald-500 px-2.5 py-1 text-xs font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60"
        >
          <PackageCheck className="h-3.5 w-3.5" /> Save &amp; mark fulfilled
        </button>
      )}
      {error && <span className="text-xs text-red-400">{error}</span>}
      <p className="basis-full text-[11px] text-zinc-500">The customer is emailed when you add a tracking number or mark the order fulfilled.</p>
    </div>
  )
}
