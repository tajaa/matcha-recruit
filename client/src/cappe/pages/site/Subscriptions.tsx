import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { cappeApi } from '../../api'
import SurfaceShell, { centsToMoney } from '../../components/SurfaceShell'
import type { CappeShopperSubscription } from '../../types'

export default function Subscriptions() {
  const { siteId } = useParams<{ siteId: string }>()
  const [rows, setRows] = useState<CappeShopperSubscription[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  useEffect(() => {
    let live = true
    cappeApi.get<CappeShopperSubscription[]>(`/sites/${siteId}/subscriptions?limit=50&offset=${offset}`)
      .then(value => { if (live) { setRows(value); setError('') } })
      .catch(e => { if (live) setError(e instanceof Error ? e.message : 'Could not load subscriptions') })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [siteId, offset])
  async function cancel(row: CappeShopperSubscription) {
    if (!window.confirm('Cancel this subscription at the end of its current billing period?')) return
    setBusy(row.id); setError('')
    try {
      const result = await cappeApi.post<{ status: string; cancel_at_period_end?: boolean }>(`/sites/${siteId}/subscriptions/${row.id}/cancel`)
      setRows(value => value.map(item => item.id === row.id ? { ...item, ...result } : item))
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not cancel subscription') }
    finally { setBusy(null) }
  }
  return <SurfaceShell title="Subscriptions" subtitle="Recurring customer orders">
    {error && <p role="alert" className="mb-4 text-red-400">{error}</p>}
    {loading ? <p>Loading…</p> : rows.length === 0 ? <p className="text-zinc-400">No subscriptions yet.</p> : rows.map(row =>
      <article key={row.id} className="mb-3 rounded-xl border border-zinc-800 p-4 text-zinc-200">
        <p>{row.items.map(item => `${item.quantity} × ${item.title}`).join(', ')}</p>
        <p className="my-2 text-sm text-zinc-400">{centsToMoney(row.total_cents, row.currency)} / {row.interval} · {row.status}{row.cancel_at_period_end ? ' · Ends this period' : ''}</p>
        {!row.cancel_at_period_end && !['canceled', 'incomplete_expired'].includes(row.status) && <button disabled={busy === row.id} onClick={() => cancel(row)} className="rounded border border-zinc-700 px-3 py-1 text-sm">{busy === row.id ? 'Cancelling…' : 'Cancel subscription'}</button>}
      </article>)}
    <div className="flex gap-4 text-zinc-300"><button disabled={!offset} onClick={() => { setLoading(true); setOffset(Math.max(0, offset - 50)) }}>Previous</button><button disabled={rows.length < 50} onClick={() => { setLoading(true); setOffset(offset + 50) }}>Next</button></div>
  </SurfaceShell>
}
