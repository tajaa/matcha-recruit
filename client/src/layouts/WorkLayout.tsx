import { Link, Outlet } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { usePresenceHeartbeat } from '../hooks/usePresenceHeartbeat'
import { OnlineUsersPanel } from '../components/work/OnlineUsersPanel'

export default function WorkLayout() {
  usePresenceHeartbeat()

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
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
      <OnlineUsersPanel />
    </div>
  )
}
