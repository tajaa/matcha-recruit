import { Button, useToast } from '../../../components/ui'
import { approveOrder, cancelOrder, receiveOrder, type InventoryItem, type InventoryOrder } from '../../api/inventory'
import { InventoryHelpButton } from './InventoryHelp'

export default function OrderQueue({
  orders,
  items,
  onChange,
  onHelp,
}: {
  orders: InventoryOrder[]
  items: InventoryItem[]
  onChange: () => void
  onHelp?: () => void
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
    <section className="rounded-xl border border-w-line bg-w-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium text-w-text">Order queue</h3>
          <p className="mt-1 text-xs text-w-dim">Orders staged from stockout signals or manually queued for approval.</p>
        </div>
        <div className="flex items-center gap-2"><InventoryHelpButton onClick={() => onHelp?.()} /><span className="rounded-full bg-amber-400/10 px-2.5 py-1 text-[10px] font-medium text-amber-200">{orders.length} waiting</span></div>
      </div>
      <div className="mt-3 space-y-1.5">
        {orders.map((order) => {
          const suggestion = order.suggestion as Record<string, unknown> | null
          const dailyRate = suggestion?.daily_rate as number | null | undefined
          const stockoutInterval = suggestion?.avg_stockout_interval_days as number | null | undefined
          const itemName = items.find((i) => i.id === order.item_id)?.name
          return (
            <div key={order.id} className="flex flex-col gap-2 rounded-lg bg-w-surface2/70 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-medium text-w-text">
                  {itemName ?? 'Item'}: {order.quantity ?? order.suggested_quantity ?? '—'}
                </p>
                {(dailyRate != null || stockoutInterval != null) && (
                  <p className="mt-1 text-xs text-w-dim">
                    {dailyRate != null ? `~${dailyRate.toFixed(1)}/day` : ''}
                    {dailyRate != null && stockoutInterval != null ? ', ' : ''}
                    {stockoutInterval != null ? `ran out every ~${Math.round(stockoutInterval)} days` : ''}
                  </p>
                )}
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => handle(() => approveOrder(order.id), 'Order approved')}>Approve</Button>
                <Button size="sm" variant="secondary" onClick={() => handle(() => receiveOrder(order.id), 'Order received')}>Receive</Button>
                <Button size="sm" variant="ghost" className="text-red-300 hover:text-red-200" onClick={() => handle(() => cancelOrder(order.id), 'Order cancelled')}>Cancel</Button>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
