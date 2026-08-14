import { Hash, FolderOpen, MessageSquare, PanelLeftClose, Mail, MailOpen, Home, Users, ClipboardList, BookOpenCheck, Package } from 'lucide-react'
import type { NavigateFunction } from 'react-router-dom'
import { formatEventsBadge } from '../../../hooks/useLoggedEventsCount'

interface Props {
  onToggle: () => void
  base: string
  pathname: string
  navigate: NavigateFunction
  isActive: (path: string) => boolean
  mwBetaLite: boolean
  totalChannelUnread: number
  pendingConnections: number
  inboxUnread: number
  inboxPath: string
  openChannels: () => void
  openProjects: () => void
  openChats: () => void
  showEvents: boolean
  showInventory: boolean
  showChannels: boolean
  loggedEventsCount: number
}

// ─── Collapsed: icon rail ───
export default function CollapsedRail({
  onToggle,
  base,
  pathname,
  navigate,
  isActive,
  mwBetaLite,
  totalChannelUnread,
  pendingConnections,
  inboxUnread,
  inboxPath,
  openChannels,
  openProjects,
  openChats,
  showEvents,
  showInventory,
  showChannels,
  loggedEventsCount,
}: Props) {
  return (
    <aside className="w-12 bg-w-surface border-r border-w-line flex flex-col items-center py-2 gap-1 shrink-0">
      <button
        onClick={onToggle}
        className="p-2 rounded-lg hover:bg-w-surface2 text-w-dim hover:text-white transition-colors mb-1"
        title="Open sidebar"
      >
        <PanelLeftClose size={16} className="rotate-180" />
      </button>
      <div className="w-6 border-t border-w-line/40 mb-1" />

      <button
        onClick={() => navigate(base)}
        className={`p-2 rounded-lg transition-colors ${isActive(base) ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
        title="Home"
      >
        <Home size={16} />
      </button>

      <button
        onClick={() => navigate(`${base}/email`)}
        className={`p-2 rounded-lg transition-colors ${isActive(`${base}/email`) ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
        title="Email"
      >
        <MailOpen size={16} />
      </button>

      {showEvents && (
        <button
          onClick={() => navigate(`${base}/events`)}
          className={`relative p-2 rounded-lg transition-colors ${isActive(`${base}/events`) ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
          title="Events"
        >
          <ClipboardList size={16} />
          {loggedEventsCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-w-accent text-[8px] font-bold text-white flex items-center justify-center">
              {formatEventsBadge(loggedEventsCount, true)}
            </span>
          )}
        </button>
      )}

      {showEvents && (
        <button
          onClick={() => navigate(`${base}/protocol`)}
          className={`p-2 rounded-lg transition-colors ${isActive(`${base}/protocol`) ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
          title="Protocol"
        >
          <BookOpenCheck size={16} />
        </button>
      )}

      {showInventory && (
        <button
          onClick={() => navigate(`${base}/inventory`)}
          className={`p-2 rounded-lg transition-colors ${isActive(`${base}/inventory`) ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
          title="Inventory"
        >
          <Package size={16} />
        </button>
      )}

      {showChannels && <button
        onClick={() => { onToggle(); openChannels() }}
        className={`relative p-2 rounded-lg transition-colors ${pathname.includes('/channels/') ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
        title="Channels"
      >
        <Hash size={16} />
        {totalChannelUnread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-w-accent text-[8px] font-bold text-white flex items-center justify-center">
            {totalChannelUnread > 9 ? '!' : totalChannelUnread}
          </span>
        )}
      </button>}

      {mwBetaLite && (
        <button
          onClick={() => { onToggle(); openProjects() }}
          className={`p-2 rounded-lg transition-colors ${pathname.includes('/projects/') ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
          title="Projects"
        >
          <FolderOpen size={16} />
        </button>
      )}

      <button
        onClick={() => { onToggle(); openChats() }}
        className={`p-2 rounded-lg transition-colors ${new RegExp(`^${base}/[^/]+$`).test(pathname) && !pathname.includes('/channels/') && !pathname.includes('/projects/') ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
        title="Huume Workspaces"
      >
        <MessageSquare size={16} />
      </button>

      <div className="flex-1" />

      <button
        onClick={() => navigate(`${base}/connections`)}
        className={`relative p-2 rounded-lg transition-colors ${isActive(`${base}/connections`) ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
        title="People"
      >
        <Users size={16} />
        {pendingConnections > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-w-accent text-[8px] font-bold text-white flex items-center justify-center">
            {pendingConnections > 9 ? '!' : pendingConnections}
          </span>
        )}
      </button>

      <button
        onClick={() => navigate(inboxPath)}
        className={`relative p-2 rounded-lg transition-colors text-w-dim hover:text-white hover:bg-w-surface2/60`}
        title="Inbox"
      >
        <Mail size={16} />
        {inboxUnread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-blue-500 text-[8px] font-bold text-white flex items-center justify-center">
            {inboxUnread > 9 ? '!' : inboxUnread}
          </span>
        )}
      </button>
    </aside>
  )
}
