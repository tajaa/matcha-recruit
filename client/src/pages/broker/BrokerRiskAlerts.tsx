import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Loader2, Check, CheckCircle2, Lightbulb, Sparkles } from 'lucide-react'
import { fetchBrokerRiskAlerts, markBrokerRiskAlertRead, scanBrokerThemeAlerts } from '../../api/broker'
import TabHeader from '../../components/broker/action-center/TabHeader'
import type { BrokerRiskAlert, BrokerRiskMetricKey } from '../../types/broker'

const isTheme = (a: BrokerRiskAlert) => a.kind === 'theme' || a.metric_key.startsWith('theme:')
function metricLabel(a: BrokerRiskAlert): string {
  if (isTheme(a)) return 'Risk theme'
  return METRIC_LABEL[a.metric_key] ?? a.metric_key
}
function metricCategory(a: BrokerRiskAlert): string | undefined {
  if (isTheme(a)) return 'Safety theme'
  return CATEGORY[a.metric_key]
}

// behavioral_friction intentionally omitted — the Behavioral Friction & Retention
// Risk section was retired 2026-06-08 (EB-broker feature, low value). Those alerts
// are filtered out in load() so they never render here.
const METRIC_LABEL: Partial<Record<BrokerRiskMetricKey, string>> = {
  trir: 'TRIR',
  dart: 'DART rate',
  lost_days: 'Lost workdays',
  claim_free_broken: 'Claim-free streak',
  premium_increase: 'Premium impact',
}

// Risk categories — P&C safety metrics. Shown as a subtle tag.
const CATEGORY: Partial<Record<BrokerRiskMetricKey, string>> = {
  trir: 'Property & Casualty',
  dart: 'Property & Casualty',
  lost_days: 'Property & Casualty',
  claim_free_broken: 'Property & Casualty',
  premium_increase: 'Property & Casualty',
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
  const [scanning, setScanning] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchBrokerRiskAlerts(includeResolved)
      // Behavioral Friction & Retention Risk section retired — drop those alerts.
      setAlerts(res.alerts.filter((a) => a.metric_key !== 'behavioral_friction'))
    } catch {
      setError('Failed to load risk alerts.')
    } finally {
      setLoading(false)
    }
  }

  // On mount, (re)generate qualitative risk-theme alerts from the clients' IR
  // themes (runs in FastAPI), then reload so they appear alongside trend alerts.
  useEffect(() => {
    let cancelled = false
    setScanning(true)
    scanBrokerThemeAlerts()
      .catch(() => {})
      .finally(() => { if (!cancelled) { setScanning(false); load() } })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
    <div className="space-y-4">
      <TabHeader
        icon={AlertTriangle}
        title="Risk Alerts"
        hint="Safety / Workers Comp metrics trending negative across your book."
        badge={activeUnread > 0 ? (
          <span className="px-2 py-0.5 rounded-full bg-red-500/15 text-red-400 text-xs font-medium">
            {activeUnread} new
          </span>
        ) : null}
        actions={
          <div className="flex items-center gap-3">
            {scanning && (
              <span className="flex items-center gap-1 text-[11px] text-emerald-400/80">
                <Loader2 className="w-3 h-3 animate-spin" /> Scanning risk themes…
              </span>
            )}
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
        }
      />

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
            <div key={g.company_id} className="rounded-xl border border-white/[0.06] bg-zinc-950 overflow-hidden">
              <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
                <Link
                  to={`/broker/clients/${g.company_id}`}
                  className="text-sm font-medium text-zinc-100 hover:text-emerald-400"
                >
                  {g.name}
                </Link>
                <span className="text-xs text-zinc-600">{g.rows.length} alert{g.rows.length !== 1 ? 's' : ''}</span>
              </div>
              <div className="divide-y divide-white/[0.06]">
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
                          <span className="text-xs font-medium text-zinc-300 inline-flex items-center gap-1">
                            {isTheme(a) && <Sparkles className="w-3 h-3 text-emerald-400" />}
                            {metricLabel(a)}
                          </span>
                          {metricCategory(a) && (
                            <span className="px-1.5 py-0.5 rounded bg-white/[0.06] text-[9px] uppercase tracking-wider text-zinc-500">
                              {metricCategory(a)}
                            </span>
                          )}
                          {!a.is_read && !a.resolved_at && (
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          )}
                        </div>
                        <p className="text-sm text-zinc-400 mt-0.5">{a.message}</p>
                        {a.suggestion && (
                          <p className="text-[11px] text-emerald-300/90 mt-1 flex items-start gap-1">
                            <Lightbulb className="w-3 h-3 mt-0.5 shrink-0" />
                            <span><span className="text-emerald-400 font-medium">Suggested:</span> {a.suggestion}</span>
                          </p>
                        )}
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
