import { useState, useEffect, useCallback } from 'react'
import { api } from '../../api/client'
import { Badge, Select, FileUpload } from '../ui'
import type { IRDocument } from '../../types/ir'

const DOC_TYPE_OPTIONS = [
  { value: 'photo', label: 'Photo' },
  { value: 'form', label: 'Form' },
  { value: 'statement', label: 'Statement' },
  { value: 'other', label: 'Other' },
]

export function IRDocumentPanel({ incidentId }: { incidentId: string }) {
  const [docs, setDocs] = useState<IRDocument[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [docType, setDocType] = useState('other')

  const fetchDocs = useCallback(async () => {
    setLoading(true)
    try { setDocs(await api.get<IRDocument[]>(`/ir/incidents/${incidentId}/documents`)) }
    catch { setDocs([]) }
    finally { setLoading(false) }
  }, [incidentId])

  useEffect(() => { fetchDocs() }, [fetchDocs])

  async function handleUpload(files: File[]) {
    setUploading(true)
    try {
      for (const file of files) {
        const fd = new FormData()
        fd.append('file', file)
        fd.append('document_type', docType)
        await api.upload(`/ir/incidents/${incidentId}/documents`, fd)
      }
      fetchDocs()
    } finally { setUploading(false) }
  }

  async function handleDelete(docId: string) {
    await api.delete(`/ir/incidents/${incidentId}/documents/${docId}`)
    setDocs((prev) => prev.filter((d) => d.id !== docId))
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3">
        <div className="w-40">
          <Select label="Document type" options={DOC_TYPE_OPTIONS} value={docType} onChange={(e) => setDocType(e.target.value)} />
        </div>
        <FileUpload onFiles={handleUpload} accept=".pdf,.docx,.doc,.txt,.jpg,.jpeg,.png" disabled={uploading}>
          {uploading ? 'Uploading...' : 'Drop files here or browse'}
        </FileUpload>
      </div>
      {loading ? (
        <p className="text-sm text-zinc-500">Loading documents...</p>
      ) : docs.length === 0 ? (
        <p className="text-sm text-zinc-600">No documents uploaded yet.</p>
      ) : (
        <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
          {docs.map((doc) => (
            <div key={doc.id} className="flex items-center justify-between px-4 py-2.5">
              <div>
                <p className="text-sm text-zinc-200">{doc.filename}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <Badge variant="neutral">{doc.document_type}</Badge>
                  {doc.file_size && <span className="text-[11px] text-zinc-600">{Math.round(doc.file_size / 1024)} KB</span>}
                </div>
              </div>
              <button type="button" onClick={() => handleDelete(doc.id)}
                className="text-xs text-zinc-600 hover:text-red-400 transition-colors">Delete</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
