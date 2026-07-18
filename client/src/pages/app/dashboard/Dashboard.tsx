import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Zap } from 'lucide-react'
import { Button } from '../../../components/ui'

import { useMe } from '../../../hooks/useMe'
import { isIrOnlyTier } from '../../../utils/tier'
import { fetchDashboardStats, fetchDashboardFlags, analyzeDashboardFlags } from '../../../api/hr/dashboard'

import {
  ProfileBanner,
  GettingStarted,
  FlagsTable,
} from '../../../components/dashboard'

import type { DashboardStats, DashboardFlagsResponse } from '../../../types/dashboard'

export default function Dashboard() {
  const { me, loading: meLoading } = useMe()
  const navigate = useNavigate()

  const irOnly = isIrOnlyTier(me?.profile)

  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [flagsData, setFlagsData] = useState<DashboardFlagsResponse | null>(null)
  const [flagsRefreshing, setFlagsRefreshing] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (meLoading) return
    if (irOnly) {
      // Matcha Lite has no dashboard nav entry (IrSidebar's logo already
      // points at /app/ir) — skip the fetch and let the redirect below fire.
      setLoading(false)
      return
    }

    Promise.allSettled([
      fetchDashboardStats().then(setStats).catch(() => setStats(null)),
      fetchDashboardFlags().then(setFlagsData).catch(() => setFlagsData(null)),
    ]).finally(() => setLoading(false))
  }, [meLoading, irOnly])

  if (meLoading || loading) {
    return <p className="text-sm text-zinc-500">Loading...</p>
  }

  if (irOnly) {
    return <Navigate to="/app/ir" replace />
  }

  const onboarding = me?.onboarding_needed ?? {}
  const enabledFeatures = me?.profile?.enabled_features ?? {}
  const isClient = me?.user?.role === 'client'
  const hasZeroEmployees = (stats?.total_employees ?? 0) === 0
  const hasZeroPolicies = (stats?.active_policies ?? 0) === 0

  return (
    // Same frame as Compliance/Company: one bg-zinc-950 shell, masthead band,
    // content padded below. The stat chips and quick-setup nudge used to run
    // on vsc-panel/vsc-border — a separate token set (from the VS-Code-ish
    // editor palette) that isn't what any other /app page uses, so it read as
    // a slightly different app once you'd seen the framed pages. Rebuilt on
    // the same zinc-900/40 + white/[0.06] pattern as everywhere else.
    <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
      <div className="flex items-center gap-4 flex-wrap border-b border-white/[0.06] px-5 py-4">
        <h1 className="text-2xl font-light tracking-tight text-zinc-50">Command Center</h1>
        <span className="flex items-center gap-1.5 rounded-full bg-amber-500/10 border border-amber-500/20 px-2.5 py-0.5 text-[10px] font-medium text-amber-400 uppercase tracking-wider">
          <Zap className="h-2.5 w-2.5" /> Live
        </span>
        <div className="flex items-center gap-2 ml-auto">
          <div className="rounded-lg border border-white/[0.06] bg-zinc-900/40 px-4 py-2 flex items-center gap-3">
            <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-500">Open Flags</p>
            <p className="text-xl font-semibold font-mono tabular-nums text-zinc-100">{flagsData?.total_flags ?? 0}</p>
          </div>
          <div className={`rounded-lg border px-4 py-2 flex items-center gap-3 ${
            (flagsData?.critical_count ?? 0) > 0 ? 'border-red-500/30 bg-red-500/[0.06]' : 'border-white/[0.06] bg-zinc-900/40'
          }`}>
            <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-500">Critical</p>
            <p className={`text-xl font-semibold font-mono tabular-nums ${(flagsData?.critical_count ?? 0) > 0 ? 'text-red-400' : 'text-zinc-100'}`}>
              {flagsData?.critical_count ?? 0}
            </p>
          </div>
        </div>
      </div>

      <div className="p-5">
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

        {/* Quick setup nudge */}
        {hasZeroEmployees && hasZeroPolicies && (
          <div className="mb-6 rounded-lg border border-white/[0.06] bg-zinc-900/40 p-5 flex flex-col sm:flex-row sm:items-center gap-4">
            <div className="flex-1">
              <p className="text-sm font-medium text-zinc-100">Quick Setup</p>
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
          locations={flagsData?.locations ?? []}
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
    </div>
  )
}
