import { useNavigate } from 'react-router-dom'
import { Card, Badge } from '../ui'
import type {
  CredentialExpirationSummary,
  CredentialExpiration,
} from '../../types/dashboard'

interface CredentialAlertsProps {
  summary: CredentialExpirationSummary
  expirations: CredentialExpiration[]
}

const SEV_CLASSES: Record<string, string> = {
  expired: 'text-red-400',
  critical: 'text-amber-400',
  warning: 'text-yellow-400',
}

export function CredentialAlerts({ summary, expirations }: CredentialAlertsProps) {
  const navigate = useNavigate()
  const total = summary.expired + summary.critical + summary.warning

  if (total === 0) return null

  return (
    <Card className="p-5">
      <h3 className="text-sm font-medium text-zinc-200 mb-3">Credential Alerts</h3>

      <div className="flex gap-2 mb-4">
        {summary.expired > 0 && (
          <Badge variant="danger">{summary.expired} Expired</Badge>
        )}
        {summary.critical > 0 && (
          <Badge variant="warning">{summary.critical} Critical</Badge>
        )}
        {summary.warning > 0 && (
          <Badge variant="neutral">{summary.warning} Warning</Badge>
        )}
      </div>

      <div className="space-y-2">
        {expirations.slice(0, 5).map((c, i) => (
          <div key={i} className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-sm text-zinc-200 truncate">{c.employee_name}</p>
              <p className="text-[11px] text-zinc-500 truncate">{c.credential_label}</p>
            </div>
            <span className={`text-xs font-mono shrink-0 ml-3 ${SEV_CLASSES[c.severity] || 'text-zinc-500'}`}>
              {c.expiry_date}
            </span>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={() => navigate('/app/employees')}
        className="mt-3 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        View All Employees &rarr;
      </button>
    </Card>
  )
}
