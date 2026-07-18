import { useEffect, useState } from 'react'
import { Loader2, ShieldCheck } from 'lucide-react'
import { Card } from '../../../components/ui'
import {
  fetchInsuranceBook, fetchInsuranceRenewals,
  type InsuranceBook, type Renewal,
} from '../../../api/broker/brokerInsurance'

type Tab = 'book' | 'renewals'
const TABS: { key: Tab; label: string }[] = [
  { key: 'book', label: 'Policies book' },
  { key: 'renewals', label: 'Renewals' },
]

const LINE_LABEL: Record<string, string> = {
  bop: "Business Owner's Policy", gl: 'General Liability', wc: "Workers' Comp", professional: 'Professional Liability',
}
function dollars(cents: number | null | undefined): string {
  return cents == null ? '—' : `$${(cents / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}

export default function BrokerInsurance() {
  const [tab, setTab] = useState<Tab>('book')
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-zinc-400" /> Insurance
        </h1>
        <p className="text-sm text-zinc-500 mt-1 max-w-2xl">
          Policies you've placed across your book, and renewals coming due. Quote and bind from a client's Insurance tab.
        </p>
      </div>

      <div className="flex gap-1 border-b border-zinc-800">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors ${tab === t.key ? 'text-zinc-100 border-b-2 border-zinc-100' : 'text-zinc-500 hover:text-zinc-300'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'book' && <BookTab />}
      {tab === 'renewals' && <RenewalsTab />}
    </div>
  )
}

function BookTab() {
  const [data, setData] = useState<InsuranceBook | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchInsuranceBook().then(setData).catch(() => setData(null)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />
  if (!data) return <p className="text-sm text-zinc-500">Unable to load the book.</p>

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4">
        <Kpi label="Policies placed" value={String(data.count)} />
        <Kpi label="Placed premium" value={dollars(data.total_premium_cents)} />
        <Kpi label="Est. commission" value={dollars(data.est_commission_cents)} tone="text-emerald-400" />
      </div>
      <Card className="p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
            <th className="py-2.5 px-4">Client</th><th>Line</th><th>Premium</th><th>Commission</th><th>Expires</th>
          </tr></thead>
          <tbody>
            {data.policies.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-zinc-600">No policies placed yet.</td></tr>}
            {data.policies.map((p) => (
              <tr key={p.id} className="border-b border-zinc-900">
                <td className="px-4 py-2.5 text-zinc-200">
                  {p.client_name || '—'}
                  {!p.on_platform && <span className="ml-2 text-[10px] text-zinc-500 uppercase tracking-wider">external</span>}
                </td>
                <td className="text-zinc-400">{LINE_LABEL[p.line] ?? p.line}</td>
                <td className="text-zinc-200">{dollars(p.premium_cents)}</td>
                <td className="text-emerald-400">{dollars(p.est_commission_cents)}<span className="text-[10px] text-zinc-500"> ({p.commission_bps ?? 0}bps)</span></td>
                <td className="text-zinc-400">{p.policy_expiry || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}

function RenewalsTab() {
  const [rows, setRows] = useState<Renewal[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(90)

  useEffect(() => {
    setLoading(true)
    fetchInsuranceRenewals(days).then((r) => setRows(r.renewals)).catch(() => setRows(null)).finally(() => setLoading(false))
  }, [days])

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {[30, 60, 90, 180].map((d) => (
          <button key={d} onClick={() => setDays(d)}
            className={`text-sm rounded-lg px-3 py-1.5 border ${days === d ? 'bg-zinc-100 text-zinc-900 border-zinc-100' : 'border-zinc-800 text-zinc-300 hover:border-zinc-600'}`}>
            {d}d
          </button>
        ))}
      </div>
      {loading ? <Spinner /> : !rows ? <p className="text-sm text-zinc-500">Unable to load renewals.</p> : (
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
              <th className="py-2.5 px-4">Client</th><th>Line</th><th>Premium</th><th>Expires</th>
            </tr></thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={4} className="px-4 py-6 text-zinc-600">No renewals in this window.</td></tr>}
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-zinc-900">
                  <td className="px-4 py-2.5 text-zinc-200">
                    {r.client_name || '—'}
                    {!r.on_platform && <span className="ml-2 text-[10px] text-zinc-500 uppercase tracking-wider">external</span>}
                  </td>
                  <td className="text-zinc-400">{LINE_LABEL[r.line] ?? r.line}</td>
                  <td className="text-zinc-200">{dollars(r.premium_cents)}</td>
                  <td className="text-amber-400">{r.policy_expiry || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 min-w-[140px]">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`text-xl font-mono mt-0.5 ${tone ?? 'text-zinc-100'}`}>{value}</div>
    </div>
  )
}
function Spinner() {
  return <div className="flex items-center justify-center h-40"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
}
