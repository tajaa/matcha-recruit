import { useEffect, useState } from 'react'
import { Loader2, Search, Zap, Plus } from 'lucide-react'
import { api } from '../../api/client'

interface IndividualUser {
  user_id: string
  email: string
  name: string | null
  company_id: string
  created_at: string | null
  free_tokens_used: number
  free_token_limit: number
  free_tokens_remaining: number
  subscription_token_limit: number
  subscription_tokens_remaining: number
  has_active_subscription: boolean
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`
  return String(n)
}

function relTime(iso: string | null): string {
  if (!iso) return '--'
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (d === 0) return 'Today'
  if (d === 1) return 'Yesterday'
  return `${d}d ago`
}

export default function Individuals() {
  const [users, setUsers] = useState<IndividualUser[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [grantTarget, setGrantTarget] = useState<IndividualUser | null>(null)
  const [grantAmount, setGrantAmount] = useState('')
  const [granting, setGranting] = useState(false)

  useEffect(() => {
    api.get<IndividualUser[]>('/matcha-work/billing/admin/individuals')
      .then(setUsers)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  async function handleGrant() {
    if (!grantTarget || !grantAmount) return
    const amount = parseInt(grantAmount, 10)
    if (isNaN(amount) || amount <= 0) return
    setGranting(true)
    try {
      await api.post(`/matcha-work/billing/admin/companies/${grantTarget.company_id}/tokens`, {
        tokens: amount,
        description: `Admin grant to individual: ${grantTarget.email}`,
      })
      // Refresh list
      const updated = await api.get<IndividualUser[]>('/matcha-work/billing/admin/individuals')
      setUsers(updated)
      setGrantTarget(null)
      setGrantAmount('')
    } catch {}
    setGranting(false)
  }

  const filtered = users.filter((u) => {
    if (!search) return true
    const q = search.toLowerCase()
    return u.email.toLowerCase().includes(q) || (u.name || '').toLowerCase().includes(q)
  })

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-zinc-500" size={24} />
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Individual Users</h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            Personal account users ({users.length} total)
          </p>
        </div>
      </div>

      {/* Search */}
      <div className="relative mb-4 max-w-xs">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by email or name..."
          className="w-full pl-9 pr-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-600"
        />
      </div>

      {/* Table */}
      <div className="rounded-xl border border-zinc-800 overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-zinc-900/80 border-b border-zinc-800">
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400">Email</th>
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400">Name</th>
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400">Joined</th>
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400">Tokens Used</th>
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400">Token Limit</th>
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400">Remaining</th>
              <th className="text-left px-4 py-2.5 font-medium text-zinc-400 w-32">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-zinc-500">
                  {search ? 'No users match your search.' : 'No individual users yet.'}
                </td>
              </tr>
            )}
            {filtered.map((u) => {
              const pct = u.free_token_limit > 0 ? Math.min(100, (u.free_tokens_used / u.free_token_limit) * 100) : 0
              const low = u.free_tokens_remaining <= 0
              const warn = !low && pct > 80
              return (
                <tr key={u.user_id} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                  <td className="px-4 py-3 text-zinc-200">{u.email}</td>
                  <td className="px-4 py-3 text-zinc-400">{u.name || '--'}</td>
                  <td className="px-4 py-3 text-zinc-500">{relTime(u.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${low ? 'bg-red-500' : warn ? 'bg-amber-500' : 'bg-emerald-500'}`}
                          style={{ width: `${Math.min(pct, 100)}%` }}
                        />
                      </div>
                      <span className={`${low ? 'text-red-400' : warn ? 'text-amber-400' : 'text-zinc-400'}`}>
                        {formatTokens(u.free_tokens_used)}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-zinc-400">{formatTokens(u.free_token_limit)}</td>
                  <td className="px-4 py-3">
                    <span className={low ? 'text-red-400 font-medium' : 'text-zinc-400'}>
                      {formatTokens(u.free_tokens_remaining)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => { setGrantTarget(u); setGrantAmount('') }}
                      className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors"
                    >
                      <Plus size={10} />
                      Grant Tokens
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Grant tokens modal */}
      {grantTarget && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 w-full max-w-sm">
            <h3 className="text-sm font-semibold text-zinc-100 mb-1">Grant Tokens</h3>
            <p className="text-xs text-zinc-500 mb-4">{grantTarget.email}</p>
            <p className="text-[11px] text-zinc-500 mb-3">
              Current: {formatTokens(grantTarget.free_tokens_remaining)} remaining of {formatTokens(grantTarget.free_token_limit)}
            </p>
            <div className="flex gap-2 mb-4">
              {[100_000, 500_000, 1_000_000, 5_000_000].map((amt) => (
                <button
                  key={amt}
                  onClick={() => setGrantAmount(String(amt))}
                  className={`px-2 py-1 rounded text-[10px] font-medium transition-colors ${
                    grantAmount === String(amt) ? 'bg-emerald-700 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  +{formatTokens(amt)}
                </button>
              ))}
            </div>
            <input
              value={grantAmount}
              onChange={(e) => setGrantAmount(e.target.value.replace(/\D/g, ''))}
              placeholder="Custom amount..."
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-600 mb-4"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setGrantTarget(null)}
                className="px-3 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200"
              >
                Cancel
              </button>
              <button
                onClick={handleGrant}
                disabled={!grantAmount || granting}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-emerald-700 text-white text-xs font-medium hover:bg-emerald-600 disabled:opacity-40 transition-colors"
              >
                {granting ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
                Grant {grantAmount ? formatTokens(parseInt(grantAmount, 10) || 0) : ''}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
