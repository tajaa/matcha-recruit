import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Download, Loader2, PackageCheck, RefreshCw, ShoppingCart, Store, Truck } from 'lucide-react'
import { Button, Input, useToast } from '../../components/ui'
import { listChannelLocations, type ChannelLocation } from '../api/channels'
import {
  createBuyingRun, createForecastRun, createInventorySupplier, downloadBuyingPlan, getLatestForecastRun,
  listInventorySuppliers, listItems, putInventorySupplierItem, stageBuyingLine,
  type BuyingLine, type BuyingPlan, type InventoryItem, type InventorySupplier,
} from '../api/inventory'
import InventoryNavigation from '../components/inventory/InventoryNavigation'

const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })

export default function InventoryBuying() {
  const { toast } = useToast()
  const [locations, setLocations] = useState<ChannelLocation[]>([])
  const [items, setItems] = useState<InventoryItem[]>([])
  const [suppliers, setSuppliers] = useState<InventorySupplier[]>([])
  const [locationId, setLocationId] = useState('')
  const [plan, setPlan] = useState<BuyingPlan | null>(null)
  const [loading, setLoading] = useState(true)
  const [stagingId, setStagingId] = useState<string | null>(null)
  const [supplierName, setSupplierName] = useState('')
  const [term, setTerm] = useState({ supplierId: '', itemId: '', unitPrice: '', leadDays: '', unitsPerPack: '1', minimum: '0', freight: '' })

  useEffect(() => {
    Promise.all([listChannelLocations(), listItems(), listInventorySuppliers()])
      .then(([nextLocations, itemResponse, supplierResponse]) => {
        setLocations(nextLocations); setItems(itemResponse.items); setSuppliers(supplierResponse.suppliers)
      })
      .catch(() => toast('Could not load purchasing setup', 'error'))
  }, [toast])

  useEffect(() => { void refresh() }, [locationId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function refresh() {
    setLoading(true)
    try {
      let forecast = await getLatestForecastRun(locationId || undefined)
      if (!forecast || Date.now() - new Date(forecast.created_at).getTime() > 12 * 60 * 60 * 1000) {
        forecast = await createForecastRun({ location_id: locationId || null })
      }
      setPlan(await createBuyingRun({ forecast_run_id: forecast.id, location_id: locationId || null }))
    } catch {
      setPlan(null); toast('Could not build the buying plan', 'error')
    } finally { setLoading(false) }
  }

  async function addSupplier() {
    if (!supplierName.trim()) return
    try {
      const next = await createInventorySupplier({ name: supplierName.trim() })
      setSuppliers((current) => [...current.filter((supplier) => supplier.id !== next.id), next].sort((a, b) => a.name.localeCompare(b.name)))
      setSupplierName(''); setTerm((current) => ({ ...current, supplierId: next.id })); toast('Supplier saved', 'success')
    } catch { toast('Could not save supplier', 'error') }
  }

  async function saveTerms() {
    if (!term.supplierId || !term.itemId) return
    try {
      await putInventorySupplierItem(term.itemId, {
        supplier_id: term.supplierId, location_id: locationId || null,
        units_per_pack: Number(term.unitsPerPack) || 1, minimum_order_quantity: Number(term.minimum) || 0,
        unit_price: term.unitPrice === '' ? undefined : Number(term.unitPrice),
        freight_flat: term.freight === '' ? undefined : Number(term.freight),
        lead_time_days: term.leadDays === '' ? undefined : Number(term.leadDays),
        price_observed_on: term.unitPrice === '' ? undefined : new Date().toISOString().slice(0, 10), active: true,
      })
      toast('Supplier terms saved', 'success'); await refresh()
    } catch { toast('Could not save supplier terms', 'error') }
  }

  async function stage(line: BuyingLine) {
    if (!line.id) return
    setStagingId(line.id)
    try { await stageBuyingLine(line.id); toast(`${line.item_name} added to the internal order queue`, 'success') }
    catch { toast('The plan changed or the recommendation could not be staged. Refresh and try again.', 'error') }
    finally { setStagingId(null) }
  }

  const scopedItems = useMemo(() => items.filter((item) => !locationId || item.location_id === locationId || item.location_id === null), [items, locationId])

  return <div className="h-full overflow-y-auto bg-w-bg text-w-text"><div className="mx-auto max-w-[1500px] space-y-4 p-3 sm:p-4">
    <header className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between"><div>
      <div className="mb-2 flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.2em] text-w-accent"><ShoppingCart size={13} /> Operations / Inventory</div>
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Buying guidance</h1>
      <p className="mt-1.5 max-w-3xl text-sm text-w-dim">Store-specific purchasing advice after confirmed inbound inventory and safe cross-store transfers. Matcha stages an internal list; it never sends an order to a supplier.</p>
    </div><div className="flex flex-wrap items-center gap-2">
      <select value={locationId} onChange={(event) => setLocationId(event.target.value)} className="rounded-lg border border-w-line bg-w-surface px-3 py-2 text-xs text-w-text"><option value="">All locations</option>{locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select>
      <Button variant="secondary" size="sm" disabled={!plan} onClick={() => plan && void downloadBuyingPlan(plan.forecast_run_id, locationId || undefined)}><Download size={14} className="mr-1.5" />Export CSV</Button>
      <Button size="sm" onClick={() => void refresh()} disabled={loading}><RefreshCw size={14} className="mr-1.5" />Refresh</Button>
    </div></header>
    <InventoryNavigation />

    {loading ? <div className="flex min-h-64 items-center justify-center"><Loader2 className="animate-spin text-w-dim" /></div> : plan ? <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Metric icon={ShoppingCart} label="Normal buys" value={plan.summary.buy} />
        <Metric icon={AlertTriangle} label="Expedite review" value={plan.summary.expedite} tone="amber" />
        <Metric icon={PackageCheck} label="Count first" value={plan.summary.count_first} />
        <Metric icon={Truck} label="Unpriced" value={plan.summary.unpriced_count} tone={plan.summary.unpriced_count ? 'amber' : undefined} />
        <Metric icon={Store} label="Known landed cost" value={plan.summary.total_landed_cost === null ? '—' : money.format(plan.summary.total_landed_cost)} />
      </section>
      <section className="overflow-hidden rounded-xl border border-w-line bg-w-surface"><div className="border-b border-w-line px-4 py-3"><h2 className="font-medium">Advisory decision queue</h2><p className="mt-1 text-xs text-w-dim">Urgent actions first. Prices older than 90 days require confirmation.</p></div>
        {plan.lines.length === 0 ? <p className="px-4 py-12 text-center text-sm text-w-dim">No purchasing action is needed from this forecast.</p> : <div className="divide-y divide-w-line">{plan.lines.map((line) => <Decision key={line.id ?? `${line.item_id}-${line.action}`} line={line} staging={stagingId === line.id} onStage={() => void stage(line)} />)}</div>}
      </section>
    </> : null}

    <details className="rounded-xl border border-w-line bg-w-surface"><summary className="cursor-pointer px-4 py-3 text-sm font-medium">Supplier evidence and store terms</summary><div className="grid gap-4 border-t border-w-line p-4 lg:grid-cols-[1fr_2fr]">
      <section><h3 className="text-sm font-medium">Add a known supplier</h3><p className="mt-1 text-xs text-w-dim">Receipt review also creates supplier and price history automatically.</p><div className="mt-3 flex gap-2"><Input value={supplierName} onChange={(event) => setSupplierName(event.target.value)} placeholder="Supplier name" /><Button onClick={() => void addSupplier()}>Add</Button></div></section>
      <section><h3 className="text-sm font-medium">Configure item terms</h3><div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <select value={term.supplierId} onChange={(event) => setTerm({ ...term, supplierId: event.target.value })} className="rounded-lg border border-w-line bg-w-bg px-3 py-2 text-sm"><option value="">Supplier</option>{suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}</option>)}</select>
        <select value={term.itemId} onChange={(event) => setTerm({ ...term, itemId: event.target.value })} className="rounded-lg border border-w-line bg-w-bg px-3 py-2 text-sm"><option value="">Inventory item</option>{scopedItems.map((item) => <option key={item.id} value={item.id}>{item.name}{item.location_name ? ` · ${item.location_name}` : ''}</option>)}</select>
        <Input type="number" min="0" step="any" value={term.unitPrice} onChange={(event) => setTerm({ ...term, unitPrice: event.target.value })} placeholder="Unit price" />
        <Input type="number" min="0" value={term.leadDays} onChange={(event) => setTerm({ ...term, leadDays: event.target.value })} placeholder="Lead days" />
        <Input type="number" min="0.0001" step="any" value={term.unitsPerPack} onChange={(event) => setTerm({ ...term, unitsPerPack: event.target.value })} placeholder="Units / case" />
        <Input type="number" min="0" step="any" value={term.minimum} onChange={(event) => setTerm({ ...term, minimum: event.target.value })} placeholder="Minimum order" />
        <Input type="number" min="0" step="any" value={term.freight} onChange={(event) => setTerm({ ...term, freight: event.target.value })} placeholder="Flat freight" />
        <Button onClick={() => void saveTerms()} disabled={!term.supplierId || !term.itemId}>Save terms</Button>
      </div></section>
    </div></details>
  </div></div>
}

function Metric({ icon: Icon, label, value, tone }: { icon: typeof ShoppingCart; label: string; value: string | number; tone?: 'amber' }) {
  return <div className="rounded-xl border border-w-line bg-w-surface p-4"><div className={`flex items-center gap-2 text-xs ${tone === 'amber' ? 'text-amber-300' : 'text-w-dim'}`}><Icon size={14} />{label}</div><p className="mt-2 text-2xl font-semibold">{value}</p></div>
}

function Decision({ line, staging, onStage }: { line: BuyingLine; staging: boolean; onStage: () => void }) {
  const action = line.action === 'count_first' ? 'Count first' : line.action === 'expedite' ? 'Expedite review' : line.action === 'hold' ? 'Hold' : 'Buy'
  return <article className="grid gap-3 px-4 py-4 lg:grid-cols-[1fr_auto] lg:items-center"><div><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium">{line.item_name}</h3><span className={`rounded-full px-2 py-0.5 text-[10px] ${line.action === 'expedite' ? 'bg-amber-400/15 text-amber-300' : line.action === 'count_first' ? 'bg-sky-400/15 text-sky-300' : 'bg-emerald-400/15 text-emerald-300'}`}>{action}</span><span className="text-xs text-w-dim">{line.location_name ?? 'Company-wide'}</span></div>
    <p className="mt-1 text-sm text-w-dim">{line.rationale}</p><div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-w-dim"><span>Transfer first: {number.format(line.transfer_quantity)}</span>{line.purchase_quantity !== null && <span>Purchase: {number.format(line.purchase_quantity)}{line.unit ? ` ${line.unit}` : ''}</span>}<span>Supplier: {line.supplier_name ?? 'Confirm supplier'}</span><span>Arrival: {line.expected_arrival ?? 'Confirm lead time'}</span><span>Cost: {line.landed_cost === null ? 'Confirm price' : money.format(line.landed_cost)}</span></div>
    {line.price_confirmation_required && <p className="mt-2 text-xs text-amber-300">Price confirmation required before external ordering.</p>}
    {line.alternatives.length > 0 && <details className="mt-2 text-xs text-w-dim"><summary className="cursor-pointer">Compare {line.alternatives.length} alternative{line.alternatives.length === 1 ? '' : 's'}</summary><ul className="mt-1 space-y-1 pl-4">{line.alternatives.map((option) => <li key={option.supplier_id}>{option.supplier_name}: {option.reason}{option.landed_cost === null ? '' : ` · ${money.format(option.landed_cost)}`}</li>)}</ul></details>}
  </div>{(line.action === 'buy' || line.action === 'expedite') && <Button size="sm" variant={line.price_confirmation_required ? 'secondary' : undefined} disabled={!line.id || staging} onClick={onStage}>{staging ? 'Staging…' : 'Stage internally'}</Button>}</article>
}
