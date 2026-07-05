import { useRef, useState } from 'react'
import { ExternalLink, FileUp, Loader2, Trash2 } from 'lucide-react'
import {
  uploadPilotDocument, deletePilotDocument, getPilotDocumentUrl,
  type PilotSession,
} from '../../../api/brokerPilot'
import { DOC_STATUS_CLASS, DOC_STATUS_LABEL, DOC_TYPE_LABEL, fmtSize } from './shared'

const ACCEPT = '.pdf,.docx,.txt,.csv'

interface DocsPanelProps {
  session: PilotSession
  onChanged: () => void
}

export function DocsPanel({ session, onChanged }: DocsPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const docs = session.documents ?? []

  const onFiles = async (files: FileList | null) => {
    if (!files?.length) return
    setUploading(true)
    setError(null)
    try {
      for (const file of Array.from(files)) {
        await uploadPilotDocument(session.id, file)
      }
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const openDoc = async (docId: string) => {
    const { url } = await getPilotDocumentUrl(session.id, docId)
    window.open(url, '_blank', 'noopener')
  }

  const removeDoc = async (docId: string) => {
    await deletePilotDocument(session.id, docId)
    onChanged()
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs uppercase tracking-wide text-zinc-500">Documents</h3>
        <button
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md border border-zinc-700 text-zinc-300 hover:text-zinc-100 hover:border-zinc-600 disabled:opacity-50 transition-colors"
        >
          {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileUp className="h-3.5 w-3.5" />}
          Upload
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          onChange={(e) => void onFiles(e.target.files)}
        />
      </div>

      {error && <p className="text-xs text-red-400 mb-2">{error}</p>}

      {docs.length === 0 ? (
        <p className="text-xs text-zinc-600">
          Upload loss runs, dec pages, quotes, or carrier letters (PDF/DOCX/TXT/CSV, 15 MB max).
          Each is analyzed once and grounds every chat turn.
        </p>
      ) : (
        <ul className="space-y-2">
          {docs.map((d) => (
            <li key={d.id} className="rounded-md border border-zinc-800 px-2.5 py-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-xs text-zinc-200 truncate" title={d.filename}>{d.filename}</p>
                  <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                    {d.doc_type && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-300">
                        {DOC_TYPE_LABEL[d.doc_type]}
                      </span>
                    )}
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${DOC_STATUS_CLASS[d.status]}`}>
                      {DOC_STATUS_LABEL[d.status]}
                    </span>
                    <span className="text-[10px] text-zinc-600">{fmtSize(d.file_size)}</span>
                    {(d.extraction?.key_figures?.length ?? 0) > 0 && (
                      <span className="text-[10px] text-zinc-500">
                        {d.extraction!.key_figures.length} figure{d.extraction!.key_figures.length === 1 ? '' : 's'}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button
                    onClick={() => void openDoc(d.id)}
                    className="p-1 text-zinc-500 hover:text-zinc-200 transition-colors"
                    title="Open original"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => void removeDoc(d.id)}
                    className="p-1 text-zinc-500 hover:text-red-400 transition-colors"
                    title="Remove"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              {d.extraction?.summary && (
                <p className="text-[11px] text-zinc-500 mt-1.5">{d.extraction.summary}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
