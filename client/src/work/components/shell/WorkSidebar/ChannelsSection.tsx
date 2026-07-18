import { Hash, Plus, ChevronDown, Pencil, Compass } from 'lucide-react'
import type { NavigateFunction } from 'react-router-dom'
import type { ChannelSummary } from '../../../api/channels'
import type { SidebarRename } from './useSidebarRename'
import RenameInput from './RenameInput'

interface Props {
  channels: ChannelSummary[]
  channelsOpen: boolean
  setChannelsOpen: React.Dispatch<React.SetStateAction<boolean>>
  filter: string
  totalChannelUnread: number
  canCreate: boolean
  base: string
  navigate: NavigateFunction
  isActive: (path: string) => boolean
  setShowCreateChannel: React.Dispatch<React.SetStateAction<boolean>>
  rename: SidebarRename
}

// Channels
export default function ChannelsSection({
  channels,
  channelsOpen,
  setChannelsOpen,
  filter,
  totalChannelUnread,
  canCreate,
  base,
  navigate,
  isActive,
  setShowCreateChannel,
  rename,
}: Props) {
  const { renaming, startRename } = rename
  return (
    <div className="mt-2">
      <button
        onClick={() => setChannelsOpen(!channelsOpen)}
        className="flex items-center justify-between w-full px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-w-dim transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <Hash size={12} />
          Channels
          {/* Sections default collapsed, so without this the expanded
              sidebar shows no unread signal at all until you open it. */}
          {!channelsOpen && !filter && totalChannelUnread > 0 && (
            <span className="w-4 h-4 rounded-full bg-w-accent text-[9px] font-bold text-black flex items-center justify-center">
              {totalChannelUnread > 9 ? '9+' : totalChannelUnread}
            </span>
          )}
        </span>
        <div className="flex items-center gap-1">
          <span
            onClick={(e) => { e.stopPropagation(); navigate(`${base}/channels`) }}
            className="hover:text-w-accent cursor-pointer"
            title="Browse channels"
          >
            <Compass size={12} />
          </span>
          {canCreate && (
            <span
              onClick={(e) => { e.stopPropagation(); setShowCreateChannel(true) }}
              className="hover:text-w-accent cursor-pointer"
            >
              <Plus size={12} />
            </span>
          )}
          <ChevronDown size={12} className={`transition-transform ${channelsOpen || filter ? '' : '-rotate-90'}`} />
        </div>
      </button>
      {(channelsOpen || !!filter) && (
        <div className="space-y-0.5 mt-0.5">
          {channels.filter((ch) => ch.name.toLowerCase().includes(filter.toLowerCase())).length === 0 && (
            <p className="px-2.5 py-1 text-[11px] text-w-faint">No channels</p>
          )}
          {channels.filter((ch) => ch.name.toLowerCase().includes(filter.toLowerCase())).map((ch) => (
            <div
              key={ch.id}
              className={`group w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors cursor-pointer ${
                isActive(`${base}/channels/${ch.id}`)
                  ? 'bg-w-surface2 text-white font-medium'
                  : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
              }`}
              onClick={() => navigate(`${base}/channels/${ch.id}`)}
            >
              <Hash size={14} className="text-w-dim shrink-0" strokeWidth={1.6} />
              {ch.is_paid && (
                <span className="text-[9px] font-bold text-w-accent shrink-0">$</span>
              )}
              {renaming?.type === 'channel' && renaming.id === ch.id ? (
                <RenameInput rename={rename} />
              ) : (
                <>
                  <span className={`flex-1 min-w-0 truncate ${ch.unread_count > 0 ? 'font-semibold text-white' : ''}`}>
                    {ch.name}
                  </span>
                  <button
                    onClick={(e) => { e.stopPropagation(); startRename('channel', ch.id, ch.name) }}
                    className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 text-w-dim hover:text-w-text transition-all"
                    title="Rename"
                  >
                    <Pencil size={11} />
                  </button>
                </>
              )}
              {ch.unread_count > 0 && !renaming && (
                <span className="ml-auto w-4 h-4 rounded-full bg-w-accent text-[9px] font-bold text-white flex items-center justify-center shrink-0">
                  {ch.unread_count > 9 ? '9+' : ch.unread_count}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
