import { useEffect, useRef, useState } from 'react'
import { Loader2, Paperclip, Trash2, Upload, X, FileText } from 'lucide-react'
import {
  listTaskFiles,
  uploadTaskFile,
  deleteTaskFile,
  TASK_FILE_MAX_BYTES,
  TASK_FILE_ALLOWED_EXT,
} from '../../../api/matchaWork'
import type { MWTaskAttachment } from '../../../types'
import { formatSize, isImage } from '../../../utils/taskClipboard'

interface TaskAttachmentsProps {
  projectId: string
  taskId: string
  /** Rows the board already has from `GET /projects/{id}/tasks` (it returns full
   *  attachment rows per task, not just a count) — rendered immediately so the
   *  panel isn't blank while the authoritative list loads. */
  initial?: MWTaskAttachment[]
  /** Keeps the board's card face (its paperclip count) in step with the panel. */
  onChange?: (files: MWTaskAttachment[]) => void
}

/**
 * Ticket attachments — the web counterpart of the desktop ticket viewer's
 * Attachments section. The endpoints (`POST/GET/DELETE
 * /projects/{id}/tasks/{taskId}/files`) have existed all along; only the web UI
 * was missing, so a screenshot attached from the Mac app was invisible here.
 *
 * Images render as thumbnails (click to open full-size); everything else is a
 * name + size row. Upload accepts the file picker, drag-and-drop, AND paste —
 * paste matters most: attaching a screenshot is Cmd+Shift+4 then Cmd+V, and
 * without it every screenshot needs a save-to-disk detour first.
 */
