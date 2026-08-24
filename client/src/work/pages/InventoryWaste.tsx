import { useEffect, useState } from 'react'
import { Package, RefreshCw } from 'lucide-react'
import { Button, Select, useToast } from '../../components/ui'
import {
  askWasteAnalyst, getLatestForecastRun, getWasteRollup, getWasteVariance,
  listExpiringLots, listItems, recordWaste, type ForecastLine, type InventoryItem,
  type WasteReason, type WasteRollup,
} from '../api/inventory'
import { useMe } from '../../hooks/useMe'
import InventoryWasteGuide from '../components/inventory/InventoryWasteGuide'
import InventoryNavigation from '../components/inventory/InventoryNavigation'

function isoDay(offset = 0) { const value = new Date(); value.setDate(value.getDate() + offset); return value.toISOString().slice(0, 10) }
const money = (value: number | null) => value == null ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value)
const reasons: { value: WasteReason; label: string }[] = [
  { value: 'spoilage', label: 'Spoilage' }, { value: 'expired', label: 'Expired' }, { value: 'prep_error', label: 'Prep error' }, { value: 'overproduction', label: 'Overproduction' }, { value: 'breakage', label: 'Breakage' }, { value: 'contamination', label: 'Contamination' }, { value: 'theft', label: 'Theft' }, { value: 'comp', label: 'Comp' }, { value: 'recall', label: 'Recall' }, { value: 'unknown', label: 'Unknown' },
]

