import type { LucideIcon } from 'lucide-react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import { Logo } from './ui'

export type NavItem = {
  to: string
  icon: LucideIcon
  label: string
}

type SidebarShellProps = {
  logoTo: string
  logoLabel: string
  nav: NavItem[]
}

export default function SidebarShell({ logoTo, logoLabel, nav }: SidebarShellProps) {
  const navigate = useNavigate()
  const location = useLocation()

  function handleLogout() {
    localStorage.removeItem('matcha_access_token')
    localStorage.removeItem('matcha_refresh_token')
    navigate('/login')
  }

  return (
    <aside className="fixed inset-y-0 left-0 w-56 bg-zinc-950/80 backdrop-blur-sm border-r border-zinc-800/50 flex flex-col">
      <div className="px-5 py-6">
        <Logo to={logoTo} label={logoLabel} />
      </div>

      <nav className="flex-1 px-3 space-y-0.5">
        {nav.map((item) => {
          const isExact = item.to === '/app' || item.to === '/admin'
          const isActive = isExact
            ? location.pathname === item.to
            : location.pathname.startsWith(item.to)

          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={
                `group relative flex items-center gap-3 rounded-md px-3 py-2 text-[13px] font-medium transition-all duration-150 ${
                  isActive
                    ? 'bg-zinc-800/80 text-zinc-50'
                    : 'text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800/40'
                }`
              }
            >
              {isActive && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-r-full bg-zinc-300" />
              )}
              <item.icon className={`h-[15px] w-[15px] flex-shrink-0 ${isActive ? 'text-zinc-300' : 'text-zinc-600 group-hover:text-zinc-400'}`} />
              {item.label}
            </NavLink>
          )
        })}
      </nav>

      <div className="px-3 py-4 border-t border-zinc-800/50">
        <button
          type="button"
          onClick={handleLogout}
          className="flex items-center gap-3 w-full rounded-md px-3 py-2 text-[13px] font-medium text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800/40 transition-all duration-150"
        >
          <LogOut className="h-[15px] w-[15px]" />
          Log out
        </button>
      </div>
    </aside>
  )
}
