import type { LucideIcon } from 'lucide-react'
import { NavLink, useNavigate } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import { Logo, Button } from './ui'

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

  function handleLogout() {
    localStorage.removeItem('matcha_access_token')
    localStorage.removeItem('matcha_refresh_token')
    navigate('/login')
  }

  return (
    <aside className="fixed inset-y-0 left-0 w-56 bg-zinc-950 border-r border-zinc-800 flex flex-col">
      <div className="px-5 py-5">
        <Logo to={logoTo} label={logoLabel} />
      </div>

      <nav className="flex-1 px-3 py-2 space-y-0.5">
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                isActive
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
              }`
            }
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="px-3 py-4 border-t border-zinc-800">
        <Button variant="ghost" size="sm" className="w-full justify-start gap-3" onClick={handleLogout}>
          <LogOut className="h-4 w-4" />
          Log out
        </Button>
      </div>
    </aside>
  )
}