export default function InventoryWaste() {
  const { toast } = useToast(); const { hasFeature, me } = useMe()
  const canSales = hasFeature('sales_intake')
  const canForecast = canSales && hasFeature('inventory_forecasting')
  const [reasonRollup, setReasonRollup] = useState<WasteRollup | null>(null)
  const [categoryRollup, setCategoryRollup] = useState<WasteRollup | null>(null)
  const [itemRollup, setItemRollup] = useState<WasteRollup | null>(null)
  const [lots, setLots] = useState<{ id: string; name: string; quantity_remaining: number; expires_on: string; days_to_expiry: number }[]>([])
  const [variance, setVariance] = useState<{ item_id: string; name: string; theoretical_usage: number | null; actual_usage: number | null; usage_variance: number | null }[]>([])
  const [parLines, setParLines] = useState<ForecastLine[]>([])
  const [items, setItems] = useState<InventoryItem[]>([])
  const [loading, setLoading] = useState(true); const [recording, setRecording] = useState(false)
  const [question, setQuestion] = useState(''); const [answer, setAnswer] = useState('')
  const [wasteItem, setWasteItem] = useState(''); const [wasteQuantity, setWasteQuantity] = useState(''); const [wasteReason, setWasteReason] = useState<WasteReason>('spoilage')
  const [guideOpen, setGuideOpen] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const start = isoDay(-6); const end = isoDay()
      const forecastRequest = canForecast ? getLatestForecastRun() : Promise.resolve(null)
      const usageRequest = canSales ? getWasteVariance(start, end) : Promise.resolve({ lines: [] })
      const [byReason, byCategory, byItem, expiring, usage, itemResult, forecast] = await Promise.all([
        getWasteRollup(start, end, 'reason'), getWasteRollup(start, end, 'category'), getWasteRollup(start, end, 'item'), listExpiringLots(7), usageRequest, listItems(), forecastRequest,
      ])
      setReasonRollup(byReason); setCategoryRollup(byCategory); setItemRollup(byItem); setLots(expiring.lots); setVariance(usage.lines); setItems(itemResult.items); setParLines(forecast?.lines ?? [])
    } catch { toast('Failed to load inventory waste', 'error') } finally { setLoading(false) }
  }
  useEffect(() => { void load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function submitWaste() {
    const quantity = Number(wasteQuantity)
    if (!wasteItem || !Number.isFinite(quantity) || quantity <= 0) return
    setRecording(true)
    try {
      await recordWaste({ item_id: wasteItem, quantity, reason: wasteReason })
      setWasteQuantity(''); toast('Waste recorded', 'success'); await load()
    } catch { toast('Could not record waste', 'error') } finally { setRecording(false) }
  }

  const latestVariance = variance.filter((line, index, values) => values.findIndex((candidate) => candidate.item_id === line.item_id) === index).slice(0, 5)
  const parDrift = parLines.filter((line) => line.recommended_par != null && line.current_par != null).sort((a, b) => Math.abs((b.recommended_par ?? 0) - (b.current_par ?? 0)) - Math.abs((a.recommended_par ?? 0) - (a.current_par ?? 0))).slice(0, 5)
  return <div className="h-full overflow-y-auto bg-w-bg text-w-text"><div className="mx-auto max-w-[1500px] space-y-4 p-3 sm:p-4">
    <header className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between"><div><div className="mb-2 flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.2em] text-w-accent"><Package size={13} /> Operations / Inventory</div><h1 className="text-2xl font-semibold tracking-tight text-w-text sm:text-3xl">Waste & loss</h1><p className="mt-1.5 max-w-2xl text-sm text-w-dim">Record confirmed loss, identify recurring causes, and protect perishable stock.</p></div><div className="flex flex-wrap items-center gap-2"><button type="button" onClick={() => void load()} disabled={loading} className="inline-flex items-center gap-2 rounded-lg border border-w-line bg-w-surface px-3 py-2 text-xs font-medium text-w-dim transition-colors hover:border-w-accent/40 hover:text-w-text disabled:opacity-50"><RefreshCw size={13} /> Refresh</button><Button variant="secondary" size="sm" onClick={() => setGuideOpen(true)}>How this works</Button></div></header>
    <InventoryNavigation />
    <section className="grid overflow-hidden rounded-xl bg-w-surface grid-cols-1 divide-y divide-w-line sm:grid-cols-3 sm:divide-x sm:divide-y-0"><Metric label="Waste value" value={money(reasonRollup?.total_value ?? null)} /><Metric label="Waste / revenue" value={reasonRollup?.waste_pct_of_revenue == null ? '—' : `${(reasonRollup.waste_pct_of_revenue * 100).toFixed(1)}%`} /><Metric label="Units discarded" value={String(reasonRollup?.total_units ?? 0)} /></section>
    <section id="waste-record" className="scroll-mt-6 rounded-xl border border-w-line bg-w-surface p-4"><h2 className="font-medium text-w-text">Record waste</h2><p className="mt-1 text-xs text-w-dim">Human entry may explicitly classify theft; chat reports never do.</p><div className="mt-3 grid gap-2 sm:grid-cols-[1fr_9rem_10rem_auto]"><Select options={items.map((item) => ({ value: item.id, label: item.name }))} value={wasteItem} onChange={(event) => setWasteItem(event.target.value)} placeholder="Choose item…" /><input type="number" min="0.001" step="any" value={wasteQuantity} onChange={(event) => setWasteQuantity(event.target.value)} placeholder="Quantity" className="rounded-lg border border-w-line bg-w-surface2 px-3 py-2 text-sm text-w-text" /><Select options={reasons} value={wasteReason} onChange={(event) => setWasteReason(event.target.value as WasteReason)} /><Button disabled={recording || !wasteItem || !wasteQuantity} onClick={() => void submitWaste()}>Record</Button></div></section>
    <section id="waste-review" className="scroll-mt-6 grid gap-4 lg:grid-cols-2"><Rollup title="By reason" rollup={reasonRollup} /><Rollup title="By category" rollup={categoryRollup} /></section>
    <section className="grid gap-4 lg:grid-cols-2"><SimpleList title="Top bleeders" empty="No waste recorded in this period." rows={itemRollup?.groups.map((group) => ({ label: group.label, value: `${group.units} units · ${money(group.value)}` })) ?? []} /><SimpleList title="Expiring within 7 days" empty="No open lots expiring this week." rows={lots.map((lot) => ({ label: lot.name, value: `${lot.quantity_remaining} left · ${lot.days_to_expiry}d` }))} /></section>
    <section className="grid gap-4 lg:grid-cols-2"><SimpleList title="Theoretical vs actual usage" empty={canSales ? 'No persisted audit usage variance yet.' : 'Enable Sales Intake to compare theoretical and actual use.'} rows={latestVariance.map((line) => ({ label: line.name, value: line.usage_variance == null ? '—' : `${line.usage_variance > 0 ? '+' : ''}${line.usage_variance} units` }))} /><SimpleList title="PAR drift" empty={canForecast ? 'No forecast par drift yet.' : 'Enable Sales Intake and Forecasting to see par drift.'} rows={parDrift.map((line) => ({ label: line.name, value: `${line.current_par} → ${line.recommended_par} · ${line.par_basis.replace('_', ' ')}` }))} /></section>
    <section className="rounded-xl border border-w-line bg-w-surface p-4"><h2 className="font-medium text-w-text">Ask the waste analyst</h2><div className="mt-3 flex gap-2"><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="What is driving waste?" className="min-w-0 flex-1 rounded-lg border border-w-line bg-w-surface2 px-3 py-2 text-sm text-w-text" /><Button size="sm" disabled={!question.trim()} onClick={() => void askWasteAnalyst(question).then((result) => setAnswer(result.answer)).catch(() => toast('Analyst unavailable', 'error'))}>Ask</Button></div>{answer && <p className="mt-3 text-sm text-w-dim">{answer}</p>}</section>
    <InventoryWasteGuide open={guideOpen} onClose={() => setGuideOpen(false)} autoOpenKey={me?.profile?.company_id ?? me?.user?.id ?? 'current'} />
  </div></div>
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="p-4"><p className="text-xs text-w-dim">{label}</p><p className="mt-1 text-2xl font-semibold text-w-text">{value}</p></div> }
function Rollup({ title, rollup }: { title: string; rollup: WasteRollup | null }) { return <SimpleList title={title} empty="No waste recorded in this period." rows={rollup?.groups.map((group) => ({ label: group.label, value: `${group.units} units · ${money(group.value)}` })) ?? []} /> }
function SimpleList({ title, empty, rows }: { title: string; empty: string; rows: { label: string; value: string }[] }) { return <section className="rounded-xl border border-w-line bg-w-surface p-4"><h2 className="font-medium text-w-text">{title}</h2><div className="mt-3 divide-y divide-w-line">{rows.map((row) => <div key={`${row.label}-${row.value}`} className="flex justify-between gap-4 py-2 text-sm"><span className="text-w-text">{row.label}</span><span className="text-right text-w-dim">{row.value}</span></div>)}{!rows.length && <p className="text-sm text-w-dim">{empty}</p>}</div></section> }
