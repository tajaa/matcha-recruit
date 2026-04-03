import { Link, Outlet } from 'react-router-dom'
import { ArrowLeft, Mail, Zap } from 'lucide-react'
import { usePresenceHeartbeat } from '../hooks/usePresenceHeartbeat'
import { OnlineUsersPanel } from '../components/work/OnlineUsersPanel'
import { useEffect, useState } from 'react'
import { getUnreadCount } from '../api/inbox'
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
        <div className="w-16 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${low ? 'bg-red-500' : warn ? 'bg-amber-500' : 'bg-emerald-500'}`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
        <span className={low ? 'text-red-400' : warn ? 'text-amber-400' : 'text-zinc-500'}>
          {formatTokens(total_tokens_remaining)} left
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
  const [unread, setUnread] = useState(0)

  useEffect(() => {
    getUnreadCount().then((r) => setUnread(r.count)).catch(() => {})
    const id = setInterval(() => {
      getUnreadCount().then((r) => setUnread(r.count)).catch(() => {})
    }, 60_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col">
      <header className="flex items-center gap-3 px-6 py-3 border-b border-zinc-800">
        {!isPersonal && (
          <>
            <Link
              to="/app"
              className="flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white transition-colors"
            >
              <ArrowLeft size={16} />
              Back to app
            </Link>
            <div className="h-4 w-px bg-zinc-700" />
          </>
        )}
        <span className="text-sm font-medium text-white">Matcha Work</span>

        <div className="ml-auto flex items-center gap-4">
          <TokenIndicator />
          <Link
            to={isPersonal ? '/work' : '/app/inbox'}
            className="relative flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white transition-colors"
          >
            <Mail size={16} />
            <span className="hidden sm:inline">Inbox</span>
            {unread > 0 && (
              <span className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-blue-500 text-[9px] font-bold text-white flex items-center justify-center">
                {unread > 9 ? '9+' : unread}
              </span>
            )}
          </Link>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
      <OnlineUsersPanel />
    </div>
  )
}
