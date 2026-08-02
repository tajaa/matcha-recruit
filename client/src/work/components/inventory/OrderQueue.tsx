import { Button, useToast } from '../../../components/ui'
import { approveOrder, cancelOrder, receiveOrder, type InventoryItem, type InventoryOrder } from '../../api/inventory'

export default function OrderQueue({
  orders,
  items,
  onChange,
}: {
  orders: InventoryOrder[]
  items: InventoryItem[]
  onChange: () => void
}) {
  const { toast } = useToast()

  if (orders.length === 0) return null

  async function handle(action: () => Promise<unknown>, label: string) {
    try {
      await action()
      toast(label, 'success')
      onChange()
    } catch {
      toast(`Failed to ${label.toLowerCase()}`, 'error')
    }
  }

  return (
    <div>
      <h3 className="text-sm font-medium text-zinc-500 dark:text-zinc-400 mb-2">Order queue</h3>
      <div className="space-y-2">
        {orders.map((order) => {
          const suggestion = order.suggestion as Record<string, unknown> | null
          const dailyRate = suggestion?.daily_rate as number | null | undefined
          const stockoutInterval = suggestion?.avg_stockout_interval_days as number | null | undefined
          const itemName = items.find((i) => i.id === order.item_id)?.name
          return (
            <div key={order.id} className="rounded-lg border border-zinc-200 dark:border-zinc-800 px-4 py-3 flex items-center justify-between">
              <div>
                <p className="text-sm">
                  {itemName ?? 'Item'}: {order.quantity ?? order.suggested_quantity ?? '—'}
                </p>
                {(dailyRate != null || stockoutInterval != null) && (
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {dailyRate != null ? `~${dailyRate.toFixed(1)}/day` : ''}
                    {dailyRate != null && stockoutInterval != null ? ', ' : ''}
                    {stockoutInterval != null ? `ran out every ~${Math.round(stockoutInterval)} days` : ''}
                  </p>
                )}
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => handle(() => approveOrder(order.id), 'Order approved')}>Approve</Button>
                <Button size="sm" variant="secondary" onClick={() => handle(() => receiveOrder(order.id), 'Order received')}>Receive</Button>
                <Button size="sm" variant="ghost" className="text-red-400 hover:text-red-300" onClick={() => handle(() => cancelOrder(order.id), 'Order cancelled')}>Cancel</Button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
