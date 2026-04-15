import type { LucideIcon } from 'lucide-react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { LogOut, Settings, ChevronDown } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'
import { Logo } from './ui'
import Avatar from './Avatar'
import { invalidateMeCache } from '../hooks/useMe'
import { disconnectSharedChannelSocket } from '../api/channelSocket'

export type NavItem = {
  to: string
  icon: LucideIcon
  label: string
  badge?: number
  onSeen?: () => void
}

export type NavGroup = {
  label: string
  items: NavItem[]
}

type SidebarShellProps = {
  logoTo: string
  logoLabel: string
  nav: (NavItem | NavGroup)[]
  user?: { name: string; avatarUrl?: string | null; settingsTo?: string }
}

function isGroup(item: NavItem | NavGroup): item is NavGroup {
  return 'items' in item
}

function NavItemLink({ item, location }: { item: NavItem; location: ReturnType<typeof useLocation> }) {
  const isExact = item.to === '/app' || item.to === '/admin' || item.to === '/broker'
  const isActive = isExact
    ? location.pathname === item.to
    : location.pathname.startsWith(item.to)

  const seenRef = useRef(false)
  const onSeenRef = useRef(item.onSeen)
  onSeenRef.current = item.onSeen
  useEffect(() => {
    if (isActive && item.badge && item.badge > 0 && !seenRef.current) {
      seenRef.current = true
      onSeenRef.current?.()
    }
    if (!isActive) seenRef.current = false
  }, [isActive, item.badge])

  return (
    <NavLink
      to={item.to}
      className={
        `group relative flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[13px] transition-colors duration-100 ${
          isActive
            ? 'bg-zinc-800/60 text-zinc-100 font-medium'
            : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30 font-normal'
        }`
      }
    >
      <item.icon className={`h-4 w-4 flex-shrink-0 ${isActive ? 'text-white' : 'text-zinc-50 group-hover:text-white'}`} strokeWidth={1.6} />
      <span className="flex-1">{item.label}</span>
      {!!item.badge && item.badge > 0 && (
        <span className="ml-auto min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-vsc-accent/20 border border-vsc-accent/30 text-[10px] font-semibold text-vsc-accent/80 px-1 leading-none">
          +{item.badge > 99 ? '99' : item.badge}
        </span>
      )}
    </NavLink>
  )
}

function NavGroupSection({ group, location }: { group: NavGroup; location: ReturnType<typeof useLocation> }) {
  const hasActiveChild = group.items.some((item) => {
    const isExact = item.to === '/app' || item.to === '/admin' || item.to === '/broker'
    return isExact ? location.pathname === item.to : location.pathname.startsWith(item.to)
  })
  const [open, setOpen] = useState(hasActiveChild)

  // Auto-expand when navigating to a child (e.g. via URL)
  useEffect(() => {
    if (hasActiveChild) setOpen(true)
  }, [hasActiveChild])

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center justify-between w-full px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-zinc-500 hover:text-zinc-400 transition-colors"
      >
        {group.label}
        <ChevronDown className={`h-3 w-3 transition-transform duration-150 ${open ? '' : '-rotate-90'}`} strokeWidth={2} />
      </button>
      {open && (
        <div className="space-y-0.5 mt-0.5">
          {group.items.map((item) => (
            <NavItemLink key={item.to} item={item} location={location} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function SidebarShell({ logoTo, logoLabel, nav, user }: SidebarShellProps) {
  const navigate = useNavigate()
  const location = useLocation()

  function handleLogout() {
    localStorage.removeItem('matcha_access_token')
    localStorage.removeItem('matcha_refresh_token')
    // Drop cached /auth/me so the next user's data is fetched fresh
    // (client-side navigation keeps module state alive otherwise).
    invalidateMeCache()
    // Tear down the shared channel WebSocket so the next user gets a fresh
    // connection authenticated with their token.
    disconnectSharedChannelSocket()
    navigate('/login')
  }

  return (
    <aside className="h-full w-full bg-[#2d2d30] border-r border-vsc-border/30 flex flex-col">
      {/* Logo area */}
      <div className="px-4 pt-5 pb-4">
        <Logo to={logoTo} label={logoLabel} />
      </div>

      {/* Divider */}
      <div className="mx-4 border-t border-zinc-800/40" />

      {/* Navigation */}
      <nav className="flex-1 px-2.5 pt-3 space-y-1 overflow-y-auto">
        {nav.map((item) =>
          isGroup(item) ? (
            <NavGroupSection key={item.label} group={item} location={location} />
          ) : (
            <NavItemLink key={item.to} item={item} location={location} />
          )
        )}
      </nav>

      {/* Footer */}
      <div className="px-2.5 py-3 border-t border-zinc-800/30 space-y-1">
        {user && (
          <div className="flex items-center gap-2.5 px-2.5 py-1.5">
            <Avatar name={user.name} avatarUrl={user.avatarUrl} size="sm" />
            <span className="text-[13px] text-zinc-300 truncate flex-1">{user.name}</span>
            {user.settingsTo && (
              <NavLink
                to={user.settingsTo}
                className="text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                <Settings className="h-3.5 w-3.5" strokeWidth={1.6} />
              </NavLink>
            )}
          </div>
        )}
        <button
          type="button"
          onClick={handleLogout}
          className="flex items-center gap-2.5 w-full rounded-md px-2.5 py-[7px] text-[13px] text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/30 transition-colors duration-100 group"
        >
          <LogOut className="h-4 w-4 text-zinc-500 group-hover:text-zinc-200" strokeWidth={1.6} />
          Log out
        </button>
      </div>
    </aside>
  )
}
