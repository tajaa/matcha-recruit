import { useEffect, useRef, useState } from 'react'
import { Loader2, FileText, Trash2, Upload } from 'lucide-react'
import { listProjectFiles, uploadProjectFile, deleteProjectFile, type ProjectFile } from '../../api/matchaWork'

interface BoardFilesTabProps {
  projectId: string
}

const ALLOWED_FILE_EXT = /\.(pdf|docx?|txt|csv|xlsx?|png|jpe?g|gif|webp|svg|pptx|md)$/i

function formatBytes(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`
  if (bytes >= 1_000) return `${Math.round(bytes / 1_000)} KB`
  return `${bytes} B`
}

export default function BoardFilesTab({ projectId }: BoardFilesTabProps) {
  const [files, setFiles] = useState<ProjectFile[]>([])
  const [loading, setLoading] = useState(true)
  const [uploadingNames, setUploadingNames] = useState<string[]>([])
  const [isDragOver, setIsDragOver] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    listProjectFiles(projectId)
      .then((rows) => {
        if (active) setFiles(rows)
      })
      .catch(() => {
        if (active) setError('Failed to load files')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [projectId])

  async function handleUploadList(fileList: File[]) {
    const valid = fileList.filter((f) => ALLOWED_FILE_EXT.test(f.name) && f.size <= 10 * 1024 * 1024)
    if (valid.length === 0) return
    for (const file of valid) {
      setUploadingNames((prev) => [...prev, file.name])
      try {
        const uploaded = await uploadProjectFile(projectId, file)
        setFiles((prev) => [uploaded, ...prev])
      } catch {
        setError(`Failed to upload ${file.name}`)
      }
      setUploadingNames((prev) => prev.filter((n) => n !== file.name))
    }
  }

  async function handleDelete(fileId: string) {
    const prev = files
    setFiles((p) => p.filter((f) => f.id !== fileId))
    try {
      await deleteProjectFile(projectId, fileId)
    } catch {
      setFiles(prev)
      setError('Failed to delete file')
    }
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-w-dim" />
      </div>
    )
  }

  return (
    <div
      className="flex h-full flex-col overflow-y-auto px-4 py-4"
      onDragOver={(e) => {
        e.preventDefault()
        setIsDragOver(true)
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setIsDragOver(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        setIsDragOver(false)
        handleUploadList(Array.from(e.dataTransfer.files))
      }}
    >
      {error && (
        <div className="mb-3 flex items-center justify-between rounded-lg border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-300">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-200">
            ×
          </button>
        </div>
      )}

      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-w-dim">
          Files ({files.length})
        </span>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-1.5 rounded-lg border border-w-line px-2.5 py-1.5 text-xs font-medium text-w-text transition-colors hover:bg-w-surface2"
        >
          <Upload className="h-3.5 w-3.5" />
          Upload
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            const list = Array.from(e.target.files ?? [])
            if (list.length > 0) handleUploadList(list)
            e.target.value = ''
          }}
        />
      </div>

      <div
        className={`flex-1 rounded-xl border ${
          isDragOver ? 'border-w-accent/60 bg-w-accent/10' : 'border-w-line'
        }`}
      >
        {uploadingNames.map((name) => (
          <div key={name} className="flex items-center gap-2 border-b border-w-line px-3 py-2 text-xs text-w-dim">
            <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
            <span className="truncate">{name}</span>
          </div>
        ))}

        {files.length === 0 && uploadingNames.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-1 py-16 text-center text-sm text-w-faint">
            <p>No files yet.</p>
            <p className="text-xs text-w-faint">Drag files here or click Upload.</p>
          </div>
        ) : (
          files.map((f) => (
            <div key={f.id} className="group flex items-center gap-2 border-b border-w-line px-3 py-2 last:border-b-0">
              <FileText className="h-3.5 w-3.5 shrink-0 text-w-dim" />
              <a
                href={f.storage_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 truncate text-sm text-w-text hover:underline"
              >
                {f.filename}
              </a>
              <span className="shrink-0 text-[10px] text-w-dim">{formatBytes(f.file_size)}</span>
              <button
                onClick={() => handleDelete(f.id)}
                className="shrink-0 text-w-faint opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
