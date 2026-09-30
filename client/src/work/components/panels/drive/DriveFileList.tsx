import { useState, type FormEvent } from 'react'
import { Download, FileText, Folder, FolderInput, FolderLock, Pencil, Trash2 } from 'lucide-react'
import type { DriveCap, DriveFile, DriveFolder } from '../../../types'
import { formatBytes, hasCap } from './driveTree'

interface Props {
  folders: DriveFolder[]
  files: DriveFile[]
  caps: DriveCap[]
  onOpenFolder: (folderId: string) => void
  onDownload: (file: DriveFile) => void
  onRename: (file: DriveFile, filename: string) => Promise<void>
  onMove: (file: DriveFile) => void
  onDelete: (file: DriveFile) => void
}

const TEXT_NOTE: Partial<Record<DriveFile['text_status'], string>> = {
  empty: 'No readable text (scanned?)',
  failed: "Couldn't read text",
}

export default function DriveFileList({ folders, files, caps, onOpenFolder, onDownload, onRename, onMove, onDelete }: Props) {
  const canManage = hasCap(caps, 'manage')
  const canRead = hasCap(caps, 'read')
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  async function submitRename(e: FormEvent, file: DriveFile) {
    e.preventDefault()
    const name = draft.trim()
    if (!name || name === file.filename) { setEditing(null); return }
    setSaving(true)
    try {
      await onRename(file, name)
      setEditing(null)
    } finally {
      setSaving(false)
    }
  }

  if (folders.length === 0 && files.length === 0) {
    return <p className="rounded-xl border border-dashed border-w-line px-6 py-8 text-center text-sm text-w-faint">This folder is empty.</p>
  }

  return (
    <ul className="divide-y divide-w-line rounded-xl border border-w-line bg-w-surface">
      {folders.map((folder) => {
        const Icon = folder.space === 'hr' ? FolderLock : Folder
        return (
          <li key={folder.id}>
            <button
              type="button"
              onClick={() => onOpenFolder(folder.id)}
              className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-sm text-w-text hover:bg-w-surface2"
            >
              <Icon size={15} className="shrink-0 text-w-dim" />
              <span className="truncate font-medium">{folder.name}</span>
            </button>
          </li>
        )
      })}
      {files.map((file) => (
        <li key={file.id} className="flex items-center gap-2.5 px-4 py-2.5">
          <FileText size={15} className="shrink-0 text-w-dim" />
          <div className="min-w-0 flex-1">
            {editing === file.id ? (
              <form onSubmit={(e) => void submitRename(e, file)} className="flex items-center gap-2">
                <input
                  autoFocus
                  aria-label="File name"
                  value={draft}
                  disabled={saving}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Escape') setEditing(null) }}
                  className="w-full rounded-md border border-w-line bg-w-surface2/60 px-2 py-1 text-sm text-w-text outline-none focus:border-w-accent/50"
                />
              </form>
            ) : (
              <p className="truncate text-sm text-w-text">{file.filename}</p>
            )}
            <p className="text-[11px] text-w-faint">
              {formatBytes(file.file_size)} · {new Date(file.created_at).toLocaleDateString()}
              {file.source === 'google_drive' && ' · from Google Drive'}
              {TEXT_NOTE[file.text_status] && ` · ${TEXT_NOTE[file.text_status]}`}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-0.5">
            {canRead && (
              <IconButton label={`Download ${file.filename}`} onClick={() => onDownload(file)}><Download size={14} /></IconButton>
            )}
            {canManage && (
              <>
                <IconButton label={`Rename ${file.filename}`} onClick={() => { setDraft(file.filename); setEditing(file.id) }}><Pencil size={14} /></IconButton>
                <IconButton label={`Move ${file.filename}`} onClick={() => onMove(file)}><FolderInput size={14} /></IconButton>
                <IconButton label={`Delete ${file.filename}`} onClick={() => onDelete(file)}><Trash2 size={14} /></IconButton>
              </>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick} className="rounded-md p-1.5 text-w-faint hover:bg-w-surface2 hover:text-w-text">
      {children}
    </button>
  )
}
