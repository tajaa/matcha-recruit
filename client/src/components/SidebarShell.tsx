import type { LucideIcon } from 'lucide-react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { LogOut, Settings, ChevronDown, Lock } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'
import { Logo } from './ui'
import Avatar from './Avatar'
import { useMe } from '../hooks/useMe'
import { resetAuthCaches } from '../api/authReset'
import { disconnectSharedChannelSocket } from '../api/channelSocket'
import { useLayoutContext } from '../layouts/LayoutContext'

export type NavItem = {
  to: string
  icon: LucideIcon
  label: string
  badge?: number
  onSeen?: () => void
  /** Small text chip after the label (e.g. "Pro" on an upsell / teaser entry). */
  tag?: string
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
  /** Start expanded even without an active child (default false). */
  defaultOpen?: boolean
}

type SidebarShellProps = {
  logoTo: string
  logoLabel: string
  nav: (NavItem | NavGroup)[]
  user?: { name: string; avatarUrl?: string | null; settingsTo?: string }
  /** Renders above the user/logout footer — e.g. an upgrade panel. */
  upgradeFooter?: React.ReactNode
  /** Small accessory rendered in the footer next to logout (both collapsed +
   *  expanded) — e.g. a theme toggle. */
  footerSlot?: React.ReactNode
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
        className={`group flex items-center py-1.5 text-[12px] w-full text-zinc-700 hover:text-zinc-500 transition-colors cursor-pointer ${collapsed ? 'justify-center px-0' : 'gap-2.5 pl-3 pr-2 text-left'}`}
      >
        <item.icon className="h-[14px] w-[14px] flex-shrink-0" strokeWidth={1.4} />
        {!collapsed && <><span className="flex-1 tracking-wide font-light">{item.label}</span><Lock className="h-3 w-3 text-zinc-700 group-hover:text-emerald-400 flex-shrink-0" strokeWidth={1.6} /></>}
      </button>
    )
  }

  return (
    <NavLink
      to={item.to}
      title={collapsed ? item.label : undefined}
      className={`group relative flex items-center py-2 text-[12px] transition-colors duration-100 ${collapsed ? 'justify-center px-0' : 'gap-2.5 pl-3 pr-2'} ${
        isActive
          ? 'text-zinc-50 font-normal'
          : 'text-zinc-500 hover:text-zinc-200 font-light'
      }`}
    >
      {/* Subtle accent strip on active */}
      {isActive && !collapsed && (
        <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 bg-emerald-400 rounded-r" />
      )}
      <item.icon
        className={`h-[14px] w-[14px] flex-shrink-0 ${isActive ? 'text-zinc-100' : 'text-zinc-600 group-hover:text-zinc-300'}`}
        strokeWidth={1.4}
      />
      {!collapsed && (
        <>
          <span className="flex-1 tracking-wide">{item.label}</span>
          {item.tag && (
            <span className="text-[8.5px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/20 leading-none">
              {item.tag}
            </span>
          )}
          {!!item.badge && item.badge > 0 && (
            <span className="min-w-[18px] h-[16px] flex items-center justify-center rounded bg-emerald-500/10 text-[9px] font-mono text-emerald-400 px-1.5 leading-none">
              {item.badge > 99 ? '99+' : item.badge}
            </span>
          )}
        </>
      )}
      {collapsed && !!item.badge && item.badge > 0 && (
        <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-emerald-400" />
      )}
    </NavLink>
  )
}

