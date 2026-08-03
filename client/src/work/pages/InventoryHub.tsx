import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { Button, Input, useToast } from '../../components/ui'
import ItemTable from '../components/inventory/ItemTable'
import ItemDetail from '../components/inventory/ItemDetail'
import OrderQueue from '../components/inventory/OrderQueue'
import { createItem, listItems, listOrders, type InventoryItem, type InventoryOrder } from '../api/inventory'
import { listChannelLocations, type ChannelLocation } from '../api/channels'

export default function InventoryHub() {
  const { itemId } = useParams<{ itemId: string }>()
  const { toast } = useToast()
  const [items, setItems] = useState<InventoryItem[]>([])
  const [orders, setOrders] = useState<InventoryOrder[]>([])
  const [locations, setLocations] = useState<ChannelLocation[]>([])
  const [locFilter, setLocFilter] = useState<'all' | 'none' | string>('all')
  const [loading, setLoading] = useState(true)
  const [newItemName, setNewItemName] = useState('')
  const [newItemLocation, setNewItemLocation] = useState('')
  const [adding, setAdding] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([listItems(), listOrders('queued')])
      .then(([itemsRes, ordersRes]) => {
        setItems(itemsRes.items)
        setOrders(ordersRes.orders)
      })
      .catch(() => toast('Failed to load inventory', 'error'))
      .finally(() => setLoading(false))
  }, [toast])

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
