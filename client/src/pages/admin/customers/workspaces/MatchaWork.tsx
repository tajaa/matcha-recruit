/* eslint-disable react-hooks/set-state-in-effect -- Effects intentionally synchronize this tool with loaded data, URL selections, and preview inputs. */
import { AdminButton as Button, AdminInput as Input, AdminSelect, AdminTable } from '../../../../components/admin/AdminUI'
import { AdminList, AdminMetricRow, AdminPagination } from '../../../../components/admin/AdminList'
import { useAdminPagination } from '../../../../components/admin/useAdminPagination'
import { AdminTabs as PillTabs } from '../../../../components/admin/AdminTabs'
import { AdminPageHeader } from '../../../../components/admin/AdminPageHeader'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, Users, Zap } from 'lucide-react'
import { api } from '../../../../api/client'
import { Modal, useToast } from '../../../../components/ui'
import Individuals from './Individuals'

type Tab = 'personal' | 'business'

type BusinessCompany = {
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

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${Math.round(value / 1_000)}K`
  return String(value)
}

function fmtDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'
}

function CompanyStatus({ status }: { status: string }) {
  const active = status === 'active' || status === 'approved'
  return <span className={`inline-block rounded border px-1.5 py-0.5 text-[10px] capitalize ${active ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'border-zinc-600 bg-zinc-700/30 text-zinc-400'}`}>{status}</span>
}

function BusinessWork() {
  const { toast } = useToast()
  const [rows, setRows] = useState<BusinessCompany[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [sort, setSort] = useState('name')
  const [grantTarget, setGrantTarget] = useState<BusinessCompany | null>(null)
  const [grantAmount, setGrantAmount] = useState('')
  const [granting, setGranting] = useState(false)

  function fetchRows() {
    setLoading(true)
    api.get<BusinessCompany[]>('/matcha-work/billing/admin/matcha-work/business')
      .then(setRows)
      .catch(() => toast('Could not load Matcha Work businesses', 'error'))
      .finally(() => setLoading(false))
  }

  useEffect(fetchRows, [])

  async function handleGrant() {
    if (!grantTarget || !grantAmount) return
    const amount = Number.parseInt(grantAmount, 10)
    if (!Number.isFinite(amount) || amount <= 0) return
    setGranting(true)
    try {
      await api.post(`/matcha-work/billing/admin/companies/${grantTarget.company_id}/tokens`, {
        tokens: amount,
        description: `Admin grant to business: ${grantTarget.company_name}`,
      })
      toast(`${formatTokens(amount)} tokens granted to ${grantTarget.company_name}`, 'success')
      setGrantTarget(null)
      setGrantAmount('')
      fetchRows()
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Token grant failed', 'error')
    } finally {
      setGranting(false)
    }
  }

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return rows.filter((row) => {
      const active = row.company_status === 'active' || row.company_status === 'approved'
      return (!query || row.company_name.toLowerCase().includes(query) || (row.signup_source ?? '').toLowerCase().includes(query))
        && (status === 'all' || (status === 'active' ? active : !active))
    }).sort((a, b) => {
      if (sort === 'tokens') return (a.free_tokens_remaining + a.subscription_tokens_remaining) - (b.free_tokens_remaining + b.subscription_tokens_remaining) || a.company_id.localeCompare(b.company_id)
      if (sort === 'newest') return (b.created_at ? new Date(b.created_at).getTime() : 0) - (a.created_at ? new Date(a.created_at).getTime() : 0) || a.company_id.localeCompare(b.company_id)
      return a.company_name.localeCompare(b.company_name) || a.company_id.localeCompare(b.company_id)
    })
  }, [rows, search, status, sort])
  const pagination = useAdminPagination(filtered, JSON.stringify([search, status, sort]))

  const totals = useMemo(() => ({
    members: rows.reduce((sum, row) => sum + row.member_count, 0),
    subscriptions: rows.filter((row) => row.has_active_subscription).length,
    remaining: rows.reduce((sum, row) => sum + row.free_tokens_remaining + row.subscription_tokens_remaining, 0),
  }), [rows])

  if (loading && rows.length === 0) return <div className="flex min-h-32 items-center justify-center gap-2 text-sm text-zinc-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading businesses…</div>

  return (
    <div>
      <AdminMetricRow items={[
        { label: 'Businesses', value: rows.length }, { label: 'Members', value: totals.members },
        { label: 'Subscriptions', value: totals.subscriptions }, { label: 'Tokens remaining', value: formatTokens(totals.remaining) },
      ]} />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Input aria-label="Search business workspaces" placeholder="Search company or signup source…" value={search} onChange={(event) => setSearch(event.target.value)} className="max-w-xs py-1.5! text-xs!" />
        <AdminSelect aria-label="Business status" value={status} onChange={(event) => setStatus(event.target.value)} className="py-1.5! text-xs!"><option value="all">All statuses</option><option value="active">Active</option><option value="other">Other statuses</option></AdminSelect>
        <AdminSelect aria-label="Sort business workspaces" value={sort} onChange={(event) => setSort(event.target.value)} className="py-1.5! text-xs!"><option value="name">Name A–Z</option><option value="newest">Newest first</option><option value="tokens">Lowest token balance</option></AdminSelect>
        <Button variant="ghost" onClick={fetchRows} disabled={loading} className="sm:ml-auto">Refresh</Button>
      </div>
      <AdminPagination pagination={pagination} />
        <AdminTable className="min-w-[850px]">
          <thead >
            <tr><th >Company</th><th >Status</th><th className="text-right">Members</th><th >Free tokens</th><th >Subscription tokens</th><th >Created</th><th className="text-right">Actions</th></tr>
          </thead>
          <tbody >
            {pagination.rows.map((row) => (
              <tr key={row.company_id} className="text-zinc-300 hover:bg-zinc-900/30">
                <td ><Link to={`/admin/companies/${row.company_id}`} className="font-medium text-zinc-100 hover:text-emerald-400">{row.company_name}</Link>{row.signup_source && <p className="mt-0.5 text-[10px] uppercase tracking-wider text-zinc-500">{row.signup_source.replaceAll('_', ' ')}</p>}</td>
                <td ><CompanyStatus status={row.company_status} /></td>
                <td className="text-right tabular-nums"><span className="inline-flex items-center gap-1"><Users className="h-3 w-3 text-zinc-500" />{row.member_count}</span></td>
                <td className="text-zinc-300"><span className={row.free_tokens_remaining === 0 ? 'text-amber-400' : ''}>{formatTokens(row.free_tokens_remaining)}</span><span className="text-zinc-600"> / {formatTokens(row.free_token_limit)}</span></td>
                <td className="text-zinc-300">{row.has_active_subscription ? <><span>{formatTokens(row.subscription_tokens_remaining)}</span><span className="text-zinc-600"> / {formatTokens(row.subscription_token_limit)}</span></> : <span className="text-zinc-600">—</span>}</td>
                <td className="text-zinc-400">{fmtDate(row.created_at)}</td>
                <td className="text-right"><Button size="sm" variant="ghost" onClick={() => { setGrantTarget(row); setGrantAmount('') }}><Zap className="h-3.5 w-3.5" /> Grant tokens</Button></td>
              </tr>
            ))}
            {filtered.length === 0 && <tr><td colSpan={7} className="text-center text-zinc-500">No Matcha Work businesses found.</td></tr>}
          </tbody>
        </AdminTable>

      <Modal open={grantTarget != null} onClose={() => setGrantTarget(null)} title={grantTarget ? `Grant tokens — ${grantTarget.company_name}` : ''} width="sm">
        {grantTarget && <div className="space-y-4"><p className="text-sm text-zinc-400">Current free balance: {formatTokens(grantTarget.free_tokens_remaining)} of {formatTokens(grantTarget.free_token_limit)}</p><div className="flex flex-wrap gap-2">{[100_000, 500_000, 1_000_000, 5_000_000].map((amount) => <button key={amount} onClick={() => setGrantAmount(String(amount))} className={`rounded-lg border px-2.5 py-1.5 text-xs font-medium ${grantAmount === String(amount) ? 'border-emerald-500 bg-emerald-500/10 text-emerald-300' : 'border-zinc-700 text-zinc-400 hover:text-zinc-200'}`}>+{formatTokens(amount)}</button>)}</div><Input label="Custom token amount" inputMode="numeric" value={grantAmount} onChange={(event) => setGrantAmount(event.target.value.replace(/\D/g, ''))} /><div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setGrantTarget(null)}>Cancel</Button><Button variant="primary" disabled={!grantAmount || granting} onClick={handleGrant}>{granting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />} Grant tokens</Button></div></div>}
      </Modal>
    </div>
  )
}

export default function MatchaWork() {
  const [tab, setTab] = useState<Tab>('personal')
  return (
    <AdminList>
      <AdminPageHeader
        title="Matcha Work"
        description="Manage personal accounts, business workspaces, subscriptions, access, and token budgets."
      />
      <PillTabs className="mb-4!" options={[{ value: 'personal', label: 'Personal accounts' }, { value: 'business', label: 'Business workspaces' }]} value={tab} onChange={setTab} />
      {tab === 'personal' ? <Individuals embedded /> : <BusinessWork />}
    </AdminList>
  )
}