function NavGroupSection({ group, location, collapsed }: { group: NavGroup; location: ReturnType<typeof useLocation>; collapsed: boolean }) {
  const hasActiveChild = group.items.some((item) => {
    const isExact = item.to === '/app' || item.to === '/admin' || item.to === '/broker'
    return isExact ? location.pathname === item.to : location.pathname.startsWith(item.to)
  })
  const [open, setOpen] = useState(group.defaultOpen || hasActiveChild)

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
    <div className="mt-3 first:mt-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center justify-between w-full px-3 pt-2 pb-1 text-[9px] font-light uppercase tracking-[0.18em] text-zinc-700 hover:text-zinc-500 transition-colors"
      >
        {group.label}
        <ChevronDown className={`h-2.5 w-2.5 transition-transform duration-150 ${open ? '' : '-rotate-90'}`} strokeWidth={1.6} />
      </button>
      {open && (
        <div className="space-y-1">
          {group.items.map((item) => (
            <NavItemLink key={item.to} item={item} location={location} collapsed={collapsed} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function SidebarShell({ logoTo, logoLabel, nav, user, upgradeFooter, footerSlot }: SidebarShellProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { hasTopNav, sidebarCollapsed } = useLayoutContext()
  const { hasFeature } = useMe()

  // Enforce the `feature` contract declared on NavItem/NavGroup for every
  // sidebar that renders through this shell. Locked upsell entries carry no
  // `feature` key, so they survive the filter and render their lock UI.
  const visibleNav = nav.reduce<(NavItem | NavGroup)[]>((out, item) => {
    if (isGroup(item)) {
      if (item.feature && !hasFeature(item.feature)) return out
      const items = item.items.filter((child) => !child.feature || hasFeature(child.feature))
      if (items.length > 0) out.push({ ...item, items })
    } else if (!item.feature || hasFeature(item.feature)) {
      out.push(item)
    }
    return out
  }, [])

  function handleLogout() {
    localStorage.removeItem('matcha_access_token')
    localStorage.removeItem('matcha_refresh_token')
    // Clears useMe, pinned resources, and every other registered per-user
    // module cache — this SPA-navigate logout doesn't reload the page, so
    // caches would otherwise survive into the next user's session.
    resetAuthCaches()
    disconnectSharedChannelSocket()
    navigate('/login')
  }

  const navPx = sidebarCollapsed ? 'px-1' : 'px-2.5'

  return (
    <aside className="h-full w-full bg-zinc-950 border-r border-white/5 flex flex-col overflow-hidden">
      {/* Logo area — hidden when AppLayout's top navbar is present */}
      {!hasTopNav && (
        <div className="h-14 flex items-center justify-center px-4 bg-zinc-950">
          <Logo to={logoTo} label={logoLabel} />
        </div>
      )}

      {/* Navigation */}
      <nav className={`flex-1 ${navPx} pt-2 space-y-1 overflow-y-auto overflow-x-hidden`}>
        {visibleNav.map((item) =>
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
      <div className={`${navPx} py-3 border-t border-white/[0.04] space-y-1 bg-zinc-950`}>
        {footerSlot}
        {user && !sidebarCollapsed && (
          <div className="flex items-center gap-2.5 px-3 py-2">
            <Avatar name={user.name} avatarUrl={user.avatarUrl} size="sm" />
            <span className="text-[12px] text-zinc-300 truncate flex-1 font-light tracking-wide">{user.name}</span>
            {user.settingsTo && (
              <NavLink to={user.settingsTo} className="text-zinc-600 hover:text-zinc-200 transition-colors">
                <Settings className="h-3.5 w-3.5" strokeWidth={1.4} />
              </NavLink>
            )}
          </div>
        )}
        {user && sidebarCollapsed && user.settingsTo && (
          <NavLink
            to={user.settingsTo}
            title="Settings"
            className="flex justify-center w-full py-2 text-zinc-600 hover:text-zinc-300 transition-colors"
          >
            <Settings className="h-[14px] w-[14px]" strokeWidth={1.4} />
          </NavLink>
        )}
        <button
          type="button"
          onClick={handleLogout}
          title="Log out"
          className={`flex items-center w-full py-1.5 text-[12px] text-zinc-600 hover:text-zinc-200 transition-colors duration-100 group ${sidebarCollapsed ? 'justify-center px-0' : 'gap-2.5 px-3'}`}
        >
          <LogOut className="h-[14px] w-[14px] text-zinc-600 group-hover:text-zinc-300" strokeWidth={1.4} />
          {!sidebarCollapsed && <span className="font-light tracking-wide">Log out</span>}
        </button>
      </div>
    </aside>
  )
}
