import { AdminTable } from '../../../../components/admin/AdminUI'
import { Link } from 'react-router-dom'
import { AdminActionMenu } from '../../../../components/admin/AdminActionMenu'
import { fmtTokens, fmtUsd, relTime } from './helpers'
import type { Individual } from './types'

export function PersonalTable({
  rows,
  onSuspend,
  onReset,
  onCancel,
}: {
  rows: Individual[]
  onSuspend: (u: Individual) => void
  onReset: (u: Individual) => void
  onCancel: (u: Individual) => void
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-zinc-500">No personal accounts match this view.</p>
  }
  return (
    <AdminTable className="min-w-[740px]">
      <thead >
        <tr>
          <th className="text-left">Email</th>
          <th className="text-left">Joined</th>
          <th className="text-left">Subscription</th>
          <th className="text-left">Tokens</th>
          <th className="text-left">Account</th>
          <th className="text-right">Actions</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((u) => (
          <tr key={u.user_id} className="border-t border-white/[0.06] hover:bg-white/[0.02]">
            <td className="text-zinc-200">
              {u.email}
              {u.name && <div className="text-[10px] text-zinc-500">{u.name}</div>}
            </td>
            <td className="text-zinc-400">{relTime(u.created_at)}</td>
            <td >
              {u.subscription ? (
                <div className="flex flex-col gap-0.5">
                  <span className="text-zinc-300">
                    {u.subscription.pack_id} ·{' '}
                    <span className={u.subscription.status === 'active' ? 'text-emerald-400' : 'text-zinc-500'}>
                      {u.subscription.status}
                    </span>
                  </span>
                  <span className="text-[10px] text-zinc-500">
                    {fmtUsd(u.subscription.amount_cents)}
                    {u.subscription.current_period_end && (
                      <> · renews {new Date(u.subscription.current_period_end).toLocaleDateString()}</>
                    )}
                  </span>
                </div>
              ) : (
                <span className="text-zinc-600">Free</span>
              )}
            </td>
            <td className="text-zinc-400">
              {fmtTokens(u.free_tokens_used)} / {fmtTokens(u.free_token_limit)}
            </td>
            <td >
              {u.is_suspended ? (
                <span className="text-[10px] px-1.5 py-0.5 rounded border border-red-500/40 bg-red-500/10 text-red-300">
                  Suspended
                </span>
              ) : (
                <span className="text-[10px] text-zinc-600">Active</span>
              )}
            </td>
            <td >
              <div className="flex items-center justify-end gap-2 whitespace-nowrap">
                <Link
                  to={`/admin/companies/${u.company_id}`}
                  title="Tokens, billing, and refunds"
                  className="text-xs text-zinc-400 hover:text-zinc-100"
                >
                  Manage
                </Link>
                <AdminActionMenu label={`Actions for ${u.email}`} items={[
                  { label: u.is_suspended ? 'Unsuspend account' : 'Suspend account', danger: !u.is_suspended, onSelect: () => onSuspend(u) },
                  { label: 'Reset password', onSelect: () => onReset(u) },
                  ...(u.subscription?.status === 'active' ? [{ label: 'Cancel subscription', danger: true, onSelect: () => onCancel(u) }] : []),
                ]} />
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </AdminTable>
  )
}
