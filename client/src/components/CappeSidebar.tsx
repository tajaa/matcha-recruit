import { NavLink, useNavigate } from 'react-router-dom'
import { LayoutGrid, LayoutTemplate, LogOut, Globe } from 'lucide-react'
import { cappeApi, clearCappeTokens } from '../api/cappeClient'
import { invalidateCappeMeCache } from '../hooks/useCappeMe'
import type { CappeAccount } from '../types/cappe'

const linkBase =
  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors'
const linkIdle = 'text-zinc-400 hover:bg-zinc-800/70 hover:text-zinc-100'
const linkActive = 'bg-emerald-500/10 text-emerald-400 ring-1 ring-inset ring-emerald-500/20'

function Item({ to, icon: Icon, label, end }: { to: string; icon: typeof Globe; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) => `${linkBase} ${isActive ? linkActive : linkIdle}`}
    >
      <Icon className="h-4 w-4" />
      {label}
    </NavLink>
  )
}

export default function CappeSidebar({ account }: { account: CappeAccount | null }) {
  const navigate = useNavigate()

  async function signOut() {
    // Best-effort server-side revocation, then clear local session regardless.
    await cappeApi.post('/auth/logout').catch(() => {})
    clearCappeTokens()
    invalidateCappeMeCache()
    navigate('/cappe/login')
  }

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-zinc-800 bg-zinc-900">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-400 to-emerald-600 text-sm font-bold text-zinc-950 shadow-lg shadow-emerald-500/20">
          C
        </span>
        <span className="text-lg font-semibold tracking-tight text-zinc-50">Cappe</span>
      </div>

      <nav className="flex flex-1 flex-col gap-1 px-3">
        <Item to="/cappe/sites" icon={LayoutGrid} label="My Sites" end />
        <Item to="/cappe/templates" icon={LayoutTemplate} label="Templates" />
      </nav>

      <div className="border-t border-zinc-800 px-3 py-3">
        <div className="px-2 pb-2">
          <div className="truncate text-sm font-medium text-zinc-200">{account?.name || 'Account'}</div>
          <div className="truncate text-xs text-zinc-500">{account?.email}</div>
          {account?.plan && account.plan !== 'free' && (
            <span className="mt-1 inline-block rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-emerald-400">
              {account.plan}
            </span>
          )}
        </div>
        <button
          onClick={signOut}
          className={`${linkBase} ${linkIdle} w-full`}
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </aside>
  )
}
