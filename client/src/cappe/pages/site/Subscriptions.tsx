import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Repeat } from 'lucide-react'
import { cappeApi } from '../../api'
import SurfaceShell, { centsToMoney } from '../../components/SurfaceShell'
import type { CappeShopperSubscription } from '../../types'

const PAGE = 50
const ENDED = ['canceled', 'incomplete_expired']

const STATUS_LABEL: Record<string, string> = {
  active: 'Active', trialing: 'Active', past_due: 'Payment failing', unpaid: 'Unpaid',
  canceled: 'Ended', incomplete: 'Checkout not finished', incomplete_expired: 'Checkout abandoned',
  preparing: 'Checkout not finished', cancel_requested: 'Checkout not finished',
}
const STATUS_STYLE: Record<string, string> = {
  active: 'bg-emerald-500/15 text-emerald-400', trialing: 'bg-emerald-500/15 text-emerald-400',
  past_due: 'bg-amber-500/15 text-amber-400', unpaid: 'bg-red-500/15 text-red-400',
  canceled: 'bg-zinc-800 text-zinc-500',
}

const day = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : null)

export default function Subscriptions() {
  const { siteId } = useParams<{ siteId: string }>()
  const [rows, setRows] = useState<CappeShopperSubscription[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const [showAbandoned, setShowAbandoned] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let live = true
    cappeApi.get<CappeShopperSubscription[]>(
      `/sites/${siteId}/subscriptions?limit=${PAGE}&offset=${offset}${showAbandoned ? '&include_abandoned=true' : ''}`,
    )
      .then((value) => { if (live) { setRows(value); setLoadError(null) } })
      .catch((e) => { if (live) { setRows(null); setLoadError(e instanceof Error ? e.message : 'Could not load subscriptions') } })
    return () => { live = false }
  }, [siteId, offset, showAbandoned, attempt])

  function reload(next: () => void) {
    setRows(null)
    setLoadError(null)
    next()
  }

  async function change(row: CappeShopperSubscription, action: 'cancel' | 'cancel-now' | 'resume') {
    const who = row.customer_name || row.customer_email || 'this customer'
    const question = {
      cancel: `Stop ${who}'s subscription after the period they've paid for? They keep this period's delivery and aren't charged again.`,
      'cancel-now': `End ${who}'s subscription now? It stops immediately and nothing is refunded — refund the latest order from Orders if you need to.`,
      resume: `Keep ${who}'s subscription going? It will renew as normal.`,
    }[action]
    if (!window.confirm(question)) return
    setBusy(row.id)
    setError(null)
    const path = action === 'resume'
      ? `/sites/${siteId}/subscriptions/${row.id}/resume`
      : `/sites/${siteId}/subscriptions/${row.id}/cancel${action === 'cancel-now' ? '?immediate=true' : ''}`
    try {
      const result = await cappeApi.post<{ status: string; cancel_at_period_end?: boolean }>(path)
      setRows((value) => (value || []).map((item) => (item.id === row.id ? { ...item, ...result } : item)))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not change this subscription')
    } finally {
      setBusy(null)
    }
  }

  return (
    <SurfaceShell title="Subscriptions" subtitle="Customers who re-order on a schedule.">
      {error && <p role="alert" className="mb-4 text-sm text-red-400">{error}</p>}
      <label className="mb-3 flex items-center gap-2 text-xs text-zinc-400">
        <input type="checkbox" checked={showAbandoned} onChange={(e) => reload(() => { setOffset(0); setShowAbandoned(e.target.checked) })} className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-950 text-emerald-500" />
        Show checkouts that were never finished
      </label>

      {loadError ? (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">
          Couldn’t load subscriptions. {loadError}
          <button onClick={() => reload(() => setAttempt((n) => n + 1))} className="rounded-lg border border-red-500/40 px-2.5 py-1 text-xs font-medium hover:bg-red-500/10">Try again</button>
        </div>
      ) : rows === null ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : rows.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
          <Repeat className="mx-auto mb-2 h-7 w-7 text-zinc-300" />
          {offset ? 'No more subscriptions.' : 'No subscriptions yet. Turn on “Subscribe & save” on a product in your Shop.'}
        </div>
      ) : (
        <div className="divide-y divide-zinc-800 rounded-2xl border border-zinc-800 bg-zinc-900">
          {rows.map((row) => {
            const ended = ENDED.includes(row.status)
            const live = !ended && !['preparing', 'incomplete', 'cancel_requested'].includes(row.status)
            const renews = day(row.current_period_end)
            return (
              <article key={row.id} className="flex flex-wrap items-start gap-x-4 gap-y-2 px-5 py-4 text-sm">
                <div className="min-w-0 flex-1 basis-60">
                  <div className="truncate font-medium text-zinc-100">
                    {row.customer_name || row.customer_email || 'Customer'}
                    {row.customer_name && row.customer_email && <span className="ml-2 font-normal text-zinc-500">{row.customer_email}</span>}
                  </div>
                  <div className="text-zinc-300">{row.items.map((item) => `${item.quantity} × ${item.title}`).join(', ')}</div>
                  <div className="mt-1 text-xs text-zinc-400">
                    {centsToMoney(row.total_cents, row.currency)} every {row.interval}
                    {live && renews && (row.cancel_at_period_end ? ` · ends ${renews}` : ` · renews ${renews}`)}
                    {(row.order_count ?? 0) > 0 && ` · ${row.order_count} order${row.order_count === 1 ? '' : 's'}`}
                    {row.last_order_at && `, last ${day(row.last_order_at)}`}
                  </div>
                </div>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${STATUS_STYLE[row.status] || 'bg-zinc-800 text-zinc-400'}`}>
                  {row.cancel_at_period_end && live ? 'Ending' : (STATUS_LABEL[row.status] || row.status)}
                </span>
                {live && (
                  <div className="flex flex-wrap gap-2">
                    {row.cancel_at_period_end ? (
                      <button disabled={busy === row.id} onClick={() => change(row, 'resume')} className="rounded-lg border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">Keep it going</button>
                    ) : (
                      <button disabled={busy === row.id} onClick={() => change(row, 'cancel')} className="rounded-lg border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">End after this period</button>
                    )}
                    <button disabled={busy === row.id} onClick={() => change(row, 'cancel-now')} className="rounded-lg border border-red-500/40 px-2.5 py-1 text-xs font-medium text-red-300 hover:bg-red-500/10 disabled:opacity-60">End now</button>
                    {busy === row.id && <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />}
                  </div>
                )}
              </article>
            )
          })}
        </div>
      )}
      {(offset > 0 || (rows?.length ?? 0) === PAGE) && (
        <div className="mt-4 flex justify-center gap-3 text-sm">
          <button disabled={!offset} onClick={() => reload(() => setOffset(Math.max(0, offset - PAGE)))} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-zinc-300 hover:bg-zinc-800 disabled:opacity-40">Previous</button>
          <button disabled={(rows?.length ?? 0) < PAGE} onClick={() => reload(() => setOffset(offset + PAGE))} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-zinc-300 hover:bg-zinc-800 disabled:opacity-40">Next</button>
        </div>
      )}
    </SurfaceShell>
  )
}
