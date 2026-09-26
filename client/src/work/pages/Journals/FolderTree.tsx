import { useState } from 'react'
import { ChevronDown, ChevronRight, Folder, FolderPlus, Pencil, Trash2 } from 'lucide-react'
import type { JournalFolder } from '../../api/matchaWork/journals'

type Props = {
  folders: JournalFolder[]
  selected: string | null
  filter: string
  onSelect: (id: string | null, filter?: string) => void
  onCreate: (name: string, parentId?: string | null) => Promise<unknown>
  onPatch: (id: string, patch: { name?: string; color?: string }) => Promise<unknown>
  onDelete: (id: string) => Promise<unknown>
}

const colors = ['#a3a3a3', '#eab308', '#f97316', '#ef4444', '#8b5cf6', '#3b82f6', '#10b981']

export default function FolderTree({ folders, selected, filter, onSelect, onCreate, onPatch, onDelete }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [error, setError] = useState('')

  async function add(parentId?: string | null) {
    const name = window.prompt('Folder name')?.trim()
    if (!name) return
    try { await onCreate(name, parentId); setError('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create folder') }
  }

  function branch(parentId: string | null, depth = 0): React.ReactNode {
    return folders.filter((folder) => folder.parent_id === parentId).map((folder) => {
      const children = folders.some((candidate) => candidate.parent_id === folder.id)
      const open = expanded.has(folder.id)
      return (
        <div key={folder.id}>
          <div className={`group flex items-center gap-1 rounded-md pr-1 ${selected === folder.id && filter === 'folder' ? 'bg-w-surface2 text-w-text' : 'text-w-dim hover:bg-w-surface2/50'}`} style={{ paddingLeft: 8 + depth * 14 }}>
            <button aria-label={open ? `Collapse ${folder.name}` : `Expand ${folder.name}`} onClick={() => setExpanded((previous) => {
              const next = new Set(previous)
              if (open) next.delete(folder.id); else next.add(folder.id)
              return next
            })} className="p-1">
              {children ? open ? <ChevronDown size={12} /> : <ChevronRight size={12} /> : <span className="block w-3" />}
            </button>
            <button onClick={() => onSelect(folder.id)} className="flex flex-1 min-w-0 items-center gap-2 py-1.5 text-left text-xs">
              <Folder size={14} style={{ color: folder.color ?? '#a3a3a3' }} />
              <span className="truncate">{folder.name}</span>
            </button>
            <button title={`Add folder in ${folder.name}`} aria-label={`Add folder in ${folder.name}`} onClick={() => void add(folder.id)} className="hidden group-hover:block"><FolderPlus size={12} /></button>
            <button title={`Rename ${folder.name}`} aria-label={`Rename ${folder.name}`} onClick={() => {
              const name = window.prompt('Rename folder', folder.name)?.trim()
              if (name) void onPatch(folder.id, { name }).catch((cause: unknown) => setError(String(cause)))
            }} className="hidden group-hover:block"><Pencil size={12} /></button>
            <select aria-label={`Color for ${folder.name}`} value={folder.color ?? colors[0]} onChange={(event) => void onPatch(folder.id, { color: event.target.value }).catch((cause: unknown) => setError(String(cause)))} className="hidden group-hover:block w-4 bg-w-surface text-transparent" style={{ backgroundColor: folder.color ?? colors[0] }}>
              {colors.map((color) => <option key={color} value={color} style={{ backgroundColor: color }}>{color}</option>)}
            </select>
            <button title={`Delete ${folder.name}`} aria-label={`Delete ${folder.name}`} onClick={() => {
              if (window.confirm(`Delete ${folder.name} and its subfolders? Notes will move to the hub root.`)) {
                void onDelete(folder.id).catch((cause: unknown) => setError(String(cause)))
              }
            }} className="hidden group-hover:block"><Trash2 size={12} /></button>
          </div>
          {open && branch(folder.id, depth + 1)}
        </div>
      )
    })
  }

  return (
    <div className="max-h-40 overflow-y-auto border-r border-w-line bg-w-surface p-2 md:h-full md:max-h-none md:w-52 md:shrink-0">
      <p className="px-2 py-2 text-[10px] font-semibold uppercase tracking-wider text-w-faint">Library</p>
      {[['All notes', 'all'], ['Shared with me', 'shared'], ['Unfiled', 'root'], ['Archived', 'archived']].map(([label, value]) => (
        <button key={value} onClick={() => onSelect(null, value)} className={`block w-full rounded-md px-2 py-1.5 text-left text-xs ${filter === value ? 'bg-w-surface2 text-w-text' : 'text-w-dim hover:bg-w-surface2/50'}`}>{label}</button>
      ))}
      <div className="mt-4 flex items-center justify-between px-2 text-[10px] font-semibold uppercase tracking-wider text-w-faint">
        <span>Notebooks</span><button onClick={() => void add()} title="New notebook" aria-label="New notebook"><FolderPlus size={14} /></button>
      </div>
      <div className="mt-1">{branch(null)}</div>
      {error && <p role="alert" className="px-2 pt-2 text-xs text-red-400">{error}</p>}
    </div>
  )
}
