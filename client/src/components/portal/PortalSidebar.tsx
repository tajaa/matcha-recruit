import { Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, CalendarClock, HeartPulse, MessageCircleQuestion } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import { resetAuthCaches } from '../../api/authReset'
import { useState } from 'react'

interface NavItem {
  to: string
  icon: typeof LayoutDashboard
  label: string
  feature?: string
}

const NAV: NavItem[] = [
  { to: '/portal', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/portal/schedule', icon: CalendarClock, label: 'My Schedule', feature: 'employee_schedule' },
  { to: '/portal/benefits', icon: HeartPulse, label: 'My Benefits', feature: 'benefits_admin' },
  { to: '/portal/ask-hr', icon: MessageCircleQuestion, label: 'Ask HR', feature: 'ask_hr' },
]

export default function PortalSidebar() {
  const { pathname } = useLocation()
  const { me, hasFeature } = useMe()
  const [logoutHover, setLogoutHover] = useState(false)

  const navItems = NAV.filter((item) => !item.feature || hasFeature(item.feature))

  function handleLogout() {
    localStorage.removeItem('matcha_access_token')
    localStorage.removeItem('matcha_refresh_token')
    resetAuthCaches()
    window.location.href = '/login'
  }

  return (
    <aside className="w-60 shrink-0 h-full border-r border-zinc-800 bg-[#0c0c0e] flex flex-col">
      <div className="px-5 py-4 border-b border-zinc-800">
        <div className="text-emerald-400 font-semibold tracking-widest text-sm">MATCHA</div>
        <div className="text-xs text-zinc-500 mt-0.5">Employee Portal</div>
      </div>

      <nav className="flex-1 py-3 px-2 space-y-1 overflow-auto">
        {navItems.map((item) => {
          const active =
            item.to === '/portal' ? pathname === '/portal' : pathname.startsWith(item.to)
          const Icon = item.icon
          return (
            <Link
              key={item.to}
              to={item.to}
              className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                active
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-100'
              }`}
            >
              <Icon className="w-4 h-4" />
              {item.label}
            </Link>
          )
        })}
      </nav>

      <div className="p-3 border-t border-zinc-800">
        <div className="px-2 mb-2">
          <div className="text-xs text-zinc-300 truncate">{me?.user?.email}</div>
        </div>
        <button
          onClick={handleLogout}
          onMouseEnter={() => setLogoutHover(true)}
          onMouseLeave={() => setLogoutHover(false)}
          className={`w-full text-xs text-left px-2 py-1.5 rounded transition-colors ${
            logoutHover ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-500'
          }`}
        >
          Sign out
        </button>
      </div>
    </aside>
  )
}
