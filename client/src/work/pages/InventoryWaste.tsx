import { useEffect, useState } from 'react'
import { MessageSquare, Package, RefreshCw } from 'lucide-react'
import { Button, Select, useToast } from '../../components/ui'
import {
  askWasteAnalyst, getLatestForecastRun, getWasteAtRisk, getWasteInsight, getWasteRollup, getWasteSummary, getWasteVariance,
  listExpiringLots, listItems, recordWaste, type ForecastLine, type InventoryItem,
  type InventoryInsight, type WasteAnalystCitation, type WasteReason, type WasteRiskLine, type WasteRollup, type WasteSummary,
} from '../api/inventory'
import { useMe } from '../../hooks/useMe'
import InventoryWasteGuide from '../components/inventory/InventoryWasteGuide'
import InventoryNavigation from '../components/inventory/InventoryNavigation'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import { useNavigate } from 'react-router-dom'

function isoDay(offset = 0) { const value = new Date(); value.setDate(value.getDate() + offset); return value.toISOString().slice(0, 10) }
const money = (value: number | null) => value == null ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value)
// Par/quantity figures come off NUMERIC forecast math (e.g. "23.699999999999999906741265932")
// — round to a sane display precision rather than concatenating the raw DB string.
const parQty = (value: number | string | null) => value == null ? '—' : (Math.round(Number(value) * 10) / 10).toString()
const reasons: { value: WasteReason; label: string }[] = [
  { value: 'spoilage', label: 'Spoilage' }, { value: 'expired', label: 'Expired' }, { value: 'prep_error', label: 'Prep error' }, { value: 'overproduction', label: 'Overproduction' }, { value: 'breakage', label: 'Breakage' }, { value: 'contamination', label: 'Contamination' }, { value: 'theft', label: 'Theft' }, { value: 'comp', label: 'Comp' }, { value: 'recall', label: 'Recall' }, { value: 'unknown', label: 'Unknown' },
]

