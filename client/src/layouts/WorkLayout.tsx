import { Link, Outlet, useLocation } from 'react-router-dom'
import { ArrowLeft, Zap, Menu, X } from 'lucide-react'
import { usePresenceHeartbeat } from '../hooks/usePresenceHeartbeat'
import { OnlineUsersPanel } from '../components/work/OnlineUsersPanel'
import NotificationBell from '../components/work/NotificationBell'
import WorkSidebar from '../components/work/WorkSidebar'
import { useEffect, useState } from 'react'
import { useMe } from '../hooks/useMe'
import { api } from '../api/client'

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
      <Zap size={14} className={low ? 'text-red-400' : warn ? 'text-amber-400' : 'text-zinc-500'} />
      <div className="flex items-center gap-1.5">
        <div className="hidden sm:block w-16 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${low ? 'bg-red-500' : warn ? 'bg-amber-500' : 'bg-emerald-500'}`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
        <span className={low ? 'text-red-400' : warn ? 'text-amber-400' : 'text-zinc-500'}>
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
          className="ml-1 px-2 py-0.5 rounded bg-emerald-600 text-white hover:bg-emerald-500 transition-colors"
        >
          Upgrade
        </button>
      )}
    </div>
  )
}

export default function WorkLayout() {
  usePresenceHeartbeat()
  const { isPersonal } = useMe()
  const { pathname } = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    const saved = localStorage.getItem('mw-sidebar')
    return saved !== 'closed'
  })
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false)
  }, [pathname])

  function toggleSidebar() {
    setSidebarOpen((prev) => {
      const next = !prev
      localStorage.setItem('mw-sidebar', next ? 'open' : 'closed')
      return next
    })
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col">
      <header className="flex items-center gap-2 sm:gap-3 px-3 sm:px-6 py-3 border-b border-zinc-800 shrink-0">
        <button 
          onClick={() => setMobileMenuOpen(true)}
          className="md:hidden text-zinc-400 hover:text-white p-1"
        >
          <Menu className="h-5 w-5" />
        </button>
        {!isPersonal && (
          <>
            <Link
              to="/app"
              className="hidden sm:flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white transition-colors"
            >
              <ArrowLeft size={16} />
              Back
            </Link>
            <Link
              to="/app"
              className="sm:hidden flex items-center text-zinc-400 hover:text-white transition-colors"
            >
              <ArrowLeft size={16} />
            </Link>
            <div className="hidden sm:block h-4 w-px bg-zinc-700" />
          </>
        )}
        <span className="hidden sm:inline text-sm font-medium text-white">Matcha Work</span>

        <div className="ml-auto flex items-center gap-3 sm:gap-4">
          <TokenIndicator />
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
          <WorkSidebar open={sidebarOpen} onToggle={toggleSidebar} />
        </div>

        {/* Mobile Sidebar Container */}
        <div className={`fixed inset-y-0 left-0 z-50 transform transition-transform duration-200 ease-in-out md:hidden flex ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`}>
          <div className="flex-1 w-full overflow-hidden bg-[#0c0c0e]">
            {/* Always pass open=true to WorkSidebar on mobile so it's fully expanded */}
            <WorkSidebar open={true} onToggle={() => {}} />
          </div>
          <button 
            onClick={() => setMobileMenuOpen(false)}
            className="absolute top-4 -right-12 text-zinc-400 hover:text-white p-2"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        <main className="flex-1 min-w-0 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
