import { NavLink, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { Award, Bell, Building2, Coins, CreditCard, Gift, LogOut, MapPin, MessageCircle, MessageSquare, ScrollText, ShieldAlert, ShieldCheck, Sparkles, Star, Store, Tag, Trophy, Settings, ListChecks, Users } from 'lucide-react'
import { useAccount } from '../hooks/useAccount'
import { tellusApi } from '../api/tellusClient'
import type { TellusNotification } from '../api/types'

interface NavItem {
  to: string
  label: string
  icon: typeof Award
  end?: boolean
}

const CONSUMER_NAV: NavItem[] = [
  { to: '/', label: 'Rewards', icon: Award, end: true },
  { to: '/marketplace', label: 'Marketplace', icon: Gift },
  { to: '/redemptions', label: 'Redemptions', icon: Tag },
  { to: '/my-reviews', label: 'My reviews', icon: Star },
  { to: '/places', label: 'Places', icon: MapPin },
  { to: '/messages', label: 'Messages', icon: MessageCircle },
  { to: '/leaderboard', label: 'Leaderboard', icon: Trophy },
  { to: '/settings', label: 'Settings', icon: Settings },
]

const BRAND_NAV: NavItem[] = [
  { to: '/brand/feedback', label: 'Feedback', icon: MessageSquare, end: false },
  { to: '/brand/messages', label: 'Messages', icon: MessageCircle },
  { to: '/brand/stores', label: 'Stores & QR', icon: Store },
  { to: '/brand/listings', label: 'Rewards', icon: ListChecks },
  { to: '/brand/billing', label: 'Billing', icon: CreditCard },
  { to: '/brand/settings', label: 'Settings', icon: Settings },
]

const BRAND_PENDING_NAV: NavItem[] = [
  { to: '/brand/billing', label: 'Billing', icon: CreditCard },
]

const ADMIN_NAV: NavItem[] = [
  { to: '/admin/accounts', label: 'Accounts', icon: Users },
  { to: '/admin/brands', label: 'Brands', icon: Building2 },
  { to: '/admin/claims', label: 'Claims', icon: ShieldCheck },
  { to: '/admin/moderation', label: 'Moderation', icon: ShieldAlert },
  { to: '/admin/economy', label: 'Economy', icon: Coins },
  { to: '/admin/updates', label: 'Updates', icon: Sparkles },
  { to: '/admin/audit', label: 'Audit', icon: ScrollText },
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
  const isBrand = account?.account_type === 'brand'
  const isPendingBrand = isBrand && account?.plan_status !== 'active'
  const baseNav = isPendingBrand ? BRAND_PENDING_NAV : isBrand ? BRAND_NAV : CONSUMER_NAV
  const nav = account?.is_admin ? [...baseNav, ...ADMIN_NAV] : baseNav
  const [unread, setUnread] = useState(0)

  useEffect(() => {
    let cancelled = false
    async function poll() {
      try {
        const notes = await tellusApi.get<TellusNotification[]>('/notifications?unread_only=true&limit=30')
        if (!cancelled) setUnread(notes.length)
      } catch {
        // best-effort — a failed poll just tries again next tick
      }
    }
    void poll()
    const id = setInterval(poll, 60_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const FEEDBACK_SURFACE_KINDS = new Set(['dm_message', 'review_moderated', 'review_hearted', 'review_reply', 'review_published'])

  async function openNotifications() {
    // Pending (unpaid) brands can't reach /brand/feedback — it 402s. Send
    // them to their own status page instead. A pending DM takes priority
    // over the default feedback/reviews surface — that's where the actual
    // unread thing lives.
    let notes: TellusNotification[] = []
    let fetchedNotes = true
    try {
      notes = await tellusApi.get<TellusNotification[]>('/notifications?unread_only=true&limit=30')
    } catch {
      fetchedNotes = false
      // best-effort — fall through to the default surface
    }
    const hasDm = notes.some((n) => n.kind === 'dm_message')
    if (isPendingBrand) navigate('/brand/billing')
    else if (hasDm) navigate(isBrand ? '/brand/messages' : '/messages')
    else navigate(isBrand ? '/brand/feedback' : '/my-reviews')

    // Only clear notifications relevant to the surface we're navigating to —
    // a blanket mark-all-read here would silently drop unrelated points/
    // redemption notices the user never saw. Skip entirely if the fetch above
    // failed — `notes` is empty in that case, not actually zero unread.
    if (!fetchedNotes) return
    try {
      const relevant = notes.filter((n) => FEEDBACK_SURFACE_KINDS.has(n.kind))
      await Promise.all(relevant.map((n) => tellusApi.post(`/notifications/read?notification_id=${n.id}`)))
      setUnread(notes.length - relevant.length)
    } catch {
      // best-effort — leave unread count as-is on failure
    }
  }

  const bell = (
    <button onClick={openNotifications} className="relative text-tu-faint hover:text-tu-text" title="Notifications">
      <Bell className="h-4 w-4" />
      {unread > 0 && (
        <span className="absolute -right-1 -top-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-tu-accent text-[9px] font-bold text-black">
          {unread > 9 ? '9+' : unread}
        </span>
      )}
    </button>
  )

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar — pinned to the true left edge, full height */}
      <aside className="hidden w-56 shrink-0 flex-col border-r border-tu-border sm:flex">
        <button onClick={() => navigate('/')} className="flex items-center gap-2 px-5 py-4">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-tu-accent text-xs font-black text-black">TU</span>
          <span className="font-display text-sm font-bold tracking-tight">Tell-Us</span>
        </button>
        <nav className="flex flex-1 flex-col gap-0.5 px-3 py-2">
          {baseNav.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={navLinkClass}>
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
          {account?.is_admin && (
            <>
              <div className="my-2 border-t border-tu-border" />
              <div className="px-3 pb-1 font-mono text-[10px] uppercase tracking-[0.15em] text-tu-faint">
                Internal
              </div>
              {ADMIN_NAV.map(({ to, label, icon: Icon, end }) => (
                <NavLink key={to} to={to} end={end} className={navLinkClass}>
                  <Icon className="h-4 w-4" />
                  {label}
                </NavLink>
              ))}
            </>
          )}
        </nav>
        <div className="flex items-center justify-between border-t border-tu-border px-4 py-3">
          <span className="truncate text-xs text-tu-faint">{account?.display_name || account?.email}</span>
          <div className="flex shrink-0 items-center gap-3">
            {bell}
            <button onClick={logout} className="text-tu-faint hover:text-tu-text" title="Log out">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
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
            {bell}
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
