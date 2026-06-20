import { useState, useEffect } from 'react'
import { Users, AlertTriangle, Building2, Loader2, AlertCircle } from 'lucide-react'
import { StatCard } from '../../components/dashboard'
import { ClientTable, HandbookCoverageList, SetupStatusGrid } from '../../components/broker-dashboard'
import OutreachDrawer from '../../components/broker/action-center/OutreachDrawer'
import { fetchBrokerPortfolio, fetchBrokerHandbookCoverage, fetchWcPortfolio, fetchEplPortfolio } from '../../api/broker'
import { fmtMoney } from '../../utils/brokerFormat'
import type {
  BrokerPortfolioResponse,
  BrokerHandbookCoverage,
  WcPortfolioResponse,
  WcPortfolioRow,
  EplPortfolioResponse,
} from '../../types/broker'

const SAFETY_BANDS: Array<{ key: keyof WcPortfolioResponse['summary']; label: string; tone: string }> = [
  { key: 'critical', label: 'Critical', tone: 'text-red-400' },
  { key: 'at_risk',  label: 'At Risk',  tone: 'text-orange-400' },
  { key: 'fair',     label: 'Fair',     tone: 'text-amber-400' },
  { key: 'good',     label: 'Good',     tone: 'text-emerald-400' },
]

export default function BrokerDashboard() {
  const [portfolio, setPortfolio] = useState<BrokerPortfolioResponse | null>(null)
  const [wc, setWc] = useState<WcPortfolioResponse | null>(null)
  const [epl, setEpl] = useState<EplPortfolioResponse | null>(null)
  const [handbooks, setHandbooks] = useState<BrokerHandbookCoverage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [outreach, setOutreach] = useState<{ id: string; name: string } | null>(null)

  useEffect(() => {
    Promise.allSettled([
      fetchBrokerPortfolio().then(setPortfolio),
      fetchWcPortfolio().then(setWc),
      fetchEplPortfolio().then(setEpl),
      fetchBrokerHandbookCoverage().then(setHandbooks),
    ]).then((results) => {
      // Only hard-fail if the core portfolio fetch (first) rejected.
      if (results[0].status === 'rejected') setError(true)
    }).finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 text-zinc-500 animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
        <AlertCircle className="h-8 w-8 mb-2" />
        <p className="text-sm">Unable to load portfolio data. Please try again later.</p>
      </div>
    )
  }

  const summary = portfolio?.summary
  const totalEmployees = portfolio?.companies.reduce((s, c) => s + c.active_employee_count, 0) ?? 0

  // WC merge: map by company_id; net annual premium exposure across the book.
  const wcByCompany = new Map<string, WcPortfolioRow>(
    (wc?.companies ?? []).map((r) => [r.company_id, r]),
  )
  const netPremiumExposure = (wc?.companies ?? []).reduce(
    (s, r) => s + (r.premium_impact?.annual_impact_dollars ?? 0), 0,
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight">Book of Business</h1>
        <p className="text-sm text-zinc-500 mt-1">Account performance across your referred clients.</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard
          label="Total Clients"
          value={summary?.total_linked_companies ?? 0}
          icon={Building2}
        />
        <StatCard
          label="Total Employees"
          value={totalEmployees}
          icon={Users}
        />
        <StatCard
          label="At-Risk Clients"
          value={summary?.at_risk_companies ?? 0}
          icon={AlertTriangle}
          urgent={(summary?.at_risk_companies ?? 0) > 0}
        />
      </div>

      {/* Safety posture strip (WC bands + net premium exposure) */}
      {wc && wc.summary.client_count > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
          {SAFETY_BANDS.map((b) => {
            const v = wc.summary[b.key] as number
            return (
              <div key={b.key} className="bg-zinc-900 px-4 py-4">
                <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{b.label}</div>
                <div className={`text-2xl font-light font-mono mt-1.5 ${v > 0 ? b.tone : 'text-zinc-700'}`}>{v}</div>
              </div>
            )
          })}
          <div className="bg-zinc-900 px-4 py-4">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Recordables</div>
            <div className="text-2xl font-light font-mono mt-1.5 text-zinc-300">{wc.summary.total_recordable_cases}</div>
          </div>
          <div className="bg-zinc-900 px-4 py-4">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Premium Δ</div>
            <div className={`text-2xl font-light font-mono mt-1.5 ${
              netPremiumExposure > 0 ? 'text-red-400' : netPremiumExposure < 0 ? 'text-emerald-400' : 'text-zinc-300'
            }`}>
              {netPremiumExposure > 0 ? '+' : ''}{fmtMoney(netPremiumExposure)}
            </div>
          </div>
        </div>
      )}

      {/* WC claim-depth strip (cumulative trauma, post-term, open lost-time, rate pressure) */}
      {wc && wc.summary.client_count > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
          {([
            { label: 'Cumulative Trauma', value: wc.summary.total_ct_cases ?? 0, tone: 'text-red-400' },
            { label: 'Post-Termination', value: wc.summary.total_post_termination ?? 0, tone: 'text-red-400' },
            { label: 'Open Lost-Time', value: wc.summary.total_open_lost_time ?? 0, tone: 'text-orange-400' },
            { label: 'Clients · Rate ↑ States', value: wc.summary.clients_in_rate_increase_states ?? 0, tone: 'text-amber-400' },
          ] as const).map((c) => (
            <div key={c.label} className="bg-zinc-900 px-4 py-4">
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{c.label}</div>
              <div className={`text-2xl font-light font-mono mt-1.5 ${c.value > 0 ? c.tone : 'text-zinc-700'}`}>{c.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* EPL readiness strip (avg score + band distribution across the book) */}
      {epl && epl.summary.client_count > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
          <div className="bg-zinc-900 px-4 py-4">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">EPL Avg</div>
            <div className="text-2xl font-light font-mono mt-1.5 text-zinc-200">{epl.summary.avg_score}</div>
          </div>
          {([
            { label: 'EPL Strong', value: epl.summary.strong, tone: 'text-emerald-400' },
            { label: 'Adequate', value: epl.summary.adequate, tone: 'text-amber-400' },
            { label: 'Developing', value: epl.summary.developing, tone: 'text-orange-400' },
            { label: 'Exposed', value: epl.summary.exposed, tone: 'text-red-400' },
          ] as const).map((c) => (
            <div key={c.label} className="bg-zinc-900 px-4 py-4">
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{c.label}</div>
              <div className={`text-2xl font-light font-mono mt-1.5 ${c.value > 0 ? c.tone : 'text-zinc-700'}`}>{c.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Main content: table + sidebar widgets */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <ClientTable
            companies={portfolio?.companies ?? []}
            wcByCompany={wcByCompany}
            onOutreach={(id, name) => setOutreach({ id, name })}
          />
        </div>
        <div className="space-y-4">
          <SetupStatusGrid counts={portfolio?.setup_status_counts ?? {}} />
        </div>
      </div>

      {/* Handbook coverage */}
      <HandbookCoverageList handbooks={handbooks} />

      {outreach && (
        <OutreachDrawer companyId={outreach.id} companyName={outreach.name} onClose={() => setOutreach(null)} />
      )}
    </div>
  )
}
