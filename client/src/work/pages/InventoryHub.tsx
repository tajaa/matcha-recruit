import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { Button, Input, useToast } from '../../components/ui'
import ItemTable from '../components/inventory/ItemTable'
import ItemDetail from '../components/inventory/ItemDetail'
import OrderQueue from '../components/inventory/OrderQueue'
import { createItem, listItems, listOrders, type InventoryItem, type InventoryOrder } from '../api/inventory'

export default function InventoryHub() {
  const { itemId } = useParams<{ itemId: string }>()
  const { toast } = useToast()
  const [items, setItems] = useState<InventoryItem[]>([])
  const [orders, setOrders] = useState<InventoryOrder[]>([])
  const [loading, setLoading] = useState(true)
  const [newItemName, setNewItemName] = useState('')
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

  async function handleAddItem() {
    const name = newItemName.trim()
    if (!name) return
    setAdding(true)
    try {
      await createItem({ name })
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
      <h2 className="text-lg font-medium">Inventory</h2>
      <OrderQueue orders={orders} items={items} onChange={load} />
      <div className="flex items-end gap-2">
        <Input
          label="Add item"
          value={newItemName}
          onChange={(e) => setNewItemName(e.target.value)}
          placeholder="e.g. Cherry Farms Cookies"
        />
        <Button onClick={handleAddItem} disabled={adding || !newItemName.trim()}>Add item</Button>
      </div>
      <ItemTable items={items} />
    </div>
  )
}
