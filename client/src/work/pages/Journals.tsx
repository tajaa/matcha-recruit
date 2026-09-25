import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { BookOpen, Plus } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import type { JournalKind } from '../api/matchaWork/journals'
import FolderTree from './Journals/FolderTree'
import JournalList from './Journals/JournalList'
import JournalEditor from './Journals/JournalEditor'
import { journalDirtyPatch, sharedWithMe, useJournals } from './Journals/useJournals'

const createKinds: { kind: JournalKind; label: string }[] = [
  { kind: 'note', label: 'Note' }, { kind: 'todo', label: 'To-do' },
  { kind: 'blog', label: 'Blog (Lite)' }, { kind: 'novel', label: 'Novel (Lite)' },
  { kind: 'screenplay', label: 'Screenplay (Lite)' },
]

export default function Journals() {
  const { journalId } = useParams<{ journalId: string }>()
  const navigate = useNavigate()
  const base = useWorkBase()
  const { me } = useMe()
  const userId = me?.user?.id
  const vm = useJournals()
  const [folderId, setFolderId] = useState<string | null>(null)
  const [filter, setFilter] = useState('all')
  const [creating, setCreating] = useState(false)
  const [actionError, setActionError] = useState('')

  const visible = useMemo(() => {
    if (filter === 'shared') return sharedWithMe(vm.journals)
    if (filter === 'root') return vm.journals.filter((journal) => journal.folder_id === null)
    if (folderId) return vm.journals.filter((journal) => journal.folder_id === folderId)
    return vm.journals
  }, [vm.journals, filter, folderId])
  const selected = vm.journals.find((journal) => journal.id === journalId)

  function selectFolder(id: string | null, nextFilter = 'folder') {
    setFolderId(id)
    setFilter(nextFilter)
    vm.setStatus(nextFilter === 'archived' ? 'archived' : 'active')
    navigate(`${base}/journals`)
  }

  async function create(kind: JournalKind) {
    setCreating(false)
    try {
      const target = folderId ?? (filter === 'root' ? null : undefined)
      const journal = await vm.create(kind, target)
      if (journal) navigate(`${base}/journals/${journal.id}`)
      setActionError('')
    } catch (cause) { setActionError(cause instanceof Error ? cause.message : 'Could not create note') }
  }

  async function archive(id: string) {
    try { await vm.archive(id); if (journalId === id) navigate(`${base}/journals`); setActionError('') }
    catch (cause) { setActionError(cause instanceof Error ? cause.message : 'Could not archive note') }
  }

  async function restore(id: string) {
    try { await vm.restore(id); setActionError('') }
    catch (cause) { setActionError(cause instanceof Error ? cause.message : 'Could not restore note') }
  }

  async function removeFolder(id: string) {
    try {
      let selectedFolder = folderId
      let selectionRemoved = false
      while (selectedFolder) {
        if (selectedFolder === id) { selectionRemoved = true; break }
        selectedFolder = vm.folders.find((folder) => folder.id === selectedFolder)?.parent_id ?? null
      }
      await vm.removeFolder(id)
      if (selectionRemoved) selectFolder(null, 'all')
      setActionError('')
    } catch (cause) { setActionError(cause instanceof Error ? cause.message : 'Could not delete notebook') }
  }

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col bg-w-bg text-w-text">
      <div className="flex items-center justify-between gap-3 border-b border-w-line px-4 py-2">
        <h1 className="flex items-center gap-2 text-sm font-semibold"><BookOpen size={16} /> Journals</h1>
        <div className="relative">
          <button onClick={() => setCreating((value) => !value)} aria-expanded={creating} className="flex items-center gap-1 rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-black"><Plus size={14} /> New</button>
          {creating && <div className="absolute right-0 top-full z-20 mt-1 w-44 rounded-lg border border-w-line bg-w-surface p-1 shadow-xl">{createKinds.map(({ kind, label }) => <button key={kind} onClick={() => void create(kind)} className="block w-full rounded px-3 py-2 text-left text-xs hover:bg-w-surface2">{label}</button>)}</div>}
        </div>
      </div>
      {(vm.error || actionError) && <p role="alert" className="border-b border-w-line px-4 py-2 text-xs text-red-400">{vm.error || actionError}</p>}
      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <FolderTree folders={vm.folders} selected={folderId} filter={filter} onSelect={selectFolder} onCreate={vm.createFolder} onPatch={vm.patchFolder} onDelete={removeFolder} />
        {vm.loading ? <p className="p-5 text-sm text-w-faint">Loading journals…</p> : <JournalList journals={visible} selectedId={journalId} archived={vm.status === 'archived'} userId={userId} onSelect={(id) => navigate(`${base}/journals/${id}`)} onArchive={archive} onRestore={restore} />}
        {selected ? <JournalEditor key={selected.id} journal={selected} folders={vm.folders} userId={userId} onRename={(title) => vm.patch(selected.id, journalDirtyPatch('title', title))} onMove={(folder) => vm.patch(selected.id, journalDirtyPatch('folder_id', folder))} onChanged={vm.reload} /> : <div className="hidden min-w-0 flex-1 items-center justify-center text-sm text-w-faint md:flex">Choose a note to write.</div>}
      </div>
    </div>
  )
}
