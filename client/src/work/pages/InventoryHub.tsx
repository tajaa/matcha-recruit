import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BookOpen,
  Boxes,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  DollarSign,
  Gauge,
  Loader2,
  Package,
  RefreshCw,
  Search,
  Sparkles,
  Upload,
  Wrench,
} from 'lucide-react'
import { Button, Input, useToast } from '../../components/ui'
import ItemTable from '../components/inventory/ItemTable'
import ItemDetail from '../components/inventory/ItemDetail'
import OrderQueue from '../components/inventory/OrderQueue'
import ReceiveDeliveryModal from '../components/inventory/ReceiveDeliveryModal'
import SalesImportModal from '../components/inventory/SalesImportModal'
import SalesMappingsPanel from '../components/inventory/SalesMappingsPanel'
import SalesIntakeWizard from '../components/inventory/SalesIntakeWizard'
import InventoryGuideWizard, {
  INVENTORY_HELP,
  InventoryHelpButton,
  InventoryHelpModal,
  type InventorySectionHelp,
} from '../components/inventory/InventoryHelp'
import {
  createItem,
  listItems,
  listMovements,
  listOrders,
  listSalesImports,
  listSuggestions,
  type InventoryItem,
  type InventoryMovement,
  type InventoryOrder,
  type InventorySuggestion,
} from '../api/inventory'
import { listChannelLocations, type ChannelLocation } from '../api/channels'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import { useMe } from '../../hooks/useMe'
import { formatDateTimePacific } from '../../utils/dateFormat'

