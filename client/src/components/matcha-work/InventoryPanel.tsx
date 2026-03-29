import { useState, useMemo } from 'react'
import { Search, ChevronDown, ChevronUp, Package, Loader2 } from 'lucide-react'
import type { InventoryItem } from '../../types/matcha-work'

type SortKey = 'product_name' | 'quantity' | 'unit_cost' | 'total_cost' | 'vendor'

const CATEGORIES = ['all', 'protein', 'produce', 'dairy', 'dry_goods', 'beverages', 'supplies', 'equipment', 'other'] as const
const CAT_LABELS: Record<string, string> = {
  all: 'All', protein: 'Protein', produce: 'Produce', dairy: 'Dairy',
  dry_goods: 'Dry Goods', beverages: 'Beverages', supplies: 'Supplies',
  equipment: 'Equipment', other: 'Other',
}

interface InventoryPanelProps {
  state: Record<string, unknown>
  threadId: string
  lightMode: boolean
  streaming: boolean
}

export default function InventoryPanel({ state, lightMode, streaming }: InventoryPanelProps) {
  const items = (state.inventory_items as InventoryItem[] | undefined) ?? []
  const totalCount = (state.inventory_total_count as number) ?? items.length
  const totalCost = (state.inventory_total_cost as number) ?? 0
  const vendors = (state.inventory_vendors as string[]) ?? []

  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('total_cost')
  const [sortAsc, setSortAsc] = useState(false)
  const [category, setCategory] = useState('all')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    let list = [...items]
    if (category !== 'all') {
      list = list.filter((i) => i.category === category)
    }
    if (q) {
      list = list.filter(
        (i) =>
          i.product_name?.toLowerCase().includes(q) ||
          i.sku?.toLowerCase().includes(q) ||
          i.vendor?.toLowerCase().includes(q)
      )
    }
    list.sort((a, b) => {
      let av: string | number, bv: string | number
      if (sortKey === 'product_name' || sortKey === 'vendor') {
        av = (a[sortKey] ?? '').toString().toLowerCase()
        bv = (b[sortKey] ?? '').toString().toLowerCase()
      } else {
        av = (a[sortKey] as number) ?? 0
        bv = (b[sortKey] as number) ?? 0
      }
      if (av < bv) return sortAsc ? -1 : 1
      if (av > bv) return sortAsc ? 1 : -1
      return 0
    })
    return list
  }, [items, search, sortKey, sortAsc, category])

  // Categories that actually have items
  const activeCats = useMemo(() => {
    const cats = new Set(items.map((i) => i.category ?? 'other'))
    return CATEGORIES.filter((c) => c === 'all' || cats.has(c))
  }, [items])

  function handleSort(key: SortKey) {
    if (sortKey === key) setSortAsc(!sortAsc)
    else { setSortKey(key); setSortAsc(key === 'product_name' || key === 'vendor') }
  }

  const lm = lightMode
  const th = {
    bg: lm ? 'bg-white' : 'bg-zinc-950',
    border: lm ? 'border-zinc-200' : 'border-zinc-800',
    text: lm ? 'text-zinc-900' : 'text-zinc-100',
    sub: lm ? 'text-zinc-500' : 'text-zinc-400',
    muted: lm ? 'text-zinc-400' : 'text-zinc-500',
    card: lm ? 'bg-zinc-50 border-zinc-200 hover:bg-zinc-100' : 'bg-zinc-900 border-zinc-800 hover:bg-zinc-800/80',
    input: lm ? 'bg-zinc-100 text-zinc-900 border-zinc-300 placeholder-zinc-400' : 'bg-zinc-900 text-white border-zinc-700 placeholder-zinc-500',
    tag: lm ? 'bg-zinc-200 text-zinc-600' : 'bg-zinc-800 text-zinc-300',
    cost: lm ? 'text-emerald-700' : 'text-emerald-400',
    sortBtn: lm ? 'text-zinc-400 hover:text-zinc-700' : 'text-zinc-500 hover:text-zinc-200',
    sortActive: lm ? 'text-emerald-600' : 'text-emerald-400',
    catActive: lm ? 'bg-emerald-100 text-emerald-700 border-emerald-300' : 'bg-emerald-900/30 text-emerald-400 border-emerald-700/40',
    catInactive: lm ? 'bg-zinc-100 text-zinc-500 border-zinc-200 hover:bg-zinc-200' : 'bg-zinc-900 text-zinc-400 border-zinc-700 hover:bg-zinc-800',
  }

  if (items.length === 0 && !streaming) {
    return (
      <div className={`hidden md:flex md:w-1/2 items-center justify-center ${th.bg}`}>
        <p className={`text-sm ${th.muted}`}>
          No inventory yet — drop invoices or spreadsheets to start.
        </p>
      </div>
    )
  }

  return (
    <div className={`hidden md:flex md:w-1/2 flex-col ${th.bg}`}>
      {/* Header */}
      <div className={`px-4 py-3 border-b ${th.border}`}>
        <div className="flex items-center justify-between">
          <div>
            <h3 className={`text-sm font-semibold ${th.text}`}>Inventory</h3>
            <p className={`text-xs ${th.muted} mt-0.5`}>
              {totalCount} items &middot; ${totalCost.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              {streaming && <Loader2 size={10} className="inline ml-1.5 animate-spin" />}
            </p>
          </div>
          {vendors.length > 0 && (
            <div className={`text-[10px] ${th.muted}`}>
              {vendors.length} vendor{vendors.length !== 1 ? 's' : ''}
            </div>
          )}
        </div>
      </div>

      {/* Search + Sort */}
      <div className={`px-4 py-2 border-b ${th.border} space-y-2`}>
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search size={12} className={`absolute left-2.5 top-1/2 -translate-y-1/2 ${th.muted}`} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search product, SKU, vendor..."
              className={`w-full text-xs rounded pl-7 pr-2 py-1.5 border focus:outline-none focus:border-emerald-600 ${th.input}`}
            />
          </div>
          <div className="flex gap-1">
            {(['total_cost', 'quantity', 'product_name'] as SortKey[]).map((key) => {
              const labels: Record<SortKey, string> = { product_name: 'Name', quantity: 'Qty', unit_cost: 'Unit$', total_cost: 'Total', vendor: 'Vendor' }
              const active = sortKey === key
              return (
                <button
                  key={key}
                  onClick={() => handleSort(key)}
                  className={`text-[10px] font-medium px-2 py-1 rounded transition-colors ${active ? th.sortActive : th.sortBtn}`}
                >
                  {labels[key]}
                  {active && (sortAsc ? <ChevronUp size={8} className="inline ml-0.5" /> : <ChevronDown size={8} className="inline ml-0.5" />)}
                </button>
              )
            })}
          </div>
        </div>
        {/* Category pills */}
        {activeCats.length > 2 && (
          <div className="flex gap-1 flex-wrap">
            {activeCats.map((cat) => (
              <button
                key={cat}
                onClick={() => setCategory(cat)}
                className={`text-[10px] font-medium px-2 py-0.5 rounded-full border transition-colors ${
                  category === cat ? th.catActive : th.catInactive
                }`}
              >
                {CAT_LABELS[cat] ?? cat}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Items */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-1.5">
        {filtered.map((item) => {
          const expanded = expandedId === item.id
          return (
            <div
              key={item.id}
              onClick={() => setExpandedId(expanded ? null : item.id)}
              className={`rounded-lg border px-3 py-2 cursor-pointer transition-colors ${th.card}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className={`text-sm font-medium truncate ${th.text}`}>{item.product_name ?? 'Unknown Item'}</p>
                  <p className={`text-xs ${th.sub}`}>
                    {item.quantity != null && <>{item.quantity} {item.unit ?? 'ea'}</>}
                    {item.unit_cost != null && <> &middot; ${item.unit_cost.toFixed(2)}/{item.unit ?? 'ea'}</>}
                    {item.vendor && <> &middot; {item.vendor}</>}
                  </p>
                </div>
                {item.total_cost != null && (
                  <span className={`text-xs font-semibold shrink-0 ${th.cost}`}>
                    ${item.total_cost.toFixed(2)}
                  </span>
                )}
              </div>
              {expanded && (
                <div className={`mt-2 pt-2 border-t border-dashed space-y-1 text-xs ${th.sub}`} style={{ borderColor: lm ? '#e4e4e7' : '#27272a' }}>
                  {item.sku && <p>SKU: {item.sku}</p>}
                  {item.category && <p>Category: {CAT_LABELS[item.category] ?? item.category}</p>}
                  <p className={th.muted}>Source: {item.filename}</p>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Footer */}
      <div className={`px-4 py-2 border-t ${th.border} flex items-center justify-between`}>
        <p className={`text-[10px] ${th.muted}`}>
          {filtered.length} item{filtered.length !== 1 ? 's' : ''}
          {search && ` matching "${search}"`}
          {category !== 'all' && ` in ${CAT_LABELS[category]}`}
        </p>
        {vendors.length > 0 && (
          <p className={`text-[10px] ${th.muted}`}>
            {vendors.join(', ')}
          </p>
        )}
      </div>
    </div>
  )
}
