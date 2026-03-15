import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Building2,
  Users,
  Shield,
  FileText,
  Settings,
} from 'lucide-react'
import { Logo } from './ui'

const nav = [
  { to: '/admin', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/admin/companies', icon: Building2, label: 'Companies' },
  { to: '/admin/users', icon: Users, label: 'Users' },
  { to: '/admin/compliance', icon: Shield, label: 'Compliance' },
  { to: '/admin/policies', icon: FileText, label: 'Policies' },
  { to: '/admin/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 w-56 bg-zinc-950 border-r border-zinc-800 flex flex-col">
      <div className="px-5 py-5">
        <Logo to="/admin" label="Matcha Admin" />
      </div>

      <nav className="flex-1 px-3 py-2 space-y-0.5">
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/admin'}
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

      <div className="px-5 py-4 border-t border-zinc-800">
        <p className="text-xs text-zinc-500 truncate">admin@matcha.com</p>
      </div>
    </aside>
  )
}