export default function TaskAttachments({ projectId, taskId, initial = [], onChange }: TaskAttachmentsProps) {
  const [files, setFiles] = useState<MWTaskAttachment[]>(initial)
  const [uploadingNames, setUploadingNames] = useState<string[]>([])
  const [isDragOver, setIsDragOver] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<MWTaskAttachment | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let active = true
    listTaskFiles(projectId, taskId)
      .then((rows) => {
        if (!active) return
        setFiles(rows)
        onChange?.(rows)
      })
      .catch(() => {
        /* keep the `initial` rows — a failed refresh shouldn't blank the list */
      })
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, taskId])

  function commit(next: MWTaskAttachment[]) {
    setFiles(next)
    onChange?.(next)
  }

  async function handleUploadList(list: File[]) {
    // Reject client-side against the same limits the server enforces, and say
    // which file failed and why rather than surfacing a bare 400.
    const rejected = list.filter((f) => !TASK_FILE_ALLOWED_EXT.test(f.name) || f.size > TASK_FILE_MAX_BYTES)
    if (rejected.length > 0) {
      const tooBig = rejected.find((f) => f.size > TASK_FILE_MAX_BYTES)
      setError(tooBig ? `${tooBig.name} is over the 10 MB limit` : `Unsupported file type: ${rejected[0].name}`)
    }
    const valid = list.filter((f) => TASK_FILE_ALLOWED_EXT.test(f.name) && f.size <= TASK_FILE_MAX_BYTES)

    // Accumulate locally across the sequential uploads: `files` is captured
    // per render, so reading it inside the loop would drop every upload but the
    // last. commit() rather than a functional setFiles that calls onChange from
    // inside the updater — updaters must be pure (StrictMode runs them twice).
    let acc = files
    for (const file of valid) {
      setUploadingNames((prev) => [...prev, file.name])
      try {
        const uploaded = await uploadTaskFile(projectId, taskId, file)
        acc = [uploaded, ...acc]
        commit(acc)
      } catch (e) {
        setError(e instanceof Error ? e.message : `Failed to upload ${file.name}`)
      }
      setUploadingNames((prev) => prev.filter((n) => n !== file.name))
    }
  }

  async function handleDelete(fileId: string) {
    const prev = files
    commit(files.filter((f) => f.id !== fileId))
    try {
      await deleteTaskFile(projectId, taskId, fileId)
    } catch {
      commit(prev)
      setError('Failed to delete attachment')
    }
  }

  // Paste-to-attach. Scoped to a paste that actually carries files and lands
  // inside this section, so pasting text into the description or checklist
  // inputs elsewhere in the panel is untouched.
  function handlePaste(e: React.ClipboardEvent) {
    const pasted = Array.from(e.clipboardData.files)
    if (pasted.length === 0) return
    e.preventDefault()
    handleUploadList(pasted)
  }

  const images = files.filter(isImage)
  const others = files.filter((f) => !isImage(f))

  return (
    <div
      onPaste={handlePaste}
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
      // tabIndex so the section can hold focus and receive a paste without the
      // user having to click into a text input first.
      tabIndex={-1}
      className={`rounded-lg border p-2 outline-none transition-colors ${
        isDragOver ? 'border-w-accent/60 bg-w-accent/10' : 'border-transparent'
      }`}
    >
      <div className="mb-2 flex items-center gap-2">
        <Paperclip className="h-3.5 w-3.5 text-w-dim" />
        <span className="text-xs font-medium text-w-dim">Attachments</span>
        {files.length > 0 && (
          <span className="rounded bg-w-surface2 px-1.5 py-0.5 text-[10px] text-w-dim">{files.length}</span>
        )}
        <button
          onClick={() => fileInputRef.current?.click()}
          className="ml-auto flex items-center gap-1.5 rounded-lg border border-w-line px-2 py-1 text-[11px] font-medium text-w-text transition-colors hover:bg-w-surface2"
        >
          <Upload className="h-3 w-3" />
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

      {error && (
        <div className="mb-2 flex items-center justify-between gap-2 rounded-lg border border-red-900/50 bg-red-950/40 px-2.5 py-1.5 text-xs text-red-300">
          <span className="min-w-0 flex-1">{error}</span>
          <button onClick={() => setError(null)} className="shrink-0 text-red-400 hover:text-red-200">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {images.length > 0 && (
        <div className="mb-2 grid grid-cols-3 gap-1.5">
          {images.map((f) => (
            <div key={f.id} className="group relative aspect-video overflow-hidden rounded-lg border border-w-line bg-w-surface">
              <button onClick={() => setPreview(f)} className="h-full w-full" title={f.filename}>
                <img src={f.storage_url} alt={f.filename} loading="lazy" className="h-full w-full object-cover" />
              </button>
              <button
                onClick={() => handleDelete(f.id)}
                title="Remove"
                aria-label={`Remove ${f.filename}`}
                className="absolute right-1 top-1 rounded bg-black/60 p-1 text-white/80 opacity-0 transition-opacity hover:text-white group-hover:opacity-100"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {others.map((f) => (
        <div key={f.id} className="group flex items-center gap-2 rounded-lg px-1 py-1.5 hover:bg-w-surface2">
          <FileText className="h-3.5 w-3.5 shrink-0 text-w-dim" />
          <a
            href={f.storage_url}
            target="_blank"
            rel="noreferrer"
            className="min-w-0 flex-1 truncate text-xs text-w-text hover:underline"
          >
            {f.filename}
          </a>
          <span className="shrink-0 text-[10px] text-w-dim">{formatSize(f.file_size)}</span>
          <button
            onClick={() => handleDelete(f.id)}
            title="Remove"
            aria-label={`Remove ${f.filename}`}
            className="shrink-0 text-w-dim opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}

      {uploadingNames.map((name) => (
        <div key={name} className="flex items-center gap-2 px-1 py-1.5 text-xs text-w-dim">
          <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
          <span className="truncate">{name}</span>
        </div>
      ))}

      {files.length === 0 && uploadingNames.length === 0 && (
        <p className="px-1 py-1 text-[11px] text-w-faint">Drop files here, paste a screenshot, or use Upload.</p>
      )}

      {/* Full-size preview. Rendered above the detail panel (z-50), hence z-[60]. */}
      {preview && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 p-6"
          onClick={() => setPreview(null)}
        >
          <img
            src={preview.storage_url}
            alt={preview.filename}
            className="max-h-full max-w-full rounded-lg object-contain"
            onClick={(e) => e.stopPropagation()}
          />
          <button
            onClick={() => setPreview(null)}
            className="absolute right-4 top-4 rounded-lg bg-black/60 p-2 text-white/80 hover:text-white"
            aria-label="Close preview"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      )}
    </div>
  )
}
