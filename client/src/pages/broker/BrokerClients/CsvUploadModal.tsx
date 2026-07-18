import { Loader2, Upload } from 'lucide-react'
import { Button, Modal, Badge } from '../../../components/ui'
import type { BrokerBatchCreateResponse } from '../../../types/broker'
import type { CsvRow } from './types'

type Props = {
  open: boolean
  csvRows: CsvRow[]
  csvFile: File | null
  csvSubmitting: boolean
  csvResult: BrokerBatchCreateResponse | null
  csvError: string
  fileInputRef: React.RefObject<HTMLInputElement>
  onClose: () => void
  onFile: (file: File) => void
  onDrop: (e: React.DragEvent) => void
  onSubmit: () => void
}

export function CsvUploadModal({
  open, csvRows, csvFile, csvSubmitting, csvResult, csvError,
  fileInputRef, onClose, onFile, onDrop, onSubmit,
}: Props) {
  return (
    <Modal open={open} onClose={onClose} title="Upload CSV" width="lg">
      <div className="space-y-4">
        {!csvResult ? (
          <>
            {/* Drop zone */}
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-zinc-700 rounded-lg p-8 text-center cursor-pointer hover:border-zinc-500 transition-colors"
            >
              <Upload className="h-8 w-8 text-zinc-500 mx-auto mb-2" />
              <p className="text-sm text-zinc-400">
                {csvFile ? csvFile.name : 'Drop a CSV file here or click to browse'}
              </p>
              <p className="text-xs text-zinc-600 mt-1">
                Expected columns: company_name, contact_name, contact_email, contact_phone, industry, company_size, headcount, notes
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) onFile(f)
                }}
              />
            </div>

            {/* Preview table */}
            {csvRows.length > 0 && (
              <div className="overflow-x-auto max-h-64 overflow-y-auto rounded-lg border border-zinc-800">
                <table className="w-full text-xs text-left">
                  <thead className="bg-zinc-900/50 text-zinc-400 sticky top-0">
                    <tr>
                      <th className="px-3 py-2 font-medium">#</th>
                      <th className="px-3 py-2 font-medium">Company</th>
                      <th className="px-3 py-2 font-medium">Contact</th>
                      <th className="px-3 py-2 font-medium">Email</th>
                      <th className="px-3 py-2 font-medium">Industry</th>
                      <th className="px-3 py-2 font-medium">Notes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {csvRows.map((row, i) => {
                      const missing = !row.company_name.trim()
                      return (
                        <tr key={i} className={missing ? 'bg-red-950/30' : 'text-zinc-300'}>
                          <td className="px-3 py-1.5 text-zinc-500">{i + 1}</td>
                          <td className={`px-3 py-1.5 ${missing ? 'text-red-400' : ''}`}>
                            {row.company_name || '(missing)'}
                          </td>
                          <td className="px-3 py-1.5">{row.contact_name}</td>
                          <td className="px-3 py-1.5">{row.contact_email}</td>
                          <td className="px-3 py-1.5">{row.industry}</td>
                          <td className="px-3 py-1.5 max-w-[120px] truncate">{row.notes}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {csvError && <p className="text-sm text-red-400">{csvError}</p>}

            <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
              <Button
                size="sm"
                disabled={csvSubmitting || csvRows.length === 0 || csvRows.every((r) => !r.company_name.trim())}
                onClick={onSubmit}
              >
                {csvSubmitting ? (
                  <>
                    <Loader2 size={12} className="mr-1 animate-spin" />
                    Submitting...
                  </>
                ) : (
                  `Submit All (${csvRows.filter((r) => r.company_name.trim()).length} clients)`
                )}
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={onClose}>
                Cancel
              </Button>
            </div>
          </>
        ) : (
          /* Results view */
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Badge variant="success">{csvResult.count} created</Badge>
              {csvResult.errors.length > 0 && (
                <Badge variant="danger">{csvResult.errors.length} errors</Badge>
              )}
            </div>

            {csvResult.errors.length > 0 && (
              <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-3 space-y-1">
                {csvResult.errors.map((err, i) => (
                  <p key={i} className="text-xs text-red-400">
                    Row {err.index + 1} ({err.company_name}): {err.error}
                  </p>
                ))}
              </div>
            )}

            <div className="pt-2 border-t border-zinc-800">
              <Button size="sm" onClick={onClose}>Done</Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}
