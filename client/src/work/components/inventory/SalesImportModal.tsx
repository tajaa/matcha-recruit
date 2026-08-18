import { useEffect, useState } from 'react'
import { ApiError } from '../../../api/client'
import { Button, FileUpload, Modal, Select, useToast } from '../../../components/ui'
import {
  commitSales, createItem, parseSales, upsertSalesMapping,
  type InventoryItem, type SalesDraft, type SalesLine,
  getSalesImport,
} from '../../api/inventory'

type DraftLine = SalesLine & {
  selectedItemId: string
  quantityPerSale: number
  ignored: boolean
  commitError?: string
}

function toDraftLine(line: SalesLine): DraftLine {
  const component = line.components?.[0]
  return {
    ...line,
    selectedItemId: component?.item_id ?? line.auto_match?.id ?? '',
    quantityPerSale: component?.quantity_per_sale ?? line.quantity_per_sale ?? 1,
    ignored: line.status === 'ignored',
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
  const [source, setSource] = useState<'upload' | 'email'>('upload')
  const [gmailMessageId, setGmailMessageId] = useState<string | null>(null)
  const [parsing, setParsing] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null)

  const itemOptions = items.map((item) => ({ value: item.id, label: item.name }))

  useEffect(() => {
    if (!open || !draftImportId) return
    getSalesImport(draftImportId)
      .then((result) => {
        const rawLines = (result.raw?.lines ?? result.lines) as SalesLine[]
        setDraft({ business_date: result.business_date, lines: rawLines, available: rawLines.length > 0 })
        setLines(rawLines.map(toDraftLine))
        setFilename(result.filename)
        setSource(result.source)
        setGmailMessageId(result.gmail_message_id ?? null)
      })
      .catch(() => toast('Failed to load the sales draft', 'error'))
  }, [draftImportId, open, toast])

  function reset() {
    setDraft(null)
    setLines([])
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
      setSource('upload')
      setGmailMessageId(null)
      setDraft(result)
      setLines(result.lines.map(toDraftLine))
      if (!result.available) toast("Couldn't read any sales lines from that file.", 'error')
    } catch {
      toast('Failed to parse the sales export', 'error')
    } finally {
      setParsing(false)
    }
  }

  function updateLine(index: number, patch: Partial<DraftLine>) {
    setLines((prev) => prev.map((line, i) => i === index ? { ...line, ...patch } : line))
  }

  async function markIgnored(index: number) {
    const line = lines[index]
    if (!line) return
    try {
      await upsertSalesMapping({ sold_name: line.sold_name, kind: 'ignore', location_id: locationId, components: [] })
      updateLine(index, {
        ignored: true, status: 'ignored', mapping_id: null, selectedItemId: '', commitError: undefined,
      })
    } catch {
      toast('Failed to save the ignore mapping', 'error')
    }
  }

  async function createAndMap(index: number) {
    const line = lines[index]
    if (!line) return
    try {
      const item = await createItem({ name: line.sold_name, location_id: locationId })
      await upsertSalesMapping({
        sold_name: line.sold_name, kind: 'direct', location_id: locationId,
        components: [{ item_id: item.id, quantity_per_sale: line.quantityPerSale }],
      })
      updateLine(index, { selectedItemId: item.id, status: 'mapped', ignored: false, commitError: undefined })
      onCommitted()
    } catch {
      toast('Could not create or map the item', 'error')
    }
  }

  async function doCommit(force: boolean) {
    if (!draft) return
    setCommitting(true)
    try {
      const result = await commitSales({
        location_id: locationId,
        business_date: draft.business_date,
        source,
        filename,
        gmail_message_id: gmailMessageId,
        force,
        lines: lines.map((line) => ({
          sold_name: line.sold_name,
          quantity: line.quantity,
          gross_sales: line.gross_sales,
          mapping_id: line.mapping_id,
          item_id: line.ignored ? null : line.selectedItemId || null,
          quantity_per_sale: line.ignored ? null : line.quantityPerSale,
          components: line.ignored ? [] : [{ item_id: line.selectedItemId, quantity_per_sale: line.quantityPerSale }],
          status: line.ignored ? 'ignored' : line.selectedItemId ? 'mapped' : 'unmapped',
        })),
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

  const canCommit = lines.length > 0 && lines.every((line) => line.ignored || line.selectedItemId)

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
                {line.ignored ? (
                  <div className="flex items-center justify-between text-xs text-amber-400">
                    <span>Ignored by mapping</span>
                    <button type="button" onClick={() => updateLine(index, { ignored: false, status: 'unmapped', mapping_id: null, selectedItemId: '' })} className="hover:underline">Undo</button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <Select options={itemOptions} value={line.selectedItemId} onChange={(event) => updateLine(index, { selectedItemId: event.target.value, mapping_id: null, status: event.target.value ? 'mapped' : 'unmapped' })} placeholder="Map to stock item…" className="flex-1" />
                    <input type="number" min={0.0001} step="any" value={line.quantityPerSale} onChange={(event) => updateLine(index, { quantityPerSale: Number(event.target.value), mapping_id: null })} className="w-20 rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm" aria-label="Stock units per sale" />
                    <button type="button" onClick={() => void markIgnored(index)} className="text-xs text-amber-400 hover:underline">Ignore</button>
                    <button type="button" onClick={() => void createAndMap(index)} className="text-xs text-emerald-400 hover:underline">New item</button>
                  </div>
                )}
              </div>
            ))}
          </div>
          {duplicateWarning && (
            <div className="flex items-center justify-between gap-3 rounded-lg border border-amber-900 p-3 text-sm text-amber-400">
              <span>{duplicateWarning}</span>
              <Button onClick={() => void doCommit(true)} disabled={committing}>Commit anyway</Button>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button onClick={close}>Cancel</Button>
            <Button onClick={() => void doCommit(false)} disabled={committing || !canCommit}>
              {committing ? 'Committing…' : 'Commit sales'}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
