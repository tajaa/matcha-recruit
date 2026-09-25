import { Archive, BookOpen, RotateCcw } from 'lucide-react'
import type { Journal } from '../../api/matchaWork/journals'

type Props = {
  journals: Journal[]
  selectedId: string | undefined
  archived: boolean
  userId: string | undefined
  onSelect: (id: string) => void
  onArchive: (id: string) => Promise<void>
  onRestore: (id: string) => Promise<void>
}

export default function JournalList({ journals, selectedId, archived, userId, onSelect, onArchive, onRestore }: Props) {
  return (
    <div className="max-h-48 overflow-y-auto border-r border-w-line bg-w-bg md:h-full md:max-h-none md:w-64 md:shrink-0">
      <p className="border-b border-w-line px-4 py-3 text-xs text-w-faint">{journals.length} {journals.length === 1 ? 'note' : 'notes'}</p>
      {journals.length === 0 && <p className="px-4 py-8 text-sm text-w-faint">No notes here yet.</p>}
      {journals.map((journal) => (
        <div key={journal.id} className={`group border-b border-w-line/50 px-3 py-2 ${selectedId === journal.id ? 'bg-w-surface2' : 'hover:bg-w-surface2/40'}`}>
          <button onClick={() => onSelect(journal.id)} className="w-full text-left">
            <span className="flex items-center gap-2 text-sm font-medium text-w-text"><BookOpen size={13} style={{ color: journal.color ?? undefined }} /> <span className="truncate">{journal.title}</span></span>
            <span className="mt-1 block truncate text-xs text-w-faint">{journal.preview ?? 'Start writing…'}</span>
            {journal.collaborator_role && <span className="mt-1 block text-[10px] text-w-faint">Shared by {journal.owner_name ?? 'a collaborator'}</span>}
          </button>
          {journal.created_by === userId && <button onClick={() => void (archived ? onRestore(journal.id) : onArchive(journal.id))} className="mt-1 hidden items-center gap-1 text-[10px] text-w-faint hover:text-w-text group-hover:flex">
            {archived ? <RotateCcw size={11} /> : <Archive size={11} />}{archived ? 'Restore' : 'Archive'}
          </button>}
        </div>
      ))}
    </div>
  )
}
