import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Download, Loader2, Landmark } from 'lucide-react'
import { cappeApi } from '../../api'
import SurfaceShell, { centsToMoney } from '../../components/SurfaceShell'
import type { CappeBalance, CappeFinancials } from '../../types'
import { groupFor, presetWindow, type Range } from '../../utils/finances'

// What the store took, refunded and kept, for a window of days. Read-only:
// every number comes from the orders and the refund ledger
// (server/app/cappe/routes/financials.py). Before Stripe's own processing
// fees, which Stripe takes on the store's account and doesn't report to us.

const RANGES: { value: Range; label: string }[] = [
  { value: '7', label: 'Last 7 days' }, { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' }, { value: '365', label: 'Last 12 months' },
  { value: 'custom', label: 'Custom' },
]

function periodLabel(period: string, group: CappeFinancials['group']) {
  const d = new Date(`${period}T00:00:00`)
  return group === 'month'
    ? d.toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
    : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export default function Finances() {
  const { siteId } = useParams<{ siteId: string }>()
  const [range, setRange] = useState<Range>('30')
  const [custom, setCustom] = useState<[string, string]>(() => presetWindow('30'))
  const [data, setData] = useState<{ key: string; value: CappeFinancials } | null>(null)
  const [loadError, setLoadError] = useState<{ key: string; message: string } | null>(null)
  const [balance, setBalance] = useState<CappeBalance | null>(null)
  const [exporting, setExporting] = useState<string | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  const [start, end] = range === 'custom' ? custom : presetWindow(range)
  const group = groupFor(start, end)
  const key = `${siteId}|${start}|${end}|${group}|${attempt}`

  useEffect(() => {
    let live = true
    cappeApi.get<CappeFinancials>(`/sites/${siteId}/financials?start=${start}&end=${end}&group=${group}`)
      .then((value) => { if (live) setData({ key, value }) })
      .catch((e) => { if (live) setLoadError({ key, message: e instanceof Error ? e.message : 'Could not load your finances' }) })
    return () => { live = false }
  }, [siteId, start, end, group, key])

  useEffect(() => {
    cappeApi.get<CappeBalance>('/payments/balance').then(setBalance).catch(() => setBalance(null))
  }, [])

  async function exportCsv(kind: 'orders' | 'refunds') {
    setExportError(null)
    setExporting(kind)
    try {
      await cappeApi.openBlob(`/sites/${siteId}/financials/export.csv?kind=${kind}&start=${start}&end=${end}`,
        `${kind}-${start}-to-${end}.csv`)
    } catch (e) {
      setExportError(e instanceof Error ? e.message : 'Could not export')
    } finally {
      setExporting(null)
    }
  }

  const f = data?.key === key ? data.value : null
  const failed = loadError?.key === key ? loadError.message : null
  const money = (cents: number) => centsToMoney(cents, f?.currency || 'USD')

  return (
    <SurfaceShell title="Finances" subtitle="What your store took, refunded and kept — before Stripe’s processing fees.">
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <label className="text-xs text-zinc-400">
          Period
          <select value={range} onChange={(e) => setRange(e.target.value as Range)}
            className="mt-1 block rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100">
            {RANGES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </label>
        {range === 'custom' && (
          <>
            <label className="text-xs text-zinc-400">From
              <input type="date" value={custom[0]} max={custom[1]} onChange={(e) => e.target.value && setCustom([e.target.value, custom[1]])}
                className="mt-1 block rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100" />
            </label>
            <label className="text-xs text-zinc-400">To
              <input type="date" value={custom[1]} min={custom[0]} onChange={(e) => e.target.value && setCustom([custom[0], e.target.value])}
                className="mt-1 block rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100" />
            </label>
          </>
        )}
        {f?.export_enabled && (
          <div className="ml-auto flex gap-2">
            {(['orders', 'refunds'] as const).map((kind) => (
              <button key={kind} onClick={() => exportCsv(kind)} disabled={exporting !== null}
                className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">
                {exporting === kind ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                Export {kind} (CSV)
              </button>
            ))}
          </div>
        )}
      </div>
      {exportError && <p role="alert" className="mb-4 text-sm text-red-400">{exportError}</p>}

      {failed ? (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">
          Couldn’t load your finances. {failed}
          <button onClick={() => setAttempt((n) => n + 1)} className="rounded-lg border border-red-500/40 px-2.5 py-1 text-xs font-medium hover:bg-red-500/10">Try again</button>
        </div>
      ) : !f ? (
        <Loader2 className="h-5 w-5 animate-spin text-zinc-400" aria-label="Loading" />
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Sales" value={money(f.gross_cents)} hint={`${f.orders} order${f.orders === 1 ? '' : 's'}`} />
            <Stat label="Refunds" value={f.refunds_cents ? `−${money(f.refunds_cents)}` : money(0)} hint={`${f.refund_count} refund${f.refund_count === 1 ? '' : 's'}`} tone="red" />
            <Stat label="Gummfit fees" value={f.platform_fee_cents ? `−${money(f.platform_fee_cents)}` : money(0)} hint="On card orders" />
            <Stat label="Net" value={money(f.net_cents)} hint={`Average order ${money(f.average_order_cents)}`} tone="lime" />
          </dl>
          <p className="mt-2 text-xs text-zinc-500">
            Sales include {money(f.tax_cents)} tax and {money(f.shipping_cents)} shipping you collected.
            {f.other_currency_orders > 0 && ` ${f.other_currency_orders} order${f.other_currency_orders === 1 ? '' : 's'} in another currency (from before you changed it) aren't counted here.`}
          </p>

          <SalesChart f={f} money={money} />

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <section className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <h2 className="mb-3 text-sm font-semibold text-zinc-100">Best sellers</h2>
              {f.top_products.length === 0 ? (
                <p className="text-sm text-zinc-500">No sales in this period.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs text-zinc-500"><th className="pb-1 font-normal">Item</th><th className="pb-1 text-right font-normal">Sold</th><th className="pb-1 text-right font-normal">Revenue</th></tr></thead>
                  <tbody>
                    {f.top_products.map((p) => (
                      <tr key={`${p.product_id}-${p.title}`} className="border-t border-zinc-800 text-zinc-300">
                        <td className="py-1.5 pr-2">{p.title}</td>
                        <td className="py-1.5 text-right tabular-nums">{p.units}</td>
                        <td className="py-1.5 text-right tabular-nums">{money(p.revenue_cents)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
            <BalanceCard balance={balance} />
          </div>
          {!f.export_enabled && (
            <p className="mt-4 text-xs text-zinc-500">Exporting orders and refunds to CSV comes with paid plans.</p>
          )}
        </>
      )}
    </SurfaceShell>
  )
}

function Stat({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: 'red' | 'lime' }) {
  const color = tone === 'red' ? 'text-red-300' : tone === 'lime' ? 'text-lime-300' : 'text-zinc-50'
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <dt className="text-xs text-zinc-400">{label}</dt>
      <dd className={`mt-1 text-xl font-semibold tabular-nums ${color}`}>{value}</dd>
      <dd className="mt-0.5 text-xs text-zinc-500">{hint}</dd>
    </div>
  )
}

/** Sales per period as bars, refunds in red beneath each. A table of the same
 *  numbers is there for screen readers. */
function SalesChart({ f, money }: { f: CappeFinancials; money: (c: number) => string }) {
  const max = Math.max(1, ...f.series.map((p) => Math.max(p.gross_cents, p.refunds_cents)))
  return (
    <section className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <h2 className="mb-3 text-sm font-semibold text-zinc-100">Sales by {f.group}</h2>
      <div className="flex h-40 items-end gap-px" aria-hidden="true">
        {f.series.map((p) => (
          <div key={p.period} className="flex h-full flex-1 flex-col justify-end"
            title={`${periodLabel(p.period, f.group)}: ${money(p.gross_cents)} from ${p.orders} order${p.orders === 1 ? '' : 's'}${p.refunds_cents ? `, ${money(p.refunds_cents)} refunded` : ''}`}>
            <div className="rounded-t-sm bg-lime-400/80" style={{ height: `${(p.gross_cents / max) * 100}%` }} />
            {p.refunds_cents > 0 && <div className="bg-red-400/80" style={{ height: `${(p.refunds_cents / max) * 100}%` }} />}
          </div>
        ))}
      </div>
      {f.series.length > 0 && (
        <div className="mt-1 flex justify-between text-[11px] text-zinc-500" aria-hidden="true">
          <span>{periodLabel(f.series[0].period, f.group)}</span>
          <span>{periodLabel(f.series[f.series.length - 1].period, f.group)}</span>
        </div>
      )}
      <table className="sr-only">
        <caption>Sales and refunds by {f.group}</caption>
        <thead><tr><th>Period</th><th>Orders</th><th>Sales</th><th>Refunds</th></tr></thead>
        <tbody>
          {f.series.map((p) => (
            <tr key={p.period}><td>{periodLabel(p.period, f.group)}</td><td>{p.orders}</td><td>{money(p.gross_cents)}</td><td>{money(p.refunds_cents)}</td></tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function BalanceCard({ balance }: { balance: CappeBalance | null }) {
  const sum = (rows: CappeBalance['available']) => rows.map((r) => centsToMoney(r.amount_cents, r.currency)).join(' + ') || centsToMoney(0)
  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-100"><Landmark className="h-4 w-4 text-lime-400" /> Stripe balance</h2>
      {balance === null ? (
        <p className="text-sm text-zinc-500">Couldn’t reach Stripe for your balance right now.</p>
      ) : !balance.connected ? (
        <p className="text-sm text-zinc-500">Connect Stripe (on the Orders page) to take card payments and see payouts here.</p>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div><dt className="text-xs text-zinc-400">Available</dt><dd className="font-semibold text-zinc-50">{sum(balance.available)}</dd></div>
            <div><dt className="text-xs text-zinc-400">On its way</dt><dd className="font-semibold text-zinc-50">{sum(balance.pending)}</dd></div>
          </dl>
          <h3 className="mb-1 mt-4 text-xs font-medium text-zinc-400">Recent payouts</h3>
          {balance.payouts.length === 0 ? (
            <p className="text-sm text-zinc-500">No payouts yet.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {balance.payouts.map((p) => (
                <li key={p.id} className="flex justify-between text-zinc-300">
                  <span>{p.arrival_date ? new Date(p.arrival_date * 1000).toLocaleDateString() : '—'} · {p.status.replace('_', ' ')}</span>
                  <span className="tabular-nums">{centsToMoney(p.amount_cents, p.currency)}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
