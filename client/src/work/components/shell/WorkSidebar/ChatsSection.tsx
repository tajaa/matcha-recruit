import { Link, type NavigateFunction } from 'react-router-dom'
import { MessageSquare, Pencil, Plus, Users, Archive } from 'lucide-react'
import type { MWThread } from '../../../types'
import { formatDateTimePacific } from '../../../../utils/dateFormat'
import { relativeTime, shortDate } from '../../../../utils/format'
import { chatLabel } from '../../../utils/chatLabel'
import type { SidebarRename } from './useSidebarRename'
import RenameInput from './RenameInput'
import { EmptyRow, SectionAction, SidebarSection } from './SidebarSection'
import { useCappedList } from './useCappedList'

// Default collapsed to the 5 most recent — a "Show more" chevron expands in
// place. A hard cap (not "show ALL ever") still applies once expanded so a
// long-lived company doesn't render hundreds of rows into the sidebar.
const COLLAPSED_VISIBLE = 5
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
  onArchive: (thread: MWThread) => void
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
  onArchive,
}: Props) {
  const { renaming, startRename } = rename
  const matching = threads.filter((t) => t.title.toLowerCase().includes(filter.toLowerCase()))
  const { visible, toggle } = useCappedList(matching.slice(0, MAX_VISIBLE), COLLAPSED_VISIBLE, {
    filtering: !!filter,
    keep: (t) => isActive(`${base}/${t.id}`),
  })

  return (
    <SidebarSection
      label="Chats"
      open={chatsOpen || !!filter}
      onToggle={onToggle}
      actions={<SectionAction icon={Plus} label="New chat" onClick={onNewChat} />}
    >
      {matching.length === 0 && <EmptyRow>{filter ? 'No chats match' : 'No chats yet'}</EmptyRow>}
      {visible.map((t) => (
        <div
          key={t.id}
          className={`group flex w-full items-center gap-2 rounded-md px-2.5 py-1 text-[13px] transition-colors ${
            isActive(`${base}/${t.id}`)
              ? 'bg-w-surface2 font-medium text-white'
              : 'text-w-dim hover:bg-w-surface2/50 hover:text-w-text'
          }`}
        >
          <MessageSquare size={13} className="shrink-0 text-w-faint" strokeWidth={1.8} />
          {renaming?.type === 'thread' && renaming.id === t.id ? (
            <RenameInput rename={rename} />
          ) : (
            <>
              <Link to={`${base}/${t.id}`} className="min-w-0 flex-1 truncate text-left" title={t.title}>
                {chatLabel(t.title)}
              </Link>
              {t.collaborator_count > 0 && (
                <span title="Shared" className="shrink-0 text-w-faint">
                  <Users size={11} />
                </span>
              )}
              {/* When, until hover swaps it for the row's actions. */}
              <span
                className="shrink-0 text-[10px] font-normal text-w-faint group-focus-within:hidden group-hover:hidden"
                title={`Created ${formatDateTimePacific(t.created_at)}`}
              >
                {relativeTime(t.updated_at ?? t.created_at, { empty: '', justNowLabel: 'now', maxRelativeDays: 7, absolute: shortDate }).replace(' ago', '')}
              </span>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); startRename('thread', t.id, t.title) }}
                className="hidden shrink-0 p-0.5 text-w-faint hover:text-w-text group-focus-within:block group-hover:block"
                title="Rename"
                aria-label={`Rename ${chatLabel(t.title)}`}
              >
                <Pencil size={11} />
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onArchive(t) }}
                className="hidden shrink-0 p-0.5 text-w-faint hover:text-w-text group-focus-within:block group-hover:block"
                title="Archive"
                aria-label={`Archive ${chatLabel(t.title)}`}
              >
                <Archive size={11} />
              </button>
            </>
          )}
        </div>
      ))}
      {toggle}
      {matching.length > MAX_VISIBLE && (
        <button
          type="button"
          onClick={() => navigate(base)}
          className="w-full rounded px-2.5 py-1 text-left text-[11px] text-w-faint transition-colors hover:text-w-text"
        >
          All chats ({matching.length})
        </button>
      )}
    </SidebarSection>
  )
}
