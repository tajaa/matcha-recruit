import { FolderOpen, Plus, Pencil } from 'lucide-react'
import type { NavigateFunction } from 'react-router-dom'
import type { MWProject } from '../../../types'
import type { SidebarRename } from './useSidebarRename'
import RenameInput from './RenameInput'
import { EmptyRow, SectionAction, SidebarSection } from './SidebarSection'
import { useCappedList } from './useCappedList'

// The first few workspaces; the rest behind "Show N more". The open one always shows.
const VISIBLE = 8

interface Props {
  projects: MWProject[]
  projectsOpen: boolean
  onToggle: () => void
  filter: string
  isPersonal: boolean
  base: string
  navigate: NavigateFunction
  isActive: (path: string) => boolean
  setShowProjectTypePicker: React.Dispatch<React.SetStateAction<boolean>>
  rename: SidebarRename
}

/** Workspaces (projects). A personal account's are grouped by hiring client,
 *  with a group heading only when there is more than one group. */
export default function ProjectsSection({
  projects,
  projectsOpen,
  onToggle,
  filter,
  isPersonal,
  base,
  navigate,
  isActive,
  setShowProjectTypePicker,
  rename,
}: Props) {
  const { renaming, startRename } = rename
  const matching = projects.filter((p) => p.title.toLowerCase().includes(filter.toLowerCase()))
  const groups = isPersonal ? groupByClient(matching) : [{ key: 'all', name: '', items: matching }]
  // Capped in the order shown, so the hidden ones are the last ones.
  const ordered = groups.flatMap((g) => g.items)
  const { visible, toggle } = useCappedList(ordered, VISIBLE, {
    filtering: !!filter,
    keep: (p) => isActive(`${base}/projects/${p.id}`),
  })
  const shown = new Set(visible.map((p) => p.id))

  const row = (p: MWProject) => (
    <div
      key={p.id}
      className={`group flex w-full items-center gap-2 rounded-md px-2.5 py-1 text-[13px] transition-colors ${
        isActive(`${base}/projects/${p.id}`)
          ? 'bg-w-surface2 font-medium text-white'
          : 'text-w-dim hover:bg-w-surface2/50 hover:text-w-text'
      }`}
    >
      <FolderOpen size={13} className="shrink-0 text-w-faint" strokeWidth={1.8} />
      {renaming?.type === 'project' && renaming.id === p.id ? (
        <RenameInput rename={rename} />
      ) : (
        <>
          <button type="button" onClick={() => navigate(`${base}/projects/${p.id}`)} className="min-w-0 flex-1 truncate text-left">
            {p.title}
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); startRename('project', p.id, p.title) }}
            className="hidden shrink-0 p-0.5 text-w-faint hover:text-w-text group-focus-within:block group-hover:block"
            title="Rename"
            aria-label={`Rename ${p.title}`}
          >
            <Pencil size={11} />
          </button>
        </>
      )}
    </div>
  )

  return (
    <SidebarSection
      label="Workspaces"
      open={projectsOpen || !!filter}
      onToggle={onToggle}
      actions={<SectionAction icon={Plus} label="New workspace" onClick={() => setShowProjectTypePicker(true)} />}
    >
      {matching.length === 0 && <EmptyRow>{filter ? 'No workspaces match' : 'No workspaces yet'}</EmptyRow>}
      {groups.length > 1
        ? groups.map((g) => {
          const items = g.items.filter((p) => shown.has(p.id))
          if (items.length === 0) return null
          return (
            <div key={g.key}>
              <p className="truncate px-2.5 pb-0.5 pt-1.5 text-[10px] text-w-faint">{g.name}</p>
              {items.map(row)}
            </div>
          )
        })
        : visible.map(row)}
      {toggle}
    </SidebarSection>
  )
}

function groupByClient(projects: MWProject[]) {
  const groups = new Map<string, { key: string; name: string; items: MWProject[] }>()
  for (const p of projects) {
    const key = p.hiring_client_id || '__unassigned'
    if (!groups.has(key)) groups.set(key, { key, name: p.hiring_client_name || 'Unassigned', items: [] })
    groups.get(key)!.items.push(p)
  }
  return Array.from(groups.values()).sort((a, b) => {
    if (a.key === '__unassigned') return 1
    if (b.key === '__unassigned') return -1
    return a.name.localeCompare(b.name)
  })
}
