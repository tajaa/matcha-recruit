import { useNavigate } from 'react-router-dom'
import { Card } from '../ui'
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
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-red-900/30 text-red-400 border border-red-800/40">
            <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
            {summary.expired} Expired
          </span>
        )}
        {summary.critical > 0 && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-amber-900/30 text-amber-400 border border-amber-800/40">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
            {summary.critical} Critical
          </span>
        )}
        {summary.warning > 0 && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-yellow-900/30 text-yellow-400 border border-yellow-800/40">
            <span className="w-1.5 h-1.5 rounded-full bg-yellow-400" />
            {summary.warning} Warning
          </span>
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
