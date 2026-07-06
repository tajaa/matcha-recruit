import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Building2, Loader2, AlertCircle } from 'lucide-react'
import { Card } from '../../components/ui'
import { HelpHint } from '../../components/broker/HelpHint'
import { fetchPropertyPortfolio } from '../../api/broker'
import type { PropertyPortfolioRow, PropertyPortfolioResponse } from '../../types/broker'

const COPE_TONE: Record<string, string> = { A: 'text-emerald-400', B: 'text-zinc-200', C: 'text-amber-400', D: 'text-red-400' }
const CAT_TONE: Record<string, string> = {
  severe: 'text-red-400', high: 'text-red-400', elevated: 'text-amber-400', moderate: 'text-emerald-400', low: 'text-emerald-400',
}

function fmtUsd(n: number | null): string {
  if (n == null) return '—'
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`
  if (Math.abs(n) >= 1_000) return `$${Math.round(n / 1000)}K`
  return `$${Math.round(n)}`
}

export default function BrokerPropertyPortfolio() {
  const [data, setData] = useState<PropertyPortfolioResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetchPropertyPortfolio().then(setData).catch(() => setError(true)).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  if (error || !data) return (
    <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
      <AlertCircle className="h-8 w-8 mb-2" /><p className="text-sm">Unable to load the property book.</p>
    </div>
  )

  const { summary: s, companies } = data

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <Building2 className="h-5 w-5 text-zinc-400" /> Property Book
          <HelpHint text="Your clients' commercial-property posture across the book — total insured value (TIV), COPE construction grade, insurance-to-value, and worst catastrophe tier. Worst COPE + biggest TIV first." />
        </h1>
        <p className="text-sm text-zinc-500 mt-1">Per-client buildings, values, and catastrophe exposure.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="p-4"><div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Clients with property</div><div className="text-3xl font-light font-mono mt-1 text-zinc-200">{s.client_count}</div></Card>
        <Card className="p-4"><div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Total insured value</div><div className="text-3xl font-light font-mono mt-1 text-zinc-100">{fmtUsd(s.total_tiv)}</div></Card>
        <Card className="p-4"><div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Under-insured</div><div className={`text-3xl font-light font-mono mt-1 ${s.under_insured_clients ? 'text-amber-400' : 'text-zinc-200'}`}>{s.under_insured_clients}</div><div className="text-[10px] text-zinc-600">clients below 90% ITV</div></Card>
        <Card className="p-4"><div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">High cat exposure</div><div className={`text-3xl font-light font-mono mt-1 ${s.severe_cat_clients ? 'text-red-400' : 'text-zinc-200'}`}>{s.severe_cat_clients}</div><div className="text-[10px] text-zinc-600">severe / high peril</div></Card>
      </div>

      {companies.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-sm text-zinc-400">No clients have a Statement of Values yet.</p>
          <p className="text-xs text-zinc-600 mt-1">Property appears here once a client adds buildings under Commercial Property.</p>
        </Card>
      ) : (
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-800/60 bg-zinc-900/40 text-[11px] text-zinc-500 uppercase tracking-wider">
                <th className="px-4 py-2.5">Client</th>
                <th className="px-4 py-2.5 text-right">Buildings</th>
                <th className="px-4 py-2.5 text-right">TIV</th>
                <th className="px-4 py-2.5 text-center">COPE</th>
                <th className="px-4 py-2.5 text-right">ITV</th>
                <th className="px-4 py-2.5 text-center">Cat</th>
              </tr>
            </thead>
            <tbody>
              {companies.map((c: PropertyPortfolioRow) => {
                const itv = c.itv_ratio != null ? Math.round(c.itv_ratio * 100) : null
                return (
                  <tr key={c.company_id} className="border-b border-zinc-800/30 last:border-0 hover:bg-zinc-900/30">
                    <td className="px-4 py-3">
                      <Link to={`/broker/clients/${c.company_id}`} className="text-zinc-100 font-medium hover:text-emerald-400 transition-colors">{c.company_name}</Link>
                      <div className="text-[11px] text-zinc-600">{c.industry ?? '—'}</div>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-zinc-300">{c.building_count}</td>
                    <td className="px-4 py-3 text-right font-mono text-zinc-300">{fmtUsd(c.tiv)}</td>
                    <td className="px-4 py-3 text-center"><span className={`font-mono font-semibold ${c.worst_cope_grade ? COPE_TONE[c.worst_cope_grade] ?? 'text-zinc-400' : 'text-zinc-600'}`}>{c.worst_cope_grade ?? '—'}</span></td>
                    <td className={`px-4 py-3 text-right font-mono ${itv == null ? 'text-zinc-600' : itv < 90 ? 'text-amber-400' : 'text-emerald-400'}`}>{itv != null ? `${itv}%` : '—'}</td>
                    <td className="px-4 py-3 text-center text-xs">
                      {c.worst_cat_tier ? (
                        <div>
                          <span className={`uppercase font-semibold ${CAT_TONE[c.worst_cat_tier] ?? 'text-zinc-400'}`}>{c.worst_cat_tier}</span>
                          {(() => {
                            const prob = c.worst_peril ? c.by_peril_detail?.[c.worst_peril]?.annual_probability : null
                            return prob != null ? <div className="text-[9px] text-zinc-600 normal-case">{(prob * 100).toFixed(1)}% annual</div> : null
                          })()}
                        </div>
                      ) : <span className="text-zinc-600">—</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
