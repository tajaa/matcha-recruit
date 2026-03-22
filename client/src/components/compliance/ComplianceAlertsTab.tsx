import { useState } from 'react'
import { Badge } from '../ui'
import type { ComplianceAlert, ComplianceActionPlanUpdate } from '../../types/compliance'
import { CATEGORY_LABELS } from '../../types/compliance'

type Props = {
  alerts: ComplianceAlert[]
  loading: boolean
  onMarkRead: (alertId: string) => void
  onDismiss: (alertId: string) => void
  onUpdateActionPlan: (alertId: string, data: ComplianceActionPlanUpdate) => void
}

function getConfidenceLabel(score: number | null) {
  if (score === null || score === undefined) return null
  const pct = Math.round(score * 100)
  if (score >= 0.6) return { label: `${pct}%`, color: 'text-emerald-400' }
  if (score >= 0.3) return { label: `${pct}%`, color: 'text-amber-400' }
  return { label: `${pct}%`, color: 'text-red-400' }
}

export function ComplianceAlertsTab({ alerts, loading, onMarkRead, onDismiss, onUpdateActionPlan: _onUpdateActionPlan }: Props) {
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set())
  const [showDismissed, setShowDismissed] = useState(false)

  const activeAlerts = alerts.filter((a) => a.status !== 'dismissed')
  const dismissedAlerts = alerts.filter((a) => a.status === 'dismissed')
  const displayAlerts = showDismissed ? alerts : activeAlerts

  if (loading) return <p className="text-sm text-zinc-500">Loading alerts...</p>

  function toggleSources(id: string) {
    setExpandedSources((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
          Alerts ({activeAlerts.length} active)
        </h2>
        {dismissedAlerts.length > 0 && (
          <button type="button" onClick={() => setShowDismissed(!showDismissed)}
            className="text-xs text-zinc-600 hover:text-zinc-300 transition-colors">
            {showDismissed ? 'Hide dismissed' : `Show ${dismissedAlerts.length} dismissed`}
          </button>
        )}
      </div>

      {displayAlerts.length === 0 ? (
        <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
          <p className="text-sm text-zinc-600">No alerts</p>
        </div>
      ) : (
        <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
          {displayAlerts.map((alert) => {
            const confidence = getConfidenceLabel(alert.confidence_score)
            const isDismissed = alert.status === 'dismissed'
            return (
              <div key={alert.id} className={`px-4 py-3 ${isDismissed ? 'opacity-50' : ''}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-medium text-zinc-200">{alert.title}</p>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                        alert.severity === 'critical' ? 'bg-red-900/20 text-red-400 border-red-800/40'
                        : alert.severity === 'warning' ? 'bg-amber-900/20 text-amber-400 border-amber-800/40'
                        : 'bg-zinc-800 text-zinc-400 border-zinc-700'
                      }`}>
                        {alert.severity}
                      </span>
                      {alert.alert_type && (
                        <span className="text-[10px] text-zinc-600">{alert.alert_type.replace(/_/g, ' ')}</span>
                      )}
                      {alert.category && (
                        <Badge variant="neutral">{CATEGORY_LABELS[alert.category] || alert.category}</Badge>
                      )}
                      {confidence && (
                        <span className={`text-[10px] font-mono ${confidence.color}`}>{confidence.label}</span>
                      )}
                    </div>
                    <p className="text-xs text-zinc-400 mt-1 leading-5">{alert.message}</p>

                    {alert.impact_summary && (
                      <div className="mt-2 px-3 py-2 bg-indigo-950/30 border border-indigo-800/30 rounded">
                        <span className="text-[10px] text-indigo-400 uppercase tracking-wide">Impact Summary</span>
                        <p className="text-xs text-zinc-200 mt-0.5 leading-5">{alert.impact_summary}</p>
                      </div>
                    )}

                    {alert.action_required && (
                      <div className="mt-2 px-3 py-2 bg-zinc-800/50 border border-zinc-700 rounded">
                        <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Required Action</span>
                        <p className="text-xs text-zinc-200 mt-0.5">{alert.action_required}</p>
                      </div>
                    )}

                    {alert.deadline && (
                      <p className="text-[11px] text-amber-400 mt-1">Deadline: {new Date(alert.deadline).toLocaleDateString()}</p>
                    )}

                    {(alert.affected_employee_count ?? 0) > 0 && (
                      <p className="text-[11px] text-zinc-500 mt-1">{alert.affected_employee_count} employees affected</p>
                    )}

                    {/* Verification sources */}
                    {alert.verification_sources && alert.verification_sources.length > 0 && (
                      <div className="mt-2">
                        <button type="button" onClick={() => toggleSources(alert.id)}
                          className="text-[11px] text-zinc-600 hover:text-zinc-400 transition-colors">
                          {expandedSources.has(alert.id) ? 'Hide' : 'Show'} {alert.verification_sources.length} source(s)
                        </button>
                        {expandedSources.has(alert.id) && (
                          <div className="mt-1.5 space-y-1">
                            {alert.verification_sources.map((src, i) => (
                              <div key={i} className="flex items-center gap-2">
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500 border border-zinc-700">{src.type}</span>
                                <a href={src.url} target="_blank" rel="noopener noreferrer"
                                  className="text-[11px] text-zinc-400 hover:text-zinc-200 transition-colors truncate">{src.name}</a>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {alert.source_url && (
                      <a href={alert.source_url} target="_blank" rel="noopener noreferrer"
                        className="text-[11px] text-zinc-500 hover:text-zinc-300 mt-1 inline-block transition-colors">
                        {alert.source_name || 'Source'} &rarr;
                      </a>
                    )}
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    <span className="text-[11px] text-zinc-600">{new Date(alert.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
                {!isDismissed && (
                  <div className="flex items-center gap-2 mt-2">
                    {alert.status === 'unread' && (
                      <button type="button" onClick={() => onMarkRead(alert.id)}
                        className="text-xs text-zinc-600 hover:text-zinc-300 px-2 py-1 transition-colors">Mark Read</button>
                    )}
                    <button type="button" onClick={() => onDismiss(alert.id)}
                      className="text-xs text-zinc-600 hover:text-zinc-300 px-2 py-1 transition-colors">Dismiss</button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
