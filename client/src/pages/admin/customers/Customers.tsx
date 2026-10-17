import { AdminButton, AdminInput } from '../../../components/admin/AdminUI'
import { AdminTab, AdminTabBar } from '../../../components/admin/AdminTabs'
import { AdminWorkspace } from '../../../components/admin/AdminWorkspace'
import { Loader2, Search } from 'lucide-react'
import { TAB_DEFS } from './accounts/constants'
import { matchSearch } from './accounts/helpers'
import { PersonalTable } from './accounts/PersonalTable'
import { RegistrationTable } from './accounts/RegistrationTable'
import { useCustomers } from './accounts/useCustomers'
import type { Registration } from './accounts/types'

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
    <AdminWorkspace
      title="Customers"
      description={tabHelp}
      actions={
        <AdminButton
          onClick={refresh}
          disabled={busy}
          className="disabled:opacity-40" variant="ghost"
        >
          {busy ? <Loader2 className="inline h-3 w-3 animate-spin" /> : 'Refresh'}
        </AdminButton>
      }
    >
      {/* Tabs */}
      <AdminTabBar>
        {TAB_DEFS.map((t) => (
          <AdminTab
            key={t.id}
            onClick={() => setTab(t.id)}
           active={tab === t.id}
          >
            {t.label} <span className="text-zinc-600">{counts[t.id]}</span>
          </AdminTab>
        ))}
      </AdminTabBar>

      {/* Search + reset toast */}
      <div className="border-b border-white/[0.06] px-4 py-3">
        <div className="relative max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <AdminInput
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by email or company…"
            className="pl-9 pr-3"
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
    </AdminWorkspace>
  )
}
