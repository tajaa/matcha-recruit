import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ClipboardCheck, Loader2, Upload, Wrench } from 'lucide-react'
import { Button, Input, useToast } from '../../components/ui'
import ItemTable from '../components/inventory/ItemTable'
import ItemDetail from '../components/inventory/ItemDetail'
import OrderQueue from '../components/inventory/OrderQueue'
import ReceiveDeliveryModal from '../components/inventory/ReceiveDeliveryModal'
import SalesImportModal from '../components/inventory/SalesImportModal'
import SalesMappingsPanel from '../components/inventory/SalesMappingsPanel'
import { createItem, listItems, listOrders, listSalesImports, type InventoryItem, type InventoryOrder } from '../api/inventory'
import { listChannelLocations, type ChannelLocation } from '../api/channels'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import { useMe } from '../../hooks/useMe'

export default function InventoryHub() {
  const { itemId } = useParams<{ itemId: string }>()
  const navigate = useNavigate()
  const base = useWorkBase()
  const { toast } = useToast()
  const { hasFeature } = useMe()
  const canSales = hasFeature('sales_intake')
  const [items, setItems] = useState<InventoryItem[]>([])
  const [orders, setOrders] = useState<InventoryOrder[]>([])
  const [locations, setLocations] = useState<ChannelLocation[]>([])
  const [locFilter, setLocFilter] = useState<'all' | 'none' | string>('all')
  const [loading, setLoading] = useState(true)
  const [newItemName, setNewItemName] = useState('')
  const [newItemLocation, setNewItemLocation] = useState('')
  const [adding, setAdding] = useState(false)
  const [receiveOpen, setReceiveOpen] = useState(false)
  const [salesOpen, setSalesOpen] = useState(false)
  const [mappingsOpen, setMappingsOpen] = useState(false)
  const [draftCount, setDraftCount] = useState(0)
  const [reviewImportId, setReviewImportId] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    const salesRequest = canSales ? listSalesImports('draft') : Promise.resolve({ imports: [] })
    Promise.all([listItems(), listOrders('queued'), salesRequest])
      .then(([itemsRes, ordersRes, salesRes]) => {
        setItems(itemsRes.items)
        setOrders(ordersRes.orders)
        setDraftCount(salesRes.imports.length)
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
    if (locFilter === 'all') return items
    if (locFilter === 'none') return items.filter((i) => !i.location_id)
    return items.filter((i) => i.location_id === locFilter)
  }, [items, locFilter])

  const visibleOrders = useMemo(() => {
    const visibleIds = new Set(visibleItems.map((i) => i.id))
    return orders.filter((o) => visibleIds.has(o.item_id))
  }, [orders, visibleItems])

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
      <div className="flex items-center justify-center py-12">
        <Loader2 className="animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Inventory</h2>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => navigate(`${base}/inventory/audit`)}>
            <ClipboardCheck className="mr-1.5 inline h-3.5 w-3.5" /> Audit
          </Button>
          {canSales && <Button variant="secondary" onClick={() => { setReviewImportId(null); setSalesOpen(true) }}>
            <Upload className="mr-1.5 inline h-3.5 w-3.5" /> Import sales
          </Button>}
          <Button onClick={() => setReceiveOpen(true)}>Receive delivery</Button>
          {locations.length > 0 && (
            <select
              value={locFilter}
              onChange={(e) => setLocFilter(e.target.value)}
              className="text-sm rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-2 py-1"
            >
              <option value="all">All locations</option>
              {locations.map((l) => (
                <option key={l.id} value={l.id}>{l.name}</option>
              ))}
              <option value="none">Unassigned</option>
            </select>
          )}
        </div>
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
      {canSales && draftCount > 0 && (
        <div className="flex items-center justify-between rounded-xl border border-amber-500/25 bg-amber-500/[0.06] px-4 py-3 text-sm">
          <span className="text-amber-300">{draftCount} sales import{draftCount === 1 ? '' : 's'} waiting for review.</span>
          <Button variant="secondary" onClick={() => {
            listSalesImports('draft').then((result) => {
              setReviewImportId(result.imports[0]?.id ?? null)
              setSalesOpen(true)
            }).catch(() => toast('Failed to load sales drafts', 'error'))
          }}>Review imports</Button>
        </div>
      )}
      {canSales && <Button variant="ghost" onClick={() => setMappingsOpen((open) => !open)}>
        <Wrench className="mr-1.5 inline h-3.5 w-3.5" /> {mappingsOpen ? 'Hide mappings' : 'Manage mappings'}
      </Button>}
      {canSales && mappingsOpen && <SalesMappingsPanel
        items={visibleItems}
        locationId={locFilter !== 'all' && locFilter !== 'none' ? locFilter : undefined}
      />}
      <OrderQueue orders={visibleOrders} items={visibleItems} onChange={load} />
      <div className="flex items-end gap-2">
        <Input
          label="Add item"
          value={newItemName}
          onChange={(e) => setNewItemName(e.target.value)}
          placeholder="e.g. Cherry Farms Cookies"
        />
        {locations.length > 0 && (
          <select
            value={newItemLocation}
            onChange={(e) => setNewItemLocation(e.target.value)}
            className="text-sm rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-2 py-2"
          >
            <option value="">— Company-wide —</option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
        )}
        <Button onClick={handleAddItem} disabled={adding || !newItemName.trim()}>Add item</Button>
      </div>
      <ItemTable items={visibleItems} />
    </div>
  )
}
