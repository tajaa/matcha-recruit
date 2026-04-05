import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../../components/ui'
import { Plus, FileSignature, Zap } from 'lucide-react'

import { useMe } from '../../hooks/useMe'
import { fetchDashboardStats, fetchDashboardFlags } from '../../api/dashboard'

import {
  ProfileBanner,
  GettingStarted,
  FlagsTable,
} from '../../components/dashboard'

import type { DashboardStats, DashboardFlagsResponse } from '../../types/dashboard'

export default function Dashboard() {
  const { me, loading: meLoading, hasFeature } = useMe()
  const navigate = useNavigate()

  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [flagsData, setFlagsData] = useState<DashboardFlagsResponse | null>(null)
  const [flagsRefreshing, setFlagsRefreshing] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (meLoading) return

    Promise.allSettled([
      fetchDashboardStats().then(setStats).catch(() => setStats(null)),
      fetchDashboardFlags().then(setFlagsData).catch(() => setFlagsData(null)),
    ]).finally(() => setLoading(false))
  }, [meLoading])

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
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-zinc-100">
              Command Center
            </h1>
            <span className="flex items-center gap-1.5 rounded-full bg-emerald-950/60 border border-emerald-800/30 px-2.5 py-0.5 text-[10px] font-medium text-emerald-400/90 uppercase tracking-wider">
              <Zap className="h-2.5 w-2.5" /> Live
            </span>
          </div>
          <p className="text-sm text-zinc-600 mt-1">AI-analyzed risk flags and recommended actions.</p>
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

      {/* Quick setup nudge */}
      {hasZeroEmployees && hasZeroPolicies && (
        <div className="mb-8 rounded-xl border border-zinc-800/60 bg-zinc-900/40 p-5 flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="flex-1">
            <p className="text-sm font-medium text-zinc-200">Quick Setup</p>
            <p className="text-xs text-zinc-500 mt-0.5">
              Import employees and create your first policy to unlock the full dashboard.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 sm:gap-4">
            <Button size="sm" variant="secondary" onClick={() => navigate('/app/employees')}>
              Import Employees
            </Button>
            <Button size="sm" onClick={() => navigate('/app/handbooks')}>
              Create Policy
            </Button>
          </div>
        </div>
      )}

      {/* Flags & Actions — the main dashboard content */}
      <FlagsTable
        flags={flagsData?.flags ?? []}
        heatMap={flagsData?.heat_map ?? []}
        totalFlags={flagsData?.total_flags ?? 0}
        criticalCount={flagsData?.critical_count ?? 0}
        analyzedAt={flagsData?.analyzed_at ?? null}
        refreshing={flagsRefreshing}
        onRefresh={async () => {
          setFlagsRefreshing(true)
          try {
            const fresh = await fetchDashboardFlags(true)
            setFlagsData(fresh)
          } catch {}
          setFlagsRefreshing(false)
        }}
      />
    </div>
  )
}
