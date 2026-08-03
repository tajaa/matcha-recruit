import { useNavigate } from 'react-router-dom'
import { Badge } from '../../../components/ui'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import type { InventoryItem } from '../../api/inventory'

export default function ItemTable({ items }: { items: InventoryItem[] }) {
  const navigate = useNavigate()
  const base = useWorkBase()

  if (items.length === 0) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">No items yet — they auto-create the first time someone mentions them in a channel, or add one manually.</p>
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
      <table className="w-full text-sm">
        <thead className="bg-zinc-50 dark:bg-zinc-900 text-left text-zinc-500 dark:text-zinc-400">
          <tr>
            <th className="px-4 py-2 font-medium">Name</th>
            <th className="px-4 py-2 font-medium">Unit</th>
            <th className="px-4 py-2 font-medium">Count</th>
            <th className="px-4 py-2 font-medium">Threshold</th>
            <th className="px-4 py-2 font-medium">Order</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {items.map((item) => (
            <tr
              key={item.id}
              onClick={() => navigate(`${base}/inventory/${item.id}`)}
              className="cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-900"
            >
              <td className="px-4 py-2">
                {item.name}
                {item.location_name && (
                  <span className="ml-2 text-xs text-zinc-400 dark:text-zinc-500">· {item.location_name}</span>
                )}
              </td>
              <td className="px-4 py-2 text-zinc-500 dark:text-zinc-400">{item.unit ?? '—'}</td>
              <td className="px-4 py-2">
                {item.current_quantity !== null ? item.current_quantity : <span className="text-zinc-400">unknown</span>}
              </td>
              <td className="px-4 py-2 text-zinc-500 dark:text-zinc-400">{item.low_stock_threshold ?? '—'}</td>
              <td className="px-4 py-2">
                {item.open_order && <Badge variant="warning">{item.open_order.status}</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
