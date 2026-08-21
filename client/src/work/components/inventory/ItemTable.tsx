import { useNavigate } from 'react-router-dom'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import type { InventoryItem } from '../../api/inventory'

export default function ItemTable({ items }: { items: InventoryItem[] }) {
  const navigate = useNavigate()
  const base = useWorkBase()

  if (items.length === 0) {
    return <p className="px-5 py-10 text-center text-sm text-w-dim">No items yet. They auto-create from channel activity, or you can add one below.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[680px] text-sm">
        <thead className="bg-w-surface2/60 text-left text-[10px] uppercase tracking-[0.16em] text-w-faint">
          <tr>
            <th className="px-3 py-2.5 font-medium">Item</th>
            <th className="px-3 py-2.5 font-medium">On hand</th>
            <th className="px-3 py-2.5 font-medium">Threshold</th>
            <th className="px-3 py-2.5 font-medium">Location</th>
            <th className="px-3 py-2.5 font-medium">Next action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-w-line">
          {items.map((item) => (
            <tr
              key={item.id}
              onClick={() => navigate(`${base}/inventory/${item.id}`)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') navigate(`${base}/inventory/${item.id}`)
              }}
              tabIndex={0}
              role="button"
              className="cursor-pointer transition-colors hover:bg-w-surface2/55 focus:bg-w-surface2/55 focus:outline-none"
            >
              <td className="px-3 py-2.5">
                <div className="flex items-center gap-2.5">
                  <span className={`h-2 w-2 rounded-full ${stockColor(item)}`} />
                  <div className="min-w-0">
                    <div className="truncate font-medium text-w-text">{item.name}</div>
                    <div className="mt-0.5 text-[11px] text-w-faint">{item.auto_created ? 'Auto-created from channel activity' : 'Manually managed'}</div>
                  </div>
                </div>
              </td>
              <td className="px-3 py-2.5">
                <div className="font-medium text-w-text">{item.current_quantity !== null ? item.current_quantity : <span className="text-w-dim">Unknown</span>}</div>
                <div className="mt-0.5 text-[11px] text-w-faint">{item.unit ?? 'units'}</div>
              </td>
              <td className="px-3 py-2.5 text-w-dim">{item.low_stock_threshold ?? 'Not set'}</td>
              <td className="px-3 py-2.5 text-w-dim">{item.location_name ?? 'Company-wide'}</td>
              <td className="px-3 py-2.5">
                {item.open_order ? (
                  <span className="rounded-full bg-amber-400/10 px-2.5 py-1 text-[10px] font-medium capitalize text-amber-200">{item.open_order.status}</span>
                ) : item.current_quantity === null ? (
                  <span className="text-xs text-w-dim">Set a count</span>
                ) : item.current_quantity <= 0 ? (
                  <span className="text-xs text-red-300">Queue an order</span>
                ) : item.low_stock_threshold !== null && item.current_quantity <= item.low_stock_threshold ? (
                  <span className="text-xs text-amber-200">Review stock</span>
                ) : (
                  <span className="text-xs text-w-accent">Healthy</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function stockColor(item: InventoryItem) {
  if (item.current_quantity === null) return 'bg-w-faint'
  if (item.current_quantity <= 0) return 'bg-red-400'
  if (item.low_stock_threshold !== null && item.current_quantity <= item.low_stock_threshold) return 'bg-amber-400'
  return 'bg-w-accent'
}
