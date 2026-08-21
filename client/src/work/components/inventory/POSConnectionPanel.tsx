import { useEffect, useState } from 'react'
import { Check, Loader2, RefreshCw } from 'lucide-react'
import { Button, Select, useToast } from '../../../components/ui'
import {
  bindPOSLocation,
  listPOSCatalog,
  listPOSLocations,
  listPOSMappings,
  listSalesMappings,
  mapPOSItem,
  syncPOSConnection,
  type POSConnection,
  type SalesMapping,
} from '../../api/inventory'
import type { ChannelLocation } from '../../api/channels'

type POSLocation = {
  external_location_id: string
  name: string
  timezone: string
  status?: string
  location_id: string | null
}

type POSCatalogItem = {
  external_item_id: string
  name: string
  sku: string | null
}

export default function POSConnectionPanel({
  connection,
  locations,
  onConnect,
}: {
  connection: POSConnection | null
  locations: ChannelLocation[]
  onConnect: () => void
}) {
  const { toast } = useToast()
  const [posLocations, setPOSLocations] = useState<POSLocation[]>([])
  const [catalog, setCatalog] = useState<POSCatalogItem[]>([])
  const [salesMappings, setSalesMappings] = useState<SalesMapping[]>([])
  const [mapped, setMapped] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [startDate, setStartDate] = useState(yesterday())
  const [endDate, setEndDate] = useState(yesterday())

  useEffect(() => {
    if (!connection) return
    let active = true
    setLoading(true)
    Promise.all([
      listPOSLocations(connection.id),
      listPOSCatalog(connection.id),
      listPOSMappings(connection.id),
      listSalesMappings(),
    ]).then(([locationResponse, catalogResponse, mappingResponse, salesMappingResponse]) => {
      if (!active) return
      setPOSLocations(locationResponse.locations)
      setCatalog(catalogResponse.items)
      setMapped(Object.fromEntries(mappingResponse.mappings.map((item) => [item.external_item_id, item.mapping_id])))
      setSalesMappings(salesMappingResponse.mappings)
    }).catch(() => {
      if (active) toast('Failed to load Square setup', 'error')
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [connection, toast])

  async function saveLocation(posLocation: POSLocation, locationId: string) {
    if (!connection || !locationId) return
    setSaving(`location:${posLocation.external_location_id}`)
    try {
      await bindPOSLocation(connection.id, {
        external_location_id: posLocation.external_location_id,
        name: posLocation.name,
        timezone: posLocation.timezone,
        location_id: locationId,
      })
      setPOSLocations((current) => current.map((item) => item.external_location_id === posLocation.external_location_id ? { ...item, location_id: locationId } : item))
      toast(`${posLocation.name} is bound`, 'success')
    } catch {
      toast('Could not bind that Square location', 'error')
    } finally {
      setSaving(null)
    }
  }

  async function saveMapping(item: POSCatalogItem, mappingId: string) {
    if (!connection || !mappingId) return
    setSaving(`item:${item.external_item_id}`)
    try {
      await mapPOSItem(connection.id, { external_item_id: item.external_item_id, mapping_id: mappingId })
      setMapped((current) => ({ ...current, [item.external_item_id]: mappingId }))
      toast(`${item.name} mapping saved`, 'success')
    } catch {
      toast('Could not save that item mapping', 'error')
    } finally {
      setSaving(null)
    }
  }

  async function sync() {
    if (!connection || !startDate || !endDate) return
    setSyncing(true)
    try {
      const result = await syncPOSConnection(connection.id, { start_date: startDate, end_date: endDate })
      toast(`${result.imports_created ?? 0} finalized sales import(s) created`, 'success')
    } catch {
      toast('Square sync failed', 'error')
    } finally {
      setSyncing(false)
    }
  }

  return <section className="mt-3 rounded-lg border border-w-line bg-w-surface2 p-3">
    {!connection ? (
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-w-dim">Connect Square, bind each store, then map catalog items to stock mappings before importing.</p>
        <Button variant="secondary" size="sm" onClick={onConnect}>Connect Square</Button>
      </div>
    ) : loading ? (
      <div className="flex items-center gap-2 text-xs text-w-dim"><Loader2 size={13} className="animate-spin" /> Loading Square catalog…</div>
    ) : (
      <div className="space-y-4">
        <div>
          <p className="text-xs font-medium text-w-text">Store bindings</p>
          <p className="mt-1 text-[11px] text-w-dim">Only bound Square locations can be imported into a Matcha location.</p>
          <div className="mt-2 space-y-2">
            {posLocations.map((posLocation) => <div key={posLocation.external_location_id} className="flex flex-col gap-2 rounded-lg border border-w-line px-3 py-2 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1"><p className="truncate text-xs text-w-text">{posLocation.name}</p><p className="text-[10px] text-w-faint">{posLocation.timezone}</p></div>
              <Select options={locations.map((location) => ({ value: location.id, label: location.name }))} value={posLocation.location_id ?? ''} placeholder="Bind to…" onChange={(event) => void saveLocation(posLocation, event.target.value)} className="sm:w-52" disabled={saving === `location:${posLocation.external_location_id}`} />
              {posLocation.location_id && <Check size={14} className="text-w-accent" />}
            </div>)}
            {posLocations.length === 0 && <p className="text-xs text-w-dim">No active Square locations found.</p>}
          </div>
        </div>
        <div>
          <p className="text-xs font-medium text-w-text">Catalog mappings</p>
          <p className="mt-1 text-[11px] text-w-dim">Unmapped catalog lines become review drafts and never affect stock.</p>
          <div className="mt-2 max-h-64 space-y-2 overflow-y-auto">
            {catalog.map((item) => <div key={item.external_item_id} className="flex flex-col gap-2 rounded-lg border border-w-line px-3 py-2 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1"><p className="truncate text-xs text-w-text">{item.name}</p><p className="text-[10px] text-w-faint">{item.sku || item.external_item_id}</p></div>
              <Select options={salesMappings.map((mapping) => ({ value: mapping.id, label: mapping.sold_name }))} value={mapped[item.external_item_id] ?? ''} placeholder="Map to sales name…" onChange={(event) => void saveMapping(item, event.target.value)} className="sm:w-64" disabled={saving === `item:${item.external_item_id}`} />
            </div>)}
            {catalog.length === 0 && <p className="text-xs text-w-dim">No Square catalog variations found.</p>}
          </div>
        </div>
        <div className="flex flex-col gap-2 border-t border-w-line pt-3 sm:flex-row sm:items-end">
          <label className="text-[10px] uppercase tracking-wider text-w-faint">From<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="mt-1 block rounded-md border border-w-line bg-w-surface px-2 py-1.5 text-xs text-w-text" /></label>
          <label className="text-[10px] uppercase tracking-wider text-w-faint">To<input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className="mt-1 block rounded-md border border-w-line bg-w-surface px-2 py-1.5 text-xs text-w-text" /></label>
          <Button variant="secondary" size="sm" onClick={() => void sync()} disabled={syncing || !posLocations.some((item) => item.location_id)}>{syncing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Sync finalized sales</Button>
        </div>
      </div>
    )}
  </section>
}

function yesterday() {
  const day = new Date()
  day.setDate(day.getDate() - 1)
  const month = String(day.getMonth() + 1).padStart(2, '0')
  const date = String(day.getDate()).padStart(2, '0')
  return `${day.getFullYear()}-${month}-${date}`
}
