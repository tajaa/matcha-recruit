import { useState } from 'react'
import { Button, FileUpload, Modal, Toggle } from '../ui'
import { api } from '../../api/client'
import type { BulkUploadResponse } from '../../types/employee'

type BulkUploadModalProps = {
  open: boolean
  onClose: () => void
  onSuccess: () => void
}

export function BulkUploadModal({ open, onClose, onSuccess }: BulkUploadModalProps) {
  const [sendInvitations, setSendInvitations] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<BulkUploadResponse | null>(null)
  const [error, setError] = useState('')

  async function handleDownloadTemplate() {
    try {
      await api.download('/employees/bulk-upload/template', 'employee_template.csv')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to download template')
    }
  }

  async function handleFiles(files: File[]) {
    const file = files[0]
    if (!file) return
    setUploading(true)
    setError('')
    setResult(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await api.upload<BulkUploadResponse>(
        `/employees/bulk-upload?send_invitations=${sendInvitations}`,
        fd,
      )
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  function handleClose() {
    if (result && result.created > 0) onSuccess()
    setResult(null)
    setError('')
    onClose()
  }

  return (
    <Modal open={open} onClose={handleClose} title="Bulk Upload Employees">
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={handleDownloadTemplate}>
          Download CSV Template
        </Button>

        <FileUpload onFiles={handleFiles} accept=".csv" disabled={uploading}>
          <p>{uploading ? 'Uploading...' : <>Drop CSV here or <span className="text-emerald-400 underline">browse</span></>}</p>
        </FileUpload>

        <label className="flex items-center gap-2 text-sm text-zinc-400">
          <Toggle checked={sendInvitations} onChange={setSendInvitations} disabled={uploading} />
          Send invitations
        </label>

        {error && (
          <p className="text-sm text-red-400 bg-red-400/10 rounded-lg px-3 py-2">{error}</p>
        )}

        {result && (
          <div className="rounded-lg border border-zinc-800 px-4 py-3 space-y-2">
            <p className="text-sm text-zinc-200">
              <span className="text-emerald-400">{result.created} created</span>
              {result.failed > 0 && <span className="text-red-400 ml-2">{result.failed} failed</span>}
              <span className="text-zinc-500 ml-2">of {result.total_rows} rows</span>
            </p>
            {result.errors.length > 0 && (
              <div className="max-h-32 overflow-y-auto text-xs text-red-400 space-y-1">
                {result.errors.map((err, i) => (
                  <p key={i}>Row {err.row}: {err.error}</p>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex justify-end">
          <Button variant="ghost" onClick={handleClose}>
            {result ? 'Done' : 'Cancel'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
