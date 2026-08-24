import { useEffect, useState } from 'react'
import { Button, Select, useToast } from '../../../components/ui'
import { InventoryHelpButton } from './InventoryHelp'
import {
  listSalesMappings, upsertSalesMapping,
  type InventoryItem, type SalesMapping,
} from '../../api/inventory'

export default function SalesMappingsPanel({ items, locationId, onHelp }: { items: InventoryItem[]; locationId?: string; onHelp?: () => void }) {
  const { toast } = useToast()
  const [mappings, setMappings] = useState<SalesMapping[]>([])
  const [soldName, setSoldName] = useState('')
  const [kind, setKind] = useState<'direct' | 'recipe' | 'ignore'>('direct')
  const [components, setComponents] = useState([{ item_id: '', quantity_per_sale: '1', unit: '' }])
  const [saving, setSaving] = useState(false)

  function load() {
    listSalesMappings(locationId).then((result) => setMappings(result.mappings)).catch(() => toast('Failed to load sales mappings', 'error'))
  }

  useEffect(() => { load() }, [locationId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function save() {
    const validComponents = components.filter((component) => component.item_id && Number(component.quantity_per_sale) > 0)
    const isValid = kind === 'ignore'
      ? validComponents.length === 0
      : kind === 'direct' ? validComponents.length === 1 : validComponents.length >= 1
    if (!soldName.trim() || !isValid) return
    setSaving(true)
    try {
      await upsertSalesMapping({
        sold_name: soldName.trim(), kind, location_id: locationId,
        components: kind === 'ignore' ? [] : validComponents.map((component) => ({
          item_id: component.item_id,
          quantity_per_sale: Number(component.quantity_per_sale),
          unit: component.unit || null,
        })),
      })
      setSoldName('')
      setKind('direct')
      setComponents([{ item_id: '', quantity_per_sale: '1', unit: '' }])
      load()
      toast('Sales mapping saved', 'success')
    } catch {
      toast('Failed to save sales mapping', 'error')
    } finally {
      setSaving(false)
    }
  }

  function updateComponent(index: number, field: 'item_id' | 'quantity_per_sale' | 'unit', value: string) {
    setComponents((current) => current.map((component, i) => {
      if (i !== index) return component
      if (field !== 'item_id') return { ...component, [field]: value }
      const item = items.find((candidate) => candidate.id === value)
      return { ...component, item_id: value, unit: item?.unit ?? component.unit }
    }))
  }

  return (
    <div className="space-y-3 rounded-xl border border-w-line bg-w-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium text-w-text">Sales mappings</h3>
          <p className="mt-1 text-xs text-w-dim">Map a POS sold name to the stock units it depletes, including multi-item recipes.</p>
        </div>
        {onHelp && <InventoryHelpButton onClick={onHelp} />}
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="min-w-44 text-xs text-w-dim">Sold name<input value={soldName} onChange={(event) => setSoldName(event.target.value)} placeholder="Cookie 6-pack" className="mt-1 w-full rounded-lg border border-w-line bg-w-surface2 px-2 py-2 text-sm text-w-text placeholder:text-w-faint" /></label>
        <label className="min-w-32 text-xs text-w-dim">Mapping type<Select options={[{ value: 'direct', label: 'Direct item' }, { value: 'recipe', label: 'Recipe' }, { value: 'ignore', label: 'Ignore sale' }]} value={kind} onChange={(event) => setKind(event.target.value as typeof kind)} className="mt-1" /></label>
        <Button onClick={() => void save()} disabled={saving || !soldName.trim()}>Add mapping</Button>
      </div>
      {kind !== 'ignore' && <div className="space-y-2">
        {components.map((component, index) => <div key={index} className="flex flex-wrap items-end gap-2">
          <label className="min-w-48 flex-1 text-xs text-w-dim">{kind === 'recipe' ? `Ingredient ${index + 1}` : 'Stock item'}<Select options={items.map((item) => ({ value: item.id, label: item.name }))} value={component.item_id} onChange={(event) => updateComponent(index, 'item_id', event.target.value)} placeholder="Choose item…" className="mt-1" /></label>
          <label className="w-24 text-xs text-w-dim">Units/sale<input type="number" min={0.0001} step="any" value={component.quantity_per_sale} onChange={(event) => updateComponent(index, 'quantity_per_sale', event.target.value)} className="mt-1 w-full rounded-lg border border-w-line bg-w-surface2 px-2 py-2 text-sm text-w-text" /></label>
          <label className="w-24 text-xs text-w-dim">Unit<input value={component.unit} onChange={(event) => updateComponent(index, 'unit', event.target.value)} placeholder="Optional" className="mt-1 w-full rounded-lg border border-w-line bg-w-surface2 px-2 py-2 text-sm text-w-text placeholder:text-w-faint" /></label>
          {kind === 'recipe' && components.length > 1 && <Button variant="ghost" onClick={() => setComponents((current) => current.filter((_, i) => i !== index))}>Remove</Button>}
        </div>)}
        {kind === 'recipe' && <Button variant="secondary" onClick={() => setComponents((current) => [...current, { item_id: '', quantity_per_sale: '1', unit: '' }])}>Add ingredient</Button>}
      </div>}
      {mappings.length > 0 && (
        <div className="divide-y divide-w-line text-sm">
          {mappings.map((mapping) => (
            <div key={mapping.id} className="flex items-center justify-between py-2">
              <span className="text-w-text">{mapping.sold_name}</span>
              <span className="text-w-dim">{mapping.kind === 'ignore' ? 'ignored' : mapping.components.map((component) => `${items.find((item) => item.id === component.item_id)?.name ?? 'item'} × ${component.quantity_per_sale}`).join(', ')}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
