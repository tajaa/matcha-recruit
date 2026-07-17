import type { LucideIcon } from 'lucide-react'
import { NavLink, useNavigate, useLocation, Link } from 'react-router-dom'
import { LogOut, Settings, ChevronDown, Lock, PanelLeftClose } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'
import Avatar from './Avatar'
import { useMe } from '../hooks/useMe'
import { resetAuthCaches } from '../api/authReset'
import { disconnectSharedChannelSocket } from '../api/channelSocket'
import { useLayoutContext } from '../layouts/LayoutContext'
import ThemeToggle from './ThemeToggle'

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
  /** The org this session is scoped to — set as the masthead's second line.
   *  (Personal accounts pass the person's own name; deduped against the footer
   *  identity so it isn't printed twice.) */
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

// ─────────────────────────────────────────────────────────────────────────────
// The rail reads as the index of a register, not a nav bar — this product is a
// system of record, and the pages it fronts are editorial (a light sans
// headline over a Fraunces italic line; see IRList.tsx). Three rules hold it
// together:
//
//   1. The active row is a TAB CUT INTO THE PAGE. It takes the canvas colour
//      (vsc-bg) and bleeds past the rail's right edge, so the page appears to
//      reach into the index. The rail has no right border — the colour step
//      between rail and canvas *is* the edge, which is what lets the tab punch
//      through it.
//   2. EMERALD IS DATA, NOT NAVIGATION. Selection is carried by the tab and by
//      weight, never by the accent. The accent is spent only on counts that
//      want attention, so the one green mark in the rail actually means
//      something.
//   3. TYPE CARRIES HIERARCHY. Serif masthead, spaced-caps org and group
//      labels, light sans rows that shift to normal weight when selected.
// ─────────────────────────────────────────────────────────────────────────────

const FRAUNCES = "'Fraunces', Georgia, serif"

/** Row geometry shared by every line in the index, so icons sit on one optical
 *  axis expanded or collapsed. `-mr-2.5` cancels the nav's own padding so a
 *  selected row can run all the way to the rail's edge and become a tab. */
