import { AdminTable } from '../../../../components/admin/AdminUI'
import { Link } from 'react-router-dom'
import { AdminActionMenu } from '../../../../components/admin/AdminActionMenu'
import { StatusBadge } from './StatusBadge'
import { TIER_BADGE, TIER_LABEL } from './constants'
import { fmtUsd, relTime, tierFromRegistration } from './helpers'
import type { Registration, Tab } from './types'

export function RegistrationTable({
  tab,
  rows,
  onSuspend,
  onReset,
  onCancel,
  onCancelAtEnd,
  onSoftDelete,
  onRestore,
}: {
  tab: Tab
  rows: Registration[]
  onSuspend: (r: Registration) => void
  onReset: (r: Registration) => void
  onCancel: (r: Registration) => void
  onCancelAtEnd: (r: Registration) => void
  onSoftDelete: (r: Registration) => void
  onRestore: (r: Registration) => void
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-zinc-500">No customers match this view.</p>
  }

  // Show columns appropriate to the tier; All shows the union.
  const showTier = tab === 'all'
  const showSub = tab === 'lite' || tab === 'x' || tab === 'all'
  const showStatus = tab === 'platform' || tab === 'all'

  return (
    <AdminTable className="min-w-[780px]">
      <thead >
        <tr>
          <th className="text-left">Company / Email</th>
          {showTier && <th className="text-left">Tier</th>}
          <th className="text-left">Joined</th>
          {showStatus && <th className="text-left">Status</th>}
          {showSub && <th className="text-left">Subscription</th>}
          <th className="text-left">Account</th>
          <th className="text-right">Actions</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const tier = tierFromRegistration(r)
          const isDeleted = !!r.deleted_at
          return (
            <tr key={r.id} className="border-t border-white/[0.06] hover:bg-white/[0.02]">
              <td >
                <Link to={`/admin/companies/${r.id}`} className="font-medium text-zinc-100 hover:text-emerald-400">
                  {r.company_name}
                </Link>
                <div className="text-[10px] text-zinc-500">{r.owner_email}</div>
              </td>
              {showTier && (
                <td >
                  <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded border ${TIER_BADGE[tier]}`}>
                    {TIER_LABEL[tier]}
                  </span>
                </td>
              )}
              <td className="text-zinc-400">{relTime(r.created_at)}</td>
              {showStatus && (
                <td >
                  <StatusBadge status={r.status} />
                </td>
              )}
              {showSub && (
                <td >
                  {r.subscription ? (
                    <div className="flex flex-col gap-0.5">
                      <span className="text-zinc-300">
                        {r.subscription.pack_id} ·{' '}
                        <span className={r.subscription.status === 'active' ? 'text-emerald-400' : 'text-zinc-500'}>
                          {r.subscription.status}
                        </span>
                      </span>
                      <span className="text-[10px] text-zinc-500">
                        {fmtUsd(r.subscription.amount_cents)}
                        {r.subscription.current_period_end && (
                          <> · renews {new Date(r.subscription.current_period_end).toLocaleDateString()}</>
                        )}
                      </span>
                    </div>
                  ) : (
                    <span className="text-zinc-600">—</span>
                  )}
                </td>
              )}
              <td >
                <div className="flex flex-wrap gap-1">
                  {r.is_suspended && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded border border-red-500/40 bg-red-500/10 text-red-300">
                      Suspended
                    </span>
                  )}
                  {isDeleted && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded border border-zinc-700 bg-zinc-800 text-zinc-400">
                      Deleted
                    </span>
                  )}
                  {!r.is_suspended && !isDeleted && (
                    <span className="text-[10px] text-zinc-600">Active</span>
                  )}
                </div>
              </td>
              <td >
                <div className="flex items-center justify-end gap-2 whitespace-nowrap">
                  {!isDeleted && <Link to={`/admin/companies/${r.id}`} className="text-xs text-zinc-400 hover:text-zinc-100">Manage</Link>}
                  <AdminActionMenu label={`Actions for ${r.company_name}`} items={isDeleted ? [
                    { label: 'Restore company', onSelect: () => onRestore(r) },
                  ] : [
                    { label: r.is_suspended ? 'Unsuspend owner' : 'Suspend owner', danger: !r.is_suspended, onSelect: () => onSuspend(r) },
                    { label: 'Reset password', disabled: !r.owner_user_id, onSelect: () => onReset(r) },
                    ...(r.subscription?.status === 'active' ? [
                      { label: 'Cancel at period end', onSelect: () => onCancelAtEnd(r) },
                      { label: 'Cancel subscription now', danger: true, onSelect: () => onCancel(r) },
                    ] : []),
                    { label: 'Delete company', danger: true, onSelect: () => onSoftDelete(r) },
                  ]} />
                </div>
              </td>
            </tr>
          )
        })}
      </tbody>
    </AdminTable>
  )
}