export default function InventoryHub() {
  const { itemId } = useParams<{ itemId: string }>()
  const navigate = useNavigate()
  const base = useWorkBase()
  const { toast } = useToast()
  const { hasFeature, me } = useMe()
  const canSales = hasFeature('sales_intake')
  const [items, setItems] = useState<InventoryItem[]>([])
  const [orders, setOrders] = useState<InventoryOrder[]>([])
  const [movements, setMovements] = useState<InventoryMovement[]>([])
  const [suggestions, setSuggestions] = useState<Record<string, InventorySuggestion>>({})
  const [locations, setLocations] = useState<ChannelLocation[]>([])
  const [locFilter, setLocFilter] = useState<'all' | 'none' | string>('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [newItemName, setNewItemName] = useState('')
  const [newItemLocation, setNewItemLocation] = useState('')
  const [adding, setAdding] = useState(false)
  const [receiveOpen, setReceiveOpen] = useState(false)
  const [salesOpen, setSalesOpen] = useState(false)
  const [mappingsOpen, setMappingsOpen] = useState(false)
  const [draftCount, setDraftCount] = useState(0)
  const [reviewImportId, setReviewImportId] = useState<string | null>(null)
  const [salesWizardOpen, setSalesWizardOpen] = useState(false)
  const [inventoryGuideOpen, setInventoryGuideOpen] = useState(false)
  const [help, setHelp] = useState<InventorySectionHelp | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    const salesRequest = canSales ? listSalesImports('draft') : Promise.resolve({ imports: [] })
    const suggestionsRequest = listSuggestions().catch(() => ({} as Record<string, InventorySuggestion>))
    Promise.all([listItems(), listOrders('queued'), salesRequest, listMovements({ limit: 200 }), suggestionsRequest])
      .then(([itemsRes, ordersRes, salesRes, movementsRes, suggestionsRes]) => {
        setItems(itemsRes.items)
        setOrders(ordersRes.orders)
        setDraftCount(salesRes.imports.length)
        setMovements(movementsRes.movements)
        setSuggestions(suggestionsRes)
      })
      .catch(() => toast('Failed to load inventory', 'error'))
      .finally(() => setLoading(false))
  }, [canSales, toast])

  useEffect(() => {
    if (!itemId) load()
  }, [load, itemId])

  useEffect(() => {
    listChannelLocations().then(setLocations).catch(() => setLocations([]))
  }, [])

  const visibleItems = useMemo(() => {
    let filtered = items
    if (locFilter === 'none') filtered = filtered.filter((i) => !i.location_id)
    else if (locFilter !== 'all') filtered = filtered.filter((i) => i.location_id === locFilter)
    if (search.trim()) {
      const query = search.trim().toLowerCase()
      filtered = filtered.filter((i) => i.name.toLowerCase().includes(query) || i.location_name?.toLowerCase().includes(query))
    }
    return filtered
  }, [items, locFilter, search])
  const catalogIsFiltered = locFilter !== 'all' || search.trim() !== ''

  const visibleOrders = useMemo(() => {
    const visibleIds = new Set(visibleItems.map((i) => i.id))
    return orders.filter((o) => visibleIds.has(o.item_id))
  }, [orders, visibleItems])

  const insights = useMemo(() => buildInsights(visibleItems, visibleOrders, movements, suggestions), [movements, suggestions, visibleItems, visibleOrders])

  async function handleAddItem() {
    const name = newItemName.trim()
    if (!name) return
    setAdding(true)
    try {
      await createItem({ name, location_id: newItemLocation || undefined })
      setNewItemName('')
      toast('Item added', 'success')
      load()
    } catch {
      toast('An item with this name already exists', 'error')
    } finally {
      setAdding(false)
    }
  }

  if (itemId) return <ItemDetail itemId={itemId} />

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-w-bg">
        <Loader2 className="h-5 w-5 animate-spin text-w-dim" />
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto bg-w-bg text-w-text">
      <div className="mx-auto max-w-[1500px] space-y-4 p-3 sm:p-4">
        <header className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.2em] text-w-accent">
              <Package size={13} /> Operations / Inventory
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-w-text sm:text-3xl">Inventory control center</h1>
            <p className="mt-1.5 max-w-2xl text-sm text-w-dim">See what is moving, what needs attention, and where the next stock decision is waiting.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {locations.length > 0 && (
              <select
                value={locFilter}
                onChange={(e) => setLocFilter(e.target.value)}
                className="rounded-lg border border-w-line bg-w-surface px-3 py-2 text-xs text-w-text outline-none transition-colors focus:border-w-accent/50"
              >
                <option value="all">All locations</option>
                {locations.map((l) => (
                  <option key={l.id} value={l.id}>{l.name}</option>
                ))}
                <option value="none">Unassigned</option>
              </select>
            )}
            <button type="button" onClick={load} className="inline-flex items-center gap-2 rounded-lg border border-w-line bg-w-surface px-3 py-2 text-xs font-medium text-w-dim transition-colors hover:border-w-accent/40 hover:text-w-text">
              <RefreshCw size={13} /> Refresh
            </button>
            <Button variant="secondary" size="sm" onClick={() => setInventoryGuideOpen(true)}>
              <BookOpen className="h-3.5 w-3.5" /> How inventory works
            </Button>
          </div>
        </header>

        <div className="flex flex-wrap items-center gap-1.5 border-b border-w-line pb-3">
          <Button variant="secondary" size="sm" onClick={() => navigate(`${base}/inventory/audit`)}>
            <ClipboardCheck className="mr-1.5 inline h-3.5 w-3.5" /> Audit stock
          </Button>
          {canSales && <Button variant="secondary" size="sm" onClick={() => { setReviewImportId(null); setSalesOpen(true) }}>
            <Upload className="mr-1.5 inline h-3.5 w-3.5" /> Import sales
          </Button>}
          <Button size="sm" onClick={() => setReceiveOpen(true)}>Receive delivery</Button>
          {canSales && <>
            <Button variant="ghost" size="sm" onClick={() => setMappingsOpen((open) => !open)}>
              <Wrench className="mr-1.5 inline h-3.5 w-3.5" /> {mappingsOpen ? 'Hide mappings' : 'Mappings'}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setSalesWizardOpen(true)}>
              <BookOpen className="mr-1.5 inline h-3.5 w-3.5" /> Sales intake guide
            </Button>
          </>}
        </div>

      <ReceiveDeliveryModal
        open={receiveOpen}
        onClose={() => setReceiveOpen(false)}
        items={visibleItems}
        locationId={locFilter !== 'all' && locFilter !== 'none' ? locFilter : undefined}
         onCommitted={load}
      />
      {canSales && <SalesImportModal
        open={salesOpen}
        onClose={() => setSalesOpen(false)}
        items={visibleItems}
        locationId={locFilter !== 'all' && locFilter !== 'none' ? locFilter : undefined}
        draftImportId={reviewImportId}
        onCommitted={load}
      />}
      {canSales && <SalesIntakeWizard
        open={salesWizardOpen}
        companyKey={me?.profile?.company_id ?? me?.user?.id ?? 'current'}
        onClose={() => setSalesWizardOpen(false)}
        onAction={(action) => {
          if (action === 'mappings') setMappingsOpen(true)
          if (action === 'import') { setReviewImportId(null); setSalesOpen(true) }
          if (action === 'audit') navigate(`${base}/inventory/audit`)
        }}
      />}
      <InventoryGuideWizard
        open={inventoryGuideOpen}
        companyKey={me?.profile?.company_id ?? me?.user?.id ?? 'current'}
        onClose={() => setInventoryGuideOpen(false)}
        onAction={(action) => {
          if (action === 'audit') navigate(`${base}/inventory/audit`)
          if (action === 'receive') setReceiveOpen(true)
        }}
      />
      <InventoryHelpModal help={help} onClose={() => setHelp(null)} />
      {canSales && mappingsOpen && <SalesMappingsPanel
        items={visibleItems}
        locationId={locFilter !== 'all' && locFilter !== 'none' ? locFilter : undefined}
        onHelp={() => setHelp(INVENTORY_HELP.mappings)}
      />}

        {canSales && draftCount > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-400/25 bg-amber-400/[0.06] px-4 py-3 text-sm">
            <div className="flex items-center gap-2 text-amber-200"><AlertTriangle size={15} /> {draftCount} sales import{draftCount === 1 ? '' : 's'} waiting for review.</div>
            <Button variant="secondary" onClick={() => {
              listSalesImports('draft').then((result) => {
                setReviewImportId(result.imports[0]?.id ?? null)
                setSalesOpen(true)
              }).catch(() => toast('Failed to load sales drafts', 'error'))
            }}>Review imports</Button>
          </div>
        )}

        <section>
          <div className="mb-2 flex items-center justify-between gap-3 px-1">
            <div className="text-[10px] font-medium uppercase tracking-[0.16em] text-w-faint">At a glance</div>
            <InventoryHelpButton onClick={() => setHelp(INVENTORY_HELP.overview)} />
          </div>
          <div className="grid overflow-hidden rounded-xl bg-w-surface grid-cols-2 divide-y divide-w-line sm:grid-cols-4 sm:divide-x sm:divide-y-0">
            <MetricCard icon={Boxes} label="Tracked items" value={String(insights.totalItems)} detail={`${insights.knownCount} with a known count`} tone="neutral" />
            <MetricCard icon={DollarSign} label="On-hand value" value={formatCurrency(insights.inventoryValue)} detail={insights.costedCount ? `${insights.costedCount} items have unit cost` : 'Add unit costs to measure value'} tone="green" />
            <MetricCard icon={AlertTriangle} label="Needs attention" value={String(insights.attentionCount)} detail={`${insights.outCount} out · ${insights.unknownCount} unknown`} tone={insights.attentionCount > 0 ? 'amber' : 'green'} />
            <MetricCard icon={Activity} label="Open orders" value={String(insights.openOrderCount)} detail={insights.lastMovement ? `Last activity ${formatDateTimePacific(insights.lastMovement.created_at)}` : 'No movement activity yet'} tone="blue" />
          </div>
        </section>

        <section className="overflow-hidden rounded-xl border border-w-line bg-w-surface">
          <div className="flex flex-col gap-2 border-b border-w-line px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2 text-sm font-medium text-w-text"><Boxes size={15} className="text-w-accent" /> Inventory catalog <span className="text-xs font-normal text-w-faint">{visibleItems.length}{catalogIsFiltered ? ` of ${items.length}` : ''} shown</span></div>
              <p className="mt-0.5 text-xs text-w-dim">Select an item to inspect its movement ledger and adjust its count.</p>
            </div>
            <div className="flex w-full items-center gap-2 sm:w-auto">
              <InventoryHelpButton onClick={() => setHelp(INVENTORY_HELP.catalog)} />
              <div className="relative w-full sm:w-64">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-w-faint" />
                <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search items or locations" className="w-full rounded-lg border border-w-line bg-w-surface2 py-1.5 pl-9 pr-3 text-xs text-w-text outline-none placeholder:text-w-faint focus:border-w-accent/50" />
              </div>
            </div>
          </div>
          <ItemTable items={visibleItems} />
        </section>

        <div className="grid items-start gap-3 xl:grid-cols-[1.15fr_0.85fr]">
          <section className="h-fit self-start rounded-xl bg-w-surface p-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 text-sm font-medium text-w-text"><Gauge size={15} className="text-w-accent" /> Stock health</div>
                <p className="mt-1 text-xs text-w-dim">A quick read on how much of the catalog has a usable count.</p>
              </div>
              <div className="flex items-center gap-2"><InventoryHelpButton onClick={() => setHelp(INVENTORY_HELP.stockHealth)} /><span className="rounded-full bg-w-surface2 px-2.5 py-1 text-[10px] font-medium text-w-dim">{insights.knownPercent}% known</span></div>
            </div>
            <div className="mt-4 flex items-end gap-3">
              <div className="text-3xl font-semibold tracking-tight text-w-text">{insights.healthyCount}</div>
              <div className="pb-1 text-sm text-w-dim">healthy of {insights.totalItems}</div>
            </div>
            <div className="mt-4 flex h-2.5 overflow-hidden rounded-full bg-w-surface2">
              <HealthSegment count={insights.healthyCount} total={insights.totalItems} color="bg-w-accent" label="Healthy" />
              <HealthSegment count={insights.lowCount} total={insights.totalItems} color="bg-amber-400" label="Low" />
              <HealthSegment count={insights.outCount} total={insights.totalItems} color="bg-red-400" label="Out" />
              <HealthSegment count={insights.unknownCount} total={insights.totalItems} color="bg-w-faint" label="Unknown" />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              <HealthLegend color="bg-w-accent" label="Healthy" count={insights.healthyCount} />
              <HealthLegend color="bg-amber-400" label="Low stock" count={insights.lowCount} />
              <HealthLegend color="bg-red-400" label="Out" count={insights.outCount} />
              <HealthLegend color="bg-w-faint" label="Unknown" count={insights.unknownCount} />
            </div>
          </section>

          <section className="h-fit self-start rounded-xl bg-w-surface p-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 text-sm font-medium text-w-text"><Activity size={15} className="text-w-accent" /> Recent movement flow</div>
                <p className="mt-1 text-xs text-w-dim">Showing {Math.min(3, insights.movementCount)} of {insights.movementCount} latest ledger entries.</p>
              </div>
              <div className="flex items-center gap-2"><InventoryHelpButton onClick={() => setHelp(INVENTORY_HELP.movementFlow)} /><span className="font-mono text-[10px] text-w-faint">200 max</span></div>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2">
              <FlowStat icon={ArrowUpRight} label="In" value={insights.inboundCount} tone="text-w-accent" />
              <FlowStat icon={ArrowDownRight} label="Out" value={insights.outboundCount} tone="text-amber-300" />
              <FlowStat icon={ClipboardCheck} label="Adjust" value={insights.adjustmentCount} tone="text-blue-300" />
            </div>
            <div className="mt-4 space-y-1.5">
              {insights.recentMovements.length === 0 ? <p className="rounded-lg bg-w-surface2 px-3 py-3 text-xs text-w-dim">No movement data yet. Activity from channels and audits will appear here.</p> : insights.recentMovements.slice(0, 3).map((movement) => (
                <MovementRow key={movement.id} movement={movement} itemName={insights.itemNames.get(movement.item_id) ?? 'Inventory item'} />
              ))}
            </div>
          </section>
        </div>

        <div className="grid items-start gap-3 xl:grid-cols-2">
          <AttentionPanel items={insights.attentionItems} onSelect={(itemId) => navigate(`${base}/inventory/${itemId}`)} onHelp={() => setHelp(INVENTORY_HELP.attention)} />
          <ReorderPanel recommendations={insights.recommendations} onSelect={(itemId) => navigate(`${base}/inventory/${itemId}`)} onHelp={() => setHelp(INVENTORY_HELP.reorder)} />
        </div>

        <OrderQueue orders={visibleOrders} items={visibleItems} onChange={load} onHelp={() => setHelp(INVENTORY_HELP.orders)} />

        <section className="rounded-xl border border-w-line bg-w-surface p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div className="flex items-start gap-2">
              <div>
              <div className="flex items-center gap-2 text-sm font-medium text-w-text"><Sparkles size={15} className="text-w-accent" /> Add an item to the operating picture</div>
              <p className="mt-1 text-xs text-w-dim">Items can also auto-create when your team records stock activity in a channel.</p>
              </div>
              <InventoryHelpButton onClick={() => setHelp(INVENTORY_HELP.addItem)} />
            </div>
            <div className="flex w-full flex-col gap-2 sm:flex-row lg:w-auto">
              <Input
                label=""
                value={newItemName}
                onChange={(e) => setNewItemName(e.target.value)}
                placeholder="e.g. Cherry Farms Cookies"
                className="min-w-0 border-w-line bg-w-surface2 sm:w-64"
              />
              {locations.length > 0 && (
                <select
                  value={newItemLocation}
                  onChange={(e) => setNewItemLocation(e.target.value)}
                  className="rounded-lg border border-w-line bg-w-surface2 px-3 py-2 text-sm text-w-text outline-none focus:border-w-accent/50"
                >
                  <option value="">Company-wide</option>
                  {locations.map((l) => (
                    <option key={l.id} value={l.id}>{l.name}</option>
                  ))}
                </select>
              )}
              <Button onClick={handleAddItem} disabled={adding || !newItemName.trim()}>{adding ? 'Adding…' : 'Add item'}</Button>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

