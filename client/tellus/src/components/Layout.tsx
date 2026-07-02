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

function navLinkClass({ isActive }: { isActive: boolean }) {
  return `flex items-center gap-2 whitespace-nowrap rounded-md border-l-2 px-3 py-2 text-sm font-medium transition ${
    isActive
      ? 'border-tu-accent bg-tu-panel text-tu-accent'
      : 'border-transparent text-tu-dim hover:bg-tu-panel/60 hover:text-tu-text'
  }`
}

export function Layout({ children }: { children: ReactNode }) {
  const { account, logout } = useAccount()
  const navigate = useNavigate()
  const nav = account?.account_type === 'brand' ? BRAND_NAV : CONSUMER_NAV

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar — pinned to the true left edge, full height */}
      <aside className="hidden w-56 shrink-0 flex-col border-r border-tu-border sm:flex">
        <button onClick={() => navigate('/')} className="flex items-center gap-2 px-5 py-4">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-tu-accent text-xs font-black text-black">TU</span>
          <span className="font-display text-sm font-bold tracking-tight">Tell-Us</span>
        </button>
        <nav className="flex flex-1 flex-col gap-0.5 px-3 py-2">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={navLinkClass}>
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center justify-between border-t border-tu-border px-4 py-3">
          <span className="truncate text-xs text-tu-faint">{account?.display_name || account?.email}</span>
          <button onClick={logout} className="shrink-0 text-tu-faint hover:text-tu-text" title="Log out">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar + horizontal nav — desktop uses the sidebar instead */}
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-tu-border bg-tu-bg/90 px-4 py-3 backdrop-blur sm:hidden">
          <button onClick={() => navigate('/')} className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-tu-accent text-xs font-black text-black">TU</span>
            <span className="font-display text-sm font-bold tracking-tight">Tell-Us</span>
          </button>
          <div className="flex items-center gap-3">
            <span className="text-xs text-tu-faint">{account?.display_name || account?.email}</span>
            <button onClick={logout} className="text-tu-faint hover:text-tu-text" title="Log out">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </header>
        <nav className="flex gap-1 overflow-x-auto border-b border-tu-border px-2 py-2 sm:hidden">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={navLinkClass}>
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <main className="relative flex-1 p-4 sm:p-6">
          <div
            className="pointer-events-none absolute inset-0 -z-10"
            style={{ background: 'radial-gradient(ellipse 60% 30% at 50% 0%, rgba(249,115,22,0.05) 0%, rgba(249,115,22,0) 70%)' }}
          />
          <div className="mx-auto max-w-5xl">{children}</div>
        </main>
      </div>
    </div>
  )
}
