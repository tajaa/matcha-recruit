import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import ItemTable from '../components/inventory/ItemTable'
import ItemDetail from '../components/inventory/ItemDetail'
import OrderQueue from '../components/inventory/OrderQueue'
import { listItems, listOrders, type InventoryItem, type InventoryOrder } from '../api/inventory'

export default function InventoryHub() {
  const { itemId } = useParams<{ itemId: string }>()
  const [items, setItems] = useState<InventoryItem[]>([])
  const [orders, setOrders] = useState<InventoryOrder[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([listItems(), listOrders('queued')])
      .then(([itemsRes, ordersRes]) => {
        setItems(itemsRes.items)
        setOrders(ordersRes.orders)
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

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
      <OrderQueue orders={orders} onChange={load} />
      <ItemTable items={items} />
    </div>
  )
}
