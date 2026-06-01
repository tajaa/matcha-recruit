import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Loader2, Check, CheckCircle2 } from 'lucide-react'
import { fetchBrokerRiskAlerts, markBrokerRiskAlertRead } from '../../api/broker'
import type { BrokerRiskAlert, BrokerRiskMetricKey } from '../../types/broker'

const METRIC_LABEL: Record<BrokerRiskMetricKey, string> = {
  trir: 'TRIR',
  dart: 'DART rate',
  lost_days: 'Lost workdays',
  claim_free_broken: 'Claim-free streak',
  premium_increase: 'Premium impact',
  behavioral_friction: 'Behavioral Friction & Retention Risk',
}

// Risk categories — P&C safety metrics vs the workforce-retention signal.
// Shown as a subtle tag so EB brokers can spot the new category at a glance.
const CATEGORY: Record<BrokerRiskMetricKey, string> = {
  trir: 'Property & Casualty',
  dart: 'Property & Casualty',
  lost_days: 'Property & Casualty',
  claim_free_broken: 'Property & Casualty',
  premium_increase: 'Property & Casualty',
  behavioral_friction: 'Workforce Retention',
}

const SEVERITY_TONE: Record<string, { bg: string; text: string; label: string }> = {
  critical: { bg: 'bg-red-500/10 border-red-500/20', text: 'text-red-400', label: 'Critical' },
  warning: { bg: 'bg-amber-500/10 border-amber-500/20', text: 'text-amber-400', label: 'Warning' },
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function BrokerRiskAlerts() {
  const [alerts, setAlerts] = useState<BrokerRiskAlert[]>([])
  const [loading, setLoading] = useState(true)
  const [includeResolved, setIncludeResolved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchBrokerRiskAlerts(includeResolved)
      setAlerts(res.alerts)
    } catch {
      setError('Failed to load risk alerts.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [includeResolved])

  const onMarkRead = async (id: string) => {
    setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, is_read: true } : a)))
    try {
      await markBrokerRiskAlertRead(id)
    } catch {
      // revert on failure
      setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, is_read: false } : a)))
    }
  }

  // Group alerts by company for a scannable layout.
  const grouped = useMemo(() => {
    const map = new Map<string, { name: string; rows: BrokerRiskAlert[] }>()
    for (const a of alerts) {
      const g = map.get(a.company_id) ?? { name: a.company_name, rows: [] }
      g.rows.push(a)
      map.set(a.company_id, g)
    }
    return Array.from(map.entries()).map(([company_id, v]) => ({ company_id, ...v }))
  }, [alerts])

  const activeUnread = alerts.filter((a) => !a.is_read && !a.resolved_at).length

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-400" />
            Risk Alerts
            {activeUnread > 0 && (
              <span className="ml-1 px-2 py-0.5 rounded-full bg-red-500/15 text-red-400 text-xs font-medium">
                {activeUnread} new
              </span>
            )}
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            Clients whose safety / Workers&nbsp;Comp metrics trended negative, or whose workforce shows a
            sudden spike in behavioral friction &amp; retention risk.
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={includeResolved}
            onChange={(e) => setIncludeResolved(e.target.checked)}
            className="accent-emerald-500"
          />
          Show resolved
        </label>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20 text-zinc-500">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : error ? (
        <div className="text-center py-20 text-red-400 text-sm">{error}</div>
      ) : grouped.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
          <CheckCircle2 className="w-10 h-10 text-emerald-500/60 mb-3" />
          <p className="text-sm">No negative trends across your portfolio.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {grouped.map((g) => (
            <div key={g.company_id} className="rounded-xl border border-white/5 bg-zinc-900/40 overflow-hidden">
              <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
                <Link
                  to={`/broker/clients/${g.company_id}`}
                  className="text-sm font-medium text-zinc-100 hover:text-emerald-400"
                >
                  {g.name}
                </Link>
                <span className="text-xs text-zinc-600">{g.rows.length} alert{g.rows.length !== 1 ? 's' : ''}</span>
              </div>
              <div className="divide-y divide-white/5">
                {g.rows.map((a) => {
                  const tone = SEVERITY_TONE[a.severity] ?? SEVERITY_TONE.warning
                  return (
                    <div
                      key={a.id}
                      className={`px-4 py-3 flex items-start gap-3 ${a.resolved_at ? 'opacity-50' : ''}`}
                    >
                      <span className={`mt-0.5 px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase tracking-wide ${tone.bg} ${tone.text}`}>
                        {tone.label}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-zinc-300">
                            {METRIC_LABEL[a.metric_key] ?? a.metric_key}
                          </span>
                          {CATEGORY[a.metric_key] && (
                            <span className="px-1.5 py-0.5 rounded bg-white/5 text-[9px] uppercase tracking-wider text-zinc-500">
                              {CATEGORY[a.metric_key]}
                            </span>
                          )}
                          {!a.is_read && !a.resolved_at && (
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          )}
                        </div>
                        <p className="text-sm text-zinc-400 mt-0.5">{a.message}</p>
                        <p className="text-[11px] text-zinc-600 mt-1">
                          {a.resolved_at ? `Resolved ${fmtDate(a.resolved_at)}` : `Flagged ${fmtDate(a.last_alerted_at)}`}
                        </p>
                      </div>
                      {!a.is_read && !a.resolved_at && (
                        <button
                          onClick={() => onMarkRead(a.id)}
                          className="text-zinc-500 hover:text-emerald-400 p-1"
                          title="Mark read"
                        >
                          <Check className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
