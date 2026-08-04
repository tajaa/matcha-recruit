import { useState } from 'react'
import { Modal, Button, FileUpload, Select, useToast } from '../../../components/ui'
import {
  parseReceipt, commitReceipt,
  type InventoryItem, type ReceiptDraft, type ReceiptLine,
} from '../../api/inventory'
import { ApiError } from '../../../api/client'

type DraftLine = ReceiptLine & {
  selectedItemId: string
  createNew: boolean
  editableQty: number
  commitError?: string
}

function toDraftLine(line: ReceiptLine): DraftLine {
  return {
    ...line,
    selectedItemId: line.item_id ?? '',
    createNew: !line.item_id,
    editableQty: line.quantity ?? 0,
  }
}

type Props = {
  open: boolean
  onClose: () => void
  items: InventoryItem[]
  locationId?: string
  onCommitted: () => void
}

export default function ReceiveDeliveryModal({ open, onClose, items, locationId, onCommitted }: Props) {
  const { toast } = useToast()
  const [parsing, setParsing] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [draft, setDraft] = useState<ReceiptDraft | null>(null)
  const [lines, setLines] = useState<DraftLine[]>([])
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null)

  const itemOptions = items.map((i) => ({ value: i.id, label: i.name }))

  function reset() {
    setDraft(null)
    setLines([])
    setDuplicateWarning(null)
  }

  function handleClose() {
    reset()
    onClose()
  }

  async function handleFiles(files: File[]) {
    const file = files[0]
    if (!file) return
    setParsing(true)
    try {
      const result = await parseReceipt(file, locationId)
      setDraft(result)
      setLines(result.lines.map(toDraftLine))
      if (!result.available) {
        toast("Couldn't read any line items from that file — check the format or enter items manually.", 'error')
      }
    } catch {
      toast('Failed to parse the file', 'error')
    } finally {
      setParsing(false)
    }
  }

  function updateLine(idx: number, patch: Partial<DraftLine>) {
    setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, ...patch } : l)))
  }

  async function doCommit(force: boolean) {
    if (!draft) return
    setCommitting(true)
    try {
      const submitted = lines
        .map((l, idx) => ({ l, idx }))
        .filter(({ l }) => l.editableQty > 0)
      const result = await commitReceipt({
        location_id: locationId,
        vendor: draft.vendor,
        invoice_number: draft.invoice_number,
        force,
        lines: submitted.map(({ l }) => ({
          item_id: l.createNew ? undefined : l.selectedItemId || undefined,
          new_item_name: l.createNew ? l.item_name : undefined,
          quantity: l.editableQty,
          // Only claim the matched order if the user kept the original
          // match — switching to "new item" or a different item must not
          // flip a stranger's order to received.
          order_id: !l.createNew && l.selectedItemId === l.item_id ? (l.open_order_id ?? undefined) : undefined,
        })),
      })
      setDuplicateWarning(null)
      if (result.failed > 0) {
        const errorByRow = new Map(result.errors.map((e) => [e.row, e.error]))
        // Drop lines that already committed — resubmitting them on retry
        // would double-count against the ledger. Keep failed + not-yet-
        // submitted (qty 0) lines so the user can fix and retry just those.
        setLines((prev) => prev
          .map((line, i) => {
            const submittedIdx = submitted.findIndex(({ idx }) => idx === i)
            if (submittedIdx === -1) return { line, keep: true }
            const err = errorByRow.get(submittedIdx + 1)
            return err ? { line: { ...line, commitError: err }, keep: true } : { line, keep: false }
          })
          .filter((entry) => entry.keep)
          .map((entry) => entry.line))
        toast(`Received ${result.created} of ${result.total_rows} — ${result.failed} failed`, 'error')
        if (result.created > 0) onCommitted()
        return
      }
      toast(`Received ${result.created} item${result.created === 1 ? '' : 's'}`, 'success')
      onCommitted()
      handleClose()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 &&
          (err.body as { detail?: { code?: string } })?.detail?.code === 'duplicate_invoice') {
        setDuplicateWarning(err.message)
      } else {
        toast('Failed to record the delivery', 'error')
      }
    } finally {
      setCommitting(false)
    }
  }

  const canCommit = lines.some((l) => l.editableQty > 0 && (l.createNew ? l.item_name : l.selectedItemId))

  return (
    <Modal open={open} onClose={handleClose} title="Receive delivery" width="lg">
      {!draft ? (
        <FileUpload onFiles={handleFiles} accept=".csv,.pdf,.png,.jpg,.jpeg,.webp" disabled={parsing} maxSizeMB={15}>
          <div className="text-sm text-zinc-400 py-8 text-center">
            {parsing ? 'Reading invoice…' : 'Drop an invoice or packing slip (CSV, PDF, or photo)'}
          </div>
        </FileUpload>
      ) : (
        <div className="space-y-4">
          {(draft.vendor || draft.invoice_number) && (
            <div className="text-sm text-zinc-400">
              {draft.vendor}{draft.vendor && draft.invoice_number ? ' · ' : ''}
              {draft.invoice_number ? `Invoice ${draft.invoice_number}` : ''}
            </div>
          )}
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {lines.map((line, idx) => (
              <div key={idx} className="border border-zinc-800 rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between text-sm text-zinc-300">
                  <span className="font-medium">{line.item_name}</span>
                  {line.open_order_id && (
                    <span className="text-xs text-emerald-400">closes an open order</span>
                  )}
                </div>
                {(line.unit || line.pack_size) && (
                  <div className="text-xs text-zinc-500">
                    {[line.unit, line.pack_size].filter(Boolean).join(' · ')}
                  </div>
                )}
                {line.commitError && (
                  <div className="text-xs text-red-400">{line.commitError}</div>
                )}
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-1 text-xs text-zinc-400">
                    <input
                      type="checkbox"
                      checked={line.createNew}
                      onChange={(e) => updateLine(idx, { createNew: e.target.checked })}
                    />
                    New item
                  </label>
                  {!line.createNew && (
                    <Select
                      options={itemOptions}
                      value={line.selectedItemId}
                      onChange={(e) => updateLine(idx, { selectedItemId: e.target.value })}
                      placeholder="Match to existing item…"
                      className="flex-1"
                    />
                  )}
                  <input
                    type="number"
                    min={0}
                    step="any"
                    value={line.editableQty}
                    onChange={(e) => updateLine(idx, { editableQty: Number(e.target.value) })}
                    className="w-24 text-sm rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1"
                  />
                </div>
              </div>
            ))}
          </div>
          {duplicateWarning && (
            <div className="text-sm text-amber-400 border border-amber-900 rounded-lg p-3 flex items-center justify-between">
              <span>{duplicateWarning}</span>
              <Button onClick={() => doCommit(true)} disabled={committing}>Commit anyway</Button>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button onClick={handleClose}>Cancel</Button>
            <Button onClick={() => doCommit(false)} disabled={committing || !canCommit}>
              {committing ? 'Recording…' : 'Record delivery'}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