type StockState = 'healthy' | 'low' | 'out' | 'unknown'

type InventoryInsights = {
  totalItems: number
  knownCount: number
  knownPercent: number
  healthyCount: number
  lowCount: number
  outCount: number
  unknownCount: number
  attentionCount: number
  inventoryValue: number
  costedCount: number
  openOrderCount: number
  movementCount: number
  inboundCount: number
  outboundCount: number
  adjustmentCount: number
  lastMovement: InventoryMovement | null
  recentMovements: InventoryMovement[]
  itemNames: Map<string, string>
  attentionItems: InventoryItem[]
  recommendations: { item: InventoryItem; suggestion: InventorySuggestion }[]
}

function buildInsights(
  items: InventoryItem[],
  orders: InventoryOrder[],
  movements: InventoryMovement[],
  suggestions: Record<string, InventorySuggestion>,
): InventoryInsights {
  const itemNames = new Map(items.map((item) => [item.id, item.name]))
  const states = items.map((item) => getStockState(item))
  const knownCount = states.filter((state) => state !== 'unknown').length
  const healthyCount = states.filter((state) => state === 'healthy').length
  const lowCount = states.filter((state) => state === 'low').length
  const outCount = states.filter((state) => state === 'out').length
  const unknownCount = states.filter((state) => state === 'unknown').length
  const attentionItems = items
    .filter((item) => getStockState(item) !== 'healthy')
    .sort((a, b) => stockPriority(getStockState(a)) - stockPriority(getStockState(b)))
  const recommendations = Object.entries(suggestions)
    .map(([itemId, suggestion]) => {
      const item = items.find((candidate) => candidate.id === itemId)
      return item ? { item, suggestion } : null
    })
    .filter((entry): entry is { item: InventoryItem; suggestion: InventorySuggestion } => entry !== null)
    .sort((a, b) => a.suggestion.cover_days - b.suggestion.cover_days)
  const inventoryValue = items.reduce((total, item) => {
    if (item.current_quantity === null || item.unit_cost === null) return total
    return total + Number(item.current_quantity) * Number(item.unit_cost)
  }, 0)

  return {
    totalItems: items.length,
    knownCount,
    knownPercent: items.length ? Math.round((knownCount / items.length) * 100) : 0,
    healthyCount,
    lowCount,
    outCount,
    unknownCount,
    attentionCount: lowCount + outCount + unknownCount,
    inventoryValue,
    costedCount: items.filter((item) => item.unit_cost !== null).length,
    openOrderCount: orders.length,
    movementCount: movements.length,
    inboundCount: movements.filter((movement) => movement.kind === 'in').length,
    outboundCount: movements.filter((movement) => movement.kind === 'out' || movement.kind === 'sale' || movement.kind === 'stockout').length,
    adjustmentCount: movements.filter((movement) => movement.kind === 'adjust').length,
    lastMovement: movements[0] ?? null,
    recentMovements: movements,
    itemNames,
    attentionItems,
    recommendations,
  }
}

