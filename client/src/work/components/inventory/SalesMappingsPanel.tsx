import { useEffect, useState } from 'react'
import { Button, Select, useToast } from '../../../components/ui'
import {
  listSalesMappings, upsertSalesMapping,
  type InventoryItem, type SalesMapping,
} from '../../api/inventory'

export default function SalesMappingsPanel({ items, locationId }: { items: InventoryItem[]; locationId?: string }) {
  const { toast } = useToast()
  const [mappings, setMappings] = useState<SalesMapping[]>([])
  const [soldName, setSoldName] = useState('')
  const [itemId, setItemId] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [saving, setSaving] = useState(false)

  function load() {
    listSalesMappings(locationId).then((result) => setMappings(result.mappings)).catch(() => toast('Failed to load sales mappings', 'error'))
  }

  useEffect(() => { load() }, [locationId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function save() {
    if (!soldName.trim() || !itemId || Number(quantity) <= 0) return
    setSaving(true)
    try {
      await upsertSalesMapping({
        sold_name: soldName.trim(), kind: 'direct', location_id: locationId,
        components: [{ item_id: itemId, quantity_per_sale: Number(quantity) }],
      })
      setSoldName('')
      setItemId('')
      setQuantity('1')
      load()
      toast('Sales mapping saved', 'success')
    } catch {
      toast('Failed to save sales mapping', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div>
        <h3 className="font-medium">Sales mappings</h3>
        <p className="text-xs text-zinc-500">Map a POS sold name to the stock units it depletes. Recipes can be added here later without changing the import format.</p>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="min-w-44 text-xs text-zinc-500">Sold name<input value={soldName} onChange={(event) => setSoldName(event.target.value)} placeholder="Cookie 6-pack" className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-2 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900" /></label>
        <label className="min-w-48 text-xs text-zinc-500">Stock item<Select options={items.map((item) => ({ value: item.id, label: item.name }))} value={itemId} onChange={(event) => setItemId(event.target.value)} placeholder="Choose item…" className="mt-1" /></label>
        <label className="w-24 text-xs text-zinc-500">Units/sale<input type="number" min={0.0001} step="any" value={quantity} onChange={(event) => setQuantity(event.target.value)} className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-2 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900" /></label>
        <Button onClick={() => void save()} disabled={saving || !soldName.trim() || !itemId}>Add mapping</Button>
      </div>
      {mappings.length > 0 && (
        <div className="divide-y divide-zinc-100 text-sm dark:divide-zinc-800">
          {mappings.map((mapping) => (
            <div key={mapping.id} className="flex items-center justify-between py-2">
              <span>{mapping.sold_name}</span>
              <span className="text-zinc-500">{mapping.kind === 'ignore' ? 'ignored' : mapping.components.map((component) => `${items.find((item) => item.id === component.item_id)?.name ?? 'item'} × ${component.quantity_per_sale}`).join(', ')}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
