import { useState } from 'react'
import { ChevronRight, Folder, FolderLock, Inbox } from 'lucide-react'
import type { DriveFolder } from '../../../types'
import { buildDriveTree, hasCap, type DriveTreeNode } from './driveTree'

interface Props {
  folders: DriveFolder[]
  selectedId: string | null
  onSelect: (folderId: string) => void
}

export default function DriveFolderTree({ folders, selectedId, onSelect }: Props) {
  const roots = buildDriveTree(folders)
  if (roots.length === 0) return <p className="px-2 py-3 text-xs text-w-faint">No folders.</p>
  return (
    <ul className="space-y-0.5" role="tree">
      {roots.map((node) => (
        <TreeRow key={node.folder.id} node={node} depth={0} selectedId={selectedId} onSelect={onSelect} />
      ))}
    </ul>
  )
}

function TreeRow({ node, depth, selectedId, onSelect }: {
  node: DriveTreeNode
  depth: number
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const [open, setOpen] = useState(depth < 2)
  const { folder, children } = node
  const selected = folder.id === selectedId
  const dropBox = !hasCap(folder.caps, 'list') && hasCap(folder.caps, 'add')
  const Icon = dropBox ? Inbox : folder.space === 'hr' ? FolderLock : Folder
  return (
    <li role="treeitem" aria-selected={selected} aria-expanded={children.length ? open : undefined}>
      <div
        className={`flex items-center gap-1 rounded-md pr-2 text-sm ${selected ? 'bg-w-surface2 text-w-text' : 'text-w-dim hover:bg-w-surface2/60 hover:text-w-text'}`}
        style={{ paddingLeft: 4 + depth * 12 }}
      >
        <button
          type="button"
          aria-label={open ? `Collapse ${folder.name}` : `Expand ${folder.name}`}
          onClick={() => setOpen((v) => !v)}
          className={`p-0.5 text-w-faint ${children.length ? '' : 'invisible'}`}
        >
          <ChevronRight size={12} className={`transition-transform ${open ? 'rotate-90' : ''}`} />
        </button>
        <button type="button" onClick={() => onSelect(folder.id)} className="flex min-w-0 flex-1 items-center gap-1.5 py-1 text-left">
          <Icon size={14} className="shrink-0" />
          <span className="truncate">{folder.name}</span>
        </button>
      </div>
      {open && children.length > 0 && (
        <ul className="space-y-0.5">
          {children.map((child) => (
            <TreeRow key={child.folder.id} node={child} depth={depth + 1} selectedId={selectedId} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </li>
  )
}