function getStockState(item: InventoryItem): StockState {
  if (item.current_quantity === null) return 'unknown'
  if (Number(item.current_quantity) <= 0) return 'out'
  if (item.low_stock_threshold !== null && Number(item.current_quantity) <= Number(item.low_stock_threshold)) return 'low'
  return 'healthy'
}

function stockPriority(state: StockState) {
  if (state === 'out') return 0
  if (state === 'low') return 1
  return 2
}

function formatQuantity(quantity: number | null, unit?: string | null) {
  if (quantity === null) return 'Unknown'
  const value = Number.isInteger(Number(quantity)) ? String(quantity) : Number(quantity).toFixed(1)
  return `${value}${unit ? ` ${unit}` : ''}`
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

function MetricCard({ icon: Icon, label, value, detail, tone }: {
  icon: import('lucide-react').LucideIcon
  label: string
  value: string
  detail: string
  tone: 'neutral' | 'green' | 'amber' | 'blue'
}) {
  const iconTone = {
    neutral: 'text-w-dim bg-w-surface2',
    green: 'text-w-accent bg-w-accent/10',
    amber: 'text-amber-300 bg-amber-400/10',
    blue: 'text-blue-300 bg-blue-400/10',
  }[tone]
  return (
    <div className="flex min-w-0 items-center gap-2.5 px-3 py-2.5">
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${iconTone}`}><Icon size={14} /></span>
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-semibold tracking-tight text-w-text">{value}</span>
          <span className="truncate text-xs font-medium text-w-dim">{label}</span>
        </div>
        <div className="truncate text-[10px] text-w-faint">{detail}</div>
      </div>
    </div>
  )
}

function HealthSegment({ count, total, color, label }: { count: number; total: number; color: string; label: string }) {
  if (!count || !total) return null
  return <div aria-label={`${label}: ${count}`} className={`${color} transition-[width] duration-500`} style={{ width: `${(count / total) * 100}%` }} />
}

function HealthLegend({ color, label, count }: { color: string; label: string; count: number }) {
  return (
    <div className="flex items-center gap-2 text-w-dim">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      <span>{label}</span>
      <span className="ml-auto font-mono text-w-text">{count}</span>
    </div>
  )
}

function FlowStat({ icon: Icon, label, value, tone }: { icon: import('lucide-react').LucideIcon; label: string; value: number; tone: string }) {
  return (
    <div className="rounded-lg bg-w-surface2 px-2.5 py-2">
      <div className={`flex items-center gap-1.5 text-[10px] uppercase tracking-wider ${tone}`}><Icon size={12} /> {label}</div>
      <div className="mt-1.5 text-lg font-semibold text-w-text">{value}</div>
    </div>
  )
}

function MovementRow({ movement, itemName }: { movement: InventoryMovement; itemName: string }) {
  const isInbound = movement.kind === 'in'
  const isAdjustment = movement.kind === 'adjust'
  const iconTone = isInbound ? 'text-w-accent' : isAdjustment ? 'text-blue-300' : 'text-amber-300'
  const label = movement.kind === 'stockout' ? 'Stockout' : movement.kind === 'sale' ? 'Sale' : movement.kind === 'adjust' ? 'Count adjusted' : movement.kind === 'in' ? 'Received' : 'Used'
  return (
    <div className="flex items-center gap-2.5 rounded-lg bg-w-surface2 px-2.5 py-2">
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-w-bg ${iconTone}`}>
        {isInbound ? <ArrowUpRight size={14} /> : isAdjustment ? <ClipboardCheck size={14} /> : <ArrowDownRight size={14} />}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-medium text-w-text">{itemName}</div>
        <div className="mt-0.5 flex items-center gap-1.5 text-[10px] text-w-faint"><Clock3 size={10} /> {label} · {formatDateTimePacific(movement.created_at)}</div>
      </div>
      <span className={`shrink-0 font-mono text-xs ${iconTone}`}>{movement.quantity_delta != null ? `${Number(movement.quantity_delta) > 0 ? '+' : ''}${movement.quantity_delta}` : movement.quantity ?? '—'}</span>
    </div>
  )
}

