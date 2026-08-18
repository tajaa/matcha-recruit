import { useState, useEffect } from 'react'
import { AlertTriangle, Building2, Clock, Loader2, AlertCircle } from 'lucide-react'
import { ClientTable, HandbookCoverageList, SetupStatusGrid } from '../../components/broker/dashboard'
import { useToast } from '../../components/ui'
import OutreachDrawer from '../../components/broker/action-center/OutreachDrawer'
import { PageHeader } from '../../components/broker/PageHeader'
import { KpiTile } from '../../components/broker/KpiTile'
import { RiskPosturePanel } from '../../components/broker/RiskPosturePanel'
import { fetchBrokerPortfolio, fetchBrokerHandbookCoverage, fetchWcPortfolio, setClientRenewalDate } from '../../api/broker/broker'
import { daysUntilDate } from '../../utils/broker/brokerFormat'
import type {
  BrokerPortfolioResponse,
  BrokerHandbookCoverage,
  WcPortfolioResponse,
  WcPortfolioRow,
} from '../../types/broker'

/** Same threshold RenewalPill bands critical — renewing in under 60 days. */
const RENEWAL_URGENT_DAYS = 60

type Filter = 'at_risk' | 'renewal' | null

export default function BrokerDashboard() {
  const [portfolio, setPortfolio] = useState<BrokerPortfolioResponse | null>(null)
  const [wc, setWc] = useState<WcPortfolioResponse | null>(null)
  const [handbooks, setHandbooks] = useState<BrokerHandbookCoverage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [outreach, setOutreach] = useState<{ id: string; name: string } | null>(null)
  const [filter, setFilter] = useState<Filter>(null)
  const { toast } = useToast()

  useEffect(() => {
    Promise.allSettled([
      fetchBrokerPortfolio().then(setPortfolio),
      fetchWcPortfolio().then(setWc),
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
  const atRisk = summary?.at_risk_companies ?? 0
  const companies = portfolio?.companies ?? []
  const renewalUrgent = companies.filter((c) => {
    const days = daysUntilDate(c.renewal_date)
    return days !== null && days < RENEWAL_URGENT_DAYS
  })

  // WC merge: map by company_id.
  const wcByCompany = new Map<string, WcPortfolioRow>(
    (wc?.companies ?? []).map((r) => [r.company_id, r]),
  )

  const filteredCompanies =
    filter === 'at_risk' ? companies.filter((c) => c.risk_signal === 'at_risk')
    : filter === 'renewal' ? renewalUrgent
    : companies

  const filterLabel = filter === 'at_risk' ? 'At-Risk Clients' : filter === 'renewal' ? `Renewal Urgency (< ${RENEWAL_URGENT_DAYS}d)` : null

  return (
    <div className="space-y-5">
      <PageHeader
        title="Book of Business"
        subtitle="Account performance across your referred clients."
      />

      {/* Portfolio KPIs — At-Risk and Renewal Urgency double as filter toggles for the table below. */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <KpiTile label="Total Clients" value={summary?.total_linked_companies ?? 0} icon={Building2} />
        <KpiTile
          label="At-Risk Clients"
          value={atRisk}
          icon={AlertTriangle}
          tone={atRisk > 0 ? 'text-red-400' : 'text-zinc-100'}
          urgent={atRisk > 0}
          selected={filter === 'at_risk'}
          onClick={() => setFilter((f) => f === 'at_risk' ? null : 'at_risk')}
        />
        <KpiTile
          label="Renewal Urgency"
          value={renewalUrgent.length}
          icon={Clock}
          sub={`< ${RENEWAL_URGENT_DAYS} days`}
          tone={renewalUrgent.length > 0 ? 'text-red-400' : 'text-zinc-100'}
          urgent={renewalUrgent.length > 0}
          selected={filter === 'renewal'}
          onClick={() => setFilter((f) => f === 'renewal' ? null : 'renewal')}
        />
      </div>

      {/* WC claim-depth chip strip */}
      <RiskPosturePanel wc={wc} />

      {/* Main content: accounts table + setup pipeline */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-2">
          {filterLabel && (
            <div className="flex items-center gap-2 text-xs text-zinc-400 px-1">
              <span>Filtered: {filterLabel}</span>
              <button type="button" onClick={() => setFilter(null)} className="text-sky-400 hover:text-sky-300">
                Clear
              </button>
            </div>
          )}
          <ClientTable
            companies={filteredCompanies}
            wcByCompany={wcByCompany}
            onOutreach={(id, name) => setOutreach({ id, name })}
            onSetRenewal={(id, date) => {
              setClientRenewalDate(id, date).then((res) => {
                setPortfolio((p) => p && ({
                  ...p,
                  companies: p.companies.map((c) =>
                    c.company_id === id
                      ? { ...c, renewal_date: res.renewal_date, renewal_date_source: res.renewal_date_source }
                      : c
                  ),
                }))
              }).catch(() => toast('Could not update the renewal date', 'error'))
            }}
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
