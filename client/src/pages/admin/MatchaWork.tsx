import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, Search, Zap, Users, User, Building2 } from 'lucide-react'
import { api } from '../../api/client'
import Individuals from './Individuals'

type Tab = 'personal' | 'business'

interface BusinessCompany {
  company_id: string
  company_name: string
  company_status: string
  signup_source: string | null
  member_count: number
  free_tokens_used: number
  free_token_limit: number
  free_tokens_remaining: number
  subscription_token_limit: number
  subscription_tokens_remaining: number
  has_active_subscription: boolean
  created_at: string | null
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

function BusinessWork() {
  const [rows, setRows] = useState<BusinessCompany[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [grantTarget, setGrantTarget] = useState<BusinessCompany | null>(null)
  const [grantAmount, setGrantAmount] = useState('')
  const [granting, setGranting] = useState(false)

  function fetchRows() {
    api.get<BusinessCompany[]>('/matcha-work/billing/admin/matcha-work/business')
      .then(setRows)
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchRows() }, [])

  async function handleGrant() {
    if (!grantTarget || !grantAmount) return
    const amount = parseInt(grantAmount, 10)
    if (isNaN(amount) || amount <= 0) return
    setGranting(true)
    try {
      await api.post(`/matcha-work/billing/admin/companies/${grantTarget.company_id}/tokens`, {
        tokens: amount,
        description: `Admin grant to business: ${grantTarget.company_name}`,
      })
      setGrantTarget(null)
      setGrantAmount('')
      fetchRows()
    } finally {
      setGranting(false)
    }
  }

  const filtered = rows.filter((r) =>
    r.company_name.toLowerCase().includes(search.toLowerCase()),
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-zinc-500">
        <Loader2 className="animate-spin" size={20} />
      </div>
    )
  }

  return (
    <div>
      <div className="relative mb-4 max-w-sm">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search companies..."
          className="w-full rounded-lg border border-zinc-800 bg-zinc-900 pl-9 pr-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-700"
        />
      </div>

      {filtered.length === 0 ? (
        <div className="py-16 text-center text-sm text-zinc-500">
          No companies on a Matcha-Work business plan.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-zinc-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wide text-zinc-500">
                <th className="px-4 py-2.5 font-medium">Company</th>
                <th className="px-4 py-2.5 font-medium">Members</th>
                <th className="px-4 py-2.5 font-medium">Free tokens</th>
                <th className="px-4 py-2.5 font-medium">Subscription</th>
                <th className="px-4 py-2.5 font-medium">Created</th>
                <th className="px-4 py-2.5 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.company_id} className="border-b border-zinc-900 last:border-0 hover:bg-zinc-900/50">
                  <td className="px-4 py-3">
                    <Link to={`/admin/companies/${r.company_id}`} className="font-medium text-zinc-100 hover:text-emerald-400">
                      {r.company_name}
                    </Link>
                    <div className="text-[11px] text-zinc-500">{r.company_status}</div>
                  </td>
                  <td className="px-4 py-3 text-zinc-300">
                    <span className="inline-flex items-center gap-1"><Users size={12} className="text-zinc-500" />{r.member_count}</span>
                  </td>
                  <td className="px-4 py-3 text-zinc-300">
                    {formatTokens(r.free_tokens_remaining)} <span className="text-zinc-500">/ {formatTokens(r.free_token_limit)}</span>
                  </td>
                  <td className="px-4 py-3 text-zinc-300">
                    {r.has_active_subscription ? (
                      <span>{formatTokens(r.subscription_tokens_remaining)} <span className="text-zinc-500">/ {formatTokens(r.subscription_token_limit)}</span></span>
                    ) : (
                      <span className="text-zinc-600">--</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-zinc-500">{relTime(r.created_at)}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => { setGrantTarget(r); setGrantAmount('') }}
                      className="inline-flex items-center gap-1 rounded-lg bg-zinc-800 px-2.5 py-1 text-[11px] font-medium text-zinc-200 hover:bg-zinc-700"
                    >
                      <Zap size={11} /> Grant
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {grantTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded-xl border border-zinc-800 bg-zinc-900 p-6">
            <h3 className="mb-1 text-sm font-semibold text-zinc-100">Grant Tokens</h3>
            <p className="mb-3 text-xs text-zinc-500">{grantTarget.company_name}</p>
            <p className="mb-3 text-[11px] text-zinc-500">
              Current: {formatTokens(grantTarget.free_tokens_remaining)} remaining of {formatTokens(grantTarget.free_token_limit)}
            </p>
            <div className="mb-4 flex gap-2">
              {[100_000, 500_000, 1_000_000, 5_000_000].map((amt) => (
                <button
                  key={amt}
                  onClick={() => setGrantAmount(String(amt))}
                  className={`rounded px-2 py-1 text-[10px] font-medium transition-colors ${
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
              className="mb-4 w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-600"
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setGrantTarget(null)} className="rounded-lg px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200">
                Cancel
              </button>
              <button
                onClick={handleGrant}
                disabled={!grantAmount || granting}
                className="flex items-center gap-1.5 rounded-lg bg-emerald-700 px-4 py-1.5 text-xs font-medium text-white hover:bg-emerald-600 disabled:opacity-40"
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

export default function MatchaWork() {
  const [tab, setTab] = useState<Tab>('personal')

  return (
    <div className="p-6">
      <h1 className="mb-1 text-lg font-semibold text-zinc-100">Matcha-Work</h1>
      <p className="mb-4 text-xs text-zinc-500">Personal and business workspace plans.</p>

      <div className="mb-5 flex gap-1 border-b border-zinc-800">
        <button
          onClick={() => setTab('personal')}
          className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors ${
            tab === 'personal' ? 'border-b-2 border-emerald-500 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
          }`}
        >
          <User size={14} /> Personal
        </button>
        <button
          onClick={() => setTab('business')}
          className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors ${
            tab === 'business' ? 'border-b-2 border-emerald-500 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
          }`}
        >
          <Building2 size={14} /> Business
        </button>
      </div>

      {tab === 'personal' ? <Individuals /> : <BusinessWork />}
    </div>
  )
}
