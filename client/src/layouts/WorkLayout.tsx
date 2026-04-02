import { Link, Outlet } from 'react-router-dom'
import { ArrowLeft, Mail } from 'lucide-react'
import { usePresenceHeartbeat } from '../hooks/usePresenceHeartbeat'
import { OnlineUsersPanel } from '../components/work/OnlineUsersPanel'
import { useEffect, useState } from 'react'
import { getUnreadCount } from '../api/inbox'

export default function WorkLayout() {
  usePresenceHeartbeat()
  const [unread, setUnread] = useState(0)

  useEffect(() => {
    getUnreadCount().then((r) => setUnread(r.count)).catch(() => {})
    const id = setInterval(() => {
      getUnreadCount().then((r) => setUnread(r.count)).catch(() => {})
    }, 60_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col">
      <header className="flex items-center gap-3 px-6 py-3 border-b border-zinc-800">
        <Link
          to="/app"
          className="flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white transition-colors"
        >
          <ArrowLeft size={16} />
          Back to app
        </Link>
        <div className="h-4 w-px bg-zinc-700" />
        <span className="text-sm font-medium text-white">Matcha Work</span>

        <div className="ml-auto">
          <Link
            to="/app/inbox"
            className="relative flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white transition-colors"
          >
            <Mail size={16} />
            <span className="hidden sm:inline">Inbox</span>
            {unread > 0 && (
              <span className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-blue-500 text-[9px] font-bold text-white flex items-center justify-center">
                {unread > 9 ? '9+' : unread}
              </span>
            )}
          </Link>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
      <OnlineUsersPanel />
    </div>
  )
}
