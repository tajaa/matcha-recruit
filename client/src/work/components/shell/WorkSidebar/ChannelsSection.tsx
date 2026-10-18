import { Hash, Plus, Pencil, Compass, Star } from 'lucide-react'
import type { NavigateFunction } from 'react-router-dom'
import type { ChannelSummary } from '../../../api/channels'
import type { SidebarRename } from './useSidebarRename'
import RenameInput from './RenameInput'
import { toggleStar, useStars } from '../../../hooks/useStars'
import { EmptyRow, SectionAction, SidebarSection } from './SidebarSection'
import { useCappedList } from './useCappedList'

// The first few channels; the rest behind "Show N more". A channel with
// unread messages, or the one open, always shows.
const VISIBLE = 8

interface Props {
  channels: ChannelSummary[]
  channelsOpen: boolean
  onToggle: () => void
  filter: string
  totalChannelUnread: number
  canCreate: boolean
  base: string
  navigate: NavigateFunction
  isActive: (path: string) => boolean
  setShowCreateChannel: React.Dispatch<React.SetStateAction<boolean>>
  rename: SidebarRename
  userId?: string
}

export default function ChannelsSection({
  channels,
  channelsOpen,
  onToggle,
  filter,
  totalChannelUnread,
  canCreate,
  base,
  navigate,
  isActive,
  setShowCreateChannel,
  rename,
  userId,
}: Props) {
  const { renaming, startRename } = rename
  const starred = useStars(userId, 'channels')
  const query = filter.toLowerCase()
  const matching = channels.filter((ch) => ch.name.toLowerCase().includes(query))
  const { visible, toggle } = useCappedList(matching, VISIBLE, {
    filtering: !!filter,
    keep: (ch) => ch.unread_count > 0 || isActive(`${base}/channels/${ch.id}`),
  })

  return (
    <SidebarSection
      label="Channels"
      open={channelsOpen || !!filter}
      onToggle={onToggle}
      badge={totalChannelUnread > 0 && <UnreadBadge count={totalChannelUnread} />}
      actions={<>
        <SectionAction icon={Compass} label="Browse channels" onClick={() => navigate(`${base}/channels`)} />
        {canCreate && <SectionAction icon={Plus} label="New channel" onClick={() => setShowCreateChannel(true)} />}
      </>}
    >
      {matching.length === 0 && <EmptyRow>{filter ? 'No channels match' : 'No channels yet'}</EmptyRow>}
      {visible.map((ch) => {
        const active = isActive(`${base}/channels/${ch.id}`)
        const isStarred = starred.includes(ch.id)
        return (
          <div
            key={ch.id}
            className={`group flex w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1 text-[13px] transition-colors ${
              active ? 'bg-w-surface2 font-medium text-white' : 'text-w-dim hover:bg-w-surface2/50 hover:text-w-text'
            }`}
            onClick={() => navigate(`${base}/channels/${ch.id}`)}
          >
            <Hash size={13} className="shrink-0 text-w-faint" strokeWidth={1.8} />
            {renaming?.type === 'channel' && renaming.id === ch.id ? (
              <RenameInput rename={rename} />
            ) : (
              <>
                <span className={`min-w-0 flex-1 truncate ${ch.unread_count > 0 ? 'font-semibold text-white' : ''}`}>
                  {ch.name}
                </span>
                {ch.is_paid && <span className="shrink-0 text-[9px] font-bold text-w-accent" title="Paid channel">$</span>}
                <button
                  type="button"
                  onClick={(event) => { event.stopPropagation(); toggleStar(userId, 'channels', ch.id) }}
                  aria-label={`${isStarred ? 'Unstar' : 'Star'} ${ch.name}`}
                  title={isStarred ? 'Unstar' : 'Star'}
                  className={`shrink-0 ${isStarred ? 'text-w-accent' : 'hidden text-w-faint group-focus-within:block group-hover:block'}`}
                >
                  <Star size={11} fill={isStarred ? 'currentColor' : 'none'} />
                </button>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); startRename('channel', ch.id, ch.name) }}
                  aria-label={`Rename ${ch.name}`}
                  title="Rename"
                  className="hidden shrink-0 p-0.5 text-w-faint hover:text-w-text group-focus-within:block group-hover:block"
                >
                  <Pencil size={11} />
                </button>
                {ch.unread_count > 0 && <UnreadBadge count={ch.unread_count} />}
              </>
            )}
          </div>
        )
      })}
      {toggle}
    </SidebarSection>
  )
}

function UnreadBadge({ count }: { count: number }) {
  return (
    <span className="ml-auto flex h-4 min-w-4 shrink-0 items-center justify-center rounded-full bg-w-accent px-1 text-[9px] font-bold text-white" aria-label={`${count} unread`}>
      {count > 9 ? '9+' : count}
    </span>
  )
}
