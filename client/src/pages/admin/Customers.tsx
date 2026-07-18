import { Loader2, Search, Users } from 'lucide-react'
import { TAB_DEFS } from './Customers/constants'
import { matchSearch } from './Customers/helpers'
import { PersonalTable } from './Customers/PersonalTable'
import { RegistrationTable } from './Customers/RegistrationTable'
import { useCustomers } from './Customers/useCustomers'
import type { Registration } from './Customers/types'

export default function Customers() {
  const {
    tab,
    setTab,
    search,
    setSearch,
    individuals,
    busy,
    resetUrl,
    setResetUrl,
    refresh,
    tabRows,
    counts,
    suspendUser,
    passwordReset,
    cancelSub,
    softDelete,
    restore,
  } = useCustomers()

  const tabHelp = TAB_DEFS.find((t) => t.id === tab)?.help

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
        <h1 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <Users className="h-4 w-4 text-emerald-400" /> Customers
        </h1>
        <div className="flex items-center gap-4">
          <span className="hidden text-xs text-zinc-500 md:block">{tabHelp}</span>
          <button
            onClick={refresh}
            disabled={busy}
            className="rounded-md border border-white/[0.08] px-2.5 py-1 text-xs font-medium text-zinc-400 transition-colors hover:bg-white/[0.04] hover:text-zinc-100 disabled:opacity-40"
          >
            {busy ? <Loader2 className="inline h-3 w-3 animate-spin" /> : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap items-center gap-1 border-b border-white/[0.06] px-2 py-1.5">
        {TAB_DEFS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`rounded px-2 py-1 font-mono text-[10px] uppercase tracking-wide transition-colors ${
              tab === t.id ? 'bg-white/[0.06] text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {t.label} <span className="text-zinc-600">{counts[t.id]}</span>
          </button>
        ))}
      </div>

      {/* Search + reset toast */}
      <div className="border-b border-white/[0.06] px-4 py-3">
        <div className="relative max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by email or company…"
            className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] pl-9 pr-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-white/[0.16]"
          />
        </div>

        {resetUrl && (
          <div className="mt-3 flex items-start justify-between gap-3 rounded-lg border border-emerald-700/40 bg-emerald-900/20 p-3">
            <div className="text-xs">
              <div className="font-medium text-emerald-300">Reset link copied for {resetUrl.email} (1 hour)</div>
              <code className="mt-1 block break-all text-[10px] text-emerald-100">{resetUrl.url}</code>
            </div>
            <button
              onClick={() => setResetUrl(null)}
              className="shrink-0 text-[11px] text-emerald-300 hover:text-emerald-100"
            >
              Dismiss
            </button>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="flex-1 overflow-y-auto p-4">
        {tabRows === null ? (
          <div className="flex h-32 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-zinc-500" />
          </div>
        ) : tab === 'personal' ? (
          <PersonalTable
            rows={(individuals ?? []).filter((u) => matchSearch(u.email, u.name, search))}
            onSuspend={(u) => suspendUser(u.user_id, u.is_suspended)}
            onReset={(u) => passwordReset(u.user_id, u.email)}
            onCancel={(u) => cancelSub(u.company_id, true)}
          />
        ) : (
          <RegistrationTable
            tab={tab}
            rows={(tabRows as Registration[]).filter((r) => matchSearch(r.owner_email, r.company_name, search))}
            onSuspend={(r) => suspendUser(r.owner_user_id, r.is_suspended)}
            onReset={(r) => passwordReset(r.owner_user_id, r.owner_email)}
            onCancel={(r) => cancelSub(r.id, true)}
            onCancelAtEnd={(r) => cancelSub(r.id, false)}
            onSoftDelete={(r) => softDelete(r.id)}
            onRestore={(r) => restore(r.id)}
          />
        )}
      </div>
    </div>
  )
}
