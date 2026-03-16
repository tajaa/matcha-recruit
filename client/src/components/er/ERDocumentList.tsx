import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge, Button, Select, FileUpload, type BadgeVariant } from '../ui'
import type { ERDocument, ERDocumentUploadResponse, ERDocumentType } from '../../types/er'
import { documentTypeLabel } from '../../types/er'

const processingVariant: Record<string, BadgeVariant> = {
  pending: 'neutral',
  processing: 'warning',
  completed: 'success',
  failed: 'danger',
}

const DOC_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'transcript', label: 'Transcript' },
  { value: 'policy', label: 'Policy' },
  { value: 'email', label: 'Email' },
  { value: 'other', label: 'Other' },
]

type ERDocumentListProps = {
  caseId: string
  onUploadComplete?: () => void
}

export function ERDocumentList({ caseId, onUploadComplete }: ERDocumentListProps) {
  const [docs, setDocs] = useState<ERDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [docType, setDocType] = useState<ERDocumentType>('other')

  const fetchDocs = useCallback(() => {
    api.get<ERDocument[]>(`/er/cases/${caseId}/documents`)
      .then(setDocs)
      .catch(() => setDocs([]))
      .finally(() => setLoading(false))
  }, [caseId])

  useEffect(() => { fetchDocs() }, [fetchDocs])

  async function handleFiles(files: File[]) {
    setUploading(true)
    setUploadError('')
    try {
      for (const file of files) {
        const fd = new FormData()
        fd.append('file', file)
        fd.append('document_type', docType)
        const res = await api.upload<ERDocumentUploadResponse>(
          `/er/cases/${caseId}/documents`,
          fd,
        )
        setDocs((prev) => [...prev, res.document])
      }
      onUploadComplete?.()
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  async function handleDelete(docId: string) {
    try {
      await api.delete(`/er/cases/${caseId}/documents/${docId}`)
      setDocs((prev) => prev.filter((d) => d.id !== docId))
    } catch {
      // silently ignore — doc stays in list so user can retry
    }
  }

  function formatSize(bytes: number | null) {
    if (!bytes) return '—'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3">
        <Select
          label="Document type"
          options={DOC_TYPE_OPTIONS}
          value={docType}
          onChange={(e) => setDocType(e.target.value as ERDocumentType)}
          className="w-36"
        />
        <div className="flex-1">
          <FileUpload
            onFiles={handleFiles}
            accept=".pdf,.docx,.txt,.eml,.msg"
            multiple
            disabled={uploading}
          >
            <p>
              {uploading ? 'Uploading...' : <>Drop files here or <span className="text-emerald-400 underline">browse</span></>}
            </p>
          </FileUpload>
        </div>
      </div>

      {uploadError && (
        <p className="text-xs text-red-400">{uploadError}</p>
      )}

      {loading ? (
        <p className="text-xs text-zinc-500">Loading documents...</p>
      ) : docs.length === 0 ? (
        <p className="text-xs text-zinc-500">No documents uploaded.</p>
      ) : (
        <div className="space-y-2">
          {docs.map((d) => (
            <div key={d.id} className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm text-zinc-100 truncate">{d.filename}</p>
                <div className="flex items-center gap-2 mt-1">
                  <Badge variant="neutral">{documentTypeLabel[d.document_type] ?? d.document_type}</Badge>
                  <Badge variant={processingVariant[d.processing_status] ?? 'neutral'}>
                    {d.processing_status}
                  </Badge>
                  <span className="text-[10px] text-zinc-500">{formatSize(d.file_size)}</span>
                </div>
              </div>
              <Button variant="ghost" size="sm" onClick={() => handleDelete(d.id)}>
                Delete
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
