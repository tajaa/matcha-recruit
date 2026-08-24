import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Archive, Clock3, Loader2 } from 'lucide-react'
import { Button, Input, useToast } from '../../../components/ui'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import { getItem, patchItem, type InventoryItem, type InventoryMovement } from '../../api/inventory'
import { useMe } from '../../../hooks/useMe'
import {
  INVENTORY_HELP,
  InventoryHelpButton,
  InventoryHelpModal,
  type InventorySectionHelp,
} from './InventoryHelp'

export default function ItemDetail({ itemId }: { itemId: string }) {
  const navigate = useNavigate()
  const base = useWorkBase()
  const { toast } = useToast()
  const { hasFeature } = useMe()
  const canSales = hasFeature('sales_intake')
  const [item, setItem] = useState<InventoryItem | null>(null)
  const [movements, setMovements] = useState<InventoryMovement[]>([])
  const [expected, setExpected] = useState<Awaited<ReturnType<typeof getItem>>['expected']>(null)
  const [loading, setLoading] = useState(true)
  const [countInput, setCountInput] = useState('')
  const [help, setHelp] = useState<InventorySectionHelp | null>(null)

  const load = () => {
    setLoading(true)
    getItem(itemId)
      .then(({ item: it, movements: mv, expected: breakdown }) => {
        setItem(it)
        setMovements(mv)
        setExpected(breakdown ?? null)
        setCountInput(it.current_quantity !== null ? String(it.current_quantity) : '')
      })
      .catch(() => toast('Failed to load item', 'error'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemId])

  async function handleAdjust() {
    if (countInput.trim() === '') return
    const value = Number(countInput)
    if (Number.isNaN(value)) return
    try {
      await patchItem(itemId, { set_quantity: value })
      toast('Count updated', 'success')
      load()
    } catch {
      toast('Failed to update count', 'error')
    }
  }

  async function handleArchive() {
    try {
      await patchItem(itemId, { archived: true })
      toast('Item archived', 'success')
      navigate(`${base}/inventory`)
    } catch {
      toast('Failed to archive item', 'error')
    }
  }

  if (loading || !item) {
    return (
      <div className="flex h-full items-center justify-center bg-w-bg text-w-dim">
        <Loader2 className="animate-spin" />
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto bg-w-bg text-w-text">
      <div className="mx-auto max-w-[1200px] space-y-4 p-3 sm:p-4">
        <button type="button" onClick={() => navigate(`${base}/inventory`)} className="inline-flex items-center gap-1.5 text-xs font-medium text-w-dim transition-colors hover:text-w-text">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to inventory
        </button>

        <header className="flex flex-col gap-3 rounded-xl border border-w-line bg-w-surface p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.18em] text-w-accent">
              <span className={`h-2 w-2 rounded-full ${stockColor(item)}`} /> Inventory item
            </div>
            <h1 className="truncate text-2xl font-semibold tracking-tight text-w-text">{item.name}</h1>
            <p className="mt-1 text-sm text-w-dim">
              {item.current_quantity !== null ? `${item.current_quantity} ${item.unit ?? 'units'} in stock` : 'Count unknown'}
              <span className="mx-2 text-w-faint">·</span>{item.location_name ?? 'Company-wide'}
            </p>
          </div>
          <Button variant="ghost" size="sm" className="self-start text-red-300 hover:bg-red-400/10 hover:text-red-200 sm:self-center" onClick={handleArchive}>
            <Archive className="h-3.5 w-3.5" /> Archive
          </Button>
        </header>

        <div className="grid items-start gap-3 lg:grid-cols-[0.85fr_1.15fr]">
          <section className="rounded-xl border border-w-line bg-w-surface p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-medium text-w-text">Set count</h2>
                <p className="mt-1 text-xs text-w-dim">Update the physical quantity currently on hand.</p>
              </div>
              <InventoryHelpButton onClick={() => setHelp(INVENTORY_HELP.detailCount)} />
            </div>
            <div className="mt-4 flex items-end gap-2">
              <div className="min-w-0 flex-1"><Input label="Current quantity" value={countInput} onChange={(e) => setCountInput(e.target.value)} className="border-w-line bg-w-surface2" /></div>
              <Button onClick={handleAdjust}>Update</Button>
            </div>
            <p className="mt-3 text-[11px] text-w-faint">Saving creates an adjustment in the movement ledger.</p>
          </section>

          {canSales && expected ? (
            <section className="rounded-xl border border-w-line bg-w-surface p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-medium text-w-text">Expected vs last count</h2>
                  <p className="mt-1 text-xs text-w-dim">A quick variance check against the last physical baseline.</p>
                </div>
                <InventoryHelpButton onClick={() => setHelp(INVENTORY_HELP.detailExpected)} />
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                <DetailStat label="Expected now" value={`${expected.expected ?? '?'} ${item.unit ?? ''}`} />
                <DetailStat label="Last counted" value={`${expected.baseline ?? '?'} ${expected.baseline_at ? `· ${new Date(expected.baseline_at).toLocaleDateString()}` : ''}`} />
              </div>
              <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-t border-w-line pt-3 text-xs text-w-dim">
                <span>Received <strong className="font-medium text-w-text">{expected.received}</strong></span>
                <span>Sold <strong className="font-medium text-w-text">{expected.sold}</strong></span>
                <span>Used <strong className="font-medium text-w-text">{expected.manual_out}</strong></span>
                <span>Stockouts <strong className="font-medium text-w-text">{expected.stockouts}</strong></span>
              </div>
            </section>
          ) : (
            <section className="flex items-center rounded-xl border border-dashed border-w-line bg-w-surface/60 p-4">
              <div className="flex w-full items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-medium text-w-text">Movement context</h2>
                  <p className="mt-1 text-xs leading-5 text-w-dim">Enable sales intake to compare this item with a theoretical expected count.</p>
                </div>
                <InventoryHelpButton onClick={() => setHelp(INVENTORY_HELP.detailExpected)} />
              </div>
            </section>
          )}
        </div>

        <section className="rounded-xl border border-w-line bg-w-surface p-4"><h2 className="text-sm font-medium text-w-text">Perishable & par settings</h2><div className="mt-3 grid gap-2 sm:grid-cols-4"><DetailStat label="Category" value={item.category ?? 'Uncategorized'} /><DetailStat label="Shelf life" value={item.shelf_life_days ? `${item.shelf_life_days} days` : 'Not set'} /><DetailStat label="Yield" value={item.yield_pct ? `${Math.round(item.yield_pct * 100)}%` : '100%'} /><DetailStat label="Par source" value={item.par_source === 'auto' ? 'Auto-managed' : 'Manual'} /></div></section>

        <section className="overflow-hidden rounded-xl border border-w-line bg-w-surface">
          <div className="flex items-start justify-between gap-3 border-b border-w-line px-4 py-3">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-medium text-w-text"><Clock3 className="h-4 w-4 text-w-accent" /> Movement ledger</h2>
              <p className="mt-1 text-xs text-w-dim">Every quantity-changing event recorded for this item.</p>
            </div>
            <InventoryHelpButton onClick={() => setHelp(INVENTORY_HELP.detailLedger)} />
          </div>
          <div className="divide-y divide-w-line">
            {movements.length === 0 && <p className="px-4 py-6 text-sm text-w-dim">No movements yet.</p>}
            {movements.map((movement) => (
              <div key={movement.id} className="flex flex-col gap-1 px-4 py-2.5 text-sm sm:flex-row sm:items-center sm:justify-between sm:gap-4">
                <span className="text-w-text">{movement.narrative}</span>
                <span className="shrink-0 text-xs text-w-dim">{movement.kind} {movement.quantity ?? ''} <span className="text-w-faint">·</span> {new Date(movement.created_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        </section>
        <InventoryHelpModal help={help} onClose={() => setHelp(null)} />
      </div>
    </div>
  )
}

function DetailStat({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-w-surface2 px-3 py-3"><p className="text-[10px] uppercase tracking-[0.14em] text-w-faint">{label}</p><p className="mt-1 text-lg font-semibold text-w-text">{value}</p></div>
}

function stockColor(item: InventoryItem) {
  if (item.current_quantity === null) return 'bg-w-faint'
  if (item.current_quantity <= 0) return 'bg-red-400'
  if (item.low_stock_threshold !== null && item.current_quantity <= item.low_stock_threshold) return 'bg-amber-400'
  return 'bg-w-accent'
}
