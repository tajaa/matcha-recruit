import { FolderOpen, Plus, ChevronDown, Pencil } from 'lucide-react'
import type { NavigateFunction } from 'react-router-dom'
import type { MWProject } from '../../../types'
import type { SidebarRename } from './useSidebarRename'
import RenameInput from './RenameInput'

interface Props {
  projects: MWProject[]
  projectsOpen: boolean
  setProjectsOpen: React.Dispatch<React.SetStateAction<boolean>>
  filter: string
  isPersonal: boolean
  base: string
  navigate: NavigateFunction
  isActive: (path: string) => boolean
  setShowProjectTypePicker: React.Dispatch<React.SetStateAction<boolean>>
  rename: SidebarRename
}

// Projects
export default function ProjectsSection({
  projects,
  projectsOpen,
  setProjectsOpen,
  filter,
  isPersonal,
  base,
  navigate,
  isActive,
  setShowProjectTypePicker,
  rename,
}: Props) {
  const { renaming, startRename } = rename
  return (
    <div className="mt-1">
      <button
        onClick={() => setProjectsOpen(!projectsOpen)}
        className="flex items-center justify-between w-full px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-w-dim transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <FolderOpen size={12} />
          Workspaces
        </span>
        <div className="flex items-center gap-1">
          <span
            onClick={(e) => { e.stopPropagation(); setShowProjectTypePicker(true) }}
            className="hover:text-w-accent cursor-pointer"
          >
            <Plus size={12} />
          </span>
          <ChevronDown size={12} className={`transition-transform ${projectsOpen || filter ? '' : '-rotate-90'}`} />
        </div>
      </button>
      {(projectsOpen || !!filter) && (
        <div className="space-y-0.5 mt-0.5">
          {(() => {
            const filteredProjects = projects.filter((p) => p.title.toLowerCase().includes(filter.toLowerCase()))
            const renderProjectRow = (p: MWProject) => (
              <div
                key={p.id}
                className={`group w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                  isActive(`${base}/projects/${p.id}`)
                    ? 'bg-w-surface2 text-white font-medium'
                    : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
                }`}
              >
                <FolderOpen size={14} className="text-w-accent shrink-0" strokeWidth={1.6} />
                {renaming?.type === 'project' && renaming.id === p.id ? (
                  <RenameInput rename={rename} />
                ) : (
                  <>
                    <button
                      onClick={() => navigate(`${base}/projects/${p.id}`)}
                      className="flex-1 min-w-0 text-left truncate"
                    >
                      {p.title}
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); startRename('project', p.id, p.title) }}
                      className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 text-w-dim hover:text-w-text transition-all"
                      title="Rename"
                    >
                      <Pencil size={11} />
                    </button>
                  </>
                )}
              </div>
            )

            if (filteredProjects.length === 0) {
              return <p className="px-2.5 py-1 text-[11px] text-w-faint">No workspaces</p>
            }

            if (!isPersonal) {
              return filteredProjects.slice(0, 10).map(renderProjectRow)
            }

            // Personal: group by hiring client (Unassigned last)
            const groups = new Map<string, { name: string; items: MWProject[] }>()
            for (const p of filteredProjects) {
              const key = p.hiring_client_id || '__unassigned'
              const name = p.hiring_client_name || 'Unassigned'
              if (!groups.has(key)) groups.set(key, { name, items: [] })
              groups.get(key)!.items.push(p)
            }
            const orderedKeys = Array.from(groups.keys()).sort((a, b) => {
              if (a === '__unassigned') return 1
              if (b === '__unassigned') return -1
              return groups.get(a)!.name.localeCompare(groups.get(b)!.name)
            })
            return orderedKeys.map((key) => {
              const g = groups.get(key)!
              return (
                <div key={key}>
                  <p className="px-2.5 pt-1 pb-0.5 text-[10px] uppercase tracking-wider text-w-faint truncate">
                    {g.name}
                  </p>
                  {g.items.map(renderProjectRow)}
                </div>
              )
            })
          })()}
        </div>
      )}
    </div>
  )
}
