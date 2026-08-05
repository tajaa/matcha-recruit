import { Link, type NavigateFunction } from 'react-router-dom'
import { MessageSquare, ChevronDown, Pencil, Plus, Users } from 'lucide-react'
import type { MWThread } from '../../../types'
import { formatDateTimePacific } from '../../../../utils/dateFormat'
import type { SidebarRename } from './useSidebarRename'
import RenameInput from './RenameInput'

const MAX_VISIBLE = 20

interface Props {
  threads: MWThread[]
  chatsOpen: boolean
  onToggle: () => void
  onNewChat: () => void
  filter: string
  base: string
  navigate: NavigateFunction
  isActive: (path: string) => boolean
  rename: SidebarRename
}

// Chats — one flat, recent-first list (the backend already orders
// is_pinned DESC, updated_at DESC). Used to be split into "mine"/"Shared"
// sub-lists and duplicated by a separate MRU "Tabs" strip above it; both are
// gone — a thread you've opened shows up here, once, and stays put.
export default function ChatsSection({
  threads,
  chatsOpen,
  onToggle,
  onNewChat,
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
        onClick={onToggle}
        className="flex items-center justify-between w-full px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-w-dim transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <MessageSquare size={12} />
          Chats
        </span>
        <div className="flex items-center gap-1">
          <span
            onClick={(e) => { e.stopPropagation(); onNewChat() }}
            className="hover:text-w-accent cursor-pointer"
            title="New chat"
          >
            <Plus size={12} />
          </span>
          <ChevronDown size={12} className={`transition-transform ${chatsOpen || filter ? '' : '-rotate-90'}`} />
        </div>
      </button>
      {(chatsOpen || !!filter) && (() => {
        const filtered = threads.filter((t) => t.title.toLowerCase().includes(filter.toLowerCase()))

        if (filtered.length === 0) {
          return <p className="px-2.5 py-1 text-[11px] text-w-faint">No chats</p>
        }

        const visible = filtered.slice(0, MAX_VISIBLE)

        return (
          <div className="space-y-0.5 mt-0.5">
            {visible.map((t) => (
              <div
                key={t.id}
                className={`group w-full flex items-start gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                  isActive(`${base}/${t.id}`)
                    ? 'bg-w-surface2 text-white font-medium'
                    : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
                }`}
              >
                <MessageSquare size={14} className="text-w-dim shrink-0 mt-0.5" strokeWidth={1.6} />
                {renaming?.type === 'thread' && renaming.id === t.id ? (
                  <RenameInput rename={rename} />
                ) : (
                  <>
                    <Link to={`${base}/${t.id}`} className="flex-1 min-w-0 text-left">
                      <div className="truncate">{t.title}</div>
                      <div className="truncate text-[10px] text-w-faint font-normal" title="Created (Pacific time)">
                        {formatDateTimePacific(t.created_at)}
                      </div>
                    </Link>
                    {t.collaborator_count > 0 && (
                      <span title="Shared" className="shrink-0 text-w-faint mt-0.5">
                        <Users size={11} />
                      </span>
                    )}
                    <button
                      onClick={(e) => { e.stopPropagation(); startRename('thread', t.id, t.title) }}
                      className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 text-w-dim hover:text-w-text transition-all mt-0.5"
                      title="Rename"
                    >
                      <Pencil size={11} />
                    </button>
                  </>
                )}
              </div>
            ))}
            {filtered.length > MAX_VISIBLE && (
              <button
                onClick={() => navigate(base)}
                className="w-full px-2.5 py-1 text-left text-[11px] text-w-faint hover:text-w-text transition-colors"
              >
                Show all ({filtered.length})
              </button>
            )}
          </div>
        )
      })()}
    </div>
  )
}
