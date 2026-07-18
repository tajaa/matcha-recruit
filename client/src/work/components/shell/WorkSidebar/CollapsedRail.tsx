import { Hash, FolderOpen, MessageSquare, PanelLeftClose, Mail, MailOpen, Home, Users } from 'lucide-react'
import type { NavigateFunction } from 'react-router-dom'

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
  setChannelsOpen: React.Dispatch<React.SetStateAction<boolean>>
  setProjectsOpen: React.Dispatch<React.SetStateAction<boolean>>
  setThreadsOpen: React.Dispatch<React.SetStateAction<boolean>>
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
  setChannelsOpen,
  setProjectsOpen,
  setThreadsOpen,
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

      <button
        onClick={() => { onToggle(); setChannelsOpen(true) }}
        className={`relative p-2 rounded-lg transition-colors ${pathname.includes('/channels/') ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
        title="Channels"
      >
        <Hash size={16} />
        {totalChannelUnread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-w-accent text-[8px] font-bold text-white flex items-center justify-center">
            {totalChannelUnread > 9 ? '!' : totalChannelUnread}
          </span>
        )}
      </button>

      {mwBetaLite && (
        <button
          onClick={() => { onToggle(); setProjectsOpen(true) }}
          className={`p-2 rounded-lg transition-colors ${pathname.includes('/projects/') ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
          title="Projects"
        >
          <FolderOpen size={16} />
        </button>
      )}

      <button
        onClick={() => { onToggle(); setThreadsOpen(true) }}
        className={`p-2 rounded-lg transition-colors ${new RegExp(`^${base}/[^/]+$`).test(pathname) && !pathname.includes('/channels/') && !pathname.includes('/projects/') ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
        title="Threads"
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
