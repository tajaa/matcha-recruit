import { useEffect, useState } from 'react'
import { Card, Badge } from '../../components/ui'
import { api } from '../../api/client'
import { Users, Shield, FileText, AlertTriangle } from 'lucide-react'

type DashboardStats = {
  total_employees: number
  active_policies: number
  compliance_rate: number
  pending_incidents: { id: string; title: string; severity: string }[]
  incident_summary: { total_open: number; critical: number; high: number }
  stale_policies: { stale_count: number } | null
  critical_compliance_alerts: number
  warning_compliance_alerts: number
}

const severityBadge = (severity: string) => {
  if (severity === 'critical') return <Badge variant="danger">Critical</Badge>
  if (severity === 'high') return <Badge variant="warning">High</Badge>
  return <Badge variant="neutral">{severity}</Badge>
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get<DashboardStats>('/dashboard/stats')
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-sm text-zinc-500">Loading...</p>
  if (!stats) return <p className="text-sm text-zinc-500">Failed to load dashboard.</p>

  const statCards = [
    { label: 'Employees', value: stats.total_employees, icon: Users },
    { label: 'Active Policies', value: stats.active_policies, icon: FileText },
    { label: 'Compliance', value: `${Math.round(stats.compliance_rate)}%`, icon: Shield },
    { label: 'Open Incidents', value: stats.incident_summary.total_open, icon: AlertTriangle },
  ]

  return (
    <div>
      <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">
        Dashboard
      </h1>
      <p className="mt-2 text-sm text-zinc-500">Overview of your organization.</p>

      {/* Stat cards */}
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map((s) => (
          <Card key={s.label} className="flex items-center gap-4 p-5">
            <div className="rounded-lg bg-zinc-800 p-2.5">
              <s.icon className="h-5 w-5 text-emerald-400" />
            </div>
            <div>
              <p className="text-2xl font-semibold text-zinc-100">{s.value}</p>
              <p className="text-xs text-zinc-500">{s.label}</p>
            </div>
          </Card>
        ))}
      </div>

      {/* Alerts row */}
      {(stats.critical_compliance_alerts > 0 || (stats.stale_policies?.stale_count ?? 0) > 0) && (
        <div className="mt-6 flex gap-4">
          {stats.critical_compliance_alerts > 0 && (
            <Card className="flex-1 p-5">
              <p className="text-sm font-medium text-red-400">
                {stats.critical_compliance_alerts} compliance alert{stats.critical_compliance_alerts > 1 ? 's' : ''}
              </p>
              <p className="text-xs text-zinc-500 mt-1">Requires immediate attention</p>
            </Card>
          )}
          {(stats.stale_policies?.stale_count ?? 0) > 0 && (
            <Card className="flex-1 p-5">
              <p className="text-sm font-medium text-amber-400">
                {(stats.stale_policies?.stale_count ?? 0)} stale polic{(stats.stale_policies?.stale_count ?? 0) > 1 ? 'ies' : 'y'}
              </p>
              <p className="text-xs text-zinc-500 mt-1">Review and update recommended</p>
            </Card>
          )}
        </div>
      )}

      {/* Pending incidents */}
      {stats.pending_incidents.length > 0 && (
        <div className="mt-6">
          <h2 className="text-sm font-medium text-zinc-300 mb-3">Pending Incidents</h2>
          <Card className="p-0 divide-y divide-zinc-800">
            {stats.pending_incidents.map((inc) => (
              <div key={inc.id} className="flex items-center justify-between px-5 py-3">
                <p className="text-sm text-zinc-200">{inc.title}</p>
                {severityBadge(inc.severity)}
              </div>
            ))}
          </Card>
        </div>
      )}
    </div>
  )
}
