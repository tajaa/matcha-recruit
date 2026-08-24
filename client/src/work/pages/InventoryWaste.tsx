import { useEffect, useState } from 'react'
import { ArrowLeft, RefreshCw } from 'lucide-react'
import { Button, useToast } from '../../components/ui'
import { askWasteAnalyst, getWasteRollup, listExpiringLots, type WasteRollup } from '../api/inventory'
import { useNavigate } from 'react-router-dom'

function isoDay(offset = 0) { const value = new Date(); value.setDate(value.getDate() + offset); return value.toISOString().slice(0, 10) }
const money = (value: number | null) => value == null ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value)

export default function InventoryWaste() {
  const navigate = useNavigate(); const { toast } = useToast()
  const [rollup, setRollup] = useState<WasteRollup | null>(null)
  const [lots, setLots] = useState<{ id: string; name: string; quantity_remaining: number; expires_on: string; days_to_expiry: number }[]>([])
  const [loading, setLoading] = useState(true)
  const [question, setQuestion] = useState(''); const [answer, setAnswer] = useState('')
  async function load() {
    setLoading(true)
    try { const [next, expiring] = await Promise.all([getWasteRollup(isoDay(-6), isoDay()), listExpiringLots(7)]); setRollup(next); setLots(expiring.lots) }
    catch { toast('Failed to load inventory waste', 'error') } finally { setLoading(false) }
  }
  useEffect(() => { void load() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return <main className="mx-auto max-w-6xl space-y-6 p-6">
    <div className="flex items-center justify-between"><div><Button variant="ghost" size="sm" onClick={() => navigate(-1)}><ArrowLeft size={16} /> Back</Button><h1 className="mt-2 text-2xl font-semibold text-w-text">Inventory waste</h1><p className="text-sm text-w-dim">Last 7 days of recorded loss and perishable risk.</p></div><Button variant="secondary" size="sm" onClick={() => void load()} disabled={loading}><RefreshCw size={16} /> Refresh</Button></div>
    <section className="grid gap-3 sm:grid-cols-3">
      <Metric label="Waste value" value={money(rollup?.total_value ?? null)} />
      <Metric label="Waste / revenue" value={rollup?.waste_pct_of_revenue == null ? '—' : `${(rollup.waste_pct_of_revenue * 100).toFixed(1)}%`} />
      <Metric label="Units discarded" value={String(rollup?.total_units ?? 0)} />
    </section>
    <section className="rounded-xl border border-w-line bg-w-surface p-4"><h2 className="font-medium text-w-text">By reason</h2><div className="mt-3 divide-y divide-w-line">{rollup?.groups.map(group => <div key={group.key} className="flex justify-between py-2 text-sm"><span className="text-w-text">{group.label}</span><span className="text-w-dim">{group.units} units · {money(group.value)}</span></div>) ?? <p className="text-sm text-w-dim">No waste recorded in this period.</p>}</div></section>
    <section className="rounded-xl border border-w-line bg-w-surface p-4"><h2 className="font-medium text-w-text">Expiring within 7 days</h2><div className="mt-3 divide-y divide-w-line">{lots.map(lot => <div key={lot.id} className="flex justify-between py-2 text-sm"><span className="text-w-text">{lot.name}</span><span className="text-w-dim">{lot.quantity_remaining} left · {lot.days_to_expiry}d</span></div>)}{!lots.length && <p className="text-sm text-w-dim">No open lots expiring this week.</p>}</div></section>
    <section className="rounded-xl border border-w-line bg-w-surface p-4"><h2 className="font-medium text-w-text">Ask the waste analyst</h2><div className="mt-3 flex gap-2"><input value={question} onChange={event => setQuestion(event.target.value)} placeholder="What is driving waste?" className="min-w-0 flex-1 rounded-lg border border-w-line bg-w-surface2 px-3 py-2 text-sm text-w-text" /><Button size="sm" disabled={!question.trim()} onClick={() => void askWasteAnalyst(question).then(result => setAnswer(result.answer)).catch(() => toast('Analyst unavailable', 'error'))}>Ask</Button></div>{answer && <p className="mt-3 text-sm text-w-dim">{answer}</p>}</section>
  </main>
}
function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border border-w-line bg-w-surface p-4"><p className="text-xs text-w-dim">{label}</p><p className="mt-1 text-2xl font-semibold text-w-text">{value}</p></div> }
