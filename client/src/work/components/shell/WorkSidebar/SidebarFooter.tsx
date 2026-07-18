import { Mail, LogOut, Users, CreditCard, Sparkles } from 'lucide-react'
import type { NavigateFunction } from 'react-router-dom'

interface Props {
  isPersonal: boolean
  plusActive: boolean | null
  upgrading: boolean
  onUpgrade: () => void
  base: string
  navigate: NavigateFunction
  isActive: (path: string) => boolean
  inboxPath: string
  inboxUnread: number
  pendingConnections: number
  userAvatar: string | null | undefined
  userName: string
  userEmail: string
  onLogout: () => void
}

// Footer: Inbox + User profile + Logout
export default function SidebarFooter({
  isPersonal,
  plusActive,
  upgrading,
  onUpgrade,
  base,
  navigate,
  isActive,
  inboxPath,
  inboxUnread,
  pendingConnections,
  userAvatar,
  userName,
  userEmail,
  onLogout,
}: Props) {
  return (
    <div className="px-2 py-2 border-t border-w-line space-y-1">
      {isPersonal && plusActive === false && (
        <button
          onClick={onUpgrade}
          disabled={upgrading}
          className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] text-amber-400 hover:text-amber-300 hover:bg-amber-500/10 transition-colors disabled:opacity-50"
        >
          <Sparkles size={14} strokeWidth={1.8} />
          {upgrading ? 'Opening checkout…' : 'Upgrade to Plus'}
        </button>
      )}
      {isPersonal && plusActive === true && (
        <div className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] text-amber-400/80">
          <Sparkles size={14} strokeWidth={1.8} />
          Plus active
        </div>
      )}
      {/* Footer nav row — Inbox / People / Billing as compact icon+label buttons */}
      <div className="flex items-stretch gap-1">
        <button
          onClick={() => navigate(inboxPath)}
          className="relative flex-1 flex flex-col items-center gap-0.5 py-1.5 rounded-md text-[10px] font-medium text-w-dim hover:text-w-text hover:bg-w-surface2/50 transition-colors"
        >
          <Mail size={14} strokeWidth={1.6} />
          Inbox
          {inboxUnread > 0 && (
            <span className="absolute top-0.5 right-2.5 w-3.5 h-3.5 rounded-full bg-blue-500 text-[8px] font-bold text-white flex items-center justify-center">
              {inboxUnread > 9 ? '!' : inboxUnread}
            </span>
          )}
        </button>
        <button
          onClick={() => navigate(`${base}/connections`)}
          className={`relative flex-1 flex flex-col items-center gap-0.5 py-1.5 rounded-md text-[10px] font-medium transition-colors ${
            isActive(`${base}/connections`)
              ? 'bg-w-surface2 text-white'
              : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
          }`}
        >
          <Users size={14} strokeWidth={1.6} />
          People
          {pendingConnections > 0 && (
            <span className="absolute top-0.5 right-2.5 w-3.5 h-3.5 rounded-full bg-w-accent text-[8px] font-bold text-white flex items-center justify-center">
              {pendingConnections > 9 ? '!' : pendingConnections}
            </span>
          )}
        </button>
        <button
          onClick={() => navigate(`${base}/billing`)}
          className="flex-1 flex flex-col items-center gap-0.5 py-1.5 rounded-md text-[10px] font-medium text-w-dim hover:text-w-text hover:bg-w-surface2/50 transition-colors"
        >
          <CreditCard size={14} strokeWidth={1.6} />
          Billing
        </button>
      </div>

      {/* User profile */}
      <div className="flex items-center gap-2 px-2.5 py-2 mt-1">
        {userAvatar ? (
          <img src={userAvatar} alt={userName} className="w-7 h-7 rounded-full object-cover shrink-0" />
        ) : (
          <div className="w-7 h-7 rounded-full bg-w-surface2 flex items-center justify-center text-[11px] font-medium text-w-dim shrink-0">
            {userName.charAt(0).toUpperCase()}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="text-[12px] text-w-text truncate">{userName}</p>
          <p className="text-[10px] text-w-faint truncate">{userEmail}</p>
        </div>
        <button
          onClick={onLogout}
          className="shrink-0 p-1 rounded text-w-faint hover:text-red-400 hover:bg-w-surface2/60 transition-colors"
          title="Log out"
        >
          <LogOut size={13} />
        </button>
      </div>
    </div>
  )
}
