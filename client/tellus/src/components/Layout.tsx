import { NavLink, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { Award, Gift, LogOut, MessageSquare, Store, Tag, Trophy, Settings, ListChecks } from 'lucide-react'
import { useAccount } from '../hooks/useAccount'

const CONSUMER_NAV = [
  { to: '/', label: 'Rewards', icon: Award, end: true },
  { to: '/marketplace', label: 'Marketplace', icon: Gift },
  { to: '/redemptions', label: 'My rewards', icon: Tag },
  { to: '/leaderboard', label: 'Leaderboard', icon: Trophy },
  { to: '/settings', label: 'Settings', icon: Settings },
]

const BRAND_NAV = [
  { to: '/brand/feedback', label: 'Feedback', icon: MessageSquare, end: false },
  { to: '/brand/stores', label: 'Stores & QR', icon: Store },
  { to: '/brand/listings', label: 'Rewards', icon: ListChecks },
  { to: '/brand/settings', label: 'Settings', icon: Settings },
]

export function Layout({ children }: { children: ReactNode }) {
  const { account, logout } = useAccount()
  const navigate = useNavigate()
  const nav = account?.account_type === 'brand' ? BRAND_NAV : CONSUMER_NAV

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-tu-border bg-tu-bg/90 px-4 py-3 backdrop-blur">
        <button onClick={() => navigate('/')} className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-tu-accent text-sm font-black text-black">TU</span>
          <span className="text-sm font-bold tracking-tight">Tell-Us</span>
        </button>
        <div className="flex items-center gap-3">
          <span className="hidden text-xs text-tu-faint sm:inline">{account?.display_name || account?.email}</span>
          <button onClick={logout} className="text-tu-faint hover:text-tu-text" title="Log out">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </header>

      <div className="flex flex-1 flex-col sm:flex-row">
        <nav className="flex gap-1 overflow-x-auto border-b border-tu-border px-2 py-2 sm:w-48 sm:flex-col sm:border-b-0 sm:border-r sm:py-4">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition ${
                  isActive ? 'bg-tu-panel text-tu-accent' : 'text-tu-dim hover:bg-tu-panel hover:text-tu-text'
                }`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <main className="flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  )
}
