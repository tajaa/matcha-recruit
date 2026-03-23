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
    <aside className="fixed inset-y-0 left-0 w-56 bg-[#0c0c0e] border-r border-zinc-800/30 flex flex-col">
      {/* Logo area */}
      <div className="px-4 pt-5 pb-4">
        <Logo to={logoTo} label={logoLabel} />
      </div>

      {/* Divider */}
      <div className="mx-4 border-t border-zinc-800/40" />

      {/* Navigation */}
      <nav className="flex-1 px-2.5 pt-3 space-y-0.5 overflow-y-auto">
        {nav.map((item) => {
          const isExact = item.to === '/app' || item.to === '/admin' || item.to === '/broker'
          const isActive = isExact
            ? location.pathname === item.to
            : location.pathname.startsWith(item.to)

          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={
                `group relative flex items-center gap-2.5 rounded-md px-2.5 py-[6px] text-[13px] transition-colors duration-100 ${
                  isActive
                    ? 'bg-zinc-800/60 text-zinc-100 font-medium'
                    : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/30 font-normal'
                }`
              }
            >
              <item.icon className={`h-4 w-4 flex-shrink-0 ${isActive ? 'text-zinc-300' : 'text-zinc-600 group-hover:text-zinc-500'}`} strokeWidth={1.6} />
              {item.label}
            </NavLink>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="px-2.5 py-3 border-t border-zinc-800/30">
        <button
          type="button"
          onClick={handleLogout}
          className="flex items-center gap-2.5 w-full rounded-md px-2.5 py-[6px] text-[13px] text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/30 transition-colors duration-100"
        >
          <LogOut className="h-4 w-4" strokeWidth={1.6} />
          Log out
        </button>
      </div>
    </aside>
  )
}
