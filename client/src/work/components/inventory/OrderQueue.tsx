import { Button, useToast } from '../../../components/ui'
import { approveOrder, cancelOrder, receiveOrder, type InventoryOrder } from '../../api/inventory'

export default function OrderQueue({ orders, onChange }: { orders: InventoryOrder[]; onChange: () => void }) {
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
          const dailyRate = suggestion?.daily_rate as number | undefined
          const stockoutInterval = suggestion?.avg_stockout_interval_days as number | undefined
          return (
            <div key={order.id} className="rounded-lg border border-zinc-200 dark:border-zinc-800 px-4 py-3 flex items-center justify-between">
              <div>
                <p className="text-sm">Queued: {order.quantity ?? order.suggested_quantity ?? '—'}</p>
                {(dailyRate || stockoutInterval) && (
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {dailyRate ? `~${dailyRate.toFixed(1)}/day` : ''}
                    {dailyRate && stockoutInterval ? ', ' : ''}
                    {stockoutInterval ? `ran out every ~${Math.round(stockoutInterval)} days` : ''}
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
