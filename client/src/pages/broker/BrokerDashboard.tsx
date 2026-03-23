import { useState, useEffect } from 'react'
import { Users, AlertTriangle, Shield, Building2, Loader2, AlertCircle } from 'lucide-react'
import { StatCard, SignatureRing } from '../../components/dashboard'
import { ClientTable, HandbookCoverageList, SetupStatusGrid } from '../../components/broker-dashboard'
import { fetchBrokerPortfolio, fetchBrokerHandbookCoverage } from '../../api/broker'
import type { BrokerPortfolioResponse, BrokerHandbookCoverage } from '../../types/broker'

export default function BrokerDashboard() {
  const [portfolio, setPortfolio] = useState<BrokerPortfolioResponse | null>(null)
  const [handbooks, setHandbooks] = useState<BrokerHandbookCoverage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    Promise.allSettled([
      fetchBrokerPortfolio().then(setPortfolio),
      fetchBrokerHandbookCoverage().then(setHandbooks),
    ]).then((results) => {
      if (results.every((r) => r.status === 'rejected')) setError(true)
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight">Book of Business</h1>
        <p className="text-sm text-zinc-500 mt-1">Portfolio overview across your referred clients.</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
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
        <StatCard
          label="Avg Compliance"
          value={`${Math.round(summary?.average_policy_compliance_rate ?? 0)}%`}
          icon={Shield}
        />
      </div>

      {/* Main content: table + sidebar widgets */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <ClientTable companies={portfolio?.companies ?? []} />
        </div>
        <div className="space-y-4">
          <SignatureRing
            rate={summary?.average_policy_compliance_rate ?? 0}
            hasPolicies={(summary?.total_linked_companies ?? 0) > 0}
            title="Portfolio Compliance"
            label="Avg Rate"
            emptyLabel="No clients"
          />
          <SetupStatusGrid counts={portfolio?.setup_status_counts ?? {}} />
        </div>
      </div>

      {/* Handbook coverage */}
      <HandbookCoverageList handbooks={handbooks} />
    </div>
  )
}
