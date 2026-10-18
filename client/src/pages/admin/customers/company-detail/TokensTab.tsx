import { AdminCard, AdminInput, AdminButton, AdminTable } from '../../../../components/admin/AdminUI'
import { useState } from 'react'
import { useAsync } from '../../../../hooks/useAsync'
import { Zap, Loader2 } from 'lucide-react'
import { api } from '../../../../api/client'
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
    } catch { /* Preserve the existing best-effort fallback. */ }
    setGranting(false)
  }

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="w-4 h-4 text-zinc-500 animate-spin" /></div>
  if (!detail) return <p className="text-sm text-zinc-500">Failed to load token data</p>

  const b = detail.budget

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <AdminCard >
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-emerald-400" />
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Free Tokens</span>
          </div>
          <div className="text-xl font-semibold text-zinc-100">{fmtTokens(b.free_tokens_remaining)}</div>
          <div className="text-[11px] text-zinc-500">{fmtTokens(b.free_tokens_used)} / {fmtTokens(b.free_token_limit)} used</div>
        </AdminCard>
        <AdminCard >
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
        </AdminCard>
        <AdminCard >
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-zinc-400" />
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Total Remaining</span>
          </div>
          <div className="text-xl font-semibold text-zinc-100">{fmtTokens(b.total_tokens_remaining)}</div>
        </AdminCard>
      </div>

      <AdminCard >
        <h3 className="text-sm font-medium text-zinc-300 mb-3">Grant Tokens</h3>
        <div className="flex items-end gap-3">
          <div>
            <label className="block text-[10px] text-zinc-500 mb-1">Amount</label>
            <AdminInput
              type="number"
              value={grantAmount}
              onChange={(e) => setGrantAmount(e.target.value)}
              placeholder="e.g. 500000"
              className="w-36"
            />
          </div>
          <div className="flex-1">
            <label className="block text-[10px] text-zinc-500 mb-1">Description (optional)</label>
            <AdminInput
              type="text"
              value={grantDesc}
              onChange={(e) => setGrantDesc(e.target.value)}
              placeholder="Reason for grant"
            />
          </div>
          <AdminButton
            onClick={handleGrant}
            disabled={granting || !grantAmount}
            className="disabled:opacity-40" variant="success"
          >
            {granting ? 'Granting...' : 'Grant'}
          </AdminButton>
        </div>
      </AdminCard>

      <div>
        <h3 className="text-sm font-medium text-zinc-300 mb-3">Recent Usage</h3>
        {detail.recent_usage.length === 0 ? (
          <p className="text-sm text-zinc-500">No usage yet</p>
        ) : (
          <AdminTable>
            <thead>
              <tr className="bg-zinc-900 text-zinc-500 uppercase tracking-widest text-[10px]">
                <th className="text-left">Date</th>
                <th className="text-left">Model</th>
                <th className="text-right">Tokens</th>
                <th className="text-left">Operation</th>
              </tr>
            </thead>
            <tbody>
              {detail.recent_usage.map((e) => (
                <tr key={e.id} className="border-t border-zinc-800/50">
                  <td className="text-zinc-400">{relTime(e.created_at)}</td>
                  <td className="text-zinc-300">{e.model ?? '—'}</td>
                  <td className="text-right text-zinc-300">{e.total_tokens?.toLocaleString() ?? '—'}</td>
                  <td className="text-zinc-400">{e.operation ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </AdminTable>
        )}
      </div>
    </div>
  )
}
