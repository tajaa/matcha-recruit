import type { LucideIcon } from 'lucide-react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { LogOut, Settings, ChevronDown, Lock } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'
import { Logo } from './ui'
import Avatar from './Avatar'
import { invalidateMeCache } from '../hooks/useMe'
import { disconnectSharedChannelSocket } from '../api/channelSocket'
import { useLayoutContext } from '../layouts/LayoutContext'

export type NavItem = {
  to: string
  icon: LucideIcon
  label: string
  badge?: number
  onSeen?: () => void
  /** Optional company feature flag — item is hidden when the flag is false. */
  feature?: string
  /** Renders the item grayed out with a lock icon. Click fires `onLockedClick`
   *  instead of navigating. Used for upgrade-gated tabs (e.g. IR for free tier). */
  locked?: boolean
  onLockedClick?: () => void
}

export type NavGroup = {
  label: string
  items: NavItem[]
  /** Optional company feature flag — group is hidden when the flag is false. */
  feature?: string
}

type SidebarShellProps = {
  logoTo: string
  logoLabel: string
  nav: (NavItem | NavGroup)[]
  user?: { name: string; avatarUrl?: string | null; settingsTo?: string }
  /** Renders above the user/logout footer — e.g. an upgrade panel. */
  upgradeFooter?: React.ReactNode
}

function isGroup(item: NavItem | NavGroup): item is NavGroup {
  return 'items' in item
}

function NavItemLink({ item, location, collapsed }: { item: NavItem; location: ReturnType<typeof useLocation>; collapsed: boolean }) {
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

  if (item.locked) {
    return (
      <button
        type="button"
        onClick={item.onLockedClick}
        title={item.label}
        className={`group relative flex items-center rounded-md py-[7px] text-[13px] w-full text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/20 transition-colors duration-100 cursor-pointer ${collapsed ? 'justify-center px-0' : 'gap-2.5 px-2.5 text-left'}`}
      >
        <item.icon className="h-4 w-4 flex-shrink-0 text-zinc-500 group-hover:text-zinc-300" strokeWidth={1.6} />
        {!collapsed && <><span className="flex-1">{item.label}</span><Lock className="h-3 w-3 text-zinc-600 group-hover:text-emerald-400 flex-shrink-0" strokeWidth={2} /></>}
      </button>
    )
  }

  return (
    <NavLink
      to={item.to}
      title={collapsed ? item.label : undefined}
      className={`group relative flex items-center rounded-md py-[7px] text-[13px] transition-colors duration-100 ${collapsed ? 'justify-center px-0' : 'gap-2.5 px-2.5'} ${
        isActive ? 'bg-zinc-800/60 text-zinc-100 font-medium' : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30 font-normal'
      }`}
    >
      <item.icon className={`h-4 w-4 flex-shrink-0 ${isActive ? 'text-white' : 'text-zinc-50 group-hover:text-white'}`} strokeWidth={1.6} />
      {!collapsed && (
        <>
          <span className="flex-1">{item.label}</span>
          {!!item.badge && item.badge > 0 && (
            <span className="ml-auto min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-vsc-accent/20 border border-vsc-accent/30 text-[10px] font-semibold text-vsc-accent/80 px-1 leading-none">
              +{item.badge > 99 ? '99' : item.badge}
            </span>
          )}
        </>
      )}
      {collapsed && !!item.badge && item.badge > 0 && (
        <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-vsc-accent" />
      )}
    </NavLink>
  )
}

function NavGroupSection({ group, location, collapsed }: { group: NavGroup; location: ReturnType<typeof useLocation>; collapsed: boolean }) {
  const hasActiveChild = group.items.some((item) => {
    const isExact = item.to === '/app' || item.to === '/admin' || item.to === '/broker'
    return isExact ? location.pathname === item.to : location.pathname.startsWith(item.to)
  })
  const [open, setOpen] = useState(hasActiveChild)

  useEffect(() => {
    if (hasActiveChild) setOpen(true)
  }, [hasActiveChild])

  if (collapsed) {
    return (
      <div className="space-y-0.5">
        {group.items.map((item) => (
          <NavItemLink key={item.to} item={item} location={location} collapsed={collapsed} />
        ))}
      </div>
    )
  }

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
            <NavItemLink key={item.to} item={item} location={location} collapsed={collapsed} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function SidebarShell({ logoTo, logoLabel, nav, user, upgradeFooter }: SidebarShellProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { hasTopNav, sidebarCollapsed } = useLayoutContext()

  function handleLogout() {
    localStorage.removeItem('matcha_access_token')
    localStorage.removeItem('matcha_refresh_token')
    invalidateMeCache()
    disconnectSharedChannelSocket()
    navigate('/login')
  }

  const navPx = sidebarCollapsed ? 'px-1' : 'px-2.5'

  return (
    <aside className="h-full w-full bg-[#2d2d30] border-r border-vsc-border/30 flex flex-col overflow-hidden">
      {/* Logo area — hidden when AppLayout's top navbar is present */}
      {!hasTopNav && (
        <div className="h-14 flex items-center justify-center border-b border-vsc-border/30 px-4">
          <Logo to={logoTo} label={logoLabel} />
        </div>
      )}

      {/* Navigation */}
      <nav className={`flex-1 ${navPx} pt-3 space-y-1 overflow-y-auto overflow-x-hidden`}>
        {nav.map((item) =>
          isGroup(item) ? (
            <NavGroupSection key={item.label} group={item} location={location} collapsed={sidebarCollapsed} />
          ) : (
            <NavItemLink key={item.to} item={item} location={location} collapsed={sidebarCollapsed} />
          )
        )}
      </nav>

      {upgradeFooter && !sidebarCollapsed && (
        <div className="px-2.5 pt-3 pb-2">{upgradeFooter}</div>
      )}

      {/* Footer */}
      <div className={`${navPx} py-3 border-t border-zinc-800/30 space-y-1`}>
        {user && !sidebarCollapsed && (
          <div className="flex items-center gap-2.5 px-2.5 py-1.5">
            <Avatar name={user.name} avatarUrl={user.avatarUrl} size="sm" />
            <span className="text-[13px] text-zinc-300 truncate flex-1">{user.name}</span>
            {user.settingsTo && (
              <NavLink to={user.settingsTo} className="text-zinc-500 hover:text-zinc-300 transition-colors">
                <Settings className="h-3.5 w-3.5" strokeWidth={1.6} />
              </NavLink>
            )}
          </div>
        )}
        {user && sidebarCollapsed && user.settingsTo && (
          <NavLink
            to={user.settingsTo}
            title="Settings"
            className="flex justify-center w-full rounded-md py-[7px] text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/30 transition-colors"
          >
            <Settings className="h-4 w-4" strokeWidth={1.6} />
          </NavLink>
        )}
        <button
          type="button"
          onClick={handleLogout}
          title="Log out"
          className={`flex items-center w-full rounded-md py-[7px] text-[13px] text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/30 transition-colors duration-100 group ${sidebarCollapsed ? 'justify-center px-0' : 'gap-2.5 px-2.5'}`}
        >
          <LogOut className="h-4 w-4 text-zinc-500 group-hover:text-zinc-200" strokeWidth={1.6} />
          {!sidebarCollapsed && 'Log out'}
        </button>
      </div>
    </aside>
  )
}
