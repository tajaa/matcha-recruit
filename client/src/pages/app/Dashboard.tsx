import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Zap } from 'lucide-react'
import { Button } from '../../components/ui'

import { useMe } from '../../hooks/useMe'
import { fetchDashboardStats, fetchDashboardFlags, analyzeDashboardFlags } from '../../api/dashboard'

import {
  ProfileBanner,
  GettingStarted,
  FlagsTable,
} from '../../components/dashboard'

import type { DashboardStats, DashboardFlagsResponse } from '../../types/dashboard'

export default function Dashboard() {
  const { me, loading: meLoading } = useMe()
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
      <div className="flex items-center gap-4 mb-8 flex-wrap">
        <h1 className="text-2xl font-semibold text-vsc-text">Command Center</h1>
        <span className="flex items-center gap-1.5 rounded-full bg-amber-950/60 border border-amber-800/30 px-2.5 py-0.5 text-[10px] font-medium text-amber-400/80 uppercase tracking-wider">
          <Zap className="h-2.5 w-2.5" /> Live
        </span>
        <div className="flex items-center gap-2 ml-auto">
          <div className="rounded-lg border border-vsc-border bg-vsc-panel px-4 py-2 flex items-center gap-3">
            <p className="text-[10px] font-medium uppercase tracking-wider text-vsc-text/50">Open Flags</p>
            <p className="text-xl font-bold text-vsc-text">{flagsData?.total_flags ?? 0}</p>
          </div>
          <div className={`rounded-lg border px-4 py-2 flex items-center gap-3 ${
            (flagsData?.critical_count ?? 0) > 0 ? 'border-sev-critical-border bg-sev-critical-bg' : 'border-vsc-border bg-vsc-panel'
          }`}>
            <p className="text-[10px] font-medium uppercase tracking-wider text-vsc-text/50">Critical</p>
            <p className={`text-xl font-bold ${(flagsData?.critical_count ?? 0) > 0 ? 'text-sev-critical' : 'text-vsc-text'}`}>
              {flagsData?.critical_count ?? 0}
            </p>
          </div>
        </div>
      </div>

      {/* Quick setup nudge */}
      {hasZeroEmployees && hasZeroPolicies && (
        <div className="mb-8 rounded-xl border border-vsc-border bg-vsc-panel p-5 flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="flex-1">
            <p className="text-sm font-medium text-vsc-text">Quick Setup</p>
            <p className="text-xs text-vsc-text/50 mt-0.5">
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
            await analyzeDashboardFlags()
            const fresh = await fetchDashboardFlags()
            setFlagsData(fresh)
          } catch {}
          setFlagsRefreshing(false)
        }}
      />
    </div>
  )
}
