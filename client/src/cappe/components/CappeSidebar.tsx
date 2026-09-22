import { useEffect, useState } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutGrid, LayoutTemplate, LogOut, Globe, ArrowLeft, FileText, ShoppingBag,
  Receipt, Calendar, MessageSquare, Users, Mail, Inbox, Newspaper, UserCircle, Star, MapPin,
  Handshake, Wallet, Compass,
} from 'lucide-react'
import { cappeApi, clearCappeTokens } from '../api'
import { invalidateCappeMeCache } from '../hooks/useCappeMe'
import { creatorPaths } from '../creators/creatorPaths'
import { confirmLeave } from '../utils/unsavedGuard'
import type { CappeAccount, CappeThread } from '../types'

const linkBase = 'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors'
const linkIdle = 'text-zinc-400 hover:bg-zinc-800/70 hover:text-zinc-100'
const linkActive = 'bg-lime-400/10 text-lime-300 ring-1 ring-inset ring-lime-400/20'

// Every nav control in this sidebar can leave the page editor, so each one
// asks the unsaved-work guard first and cancels its own navigation when the
// user backs out. `confirmLeave()` is a no-op (returns true) anywhere else.
const guardNav = (e: { preventDefault: () => void }) => {
  if (!confirmLeave()) e.preventDefault()
}

function Item({ to, icon: Icon, label, end, badge }: {
  to: string; icon: typeof Globe; label: string; end?: boolean; badge?: number
}) {
  return (
    <NavLink to={to} end={end} onClick={guardNav} className={({ isActive }) => `${linkBase} ${isActive ? linkActive : linkIdle}`}>
      <Icon className="h-4 w-4" />
      <span className="flex-1">{label}</span>
      {badge ? (
        <span className="rounded-full bg-lime-400 px-1.5 text-[11px] font-bold leading-5 text-zinc-950">
          {badge > 99 ? '99+' : badge}
        </span>
      ) : null}
    </NavLink>
  )
}

// Site-management nav (the surfaces under one site). The sidebar is rendered by
// CappeLayout (outside the :siteId route), so siteId is parsed from the path.
const SITE_NAV: { to: string; label: string; icon: typeof Globe; end?: boolean }[] = [
  { to: '', label: 'Site & pages', icon: FileText, end: true },
  { to: 'messages', label: 'Messages', icon: MessageSquare },
  { to: 'clients', label: 'Clients', icon: Users },
  { to: 'orders', label: 'Orders', icon: Receipt },
  { to: 'subscriptions', label: 'Subscriptions', icon: Receipt },
  { to: 'bookings', label: 'Bookings', icon: Calendar },
  { to: 'locations', label: 'Locations', icon: MapPin },
  { to: 'shop', label: 'Storefront', icon: ShoppingBag },
  { to: 'subscribers', label: 'Subscribers', icon: UserCircle },
  { to: 'campaigns', label: 'Newsletter', icon: Mail },
  { to: 'forms', label: 'Forms', icon: Inbox },
  { to: 'reviews', label: 'Reviews', icon: Star },
  { to: 'blog', label: 'Blog', icon: Newspaper },
]

export default function CappeSidebar({ account }: { account: CappeAccount | null }) {
  const navigate = useNavigate()
  const location = useLocation()
  // Keyed to the site it was fetched for, so leaving a site reads as 0 without a
  // synchronous reset inside the effect.
  const [unreadFor, setUnreadFor] = useState<{ siteId: string; count: number } | null>(null)

  // Parse the active site id from the site-workspace path. The tree is mounted
  // three ways — /cappe/sites/:id, the gummfit.com host mount (/gummfit/... and
  // the bare apex /sites/:id) — and a /cappe-only regex left the whole site nav
  // missing on the apex mount.
  const m = location.pathname.match(/(?:\/cappe|\/gummfit)?\/sites\/([0-9a-f-]+)/i)
  const siteId = m?.[1] ?? null

  useEffect(() => {
    if (!siteId) return
    let cancelled = false
    cappeApi.get<CappeThread[]>(`/sites/${siteId}/threads`)
      .then((ts) => { if (!cancelled) setUnreadFor({ siteId, count: ts.reduce((n, t) => n + (t.owner_unread || 0), 0) }) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [siteId, location.pathname])

  const unread = siteId && unreadFor?.siteId === siteId ? unreadFor.count : 0

  async function signOut() {
    if (!confirmLeave()) return
    await cappeApi.post('/auth/logout').catch(() => {})
    clearCappeTokens()
    invalidateCappeMeCache()
    navigate(account?.account_type === 'creator' ? creatorPaths.login : '/cappe/login')
  }

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-zinc-800 bg-zinc-900">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-lime-300 to-lime-500 text-sm font-bold text-zinc-950 shadow-lg shadow-lime-500/20">
          G
        </span>
        <span className="text-lg font-semibold tracking-tight text-zinc-50">
          {account?.account_type === 'creator' ? 'Gummfit Creators' : 'Gummfit'}
        </span>
      </div>

      <nav className="flex flex-1 flex-col gap-1 overflow-y-auto px-3">
        {siteId ? (
          <>
            <NavLink to="/cappe/sites" onClick={guardNav} className={`${linkBase} ${linkIdle} mb-1`}>
              <ArrowLeft className="h-4 w-4" /> All sites
            </NavLink>
            {SITE_NAV.map((n) => (
              <Item
                key={n.to}
                to={n.to ? `/cappe/sites/${siteId}/${n.to}` : `/cappe/sites/${siteId}`}
                icon={n.icon}
                label={n.label}
                end={n.end}
                badge={n.to === 'messages' ? unread : undefined}
              />
            ))}
          </>
        ) : account?.account_type === 'creator' ? (
          <>
            <Item to={creatorPaths.home} icon={UserCircle} label="My Profile" end />
            <Item to={creatorPaths.deals} icon={Handshake} label="Deals" />
            <Item to={creatorPaths.earnings} icon={Wallet} label="Earnings" />
            <Item to={creatorPaths.directory} icon={Compass} label="Directory" />
          </>
        ) : (
          <>
            <Item to="/cappe/sites" icon={LayoutGrid} label="My Sites" end />
            <Item to="/cappe/templates" icon={LayoutTemplate} label="Templates" />
            {account?.account_type === 'business' && (
              <>
                <div className="mt-3 px-3 text-[11px] font-semibold uppercase tracking-wide text-zinc-600">Creators</div>
                <Item to={creatorPaths.brandHome} icon={Compass} label="Find creators" />
                <Item to={creatorPaths.brandCollabs} icon={Handshake} label="Collabs" />
              </>
            )}
          </>
        )}
      </nav>

      <div className="border-t border-zinc-800 px-3 py-3">
        <div className="px-2 pb-2">
          <div className="truncate text-sm font-medium text-zinc-200">{account?.name || 'Account'}</div>
          <div className="truncate text-xs text-zinc-500">{account?.email}</div>
          {account?.plan && account.plan !== 'free' && (
            <span className="mt-1 inline-block rounded bg-lime-400/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-lime-300">
              {account.plan}
            </span>
          )}
        </div>
        <button onClick={signOut} className={`${linkBase} ${linkIdle} w-full`}>
          <LogOut className="h-4 w-4" /> Sign out
        </button>
      </div>
    </aside>
  )
}
