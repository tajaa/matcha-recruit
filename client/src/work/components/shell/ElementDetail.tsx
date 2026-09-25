import { useCallback, useEffect, useState } from 'react'
import {
  addElementNote, createElementFolder, deleteElementNote, deleteProjectFile,
  getElementSnapshotStats, listElementFiles, listElementFolders, listElementNotes,
  listProjectTasks, uploadElementFile,
} from '../../api/matchaWork'
import type { ElementFile, ElementFolder, ElementNote, ProjectElement } from '../../api/matchaWork'
import type { MWProjectTask } from '../../types'
import { normalizeElementLink } from '../../utils/elementLink'

interface Props {
  projectId: string
  element: ProjectElement
  canEdit: boolean
  onBack: () => void
  onSave: (patch: Partial<ProjectElement>) => Promise<void>
  onDelete: () => Promise<void>
  parentError?: string | null
}

const filePattern = /\.(pdf|docx?|txt|csv|xlsx?|png|jpe?g|gif|webp|svg|pptx|md)$/i

export default function ElementDetail({ projectId, element, canEdit, onBack, onSave, onDelete, parentError }: Props) {
  const [files, setFiles] = useState<ElementFile[]>([])
  const [folders, setFolders] = useState<ElementFolder[]>([])
  const [notes, setNotes] = useState<ElementNote[]>([])
  const [tasks, setTasks] = useState<MWProjectTask[]>([])
  const [stats, setStats] = useState<{ files: number; bytes: number; updated_at: string | null } | null>(null)
  const [paths, setPaths] = useState((element.repo_paths ?? []).join('\n'))
  const [branch, setBranch] = useState(element.repo_branch ?? '')
  const [newFolder, setNewFolder] = useState('')
  const [folderParentId, setFolderParentId] = useState('')
  const [uploadFolderId, setUploadFolderId] = useState('')
  const [newNote, setNewNote] = useState('')
  const [newLink, setNewLink] = useState('')
  const [preview, setPreview] = useState<ElementFile | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    const [fileRows, folderRows, noteRows, taskRows, snapshot] = await Promise.all([
      listElementFiles(projectId, element.id), listElementFolders(projectId, element.id),
      listElementNotes(projectId, element.id), listProjectTasks(projectId),
      getElementSnapshotStats(projectId, element.id),
    ])
    setFiles(fileRows)
    setFolders(folderRows)
    setNotes(noteRows)
    setTasks(taskRows.filter((task) => task.element_id === element.id))
    setStats(snapshot)
  }, [projectId, element.id])

  useEffect(() => { queueMicrotask(() => { void load().catch((cause) => setError(cause instanceof Error ? cause.message : 'Could not load element.')) }) }, [load])

  async function upload(fileList: FileList | File[]) {
    for (const file of Array.from(fileList)) {
      if (!filePattern.test(file.name) || file.size > 10 * 1024 * 1024) {
        setError('Choose a supported file under 10 MB.')
        continue
      }
      try { await uploadElementFile(projectId, element.id, file, uploadFolderId || null); await load() }
      catch (cause) { setError(cause instanceof Error ? cause.message : 'Upload failed.') }
    }
  }

  async function saveLink() {
    const url = normalizeElementLink(newLink)
    if (!url) { setError('Enter a valid HTTP or HTTPS link.'); return }
    try { await addElementNote(projectId, element.id, { kind: 'link', url }); setNewLink(''); await load() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not add link.') }
  }

  async function openFile(file: ElementFile) {
    try {
      const fresh = (await listElementFiles(projectId, element.id)).find((row) => row.id === file.id)
      if (!fresh) throw new Error('File no longer exists.')
      setPreview(fresh)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not open file.') }
  }

  return (
    <div className="h-full space-y-5 overflow-y-auto p-4 text-sm text-w-text">
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="text-w-accent">← Elements</button>
        <h2 className="font-semibold">{element.name}</h2>
        {canEdit && <button onClick={() => void onDelete()} className="ml-auto text-red-400">Delete</button>}
      </div>
      {error && <p role="alert" className="text-orange-400">{error}</p>}
      {parentError && <p role="alert" className="text-orange-400">{parentError}</p>}
      {element.description && <p className="text-w-dim">{element.description}</p>}
      <section className="space-y-2 rounded border border-w-line p-3">
        <h3 className="font-semibold">Repository scope</h3>
        <p className="text-xs text-w-dim">One glob per line or comma. {stats?.files ?? 0} indexed files.</p>
        <textarea value={paths} onChange={(event) => setPaths(event.target.value)} disabled={!canEdit} rows={3} className="w-full rounded border border-w-line bg-w-surface p-2" placeholder="src/components/**" />
        <input value={branch} onChange={(event) => setBranch(event.target.value)} disabled={!canEdit} className="w-full rounded border border-w-line bg-w-surface p-2" placeholder="Branch (default when blank)" />
        {canEdit && <button onClick={() => void onSave({ repo_paths: paths.split(/[\n,]/).map((path) => path.trim()).filter(Boolean), repo_branch: branch.trim() || null })} className="rounded bg-w-accent px-3 py-1 text-white">Save scope</button>}
      </section>
      <section className="space-y-2 rounded border border-w-line p-3">
        <h3 className="font-semibold">Files and folders</h3>
        {folders.filter((folder) => !folder.parent_id).map((folder) => <div key={folder.id}>
          <p>📁 {folder.name}</p>
          {folders.filter((child) => child.parent_id === folder.id).map((child) => <p key={child.id} className="pl-5 text-w-dim">↳ {child.name}</p>)}
        </div>)}
        {files.map((file) => <div key={file.id} className="flex items-center gap-2">
          <button onClick={() => void openFile(file)} className="text-w-accent underline">{file.filename}</button>
          {file.folder_id && <span className="text-xs text-w-dim">{folders.find((folder) => folder.id === file.folder_id)?.name}</span>}
          {canEdit && <button onClick={() => void deleteProjectFile(projectId, file.id).then(load).catch((cause) => setError(String(cause)))} className="text-red-400">Remove</button>}
        </div>)}
        {canEdit && <div className="space-y-2 border-t border-w-line pt-2">
          <div className="flex flex-wrap gap-2"><input value={newFolder} onChange={(event) => setNewFolder(event.target.value)} placeholder="New folder" className="min-w-0 flex-1 rounded border border-w-line bg-w-surface p-1" /><select aria-label="Parent folder" value={folderParentId} onChange={(event) => setFolderParentId(event.target.value)} className="rounded border border-w-line bg-w-surface p-1"><option value="">At root</option>{folders.filter((folder) => !folder.parent_id).map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select><button disabled={!newFolder.trim()} onClick={() => void createElementFolder(projectId, element.id, newFolder.trim(), folderParentId || null).then(() => { setNewFolder(''); return load() }).catch((cause) => setError(String(cause)))}>Add folder</button></div>
          <select aria-label="Upload folder" value={uploadFolderId} onChange={(event) => setUploadFolderId(event.target.value)} className="rounded border border-w-line bg-w-surface p-1"><option value="">Upload at root</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select>
          <label className="block cursor-pointer rounded border border-dashed border-w-line p-3 text-center text-w-dim" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void upload(event.dataTransfer.files) }}>
            Drop files here or choose files
            <input type="file" multiple className="sr-only" onChange={(event) => { if (event.target.files) void upload(event.target.files) }} />
          </label>
        </div>}
      </section>
      <section className="space-y-2 rounded border border-w-line p-3">
        <h3 className="font-semibold">Notes and links</h3>
        {notes.map((note) => <div key={note.id} className="flex gap-2">
          {note.kind === 'link' && note.url && /^https?:\/\//i.test(note.url) ? <a href={note.url} target="_blank" rel="noopener noreferrer" className="min-w-0 flex-1 break-all text-w-accent underline">{note.body || note.url}</a> : <p className="min-w-0 flex-1 whitespace-pre-wrap">{note.body}</p>}
          {canEdit && <button onClick={() => void deleteElementNote(projectId, element.id, note.id).then(load).catch((cause) => setError(String(cause)))} className="text-red-400">×</button>}
        </div>)}
        {canEdit && <>
          <div className="flex gap-2"><input value={newNote} onChange={(event) => setNewNote(event.target.value)} placeholder="Add note" className="min-w-0 flex-1 rounded border border-w-line bg-w-surface p-1" /><button disabled={!newNote.trim()} onClick={() => void addElementNote(projectId, element.id, { kind: 'note', body: newNote.trim() }).then(() => { setNewNote(''); return load() }).catch((cause) => setError(String(cause)))}>Add</button></div>
          <div className="flex gap-2"><input value={newLink} onChange={(event) => setNewLink(event.target.value)} placeholder="Add link" className="min-w-0 flex-1 rounded border border-w-line bg-w-surface p-1" /><button disabled={!newLink.trim()} onClick={() => void saveLink()}>Add link</button></div>
        </>}
      </section>
      <section className="space-y-2 rounded border border-w-line p-3">
        <h3 className="font-semibold">Tickets about this element</h3>
        {tasks.length ? tasks.map((task) => <p key={task.id}>{task.title}</p>) : <p className="text-w-dim">No tickets yet.</p>}
      </section>
      {preview && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setPreview(null)}><div className="max-h-[85vh] w-full max-w-2xl overflow-auto rounded bg-w-bg p-4" onClick={(event) => event.stopPropagation()}><button onClick={() => setPreview(null)} className="float-right">Close</button><h3 className="mb-3 font-semibold">{preview.filename}</h3>{/\.(png|jpe?g|gif|webp|svg)$/i.test(preview.filename) ? <img src={preview.storage_url} alt={preview.filename} className="max-h-[65vh] max-w-full" /> : <a href={preview.storage_url} target="_blank" rel="noopener noreferrer" className="text-w-accent underline">Open file</a>}</div></div>}
    </div>
  )
}
