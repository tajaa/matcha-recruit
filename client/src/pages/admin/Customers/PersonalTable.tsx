import { Link } from 'react-router-dom'
import { Shield, KeyRound } from 'lucide-react'
import { ActionBtn } from './ActionBtn'
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
    return <p className="text-sm text-zinc-500">No personal users yet.</p>
  }
  return (
    <div className="overflow-hidden rounded-xl border border-white/[0.06]">
      <table className="w-full text-xs">
        <thead className="bg-white/[0.03] text-zinc-500 uppercase tracking-widest text-[10px]">
          <tr>
            <th className="text-left px-4 py-2.5 font-medium">Email</th>
            <th className="text-left px-4 py-2.5 font-medium">Joined</th>
            <th className="text-left px-4 py-2.5 font-medium">Subscription</th>
            <th className="text-left px-4 py-2.5 font-medium">Tokens</th>
            <th className="text-left px-4 py-2.5 font-medium">Account</th>
            <th className="text-left px-4 py-2.5 font-medium w-[280px]">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((u) => (
            <tr key={u.user_id} className="border-t border-white/[0.06] hover:bg-white/[0.02]">
              <td className="px-4 py-3 text-zinc-200">
                {u.email}
                {u.name && <div className="text-[10px] text-zinc-500">{u.name}</div>}
              </td>
              <td className="px-4 py-3 text-zinc-400">{relTime(u.created_at)}</td>
              <td className="px-4 py-3">
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
              <td className="px-4 py-3 text-zinc-400">
                {fmtTokens(u.free_tokens_used)} / {fmtTokens(u.free_token_limit)}
              </td>
              <td className="px-4 py-3">
                {u.is_suspended ? (
                  <span className="text-[10px] px-1.5 py-0.5 rounded border border-red-500/40 bg-red-500/10 text-red-300">
                    Suspended
                  </span>
                ) : (
                  <span className="text-[10px] text-zinc-600">Active</span>
                )}
              </td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  <ActionBtn icon={Shield} label={u.is_suspended ? 'Unsus' : 'Suspend'} onClick={() => onSuspend(u)} />
                  <ActionBtn icon={KeyRound} label="Reset" onClick={() => onReset(u)} />
                  {u.subscription && u.subscription.status === 'active' && (
                    <ActionBtn label="Cancel sub" tone="danger" onClick={() => onCancel(u)} />
                  )}
                  <Link
                    to={`/admin/companies/${u.company_id}`}
                    className="text-[10px] px-2 py-1 rounded bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                  >
                    Tokens / Refund →
                  </Link>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
