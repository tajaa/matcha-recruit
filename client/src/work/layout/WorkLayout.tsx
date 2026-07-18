import { Link, Navigate, Outlet, useLocation } from 'react-router-dom'
import { ArrowLeft, Zap, Menu, X } from 'lucide-react'
import { usePresenceHeartbeat } from '../hooks/usePresenceHeartbeat'
import { useChannelNotifications } from '../hooks/useChannelNotifications'
import { OnlineUsersPanel } from '../components/shell/OnlineUsersPanel'
import NotificationBell from '../components/shell/NotificationBell'
import NotificationSettingsMenu from '../components/shell/NotificationSettingsMenu'
import WorkSidebar from '../components/shell/WorkSidebar'
import WerkLiteSidebar from '../components/shell/WerkLiteSidebar'
import { useEffect, useState } from 'react'
import { useMe } from '../../hooks/useMe'
import { api } from '../../api/client'
import { useWorkSurface, useWorkBrand, useWorkBase } from '../routes/WorkSurfaceContext'

interface TokenBudget {
  free_tokens_used: number
  free_token_limit: number
  free_tokens_remaining: number
  subscription_tokens_used: number
  subscription_token_limit: number
  subscription_tokens_remaining: number
  total_tokens_remaining: number
  has_active_subscription: boolean
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`
  return String(n)
}

function TokenIndicator() {
  const [budget, setBudget] = useState<TokenBudget | null>(null)

  useEffect(() => {
    api.get<TokenBudget>('/matcha-work/billing/balance')
      .then(setBudget)
      .catch(() => {})
  }, [])

  if (!budget) return null

  const { has_active_subscription, total_tokens_remaining } = budget
  const used = has_active_subscription ? budget.subscription_tokens_used : budget.free_tokens_used
  const limit = has_active_subscription ? budget.subscription_token_limit : budget.free_token_limit
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 100
  const low = total_tokens_remaining <= 0
  const warn = !low && pct > 90

  if (total_tokens_remaining >= 999_999_000) return null // admin sentinel

  return (
    <div className="flex items-center gap-2 text-xs">
      <Zap size={14} className={low ? 'text-red-400' : warn ? 'text-amber-400' : 'text-w-faint'} />
      <div className="flex items-center gap-1.5">
        <div className="hidden sm:block w-16 h-1.5 rounded-full bg-w-surface2 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${low ? 'bg-red-500' : warn ? 'bg-amber-500' : 'bg-w-accent'}`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
        <span className={low ? 'text-red-400' : warn ? 'text-amber-400' : 'text-w-dim'}>
          {formatTokens(total_tokens_remaining)}
        </span>
      </div>
      {low && (
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
          className="ml-1 px-2 py-0.5 rounded-md bg-w-accent text-black font-medium hover:bg-w-accent-hi transition-colors"
        >
          Upgrade
        </button>
      )}
    </div>
  )
}

export default function WorkLayout() {
  usePresenceHeartbeat()
  useChannelNotifications()
  const { isPersonal, loading } = useMe()
  const { pathname, search } = useLocation()
  const surface = useWorkSurface()
  const brand = useWorkBrand()
  const base = useWorkBase()
  // Inside an open channel, offer a close (X) inline with the mobile hamburger
  // in the top bar — the channel's own header used to stack a second X-row
  // directly under the burger, which read as cramped.
  const inChannel = new RegExp(`^${base}/channels/[^/]+$`).test(pathname)
  const SidebarComp = surface === 'werk-lite' ? WerkLiteSidebar : WorkSidebar
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
  // users under /work. Bounce stale/cross bookmarks, preserving subpath + query
  // ('/work' and '/werk' are both 5 chars, so slice(5) yields the shared tail).
  // werk-lite is business-only (no personal counterpart), so it's never part of
  // the identity bounce — access is gated by the feature flag instead. The
  // slice(5) tail trick also only holds for the 5-char /work + /werk bases.
  if (!loading && surface !== 'werk-lite') {
    if (surface === 'matcha-work' && isPersonal) {
      return <Navigate to={`/werk${pathname.slice(5)}${search}`} replace />
    }
    if (surface === 'werk' && !isPersonal) {
      return <Navigate to={`/work${pathname.slice(5)}${search}`} replace />
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
        {surface === 'matcha-work' && (
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
            {/* Always pass open=true to the sidebar on mobile so it's fully expanded */}
            <SidebarComp open={true} onToggle={() => {}} />
          </div>
          <button
            onClick={() => setMobileMenuOpen(false)}
            className="absolute top-4 -right-12 text-w-dim hover:text-w-text p-2"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        <main className="flex-1 min-w-0 overflow-auto werk-radial">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
