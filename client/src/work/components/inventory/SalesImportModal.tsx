import { useEffect, useState } from 'react'
import { ApiError } from '../../../api/client'
import { Button, FileUpload, Modal, Select, useToast } from '../../../components/ui'
import {
  commitSales, createItem, parseSales,
  type InventoryItem, type SalesDraft, type SalesLine, type SalesMappingComponentInput,
  discardSalesImport, getSalesImport,
} from '../../api/inventory'

export type DraftComponent = {
  item_id: string
  quantity_per_sale: string
  unit?: string | null
}

export type MappingKind = 'direct' | 'recipe' | 'ignore'

export type DraftLine = Omit<SalesLine, 'components'> & {
  components: DraftComponent[]
  kind: MappingKind
  ignored: boolean
  mappingDirty: boolean
  commitError?: string
}

const emptyComponent = (): DraftComponent => ({ item_id: '', quantity_per_sale: '1', unit: null })

export function toDraftLine(line: SalesLine): DraftLine {
  const components = Array.isArray(line.components) && line.components.length
    ? line.components.map((component) => ({
      item_id: component.item_id,
      quantity_per_sale: String(component.quantity_per_sale),
      unit: component.unit ?? null,
    }))
    : line.item_id || line.auto_match?.id
      ? [{
        item_id: line.item_id ?? line.auto_match?.id ?? '',
        quantity_per_sale: String(line.quantity_per_sale ?? 1),
        unit: null,
      }]
      : [emptyComponent()]
  const kind: MappingKind = line.status === 'ignored'
    ? 'ignore'
    : line.mapping_kind === 'direct' || line.mapping_kind === 'recipe'
      ? line.mapping_kind
      : components.length > 1 ? 'recipe' : 'direct'
  return {
    ...line,
    components: line.status === 'ignored' ? [] : components,
    kind,
    ignored: line.status === 'ignored',
    mappingDirty: false,
  }
}

type Props = {
  open: boolean
  onClose: () => void
  items: InventoryItem[]
  locationId?: string
  draftImportId?: string | null
  onCommitted: () => void
}

