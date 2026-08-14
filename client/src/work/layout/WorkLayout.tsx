import { Link, Navigate, Outlet, useLocation } from 'react-router-dom'
import { ArrowLeft, Zap, Menu, X } from 'lucide-react'
import { usePresenceHeartbeat } from '../hooks/usePresenceHeartbeat'
import { useChannelNotifications } from '../hooks/useChannelNotifications'
import { OnlineUsersPanel } from '../components/shell/OnlineUsersPanel'
import NotificationBell from '../components/shell/NotificationBell'
import NotificationSettingsMenu from '../components/shell/NotificationSettingsMenu'
import WorkSidebar from '../components/shell/WorkSidebar'
import WerkLiteSidebar from '../components/shell/WerkLiteSidebar'
import OpsSidebar from '../../ops/components/OpsSidebar'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useMe } from '../../hooks/useMe'
import { api } from '../../api/client'
import { fetchUsageMeter, USAGE_CHANGED_EVENT, type UsageMeter } from '../api/matchaWork'
import { useWorkSurface, useWorkBrand, useWorkBase } from '../routes/WorkSurfaceContext'

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`
  return String(n)
}

// /matcha-work/usage/meter nulls company_budget for admin callers server-
// side (workspace.py:_build_usage_meter) rather than sending a sentinel —
// an admin's company_id is an arbitrary resolved tenant, not one they
// should see a budget/Upgrade button for. The old /billing/balance sentinel
// path (>= 999_999_000 remaining) is kept as a belt-and-suspenders guard
// in case any other caller of company_budget still sends one.
const ADMIN_SENTINEL = 999_999_000
// Floor between refetches triggered by USAGE_CHANGED_EVENT — a burst of
// turn-complete events (e.g. multiple tabs) coalesces into one fetch. The
// server sends no-store (fetched event-driven specifically to snap to red
// right after a 429/402), so a request inside the floor is deferred to a
// trailing fetch rather than dropped — dropping it would leave the meter
// stale until the next unrelated event.
const REFRESH_FLOOR_MS = 5_000

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  } catch {
    return iso
  }
}

// Mounted once here in the shared Work shell, which wraps every turn-
// initiating surface (MatchaWorkThread, ProjectView, werk-lite BoardChatTab
// — see WorkRouteTree.tsx / WerkLiteRoutes.tsx) — "anywhere Huume/Gemini is
// used" is exactly this one mount point, not per-page duplication.
function TokenIndicator() {
  const [meter, setMeter] = useState<UsageMeter | null>(null)
  const [open, setOpen] = useState(false)
  const lastFetch = useRef(0)
  const trailingTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  const doFetch = useCallback(() => {
    lastFetch.current = Date.now()
    fetchUsageMeter().then(setMeter).catch(() => {})
  }, [])

  const refresh = useCallback(() => {
    const elapsed = Date.now() - lastFetch.current
    if (elapsed >= REFRESH_FLOOR_MS) {
      doFetch()
      return
    }
    if (trailingTimer.current) return
    trailingTimer.current = setTimeout(() => {
      trailingTimer.current = null
      doFetch()
    }, REFRESH_FLOOR_MS - elapsed)
  }, [doFetch])

  useEffect(() => {
    refresh()
    window.addEventListener(USAGE_CHANGED_EVENT, refresh)
    return () => {
      window.removeEventListener(USAGE_CHANGED_EVENT, refresh)
      if (trailingTimer.current) clearTimeout(trailingTimer.current)
    }
  }, [refresh])

  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  if (!meter) return null
  const { user_quota, company_budget, huume_turns } = meter
  if (!user_quota && !company_budget) return null
  if (company_budget && company_budget.total_tokens_remaining >= ADMIN_SENTINEL) return null

  // The bar reflects whichever wall is closer — a full company budget
  // doesn't hide an about-to-reset-anyway user quota, and vice versa.
  const quotaFrac = user_quota && user_quota.limit > 0 ? user_quota.remaining / user_quota.limit : 1
  const budgetLimit = company_budget
    ? company_budget.free_token_limit + company_budget.subscription_token_limit
    : 0
  // No recorded limit is not "unmetered" — a company with 0 budget rows
  // still 402s every turn (check_token_budget), so a 0-limit company must
  // read as exhausted (frac 0), not full (frac 1).
  const budgetFrac = company_budget
    ? budgetLimit > 0
      ? company_budget.total_tokens_remaining / budgetLimit
      : company_budget.total_tokens_remaining > 0 ? 1 : 0
    : 1
  const frac = Math.min(quotaFrac, budgetFrac)
  const bindingIsBudget = company_budget != null && budgetFrac <= quotaFrac

  const low = frac <= 0
  const warn = !low && frac < 0.25
  const remainingLabel = bindingIsBudget
    ? company_budget
      ? formatTokens(company_budget.total_tokens_remaining)
      : ''
    : user_quota
      ? formatTokens(user_quota.remaining)
      : ''

  const color = low ? 'text-red-400' : warn ? 'text-amber-400' : 'text-w-faint'
  const barColor = low ? 'bg-red-500' : warn ? 'bg-amber-500' : 'bg-w-accent'
  const textColor = low ? 'text-red-400' : warn ? 'text-amber-400' : 'text-w-dim'

  return (
    <div ref={ref} className="relative flex items-center gap-2 text-xs">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5"
        title="AI usage"
      >
        <Zap size={14} className={color} />
        <div className="flex items-center gap-1.5">
          <div className="hidden sm:block w-16 h-1.5 rounded-full bg-w-surface2 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${barColor}`}
              style={{ width: `${Math.min(Math.max(frac, 0), 1) * 100}%` }}
            />
          </div>
          <span className={textColor}>{remainingLabel}</span>
        </div>
      </button>

      {/* Company-budget exhaustion is a checkout moment; a per-user quota
          reset is a wait-it-out moment — never show Upgrade for the latter,
          it would send an admin to buy tokens the company already has. */}
      {low && bindingIsBudget && (
        <button
          onClick={async () => {
            try {
              const res = await api.post<{ checkout_url: string }>('/matcha-work/billing/checkout', {
                success_url: window.location.href,
                cancel_url: window.location.href,
              })
              window.location.href = res.checkout_url
            } catch {}
          }}
          className="px-2 py-0.5 rounded-md bg-w-accent text-black font-medium hover:bg-w-accent-hi transition-colors"
        >
          Upgrade
        </button>
      )}
      {low && !bindingIsBudget && user_quota && (
        <span className="text-red-400">Resets {formatTime(user_quota.resets_at)}</span>
      )}

      {open && (
        <div className="absolute right-0 top-full mt-2 w-64 rounded-lg border border-w-line bg-w-surface shadow-xl z-50 text-xs p-3 space-y-2">
          {user_quota && (
            <div>
              <div className="text-w-dim">Your AI quota ({user_quota.plan})</div>
              <div className="text-w-text font-mono">
                {formatTokens(user_quota.used)}/{formatTokens(user_quota.limit)} · resets {formatTime(user_quota.resets_at)}
              </div>
            </div>
          )}
          {company_budget && (
            <div>
              <div className="text-w-dim">Company balance</div>
              <div className="text-w-text font-mono">{formatTokens(company_budget.total_tokens_remaining)} left</div>
            </div>
          )}
          {huume_turns && (
            <div>
              <div className="text-w-dim">Huume turns this hour</div>
              <div className="text-w-text font-mono">{huume_turns.used}/{huume_turns.limit}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function WorkLayout() {
  usePresenceHeartbeat()
  useChannelNotifications()
  const { isPersonal, loading, hasFeature } = useMe()
  const { pathname, search } = useLocation()
  const surface = useWorkSurface()
  const brand = useWorkBrand()
  const base = useWorkBase()
  // Inside an open channel, offer a close (X) inline with the mobile hamburger
  // in the top bar — the channel's own header used to stack a second X-row
  // directly under the burger, which read as cramped.
  const inChannel = new RegExp(`^${base}/channels/[^/]+$`).test(pathname)
  const SidebarComp = surface === 'werk-lite' ? WerkLiteSidebar : surface === 'matcha-ops' ? OpsSidebar : WorkSidebar
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    const saved = localStorage.getItem('mw-sidebar')
    return saved !== 'closed'
  })
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false)
  }, [pathname])

  // Paint <html> in the Werk black so overscroll bounce (and the iOS keyboard
  // resize) shows app chrome instead of a flash of white.
  useEffect(() => {
    document.documentElement.setAttribute('data-app-shell-bg', 'werk')
    return () => document.documentElement.removeAttribute('data-app-shell-bg')
  }, [])

  // iOS-like keyboard behavior: pin the app to the *visual* viewport. When the
  // on-screen keyboard opens, `100vh`/`100dvh` don't shrink on iOS Safari, so
  // the browser scrolls the whole page up to reveal the focused composer —
  // dragging the header off-screen and making the layout feel like it "jumps".
  // Matching the app height to `visualViewport.height` (and undoing the page
  // scroll Safari applies) resizes the column *above* the keyboard instead, so
  // the header stays put and the composer sits flush on the keyboard.
  const [viewportHeight, setViewportHeight] = useState<number | null>(null)
  useEffect(() => {
    const vv = window.visualViewport
    if (!vv) return
    const sync = () => {
      // Pinch-zoom shrinks visualViewport.height the same way the keyboard does,
      // so pinning to it while zoomed would squash the app into the top half and
      // fight the user's panning. The keyboard case is always scale === 1; when
      // zoomed, fall back to the CSS-driven 100dvh and leave scrolling alone.
      if (Math.abs(vv.scale - 1) > 0.01) {
        setViewportHeight(null)
        return
      }
      setViewportHeight(vv.height)
      if (window.scrollY !== 0) window.scrollTo(0, 0)
    }
    sync()
    vv.addEventListener('resize', sync)
    vv.addEventListener('scroll', sync)
    return () => {
      vv.removeEventListener('resize', sync)
      vv.removeEventListener('scroll', sync)
    }
  }, [])

  function toggleSidebar() {
    setSidebarOpen((prev) => {
      const next = !prev
      localStorage.setItem('mw-sidebar', next ? 'open' : 'closed')
      return next
    })
  }

  // Identity ↔ surface alignment: personal users live under /werk, business
  // users under /work. Bounce stale/cross bookmarks, preserving subpath + query.
  // werk-lite is business-only (no personal counterpart), so it's never part of
  // the identity bounce — access is gated by the feature flag instead.
  if (!loading && surface !== 'werk-lite' && surface !== 'matcha-ops') {
    // Strip the surface prefix explicitly rather than by a fixed offset: the
    // old slice(5) silently depended on '/work' and '/werk' both being 5 chars,
    // so it would corrupt the tail the moment a base of another length is added.
    const tail = pathname.replace(/^\/(?:work|werk)(?=\/|$)/, '')
    if (surface === 'matcha-work' && isPersonal) {
      return <Navigate to={`/werk${tail}${search}`} replace />
    }
    if (surface === 'werk' && !isPersonal) {
      return <Navigate to={`/work${tail}${search}`} replace />
    }
  }

  return (
    <div
      className="bg-w-bg text-w-text flex flex-col overflow-hidden"
      style={{ height: viewportHeight ? `${viewportHeight}px` : '100dvh' }}
    >
      <header className="flex items-center gap-2 sm:gap-3 px-3 sm:px-6 py-2.5 border-b border-w-line shrink-0">
        <button
          onClick={() => setMobileMenuOpen(true)}
          className="md:hidden text-w-dim hover:text-w-text p-1 rounded-md hover:bg-w-surface2 transition-colors"
        >
          <Menu className="h-5 w-5" />
        </button>
        {inChannel && (
          <Link
            to={base}
            className="md:hidden text-w-dim hover:text-w-text p-1 rounded-md hover:bg-w-surface2 transition-colors"
            title="Close channel"
            aria-label="Close channel"
          >
            <X className="h-5 w-5" />
          </Link>
        )}
        {(surface === 'matcha-work' || surface === 'matcha-ops') && (
          <>
            <Link
              to="/app"
              className="hidden sm:flex items-center gap-1.5 text-sm text-w-dim hover:text-w-text transition-colors"
            >
              <ArrowLeft size={16} />
              Back
            </Link>
            <Link
              to="/app"
              className="sm:hidden flex items-center text-w-dim hover:text-w-text transition-colors"
            >
              <ArrowLeft size={16} />
            </Link>
            <div className="hidden sm:block h-4 w-px bg-w-line" />
            {surface === 'matcha-work' && hasFeature('matcha_ops') && (
              <>
                <Link
                  to="/ops"
                  className="hidden sm:inline text-sm text-w-dim hover:text-w-text transition-colors"
                >
                  Matcha Ops
                </Link>
                <Link
                  to="/ops"
                  className="sm:hidden text-xs text-w-dim hover:text-w-text transition-colors"
                >
                  Ops
                </Link>
              </>
            )}
          </>
        )}
        <span className="hidden sm:inline text-sm font-medium tracking-tight text-w-text">{brand}</span>

        <div className="ml-auto flex items-center gap-3 sm:gap-4">
          <TokenIndicator />
          <NotificationSettingsMenu />
          <NotificationBell />
          <OnlineUsersPanel />
        </div>
      </header>

      <div className="flex flex-1 min-h-0 relative">
        {/* Mobile Sidebar Overlay */}
        {mobileMenuOpen && (
          <div 
            className="fixed inset-0 bg-black/60 z-50 md:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />
        )}

        {/* Desktop Sidebar Container */}
        <div className="hidden md:flex shrink-0">
          <SidebarComp open={sidebarOpen} onToggle={toggleSidebar} />
        </div>

        {/* Mobile Sidebar Container */}
        <div className={`fixed inset-y-0 left-0 z-50 transform transition-transform duration-200 ease-in-out md:hidden flex ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`}>
          <div className="flex-1 w-full overflow-hidden bg-w-surface border-r border-w-line">
            {/* Mount only while the drawer is open — previously always-mounted
                (just translated off-screen), so the sidebar's own data hook
                fetched everything twice and ran two parallel inbox-poll
                intervals for the lifetime of the page. The wrapper div above
                stays mounted unconditionally so its transform transition
                still animates the slide in/out; only the (fully expanded)
                sidebar content mounts fresh each time the drawer opens. */}
            {mobileMenuOpen && <SidebarComp open={true} onToggle={() => {}} />}
          </div>
          {/* Only mount the close button while the drawer is actually open.
              It sits OUTSIDE the drawer's box (-right-12), but the drawer only
              translates by its own width — so when closed the X landed right
              back on screen, overlapping the header burger. */}
          {mobileMenuOpen && (
            <button
              onClick={() => setMobileMenuOpen(false)}
              className="absolute top-4 -right-12 text-w-dim hover:text-w-text p-2"
            >
              <X className="h-6 w-6" />
            </button>
          )}
        </div>

        <main className="flex-1 min-w-0 overflow-auto werk-radial">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