function AttentionPanel({ items, onSelect, onHelp }: { items: InventoryItem[]; onSelect: (itemId: string) => void; onHelp: () => void }) {
  return (
    <section className="rounded-xl bg-w-surface p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium text-w-text"><AlertTriangle size={15} className="text-amber-300" /> Needs attention</div>
          <p className="mt-1 text-xs text-w-dim">The items most likely to need a count, order, or follow-up.</p>
        </div>
        <div className="flex items-center gap-2"><InventoryHelpButton onClick={onHelp} />{items.length > 5 && <span className="rounded-full bg-amber-400/10 px-2 py-1 text-[10px] text-amber-200">+{items.length - 5} more</span>}</div>
      </div>
      <div className="mt-2.5 space-y-1">
        {items.length === 0 ? <EmptyInsight icon={CheckCircle2} message="Everything with a count is above threshold." tone="green" /> : items.slice(0, 5).map((item) => {
          const state = getStockState(item)
          const stateLabel = state === 'unknown' ? 'Count needed' : state === 'out' ? 'Out of stock' : 'Low stock'
          const stateTone = state === 'out' ? 'text-red-300 bg-red-400/10' : state === 'unknown' ? 'text-w-dim bg-w-surface2' : 'text-amber-200 bg-amber-400/10'
          return (
            <button type="button" key={item.id} onClick={() => onSelect(item.id)} className="flex w-full items-center gap-3 rounded-lg bg-w-surface2/70 px-2.5 py-1.5 text-left transition-colors hover:bg-w-surface2">
              <span className="min-w-0 flex-1"><span className="block truncate text-xs font-medium text-w-text">{item.name}</span><span className="mt-0.5 block text-[10px] text-w-faint">{item.location_name ?? 'Company-wide'}</span></span>
              <span className="shrink-0 text-xs text-w-dim">{formatQuantity(item.current_quantity, item.unit)}</span>
              <span className={`shrink-0 rounded-full px-2 py-1 text-[10px] font-medium ${stateTone}`}>{stateLabel}</span>
            </button>
          )
        })}
      </div>
    </section>
  )
}

