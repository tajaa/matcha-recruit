import { useRef, useState } from 'react'
import { ExternalLink, FileUp, Loader2, Trash2 } from 'lucide-react'
import {
  uploadPilotDocument, deletePilotDocument, getPilotDocumentUrl,
  type PilotSession,
} from '../../../api/brokerPilot'
import { DOC_STATUS_CLASS, DOC_STATUS_LABEL, DOC_TYPE_LABEL, LABEL, fmtSize } from './shared'

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
      for (const file of Array.from(files)) await uploadPilotDocument(session.id, file)
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
    <div className="flex flex-col border-b border-white/[0.06]">
      <div className="flex items-center justify-between px-4 pb-2 pt-4">
        <span className={LABEL}>Documents</span>
        <button
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="inline-flex items-center gap-1.5 rounded border border-white/[0.08] px-2 py-0.5 text-[11px] text-zinc-300 transition-colors hover:border-emerald-500/40 hover:text-zinc-100 disabled:opacity-50"
        >
          {uploading ? <Loader2 className="h-3 w-3 animate-spin" /> : <FileUp className="h-3 w-3" />} Upload
        </button>
        <input ref={inputRef} type="file" accept={ACCEPT} multiple className="hidden" onChange={(e) => void onFiles(e.target.files)} />
      </div>

      {error && <p className="px-4 pb-2 text-[11px] text-red-400">{error}</p>}

      {docs.length === 0 ? (
        <p className="px-4 pb-3 text-[11px] leading-relaxed text-zinc-600">
          Upload loss runs, dec pages, quotes, or carrier letters (PDF/DOCX/TXT/CSV, 15 MB max).
          Each is analyzed once and grounds every chat turn.
        </p>
      ) : (
        <div className="pb-1">
          {docs.map((d) => (
            <div key={d.id} className="border-t border-white/[0.04] px-4 py-2 first:border-t-0">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-xs text-zinc-200" title={d.filename}>{d.filename}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    {d.doc_type && (
                      <span className="rounded border border-white/[0.08] bg-white/[0.03] px-1.5 py-px text-[10px] text-zinc-300">
                        {DOC_TYPE_LABEL[d.doc_type]}
                      </span>
                    )}
                    <span className={`rounded border px-1.5 py-px text-[10px] ${DOC_STATUS_CLASS[d.status]}`}>
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
                <div className="flex shrink-0 items-center gap-1">
                  <button onClick={() => void openDoc(d.id)} className="p-1 text-zinc-500 transition-colors hover:text-zinc-200" title="Open original">
                    <ExternalLink className="h-3.5 w-3.5" />
                  </button>
                  <button onClick={() => void removeDoc(d.id)} className="p-1 text-zinc-500 transition-colors hover:text-red-400" title="Remove">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              {d.extraction?.summary && <p className="mt-1.5 text-[11px] leading-snug text-zinc-500">{d.extraction.summary}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
