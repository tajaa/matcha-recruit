import { useNavigate } from 'react-router-dom'
import { Card } from '../ui'
import { ChevronRight, CheckCircle2 } from 'lucide-react'
import type {
  PendingIncident,
  WageAlertSummary,
  CredentialExpirationSummary,
  ComplianceDashboardItem,
} from '../../types/dashboard'

interface PendingActionsProps {
  pendingIncidents: PendingIncident[]
  wageAlerts: WageAlertSummary | null
  credentialSummary?: CredentialExpirationSummary | null
  complianceAlerts: number
  compliancePendingActions: ComplianceDashboardItem[]
}

const SEV_DOT: Record<string, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  warning: 'bg-amber-500',
  medium: 'bg-yellow-500',
  low: 'bg-blue-400',
  info: 'bg-zinc-500',
}

interface ActionRow {
  key: string
  severity: string
  title: string
  subtitle: string
  href: string
}

export function PendingActions({
  pendingIncidents,
  wageAlerts,
  credentialSummary,
  complianceAlerts,
  compliancePendingActions,
}: PendingActionsProps) {
  const navigate = useNavigate()

  const rows: ActionRow[] = []

  // Compliance actions (top-3 by severity + SLA)
  const sortedCompliance = [...compliancePendingActions]
    .filter((a) => a.action_status !== 'actioned')
    .sort((a, b) => {
      const sevOrder: Record<string, number> = { critical: 0, warning: 1, info: 2 }
      const sa = sevOrder[a.severity] ?? 3
      const sb = sevOrder[b.severity] ?? 3
      if (sa !== sb) return sa - sb
      return (a.days_until ?? 999) - (b.days_until ?? 999)
    })
    .slice(0, 3)

  for (const item of sortedCompliance) {
    rows.push({
      key: `comp-${item.legislation_id}`,
      severity: item.severity,
      title: item.title,
      subtitle: item.location_name + (item.days_until != null ? ` \u00b7 ${item.days_until}d` : ''),
      href: '/app/compliance',
    })
  }

  // Compliance alert count
  if (complianceAlerts > 0 && rows.length === 0) {
    rows.push({
      key: 'comp-alerts',
      severity: 'critical',
      title: `${complianceAlerts} compliance alert${complianceAlerts > 1 ? 's' : ''}`,
      subtitle: 'Requires immediate attention',
      href: '/app/compliance',
    })
  }

  // Pending incidents
  for (const inc of pendingIncidents.slice(0, 2)) {
    rows.push({
      key: `inc-${inc.id}`,
      severity: inc.severity || 'medium',
      title: inc.title,
      subtitle: inc.incident_number,
      href: `/app/ir/${inc.id}`,
    })
  }

  // Wage alerts
  if (wageAlerts && (wageAlerts.hourly_violations > 0 || wageAlerts.salary_violations > 0)) {
    const total = wageAlerts.hourly_violations + wageAlerts.salary_violations
    rows.push({
      key: 'wages',
      severity: 'warning',
      title: `${total} wage violation${total > 1 ? 's' : ''} across ${wageAlerts.locations_affected} location${wageAlerts.locations_affected > 1 ? 's' : ''}`,
      subtitle: `${wageAlerts.hourly_violations} hourly, ${wageAlerts.salary_violations} salary`,
      href: '/app/compliance',
    })
  }

  // Credential alerts
  if (credentialSummary) {
    const total = credentialSummary.expired + credentialSummary.critical + credentialSummary.warning
    if (total > 0) {
      rows.push({
        key: 'creds',
        severity: credentialSummary.expired > 0 ? 'critical' : 'warning',
        title: `${total} credential${total > 1 ? 's' : ''} expiring or expired`,
        subtitle: [
          credentialSummary.expired > 0 && `${credentialSummary.expired} expired`,
          credentialSummary.critical > 0 && `${credentialSummary.critical} critical`,
          credentialSummary.warning > 0 && `${credentialSummary.warning} warning`,
        ].filter(Boolean).join(', '),
        href: '/app/employees',
      })
    }
  }

  return (
    <Card className="p-0">
      <div className="px-5 pt-4 pb-3">
        <h3 className="text-sm font-medium text-zinc-200">Pending Actions</h3>
      </div>
      {rows.length === 0 ? (
        <div className="flex items-center gap-2 px-5 pb-4 text-emerald-500">
          <CheckCircle2 className="h-4 w-4" />
          <span className="text-sm">All caught up</span>
        </div>
      ) : (
        <div className="divide-y divide-zinc-800">
          {rows.map((row) => (
            <button
              key={row.key}
              type="button"
              onClick={() => navigate(row.href)}
              className="flex items-center gap-3 w-full px-5 py-3 text-left hover:bg-zinc-800/50 transition-colors"
            >
              <span className={`h-2 w-2 rounded-full shrink-0 ${SEV_DOT[row.severity] || SEV_DOT.info}`} />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-zinc-200 truncate">{row.title}</p>
                <p className="text-[11px] text-zinc-500 truncate">{row.subtitle}</p>
              </div>
              <ChevronRight className="h-4 w-4 text-zinc-600 shrink-0" />
            </button>
          ))}
        </div>
      )}
    </Card>
  )
}
