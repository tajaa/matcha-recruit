import { Hash, FolderOpen, MessageSquare, PanelLeftClose, Mail, MailOpen, Home, Users, ClipboardList, BookOpenCheck, Package, NotebookPen } from 'lucide-react'
import type { NavigateFunction } from 'react-router-dom'
import { formatEventsBadge } from '../../../hooks/useLoggedEventsCount'
import { RailNavButton } from './SidebarNavButton'

interface Props {
  onToggle: () => void
  base: string
  pathname: string
  navigate: NavigateFunction
  isActive: (path: string) => boolean
  showProjects: boolean
  totalChannelUnread: number
  pendingConnections: number
  inboxUnread: number
  inboxPath: string
  openChannels: () => void
  openProjects: () => void
  openChats: () => void
  showEvents: boolean
  showInventory: boolean
  showWaste: boolean
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
  showProjects,
  totalChannelUnread,
  pendingConnections,
  inboxUnread,
  inboxPath,
  openChannels,
  openProjects,
  openChats,
  showEvents,
  showInventory,
  showWaste,
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

      <RailNavButton icon={Home} label="Home" active={isActive(base)} onClick={() => navigate(base)} />
      <RailNavButton icon={NotebookPen} label="Journals" active={pathname.startsWith(`${base}/journals`)} onClick={() => navigate(`${base}/journals`)} />
      <RailNavButton icon={MailOpen} label="Email" active={isActive(`${base}/email`)} onClick={() => navigate(`${base}/email`)} />

      {showEvents && (
        <RailNavButton
          icon={ClipboardList}
          label="Events"
          active={isActive(`${base}/events`)}
          onClick={() => navigate(`${base}/events`)}
          badge={loggedEventsCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-w-accent text-[8px] font-bold text-white flex items-center justify-center">
              {formatEventsBadge(loggedEventsCount, true)}
            </span>
          )}
        />
      )}
      {showEvents && <RailNavButton icon={BookOpenCheck} label="Protocol" active={isActive(`${base}/protocol`)} onClick={() => navigate(`${base}/protocol`)} />}
      {showInventory && <RailNavButton icon={Package} label="Inventory" active={isActive(`${base}/inventory`)} onClick={() => navigate(`${base}/inventory`)} />}
      {showWaste && <RailNavButton icon={Package} label="Waste & par" active={isActive(`${base}/inventory/waste`)} onClick={() => navigate(`${base}/inventory/waste`)} />}

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

      {showProjects && (
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
