import { useState, useEffect } from 'react'
import { Users, AlertTriangle, Building2, Gauge, Loader2, AlertCircle } from 'lucide-react'
import { ClientTable, HandbookCoverageList, SetupStatusGrid } from '../../components/broker/dashboard'
import OutreachDrawer from '../../components/broker/action-center/OutreachDrawer'
import { PageHeader } from '../../components/broker/PageHeader'
import { KpiTile } from '../../components/broker/KpiTile'
import { RiskPosturePanel } from '../../components/broker/RiskPosturePanel'
import { fetchBrokerPortfolio, fetchBrokerHandbookCoverage, fetchWcPortfolio, fetchEplPortfolio } from '../../api/broker'
import { fetchRiskIndexPortfolio } from '../../api/riskIndex'
import type { RiskIndexPortfolio } from '../../types/riskIndex'
import type {
  BrokerPortfolioResponse,
  BrokerHandbookCoverage,
  WcPortfolioResponse,
  WcPortfolioRow,
  EplPortfolioResponse,
} from '../../types/broker'

export default function BrokerDashboard() {
  const [portfolio, setPortfolio] = useState<BrokerPortfolioResponse | null>(null)
  const [wc, setWc] = useState<WcPortfolioResponse | null>(null)
  const [epl, setEpl] = useState<EplPortfolioResponse | null>(null)
  const [riskIndex, setRiskIndex] = useState<RiskIndexPortfolio | null>(null)
  const [handbooks, setHandbooks] = useState<BrokerHandbookCoverage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [outreach, setOutreach] = useState<{ id: string; name: string } | null>(null)

  useEffect(() => {
    Promise.allSettled([
      fetchBrokerPortfolio().then(setPortfolio),
      fetchWcPortfolio().then(setWc),
      fetchEplPortfolio().then(setEpl),
      fetchRiskIndexPortfolio().then(setRiskIndex),
      fetchBrokerHandbookCoverage().then(setHandbooks),
    ]).then((results) => {
      // Only hard-fail if the core portfolio fetch (first) rejected.
      if (results[0].status === 'rejected') setError(true)
    }).finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex h-64 flex-col items-center justify-center text-zinc-500">
        <AlertCircle className="mb-2 h-8 w-8" />
        <p className="text-sm">Unable to load portfolio data. Please try again later.</p>
      </div>
    )
  }

  const summary = portfolio?.summary
  const totalEmployees = portfolio?.companies.reduce((s, c) => s + c.active_employee_count, 0) ?? 0
  const atRisk = summary?.at_risk_companies ?? 0

  // WC merge: map by company_id; net annual premium exposure across the book.
  const wcByCompany = new Map<string, WcPortfolioRow>(
    (wc?.companies ?? []).map((r) => [r.company_id, r]),
  )
  const netPremiumExposure = (wc?.companies ?? []).reduce(
    (s, r) => s + (r.premium_impact?.annual_impact_dollars ?? 0), 0,
  )

  const hasRiskIndex = !!riskIndex && riskIndex.summary.client_count > 0

  return (
    <div className="space-y-5">
      <PageHeader
        title="Book of Business"
        subtitle="Account performance across your referred clients."
      />

      {/* Portfolio KPIs */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiTile label="Total Clients" value={summary?.total_linked_companies ?? 0} icon={Building2} />
        <KpiTile label="Total Employees" value={totalEmployees} icon={Users} />
        <KpiTile
          label="At-Risk Clients"
          value={atRisk}
          icon={AlertTriangle}
          tone={atRisk > 0 ? 'text-red-400' : 'text-zinc-100'}
          urgent={atRisk > 0}
        />
        <KpiTile
          label="Risk Index"
          value={hasRiskIndex ? riskIndex!.summary.avg_index : '—'}
          icon={Gauge}
          sub="Composite 0–100 avg"
        />
      </div>

      {/* Unified risk posture (WC + EPL + composite index + claim depth) */}
      <RiskPosturePanel wc={wc} epl={epl} riskIndex={riskIndex} netPremiumExposure={netPremiumExposure} />

      {/* Main content: accounts table + setup pipeline */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
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
