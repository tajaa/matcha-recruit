import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { Button, Input, useToast } from '../../../components/ui'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import { getItem, patchItem, type InventoryItem, type InventoryMovement } from '../../api/inventory'
import { useMe } from '../../../hooks/useMe'

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
      <div className="flex items-center justify-center py-12">
        <Loader2 className="animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium">{item.name}</h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {item.current_quantity !== null ? `${item.current_quantity} ${item.unit ?? ''} in stock` : 'Count unknown'}
          </p>
        </div>
        <Button variant="ghost" className="text-red-400 hover:text-red-300" onClick={handleArchive}>Archive</Button>
      </div>

      <div className="flex items-end gap-2">
        <Input label="Set count" value={countInput} onChange={(e) => setCountInput(e.target.value)} />
        <Button onClick={handleAdjust}>Update</Button>
      </div>

      {canSales && expected && (
        <div className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
          <h3 className="text-sm font-medium">Expected vs last count</h3>
          <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
            <div><p className="text-xs text-zinc-500">Expected now</p><p className="text-lg">{expected.expected ?? '?'} {item.unit ?? ''}</p></div>
            <div><p className="text-xs text-zinc-500">Last counted</p><p className="text-lg">{expected.baseline ?? '?'} {expected.baseline_at ? `· ${new Date(expected.baseline_at).toLocaleDateString()}` : ''}</p></div>
          </div>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-500">
            <span>Received {expected.received}</span>
            <span>Sold {expected.sold}</span>
            <span>Used {expected.manual_out}</span>
            <span>Stockouts {expected.stockouts}</span>
          </div>
        </div>
      )}

      <div>
        <h3 className="text-sm font-medium text-zinc-500 dark:text-zinc-400 mb-2">Movement ledger</h3>
        <div className="divide-y divide-zinc-100 dark:divide-zinc-800 rounded-lg border border-zinc-200 dark:border-zinc-800">
          {movements.length === 0 && <p className="px-4 py-3 text-sm text-zinc-400">No movements yet.</p>}
          {movements.map((m) => (
            <div key={m.id} className="px-4 py-3 text-sm flex justify-between">
              <span>{m.narrative}</span>
              <span className="text-zinc-500 dark:text-zinc-400">
                {m.kind} {m.quantity ?? ''} · {new Date(m.created_at).toLocaleDateString()}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
