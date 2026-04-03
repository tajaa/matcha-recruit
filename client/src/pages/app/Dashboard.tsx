import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../../components/ui'
import {
  Shield, Briefcase, AlertTriangle, FileText,
  Plus, FileSignature, Zap, MessageSquareWarning,
} from 'lucide-react'

import { useMe } from '../../hooks/useMe'
import { fetchDashboardStats, fetchCredentialExpirations, fetchUpcoming } from '../../api/dashboard'
import { fetchPinnedRequirements, pinRequirement, fetchComplianceDashboard } from '../../api/compliance'
import { ComplianceWidget } from '../../components/compliance/ComplianceWidget'

import {
  StatCard,
  ProfileBanner,
  GettingStarted,
  ComplianceImpact,
  CompliancePinned,
  IncidentGrid,
  ActivityFeed,
  SignatureRing,
  CredentialAlerts,
  UpcomingDeadlines,
} from '../../components/dashboard'

import type { DashboardStats, CredentialExpirationsResponse, UpcomingResponse, ComplianceDashboard } from '../../types/dashboard'
import type { PinnedRequirement } from '../../types/compliance'

export default function Dashboard() {
  const { me, loading: meLoading, hasFeature, isHealthcare } = useMe()
  const navigate = useNavigate()

  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [credentials, setCredentials] = useState<CredentialExpirationsResponse | null>(null)
  const [upcoming, setUpcoming] = useState<UpcomingResponse | null>(null)
  const [pinned, setPinned] = useState<PinnedRequirement[]>([])
  const [complianceDash, setComplianceDash] = useState<ComplianceDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [pinnedLoading, setPinnedLoading] = useState(true)
  const [upcomingLoading, setUpcomingLoading] = useState(true)
  const [tab, setTab] = useState<'overview' | 'operations'>('overview')

  // Parallel data fetching once /me resolves
  useEffect(() => {
    if (meLoading) return

    const promises: Promise<void>[] = []

    promises.push(
      fetchDashboardStats()
        .then(setStats)
        .catch(() => setStats(null))
    )

    if (isHealthcare) {
      promises.push(
        fetchCredentialExpirations()
          .then(setCredentials)
          .catch(() => setCredentials(null))
      )
    }

    promises.push(
      fetchUpcoming()
        .then(setUpcoming)
        .catch(() => setUpcoming(null))
        .finally(() => setUpcomingLoading(false))
    )

    if (hasFeature('compliance')) {
      promises.push(
        fetchPinnedRequirements()
          .then(setPinned)
          .catch(() => setPinned([]))
          .finally(() => setPinnedLoading(false))
      )
      promises.push(
        fetchComplianceDashboard(90)
          .then(setComplianceDash)
          .catch(() => setComplianceDash(null))
      )
    } else {
      setPinnedLoading(false)
    }

    Promise.allSettled(promises).finally(() => setLoading(false))
  }, [meLoading, isHealthcare, hasFeature])

  const handleUnpin = async (id: string) => {
    try {
      await pinRequirement(id, false)
      setPinned((prev) => prev.filter((r) => r.id !== id))
    } catch { /* ignore */ }
  }

  if (meLoading || loading) {
    return <p className="text-sm text-zinc-500">Loading...</p>
  }

  const onboarding = me?.onboarding_needed ?? {}
  const enabledFeatures = me?.profile?.enabled_features ?? {}
  const isClient = me?.user?.role === 'client'
  const hasZeroEmployees = (stats?.total_employees ?? 0) === 0
  const hasZeroPolicies = (stats?.active_policies ?? 0) === 0

  return (
    <div>
      {/* Profile banner */}
      <ProfileBanner onboardingNeeded={onboarding} />

      {/* Getting started checklist */}
      {isClient && me?.user?.id && (
        <GettingStarted
          userId={me.user.id}
          onboardingNeeded={onboarding}
          enabledFeatures={enabledFeatures}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-zinc-100">
              Command Center
            </h1>
            <span className="flex items-center gap-1.5 rounded-full bg-emerald-950/60 border border-emerald-800/30 px-2.5 py-0.5 text-[10px] font-medium text-emerald-400/90 uppercase tracking-wider">
              <Zap className="h-2.5 w-2.5" /> Live
            </span>
          </div>
          <p className="text-sm text-zinc-600 mt-1">Monitor compliance, incidents, and team operations.</p>
        </div>
        <div className="flex gap-2">
          {hasFeature('policies') && (
            <Button size="sm" variant="secondary" onClick={() => navigate('/app/handbooks')}>
              <Plus className="h-3.5 w-3.5" /> New Policy
            </Button>
          )}
          {hasFeature('offer_letters') && (
            <Button size="sm" variant="secondary" onClick={() => navigate('/app/offer-letters')}>
              <FileSignature className="h-3.5 w-3.5" /> Create Offer
            </Button>
          )}
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-5 mb-8">
        <StatCard
          label="Compliance Alerts"
          value={(stats?.critical_compliance_alerts ?? 0) + (stats?.warning_compliance_alerts ?? 0)}
          subtitle={
            (stats?.critical_compliance_alerts ?? 0) + (stats?.warning_compliance_alerts ?? 0) > 0
              ? `${stats?.critical_compliance_alerts ?? 0} critical · ${stats?.warning_compliance_alerts ?? 0} warning`
              : 'All clear'
          }
          icon={Shield}
          href="/app/compliance"
          urgent={(stats?.critical_compliance_alerts ?? 0) > 0}
        />
        <StatCard
          label="Open ER Cases"
          value={stats?.er_case_summary?.open_cases ?? 0}
          subtitle={
            (stats?.er_case_summary?.open_cases ?? 0) > 0
              ? [
                  stats?.er_case_summary?.open && `${stats.er_case_summary.open} open`,
                  stats?.er_case_summary?.in_review && `${stats.er_case_summary.in_review} in review`,
                  stats?.er_case_summary?.pending_determination && `${stats.er_case_summary.pending_determination} pending`,
                ].filter(Boolean).join(' · ') || 'Open cases'
              : 'No open cases'
          }
          icon={Briefcase}
          href="/app/er-copilot"
        />
        <StatCard
          label="Open Incidents"
          value={stats?.incident_summary?.total_open ?? 0}
          subtitle={
            (stats?.incident_summary?.total_open ?? 0) > 0
              ? `${stats?.incident_summary?.critical ?? 0} critical · ${stats?.incident_summary?.high ?? 0} high`
              : 'No open incidents'
          }
          icon={AlertTriangle}
          href="/app/ir"
          urgent={(stats?.incident_summary?.critical ?? 0) > 0}
        />
        <StatCard
          label="Stale Policies"
          value={stats?.stale_policies?.stale_count ?? 0}
          subtitle={
            (stats?.stale_policies?.stale_count ?? 0) > 0
              ? `Oldest: ${stats?.stale_policies?.oldest_days ?? 0}d ago`
              : 'All up to date'
          }
          icon={FileText}
          href="/app/handbooks"
        />
        <StatCard
          label="Escalated Queries"
          value={stats?.escalated_queries_open ?? 0}
          subtitle={
            (stats?.escalated_queries_open ?? 0) > 0
              ? `${stats?.escalated_queries_high ?? 0} high severity`
              : 'No open escalations'
          }
          icon={MessageSquareWarning}
          href="/app/escalated-queries"
          urgent={(stats?.escalated_queries_high ?? 0) > 0}
        />
      </div>

      {/* Quick setup nudge */}
      {hasZeroEmployees && hasZeroPolicies && (
        <div className="mb-8 rounded-xl border border-zinc-800/60 bg-zinc-900/40 p-5 flex items-center gap-4">
          <div className="flex-1">
            <p className="text-sm font-medium text-zinc-200">Quick Setup</p>
            <p className="text-xs text-zinc-500 mt-0.5">
              Import employees and create your first policy to unlock the full dashboard.
            </p>
          </div>
          <Button size="sm" variant="secondary" onClick={() => navigate('/app/employees')}>
            Import Employees
          </Button>
          <Button size="sm" onClick={() => navigate('/app/handbooks')}>
            Create Policy
          </Button>
        </div>
      )}

      {/* Tab buttons */}
      <div className="flex gap-1 mb-8 border-b border-zinc-800/60 pb-px">
        {(['overview', 'operations'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-xs font-medium transition-colors relative ${
              tab === t
                ? 'text-zinc-100'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
            {tab === t && (
              <span className="absolute bottom-0 left-2 right-2 h-px bg-zinc-300 rounded-full" />
            )}
          </button>
        ))}
      </div>

      {/* Overview tab */}
      {tab === 'overview' && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
            <div className="lg:col-span-2 space-y-6">
              <ComplianceWidget />
              {isHealthcare && credentials && (
                <CredentialAlerts
                  summary={credentials.summary}
                  expirations={credentials.expirations}
                />
              )}
              <UpcomingDeadlines
                items={upcoming?.items ?? []}
                loading={upcomingLoading}
              />
            </div>
            <div>
              <SignatureRing
                rate={stats?.compliance_rate ?? 0}
                hasPolicies={(stats?.active_policies ?? 0) > 0}
              />
            </div>
          </div>

          {/* Full-width compliance section */}
          {pinned.length > 0 && (
            <div className="mb-6">
              <CompliancePinned
                items={pinned}
                loading={pinnedLoading}
                onUnpin={handleUnpin}
              />
            </div>
          )}

          {hasFeature('compliance') && (
            <div className="mb-6">
              <ComplianceImpact initialData={complianceDash} />
            </div>
          )}
        </>
      )}

      {/* Operations tab */}
      {tab === 'operations' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ActivityFeed activities={stats?.recent_activity ?? []} />
          <IncidentGrid summary={stats?.incident_summary ?? null} />
        </div>
      )}
    </div>
  )
}