export default function SalesImportModal({ open, onClose, items, locationId, draftImportId, onCommitted }: Props) {
  const { toast } = useToast()
  const [draft, setDraft] = useState<SalesDraft | null>(null)
  const [lines, setLines] = useState<DraftLine[]>([])
  const [filename, setFilename] = useState<string | null>(null)
  const [source, setSource] = useState<'upload' | 'email' | 'square' | 'toast'>('upload')
  const [loadedImportId, setLoadedImportId] = useState<string | null>(null)
  const [gmailMessageId, setGmailMessageId] = useState<string | null>(null)
  const [parsing, setParsing] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [discarding, setDiscarding] = useState(false)
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null)

  const itemOptions = items.map((item) => ({ value: item.id, label: item.name }))

  useEffect(() => {
    if (!open || !draftImportId) return
    getSalesImport(draftImportId)
      .then((result) => {
        const rawLines = (result.raw?.lines ?? result.lines) as SalesLine[]
        setDraft({ business_date: result.business_date, lines: rawLines, available: rawLines.length > 0 })
        setLines(rawLines.map(toDraftLine))
        setLoadedImportId(result.id)
        setFilename(result.filename)
        setSource(result.source)
        setGmailMessageId(result.gmail_message_id ?? null)
      })
      .catch(() => toast('Failed to load the sales draft', 'error'))
  }, [draftImportId, open, toast])

  function reset() {
    setDraft(null)
    setLines([])
    setLoadedImportId(null)
    setFilename(null)
    setSource('upload')
    setGmailMessageId(null)
    setDuplicateWarning(null)
  }

  function close() {
    reset()
    onClose()
  }

  async function handleFiles(files: File[]) {
    const file = files[0]
    if (!file) return
    setParsing(true)
    setFilename(file.name)
    try {
      const result = await parseSales(file, locationId)
      setLoadedImportId(null)
      setSource('upload')
      setGmailMessageId(null)
      setDraft(result)
      setLines(result.lines.map(toDraftLine))
      if (!result.available) toast("Couldn't read any sales lines from that file.", 'error')
    } catch (error) {
      toast(error instanceof ApiError ? error.message : 'Failed to parse the sales export', 'error')
    } finally {
      setParsing(false)
    }
  }

  function updateLine(index: number, patch: Partial<DraftLine>) {
    setLines((prev) => prev.map((line, i) => i === index ? { ...line, ...patch } : line))
  }

  function updateComponent(lineIndex: number, componentIndex: number, patch: Partial<DraftComponent>) {
    setLines((prev) => prev.map((line, index) => {
      if (index !== lineIndex) return line
      const components = line.components.map((component, i) => {
        if (i !== componentIndex) return component
        if (!('item_id' in patch)) return { ...component, ...patch }
        const item = items.find((candidate) => candidate.id === patch.item_id)
        return { ...component, ...patch, unit: item?.unit ?? component.unit }
      })
      return { ...line, components, mapping_id: null, mappingDirty: true, ignored: false, status: 'mapped', commitError: undefined }
    }))
  }

  function addComponent(lineIndex: number) {
    setLines((prev) => prev.map((line, index) => index === lineIndex
      ? { ...line, components: [...line.components, emptyComponent()], mapping_id: null, mappingDirty: true, ignored: false, status: 'mapped' }
      : line))
  }

  function removeComponent(lineIndex: number, componentIndex: number) {
    setLines((prev) => prev.map((line, index) => index === lineIndex
      ? { ...line, components: line.components.filter((_, i) => i !== componentIndex), mapping_id: null, mappingDirty: true, status: 'mapped' }
      : line))
  }

  function setLineKind(lineIndex: number, kind: MappingKind) {
    setLines((prev) => prev.map((line, index) => {
      if (index !== lineIndex) return line
      if (kind === 'ignore') {
        return { ...line, kind, ignored: true, status: 'ignored', mapping_id: null, components: [], mappingDirty: true, commitError: undefined }
      }
      const components = kind === 'direct'
        ? line.components.length ? [line.components[0]] : [emptyComponent()]
        : line.components.length ? line.components : [emptyComponent()]
      return { ...line, kind, ignored: false, status: 'mapped', mapping_id: null, components, mappingDirty: true, commitError: undefined }
    }))
  }

  async function createAndMap(index: number) {
    const line = lines[index]
    if (!line) return
    try {
      const item = await createItem({ name: line.sold_name, location_id: locationId })
      updateLine(index, {
        components: [{ item_id: item.id, quantity_per_sale: '1', unit: item.unit ?? null }],
        kind: 'direct', mapping_id: null, mappingDirty: true, status: 'mapped', ignored: false, commitError: undefined,
      })
      onCommitted()
    } catch {
      toast('Could not create or map the item', 'error')
    }
  }

  async function doCommit() {
    if (!draft) return
    setCommitting(true)
    try {
      const result = await commitSales({
        import_id: loadedImportId,
        location_id: locationId,
        business_date: draft.business_date,
        source,
        filename,
        gmail_message_id: gmailMessageId,
        force: false,
        lines: lines.map((line) => buildCommitLine(line, locationId)),
      })
      if (result.unmapped > 0) {
        toast('Map or ignore every sales line before committing.', 'error')
        return
      }
      toast(`Applied ${result.items_affected} item depletion${result.items_affected === 1 ? '' : 's'}`, 'success')
      onCommitted()
      close()
    } catch (error) {
      if (error instanceof ApiError && error.status === 409 &&
          (error.body as { detail?: { code?: string } })?.detail?.code === 'duplicate_sales_period') {
        setDuplicateWarning(error.message)
      } else {
        toast('Failed to commit sales', 'error')
      }
    } finally {
      setCommitting(false)
    }
  }

  async function discardDraft() {
    if (!loadedImportId) return
    setDiscarding(true)
    try {
      await discardSalesImport(loadedImportId)
      toast('Sales import discarded', 'success')
      onCommitted()
      close()
    } catch {
      toast('Failed to discard sales import', 'error')
    } finally {
      setDiscarding(false)
    }
  }

  const canCommit = lines.length > 0 && lines.every(isLineValid)

  return (
    <Modal open={open} onClose={close} title="Import sales" width="lg">
      {!draft ? (
        <FileUpload onFiles={handleFiles} accept=".csv,.pdf,.png,.jpg,.jpeg,.webp" disabled={parsing} maxSizeMB={15}>
          <div className="py-8 text-center text-sm text-zinc-400">
            {parsing ? 'Reading sales export…' : 'Drop a POS export (CSV, PDF, or photo)'}
          </div>
        </FileUpload>
      ) : (
        <div className="space-y-4">
          <div className="text-sm text-zinc-400">
            {filename} {draft.business_date ? `· ${draft.business_date}` : '· date not detected'}
          </div>
          <div className="max-h-96 space-y-3 overflow-y-auto">
            {lines.map((line, index) => (
              <div key={`${line.sold_name}-${index}`} className="space-y-2 rounded-lg border border-zinc-800 p-3">
                <div className="flex items-center justify-between gap-2 text-sm">
                  <span className="font-medium text-zinc-200">{line.sold_name}</span>
                  <span className="text-zinc-500">{line.quantity} sold</span>
                </div>
                {line.commitError && <p className="text-xs text-red-400">{line.commitError}</p>}
                <Select
                  label="Mapping type"
                  options={[{ value: 'direct', label: 'Direct item' }, { value: 'recipe', label: 'Recipe' }, { value: 'ignore', label: 'Ignore sale' }]}
                  value={line.kind}
                  onChange={(event) => setLineKind(index, event.target.value as MappingKind)}
                  className="w-40"
                />
                {line.ignored ? (
                  <p className="text-xs text-amber-400">This sale will be ignored — no stock will be deducted.</p>
                ) : (
                  <div className="space-y-2">
                    {line.components.map((component, componentIndex) => {
                      const selectedElsewhere = new Set(line.components.filter((_, i) => i !== componentIndex).map((entry) => entry.item_id))
                      const options = itemOptions.filter((option) => !selectedElsewhere.has(option.value))
                      return <div key={componentIndex} className="flex items-end gap-2">
                        <Select label={line.kind === 'recipe' ? `Ingredient ${componentIndex + 1}` : 'Stock item'} options={options} value={component.item_id} onChange={(event) => updateComponent(index, componentIndex, { item_id: event.target.value })} placeholder="Map to stock item…" className="min-w-0 flex-1" />
                        <label className="w-24 text-xs text-zinc-400">Units/sale<input type="number" min={0.0001} step="any" value={component.quantity_per_sale} onChange={(event) => updateComponent(index, componentIndex, { quantity_per_sale: event.target.value })} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm" /></label>
                        <label className="w-20 text-xs text-zinc-400">Unit<input value={component.unit ?? ''} onChange={(event) => updateComponent(index, componentIndex, { unit: event.target.value || null })} placeholder="Optional" className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm placeholder:text-zinc-600" /></label>
                        {line.kind === 'recipe' && line.components.length > 1 && <button type="button" onClick={() => removeComponent(index, componentIndex)} className="mb-1 text-xs text-zinc-400 hover:text-zinc-100">Remove</button>}
                      </div>
                    })}
                    <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
                      {line.kind === 'recipe' && <button type="button" onClick={() => addComponent(index)} className="text-blue-300 hover:underline">Add ingredient</button>}
                      <button type="button" onClick={() => void createAndMap(index)} className="text-emerald-400 hover:underline">New item</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
          {duplicateWarning && <p className="rounded-lg border border-amber-900 p-3 text-sm text-amber-400">{duplicateWarning}</p>}
          {!canCommit && <p className="text-xs text-amber-400">Map or ignore every sales line to enable Commit sales.</p>}
          <div className="flex justify-end gap-2">
            <Button onClick={close}>Cancel</Button>
            {loadedImportId && <Button variant="ghost" onClick={() => void discardDraft()} disabled={committing || discarding}>Discard import</Button>}
            <Button onClick={() => void doCommit()} disabled={committing || discarding || !canCommit}>
              {committing ? 'Committing…' : 'Commit sales'}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function validComponents(line: DraftLine): SalesMappingComponentInput[] {
  return line.components.map((component) => ({
    item_id: component.item_id,
    quantity_per_sale: Number(component.quantity_per_sale),
    unit: component.unit ?? null,
  }))
}

export function isLineValid(line: DraftLine) {
  if (line.kind === 'ignore') return true
  const components = validComponents(line)
  const countOk = line.kind === 'direct' ? components.length === 1 : components.length > 0
  return countOk && components.every((component) => component.item_id && Number.isFinite(component.quantity_per_sale) && component.quantity_per_sale > 0)
    && new Set(components.map((component) => component.item_id)).size === components.length
}

export function buildCommitLine(line: DraftLine, locationId?: string): SalesLine {
  if (line.ignored) {
    return {
      sold_name: line.sold_name, quantity: line.quantity, gross_sales: line.gross_sales,
      mapping_id: line.mappingDirty ? null : line.mapping_id, item_id: null, quantity_per_sale: null,
      components: [], status: 'ignored',
      ...(line.mappingDirty ? { new_mapping: { sold_name: line.sold_name, kind: 'ignore', location_id: locationId ?? null, components: [] } } : {}),
    }
  }
  const components = validComponents(line)
  const needsMapping = line.mappingDirty || !line.mapping_id
  return {
    sold_name: line.sold_name, quantity: line.quantity, gross_sales: line.gross_sales,
    mapping_id: needsMapping ? null : line.mapping_id,
    item_id: components[0]?.item_id ?? null,
    quantity_per_sale: components[0]?.quantity_per_sale ?? null,
    components,
    status: components.length ? 'mapped' : 'unmapped',
    ...(needsMapping ? {
      new_mapping: {
        sold_name: line.sold_name,
        kind: line.kind,
        location_id: locationId ?? null,
        components,
      },
    } : {}),
  }
}