const ROW = 'group relative flex h-[34px] items-center rounded-l-md -mr-2.5 transition-colors duration-100'
const ROW_PAD = (collapsed: boolean) => (collapsed ? 'justify-center pl-0 pr-2.5' : 'gap-3 pl-2.5 pr-3')

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
        className={`w-full text-left text-[13px] font-light text-zinc-600 hover:bg-zinc-900 hover:text-zinc-400 ${ROW} ${ROW_PAD(collapsed)}`}
      >
        <item.icon className="h-[15px] w-[15px] shrink-0" strokeWidth={1.5} />
        {!collapsed && (
          <>
            <span className="flex-1 truncate">{item.label}</span>
            <Lock className="h-3 w-3 shrink-0 text-zinc-700 group-hover:text-emerald-400" strokeWidth={1.6} />
          </>
        )}
      </button>
    )
  }

  return (
    <NavLink
      to={item.to}
      title={collapsed ? item.label : undefined}
      className={`text-[13px] ${ROW} ${ROW_PAD(collapsed)} ${
        isActive
          // The tab: canvas colour, running off the rail's right edge.
          ? 'bg-vsc-bg font-normal text-zinc-50'
          : 'font-light text-zinc-500 hover:bg-zinc-900 hover:text-zinc-200'
      }`}
    >
      <item.icon
        className={`h-[15px] w-[15px] shrink-0 ${isActive ? 'text-zinc-300' : 'text-zinc-600 group-hover:text-zinc-400'}`}
        strokeWidth={1.5}
      />
      {!collapsed && (
        <>
          <span className="flex-1 truncate">{item.label}</span>
          {item.tag && (
            <span className="shrink-0 text-[8.5px] font-medium uppercase tracking-[0.14em] text-amber-500/80">
              {item.tag}
            </span>
          )}
          {!!item.badge && item.badge > 0 && (
            <span className="shrink-0 font-mono text-[10px] leading-none text-emerald-400">
              {item.badge > 99 ? '99+' : item.badge}
            </span>
          )}
        </>
      )}
      {collapsed && !!item.badge && item.badge > 0 && (
        <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-emerald-400" />
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

  // Collapsed rail has no room for labels; a hairline keeps the grouping as
  // rhythm rather than dropping it.
  if (collapsed) {
    return (
      <div className="space-y-px border-t border-zinc-900 py-2 first:border-t-0 first:pt-0">
        {group.items.map((item) => (
          <NavItemLink key={item.to} item={item} location={location} collapsed={collapsed} />
        ))}
      </div>
    )
  }

  return (
    <div className="mt-5 first:mt-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="group mb-1 flex w-full items-center gap-1.5 pl-2.5 pr-3 text-[9px] font-medium uppercase tracking-[0.2em] text-zinc-600 transition-colors hover:text-zinc-400"
      >
        <span className="truncate">{group.label}</span>
        <span className="h-px flex-1 bg-zinc-900" />
        <ChevronDown
          className={`h-2.5 w-2.5 shrink-0 transition-all duration-150 ${open ? 'opacity-0 group-hover:opacity-100' : '-rotate-90 opacity-100'}`}
          strokeWidth={2}
        />
      </button>
      {open && (
        <div className="space-y-px">
          {group.items.map((item) => (
            <NavItemLink key={item.to} item={item} location={location} collapsed={collapsed} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function SidebarShell({ logoTo, logoLabel, nav, user, upgradeFooter, footerSlot = <ThemeToggle /> }: SidebarShellProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { sidebarCollapsed, setSidebarCollapsed } = useLayoutContext()
  const { hasFeature, me } = useMe()

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

  // Who is signed in, as distinct from which org the session is scoped to. The
  // old top bar showed the person and the rail showed the org; with the bar
  // gone the rail carries both — org in the masthead, person in the footer.
  const personName = me?.profile?.name || me?.user?.email || ''
  const orgName = user?.name
  const showOrg = !!orgName && orgName !== personName

  return (
    <aside className="flex h-full w-full flex-col overflow-hidden bg-zinc-950">
      {/* Masthead — serif wordmark over spaced-caps org, the same editorial
          voice the pages themselves use. */}
      <div className={`group flex h-16 shrink-0 items-center ${sidebarCollapsed ? 'justify-center px-2' : 'gap-2.5 pl-4 pr-2.5'}`}>
        {sidebarCollapsed ? (
          // The mark doubles as the expander: a 56px rail has no room for both,
          // and an expand control is worth more here than a home link.
          <button
            type="button"
            onClick={() => setSidebarCollapsed(false)}
            title="Expand sidebar"
            aria-label="Expand sidebar"
            className="rounded-md p-1.5 transition-opacity hover:opacity-70"
          >
            <img src="/logo.svg" alt="" className="h-6 w-6" />
          </button>
        ) : (
          <>
            <Link to={logoTo} className="flex min-w-0 flex-1 flex-col justify-center" title={logoLabel}>
              <span
                className="truncate text-[17px] font-light leading-none tracking-tight text-zinc-100"
                style={{ fontFamily: FRAUNCES }}
              >
                {logoLabel}
              </span>
              {showOrg && (
                <span className="mt-1.5 truncate text-[9px] font-medium uppercase leading-none tracking-[0.22em] text-zinc-600">
                  {orgName}
                </span>
              )}
            </Link>
            <button
              type="button"
              onClick={() => setSidebarCollapsed(true)}
              title="Collapse sidebar"
              aria-label="Collapse sidebar"
              className="shrink-0 rounded-md p-1.5 text-zinc-700 opacity-0 transition-all hover:text-zinc-300 focus-visible:opacity-100 group-hover:opacity-100"
            >
              <PanelLeftClose className="h-4 w-4" strokeWidth={1.5} />
            </button>
          </>
        )}
      </div>

      {/* Index */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden pb-3 pl-2.5 pr-2.5 pt-1">
        {visibleNav.map((item) =>
          isGroup(item) ? (
            <NavGroupSection key={item.label} group={item} location={location} collapsed={sidebarCollapsed} />
          ) : (
            <NavItemLink key={item.to} item={item} location={location} collapsed={sidebarCollapsed} />
          )
        )}
      </nav>

      {upgradeFooter && !sidebarCollapsed && <div className="px-2.5 pb-2 pt-3">{upgradeFooter}</div>}

      {/* Colophon — who's signed in, plus session controls. */}
      <div className="shrink-0 border-t border-zinc-900 px-2.5 py-2.5">
        {personName && !sidebarCollapsed && (
          <div className="flex items-center gap-2.5 px-1 pb-2">
            <Avatar name={personName} avatarUrl={me?.user?.avatar_url} size="sm" />
            <span className="min-w-0 flex-1 truncate text-[12px] font-light tracking-wide text-zinc-400">
              {personName}
            </span>
          </div>
        )}
        {personName && sidebarCollapsed && (
          <div className="flex justify-center pb-2" title={personName}>
            <Avatar name={personName} avatarUrl={me?.user?.avatar_url} size="sm" />
          </div>
        )}

        <div className={`flex items-center ${sidebarCollapsed ? 'flex-col gap-1' : 'gap-0.5'}`}>
          {footerSlot}
          {user?.settingsTo && (
            <NavLink
              to={user.settingsTo}
              title="Settings"
              aria-label="Settings"
              className="rounded-md p-1.5 text-zinc-700 transition-colors hover:text-zinc-300"
            >
              <Settings className="h-4 w-4" strokeWidth={1.5} />
            </NavLink>
          )}
          <button
            type="button"
            onClick={handleLogout}
            title="Log out"
            aria-label="Log out"
            className="rounded-md p-1.5 text-zinc-700 transition-colors hover:text-zinc-300"
          >
            <LogOut className="h-4 w-4" strokeWidth={1.5} />
          </button>
        </div>
      </div>
    </aside>
  )
}
