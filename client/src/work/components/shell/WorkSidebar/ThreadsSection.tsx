import { MessageSquare, ChevronDown, Pencil, Users } from 'lucide-react'
import type { NavigateFunction } from 'react-router-dom'
import type { MWThread } from '../../../types'
import type { SidebarRename } from './useSidebarRename'
import RenameInput from './RenameInput'

interface Props {
  threads: MWThread[]
  threadsOpen: boolean
  setThreadsOpen: React.Dispatch<React.SetStateAction<boolean>>
  filter: string
  base: string
  navigate: NavigateFunction
  isActive: (path: string) => boolean
  rename: SidebarRename
}

// Threads
export default function ThreadsSection({
  threads,
  threadsOpen,
  setThreadsOpen,
  filter,
  base,
  navigate,
  isActive,
  rename,
}: Props) {
  const { renaming, startRename } = rename
  return (
    <div className="mt-1">
      <button
        onClick={() => setThreadsOpen(!threadsOpen)}
        className="flex items-center justify-between w-full px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-w-dim transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <MessageSquare size={12} />
          Threads
        </span>
        <ChevronDown size={12} className={`transition-transform ${threadsOpen || filter ? '' : '-rotate-90'}`} />
      </button>
      {(threadsOpen || !!filter) && (() => {
        const filteredThreads = threads.filter((t) => t.title.toLowerCase().includes(filter.toLowerCase()))
        const myThreads = filteredThreads.filter((t) => t.collaborator_count === 0)
        const sharedThreads = filteredThreads.filter((t) => t.collaborator_count > 0)

        const renderThread = (t: MWThread) => (
          <div
            key={t.id}
            className={`group w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
              isActive(`${base}/${t.id}`)
                ? 'bg-w-surface2 text-white font-medium'
                : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
            }`}
          >
            <MessageSquare size={14} className="text-w-dim shrink-0" strokeWidth={1.6} />
            {renaming?.type === 'thread' && renaming.id === t.id ? (
              <RenameInput rename={rename} />
            ) : (
              <>
                <button
                  onClick={() => navigate(`${base}/${t.id}`)}
                  className="flex-1 min-w-0 text-left truncate"
                >
                  {t.title}
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); startRename('thread', t.id, t.title) }}
                  className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 text-w-dim hover:text-w-text transition-all"
                  title="Rename"
                >
                  <Pencil size={11} />
                </button>
              </>
            )}
          </div>
        )

        if (filteredThreads.length === 0) {
          return <p className="px-2.5 py-1 text-[11px] text-w-faint">No threads</p>
        }

        return (
          <div className="space-y-0.5 mt-0.5">
            {myThreads.slice(0, 10).map(renderThread)}
            {sharedThreads.length > 0 && (
              <>
                <p className="px-2.5 pt-2 pb-0.5 text-[10px] uppercase tracking-wider text-w-faint flex items-center gap-1">
                  <Users size={10} />
                  Shared
                </p>
                {sharedThreads.slice(0, 10).map(renderThread)}
              </>
            )}
          </div>
        )
      })()}
    </div>
  )
}