function ReorderPanel({ recommendations, onSelect, onHelp }: { recommendations: { item: InventoryItem; suggestion: InventorySuggestion }[]; onSelect: (itemId: string) => void; onHelp: () => void }) {
  return (
    <section className="rounded-xl bg-w-surface p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium text-w-text"><Sparkles size={15} className="text-w-accent" /> Reorder intelligence</div>
          <p className="mt-1 text-xs text-w-dim">Suggestions calculated from the last 90 days of movement history.</p>
        </div>
        <div className="flex items-center gap-2"><InventoryHelpButton onClick={onHelp} /><span className="font-mono text-[10px] text-w-faint">90 days</span></div>
      </div>
      <div className="mt-2.5 space-y-1">
        {recommendations.length === 0 ? <EmptyInsight icon={Activity} message="Not enough movement history for a recommendation yet." tone="neutral" /> : recommendations.slice(0, 5).map(({ item, suggestion }) => (
          <button type="button" key={item.id} onClick={() => onSelect(item.id)} className="flex w-full items-center gap-3 rounded-lg bg-w-surface2/70 px-2.5 py-1.5 text-left transition-colors hover:bg-w-surface2">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-w-accent/10 text-w-accent"><ArrowDownRight size={15} /></span>
            <span className="min-w-0 flex-1"><span className="block truncate text-xs font-medium text-w-text">{item.name}</span><span className="mt-0.5 block text-[10px] text-w-faint">{suggestion.daily_rate != null ? `~${Number(suggestion.daily_rate).toFixed(1)}/day` : 'Usage trend forming'} · {suggestion.confidence} confidence</span></span>
            <span className="shrink-0 text-right"><span className="block text-xs font-medium text-w-text">{suggestion.suggested_quantity ?? '—'} {item.unit ?? 'units'}</span><span className="mt-0.5 block text-[10px] text-w-faint">{Math.round(suggestion.cover_days)} days cover</span></span>
          </button>
        ))}
      </div>
    </section>
  )
}

function EmptyInsight({ icon: Icon, message, tone }: { icon: import('lucide-react').LucideIcon; message: string; tone: 'green' | 'neutral' }) {
  return <div className="flex items-center gap-3 rounded-xl bg-w-surface2 px-3 py-4 text-xs text-w-dim"><Icon size={15} className={tone === 'green' ? 'text-w-accent' : 'text-w-faint'} /> {message}</div>
}