export default function InventoryWaste() {
  const base = useWorkBase(); const navigate = useNavigate(); const { toast } = useToast(); const { hasFeature, me } = useMe()
  const canSales = hasFeature('sales_intake')
  const canForecast = canSales && hasFeature('inventory_forecasting')
  const [reasonRollup, setReasonRollup] = useState<WasteRollup | null>(null)
  const [summary, setSummary] = useState<WasteSummary | null>(null)
  const [atRisk, setAtRisk] = useState<WasteRiskLine[]>([])
  const [insight, setInsight] = useState<InventoryInsight | null>(null)
  const [periodDays, setPeriodDays] = useState(28)
  const [categoryRollup, setCategoryRollup] = useState<WasteRollup | null>(null)
  const [itemRollup, setItemRollup] = useState<WasteRollup | null>(null)
  const [lots, setLots] = useState<{ id: string; name: string; quantity_remaining: number; expires_on: string; days_to_expiry: number }[]>([])
  const [variance, setVariance] = useState<{ item_id: string; name: string; theoretical_usage: number | null; actual_usage: number | null; usage_variance: number | null }[]>([])
  const [parLines, setParLines] = useState<ForecastLine[]>([])
  const [items, setItems] = useState<InventoryItem[]>([])
  const [loading, setLoading] = useState(true); const [recording, setRecording] = useState(false)
  const [question, setQuestion] = useState(''); const [answer, setAnswer] = useState('')
  const [citations, setCitations] = useState<WasteAnalystCitation[]>([])
  const [wasteItem, setWasteItem] = useState(''); const [wasteQuantity, setWasteQuantity] = useState(''); const [wasteReason, setWasteReason] = useState<WasteReason>('spoilage')
  const [guideOpen, setGuideOpen] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const start = isoDay(-(periodDays - 1)); const end = isoDay()
      const forecastRequest = canForecast ? getLatestForecastRun() : Promise.resolve(null)
      const usageRequest = canSales ? getWasteVariance(start, end) : Promise.resolve({ lines: [] })
      const [nextSummary, nextRisk, byReason, byCategory, byItem, expiring, usage, itemResult, forecast] = await Promise.all([
        getWasteSummary(start, end), getWasteAtRisk(), getWasteRollup(start, end, 'reason'), getWasteRollup(start, end, 'category'), getWasteRollup(start, end, 'item'), listExpiringLots(7), usageRequest, listItems(), forecastRequest,
      ])
      setSummary(nextSummary); setAtRisk(nextRisk.lines.filter((line) => line.quantity_at_risk > 0)); setReasonRollup(byReason); setCategoryRollup(byCategory); setItemRollup(byItem); setLots(expiring.lots); setVariance(usage.lines); setItems(itemResult.items); setParLines(forecast?.lines ?? [])
      void getWasteInsight({ start, end }).then(setInsight).catch(() => setInsight(null))
    } catch { toast('Failed to load inventory waste', 'error') } finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [periodDays]) // eslint-disable-line react-hooks/exhaustive-deps

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
  const locationById = new Map(items.map((item) => [item.id, item.location_name]))
  const parDrift = parLines.filter((line) => line.recommended_par != null && line.current_par != null).sort((a, b) => Math.abs((b.recommended_par ?? 0) - (b.current_par ?? 0)) - Math.abs((a.recommended_par ?? 0) - (a.current_par ?? 0))).slice(0, 5)
  return <div className="h-full overflow-y-auto bg-w-bg text-w-text"><div className="mx-auto max-w-[1500px] space-y-4 p-3 sm:p-4">
    <header className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between"><div><div className="mb-2 flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.2em] text-w-accent"><Package size={13} /> Operations / Inventory</div><h1 className="text-2xl font-semibold tracking-tight text-w-text sm:text-3xl">Waste & loss</h1><p className="mt-1.5 max-w-2xl text-sm text-w-dim">Record confirmed loss, identify recurring causes, and protect perishable stock.</p></div><div className="flex flex-wrap items-center gap-2"><button type="button" onClick={() => void load()} disabled={loading} className="inline-flex items-center gap-2 rounded-lg border border-w-line bg-w-surface px-3 py-2 text-xs font-medium text-w-dim transition-colors hover:border-w-accent/40 hover:text-w-text disabled:opacity-50"><RefreshCw size={13} /> Refresh</button><Button variant="secondary" size="sm" onClick={() => setGuideOpen(true)}>How this works</Button></div></header>
    <InventoryNavigation />
    <div className="flex flex-wrap gap-2">{[7, 28, 91].map((days) => <button key={days} type="button" onClick={() => setPeriodDays(days)} className={`rounded-lg px-3 py-1.5 text-xs font-medium ${periodDays === days ? 'bg-w-accent text-white' : 'bg-w-surface text-w-dim hover:text-w-text'}`}>{days}d</button>)}</div>
    <section className="grid overflow-hidden rounded-xl bg-w-surface grid-cols-1 divide-y divide-w-line sm:grid-cols-3 sm:divide-x sm:divide-y-0"><Metric label={`${money(summary?.current.total_value ?? reasonRollup?.total_value ?? null)} lost`} value={summary?.comparable && summary.value_pct_change !== null ? `${summary.direction === 'up' ? '▲' : summary.direction === 'down' ? '▼' : '•'} ${Math.abs(summary.value_pct_change * 100).toFixed(0)}% vs prior` : 'No prior data'} /><Metric label="Waste / revenue" value={summary?.current.waste_pct_of_revenue == null ? '—' : `${(summary.current.waste_pct_of_revenue * 100).toFixed(1)}%`} /><Metric label="Units discarded" value={String(summary?.current.total_units ?? reasonRollup?.total_units ?? 0)} /></section>
    {summary?.bleeder && <section className="rounded-xl border border-w-line bg-w-surface p-4"><p className="text-[10px] font-medium uppercase tracking-[0.16em] text-w-accent">Biggest bleeder</p><div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between"><div><h2 className="text-lg font-semibold text-w-text">{summary.bleeder.label}</h2><p className="mt-1 text-sm text-w-dim">{summary.diagnosis === 'handling' ? 'Loss points to handling; review preparation and storage before changing PARs.' : summary.diagnosis === 'over_ordering' ? 'Loss points to over-ordering; review the item’s PAR before the next purchase.' : summary.diagnosis === 'unexplained_shrink' ? 'Loss is unexplained; count stock and review the movement ledger.' : 'No single loss cause is dominant enough to prescribe a change.'}</p></div><span className="text-sm font-medium text-w-text">{money(summary.bleeder.value)} · {summary.bleeder.units} units</span></div></section>}
    {insight && <section className="rounded-xl border border-w-accent/20 bg-w-surface p-4"><p className="text-[10px] font-medium uppercase tracking-[0.16em] text-w-accent">Luna’s read</p><h2 className="mt-1 font-medium text-w-text">{insight.headline}</h2><p className="mt-1 text-sm text-w-dim">{insight.detail}</p></section>}
    {atRisk.length > 0 && <section className="rounded-xl border border-amber-400/25 bg-w-surface p-4"><p className="text-[10px] font-medium uppercase tracking-[0.16em] text-amber-300">At risk now</p>{atRisk.slice(0, 3).map((line) => <div key={line.item_id} className="mt-2 flex flex-wrap items-baseline justify-between gap-2 text-sm"><span className="font-medium text-w-text">{line.name}</span><span className="text-w-dim">{parQty(line.quantity_at_risk)} {line.unit ?? 'units'} may spoil in {line.soonest_days_to_expiry}d{line.value_at_risk !== null ? ` · ${money(line.value_at_risk)}` : ''}{line.demand_basis === 'insufficient_history' ? ' · estimate, not enough sales history' : ''}</span></div>)}</section>}
    <section id="huume-capture" className="scroll-mt-6 rounded-xl border border-w-line bg-w-surface p-4"><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div className="flex items-start gap-2"><MessageSquare className="mt-0.5 h-4 w-4 text-w-accent" /><div><h2 className="text-sm font-medium text-w-text">Report waste with @huume</h2><p className="mt-1 text-xs text-w-dim">From any team chat, write <span className="font-medium text-w-text">@huume tossed 3 boxes of gloves; package was torn</span>. It logs the loss immediately — Huume only follows up if the quantity or item needs clarifying.</p></div></div><Button variant="secondary" size="sm" onClick={() => navigate(`${base}/channels`)}>Open team chat</Button></div></section>
    <section id="waste-record" className="scroll-mt-6 rounded-xl border border-w-line bg-w-surface p-4"><h2 className="font-medium text-w-text">Record waste</h2><p className="mt-1 text-xs text-w-dim">Human entry may explicitly classify theft; chat reports never do.</p><div className="mt-3 grid gap-2 sm:grid-cols-[1fr_9rem_10rem_auto]"><Select options={items.map((item) => ({ value: item.id, label: item.name }))} value={wasteItem} onChange={(event) => setWasteItem(event.target.value)} placeholder="Choose item…" /><input type="number" min="0.001" step="any" value={wasteQuantity} onChange={(event) => setWasteQuantity(event.target.value)} placeholder="Quantity" className="rounded-lg border border-w-line bg-w-surface2 px-3 py-2 text-sm text-w-text" /><Select options={reasons} value={wasteReason} onChange={(event) => setWasteReason(event.target.value as WasteReason)} /><Button disabled={recording || !wasteItem || !wasteQuantity} onClick={() => void submitWaste()}>Record</Button></div></section>
    <section id="waste-review" className="scroll-mt-6 grid gap-4 lg:grid-cols-2"><Rollup title="By reason" rollup={reasonRollup} /><Rollup title="By category" rollup={categoryRollup} /></section>
    <section className="grid gap-4 lg:grid-cols-2"><SimpleList title="Top bleeders" empty="No waste recorded in this period." rows={itemRollup?.groups.map((group) => ({ label: group.label, value: `${group.units} units · ${money(group.value)}` })) ?? []} /><SimpleList title="Expiring within 7 days" empty="No open lots expiring this week." rows={lots.map((lot) => ({ label: lot.name, value: `${lot.quantity_remaining} left · ${lot.days_to_expiry}d` }))} /></section>
    <section className="grid gap-4 lg:grid-cols-2"><SimpleList title="Theoretical vs actual usage" empty={canSales ? 'No persisted audit usage variance yet.' : 'Enable Sales Intake to compare theoretical and actual use.'} rows={latestVariance.map((line) => ({ label: line.name, value: line.usage_variance == null ? '—' : `${line.usage_variance > 0 ? '+' : ''}${line.usage_variance} units` }))} /><SimpleList title="PAR drift" empty={canForecast ? 'No forecast par drift yet.' : 'Enable Sales Intake and Forecasting to see par drift.'} rows={parDrift.map((line) => {
      const dupeName = parDrift.filter((other) => other.name === line.name).length > 1
      const location = locationById.get(line.item_id)
      const label = dupeName && location ? `${line.name} (${location})` : line.name
      return { label, value: `${parQty(line.current_par)} → ${parQty(line.recommended_par)} · ${line.par_basis.replace('_', ' ')}` }
    })} /></section>
    <section className="rounded-xl border border-w-line bg-w-surface p-4"><h2 className="font-medium text-w-text">Ask the waste analyst</h2><div className="mt-3 flex gap-2"><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="What is driving waste?" className="min-w-0 flex-1 rounded-lg border border-w-line bg-w-surface2 px-3 py-2 text-sm text-w-text" /><Button size="sm" disabled={!question.trim()} onClick={() => void askWasteAnalyst(question).then((result) => { setAnswer(result.answer); setCitations(result.citations) }).catch(() => toast('Analyst unavailable', 'error'))}>Ask</Button></div>{answer && <p className="mt-3 text-sm text-w-dim">{answer}</p>}{citations.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{citations.map((citation) => <span key={citation.id} title={JSON.stringify(citation.data)} className="rounded-full border border-w-line bg-w-surface2 px-2 py-0.5 text-[10px] uppercase tracking-wide text-w-faint">{citation.kind.replace(/_/g, ' ')}</span>)}</div>}</section>
    <InventoryWasteGuide open={guideOpen} onClose={() => setGuideOpen(false)} autoOpenKey={me?.profile?.company_id ?? me?.user?.id ?? 'current'} />
  </div></div>
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="p-4"><p className="text-xs text-w-dim">{label}</p><p className="mt-1 text-2xl font-semibold text-w-text">{value}</p></div> }
function Rollup({ title, rollup }: { title: string; rollup: WasteRollup | null }) { return <SimpleList title={title} empty="No waste recorded in this period." rows={rollup?.groups.map((group) => ({ label: group.label, value: `${group.units} units · ${money(group.value)}` })) ?? []} /> }
function SimpleList({ title, empty, rows }: { title: string; empty: string; rows: { label: string; value: string }[] }) { return <section className="rounded-xl border border-w-line bg-w-surface p-4"><h2 className="font-medium text-w-text">{title}</h2><div className="mt-3 divide-y divide-w-line">{rows.map((row) => <div key={`${row.label}-${row.value}`} className="flex justify-between gap-4 py-2 text-sm"><span className="text-w-text">{row.label}</span><span className="text-right text-w-dim">{row.value}</span></div>)}{!rows.length && <p className="text-sm text-w-dim">{empty}</p>}</div></section> }
