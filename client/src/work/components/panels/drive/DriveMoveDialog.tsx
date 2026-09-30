import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import type { DriveFile, DriveFolder } from '../../../types'
import DriveFolderTree from './DriveFolderTree'
import { hasCap } from './driveTree'
import DriveDialog from './DriveDialog'

interface Props {
  file: DriveFile
  /** Folders in the file's own space — moves never cross spaces. */
  folders: DriveFolder[]
  onMove: (folderId: string) => Promise<void>
  onClose: () => void
}

export default function DriveMoveDialog({ file, folders, onMove, onClose }: Props) {
  const targets = folders.filter((f) => hasCap(f.caps, 'add') && f.id !== file.folder_id)
  const [selected, setSelected] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (!selected) return
    setSaving(true)
    setError(null)
    try {
      await onMove(selected)
      onClose()
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Could not move the file')
      setSaving(false)
    }
  }

  return (
    <DriveDialog title={`Move "${file.filename}"`} onClose={onClose} dismissible={!saving}>
      <div className="max-h-72 overflow-y-auto rounded-lg border border-w-line p-1">
        <DriveFolderTree folders={targets} selectedId={selected} onSelect={setSelected} />
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-red-400">{error}</p>}
      <div className="mt-4 flex justify-end gap-2">
        <button type="button" onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm text-w-dim hover:text-w-text">Cancel</button>
        <button
          type="button"
          disabled={!selected || saving}
          onClick={() => void submit()}
          className="inline-flex items-center gap-1.5 rounded-lg bg-w-accent px-3 py-1.5 text-sm font-medium text-w-on-accent hover:bg-w-accent-hi disabled:opacity-50"
        >
          {saving && <Loader2 size={14} className="animate-spin" />} Move here
        </button>
      </div>
    </DriveDialog>
  )
}
