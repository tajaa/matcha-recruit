import { useState } from 'react'
import { useAsync } from '../../../hooks/useAsync'
import { Zap, Loader2 } from 'lucide-react'
import { api } from '../../../api/client'
import { relTime } from './shared'
import type { TokenDetail } from './types'

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

export function TokensTab({ companyId }: { companyId: string }) {
  const { data: detail, loading, reload: load } = useAsync(
    () => api.get<TokenDetail>(`/matcha-work/admin/companies/${companyId}/token-usage`),
    [companyId],
    null,
  )
  const [grantAmount, setGrantAmount] = useState('')
  const [grantDesc, setGrantDesc] = useState('')
  const [granting, setGranting] = useState(false)

  async function handleGrant() {
    const tokens = parseInt(grantAmount)
    if (!tokens || tokens <= 0) return
    setGranting(true)
    try {
      await api.post(`/matcha-work/admin/companies/${companyId}/tokens`, {
        tokens,
        description: grantDesc || undefined,
      })
      setGrantAmount('')
      setGrantDesc('')
      load()
    } catch {}
    setGranting(false)
  }

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="w-4 h-4 text-zinc-500 animate-spin" /></div>
  if (!detail) return <p className="text-sm text-zinc-500">Failed to load token data</p>

  const b = detail.budget

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-emerald-400" />
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Free Tokens</span>
          </div>
          <div className="text-xl font-semibold text-zinc-100">{fmtTokens(b.free_tokens_remaining)}</div>
          <div className="text-[11px] text-zinc-500">{fmtTokens(b.free_tokens_used)} / {fmtTokens(b.free_token_limit)} used</div>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-blue-400" />
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Subscription</span>
          </div>
          <div className="text-xl font-semibold text-zinc-100">
            {b.has_active_subscription ? fmtTokens(b.subscription_tokens_remaining) : 'None'}
          </div>
          {b.has_active_subscription && (
            <div className="text-[11px] text-zinc-500">{fmtTokens(b.subscription_tokens_used)} / {fmtTokens(b.subscription_token_limit)} used</div>
          )}
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-zinc-400" />
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Total Remaining</span>
          </div>
          <div className="text-xl font-semibold text-zinc-100">{fmtTokens(b.total_tokens_remaining)}</div>
        </div>
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
        <h3 className="text-sm font-medium text-zinc-300 mb-3">Grant Tokens</h3>
        <div className="flex items-end gap-3">
          <div>
            <label className="block text-[10px] text-zinc-500 mb-1">Amount</label>
            <input
              type="number"
              value={grantAmount}
              onChange={(e) => setGrantAmount(e.target.value)}
              placeholder="e.g. 500000"
              className="w-36 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
            />
          </div>
          <div className="flex-1">
            <label className="block text-[10px] text-zinc-500 mb-1">Description (optional)</label>
            <input
              type="text"
              value={grantDesc}
              onChange={(e) => setGrantDesc(e.target.value)}
              placeholder="Reason for grant"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
            />
          </div>
          <button
            onClick={handleGrant}
            disabled={granting || !grantAmount}
            className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-500 disabled:opacity-40 transition-colors"
          >
            {granting ? 'Granting...' : 'Grant'}
          </button>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-medium text-zinc-300 mb-3">Recent Usage</h3>
        {detail.recent_usage.length === 0 ? (
          <p className="text-sm text-zinc-500">No usage yet</p>
        ) : (
          <div className="overflow-hidden rounded-xl border border-zinc-800">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-zinc-900 text-zinc-500 uppercase tracking-widest text-[10px]">
                  <th className="text-left px-4 py-2.5 font-medium">Date</th>
                  <th className="text-left px-4 py-2.5 font-medium">Model</th>
                  <th className="text-right px-4 py-2.5 font-medium">Tokens</th>
                  <th className="text-left px-4 py-2.5 font-medium">Operation</th>
                </tr>
              </thead>
              <tbody>
                {detail.recent_usage.map((e) => (
                  <tr key={e.id} className="border-t border-zinc-800/50">
                    <td className="px-4 py-2 text-zinc-400">{relTime(e.created_at)}</td>
                    <td className="px-4 py-2 text-zinc-300">{e.model ?? '—'}</td>
                    <td className="px-4 py-2 text-right text-zinc-300">{e.total_tokens?.toLocaleString() ?? '—'}</td>
                    <td className="px-4 py-2 text-zinc-400">{e.operation ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
