import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { WcMetrics } from './risk/IRWcMetricsCard'
import type { IRLeadingIndicators } from '../../types/ir'

/**
 * Top-of-dashboard KPI strip. Surfaces the safety numbers that previously
 * only appeared if the user opened the Risk Insights tab — TRIR, DART,
 * days-since-recordable — plus the leading indicators (near-miss ratio,
 * open corrective actions). Best-effort: a failed fetch just hides the tile.
 */
type Tile = {
  label: string
  value: string
  sub?: string
  tone?: 'default' | 'good' | 'warn' | 'bad'
}

const TONE: Record<NonNullable<Tile['tone']>, string> = {
  default: 'text-zinc-100',
  good: 'text-emerald-400',
  warn: 'text-amber-400',
  bad: 'text-red-400',
}

export function IRKpiStrip() {
  const [wc, setWc] = useState<WcMetrics | null>(null)
  const [li, setLi] = useState<IRLeadingIndicators | null>(null)

  useEffect(() => {
    api.get<WcMetrics>('/ir/incidents/analytics/wc-metrics')
      .then(setWc)
      .catch(() => setWc(null))
    api.get<IRLeadingIndicators>('/ir/incidents/analytics/leading-indicators')
      .then(setLi)
      .catch(() => setLi(null))
  }, [])

  if (!wc && !li) return null

  const fmt = (n: number | null | undefined) => (n === null || n === undefined ? '—' : String(n))

  const tiles: Tile[] = []
  if (wc) {
    tiles.push({
      label: 'TRIR',
      value: fmt(wc.trir),
      sub: wc.benchmark ? `industry ${wc.benchmark.trir}` : 'trailing 12 mo',
      tone:
        wc.trir === null ? 'default'
          : wc.benchmark && wc.trir > wc.benchmark.trir ? 'bad'
          : wc.benchmark ? 'good' : 'default',
    })
    tiles.push({ label: 'DART', value: fmt(wc.dart_rate), sub: 'rate per 100' })
    tiles.push({
      label: 'Days since recordable',
      value: wc.days_since_last_recordable === null ? '—' : String(wc.days_since_last_recordable),
      sub: wc.ever_recordable ? 'streak' : 'none on record',
      tone: (wc.days_since_last_recordable ?? 0) > 90 ? 'good' : 'default',
    })
  }
  if (li) {
    tiles.push({
      label: 'Open actions',
      value: String(li.corrective_actions_open),
      sub: li.corrective_actions_overdue > 0 ? `${li.corrective_actions_overdue} overdue` : 'on track',
      tone: li.corrective_actions_overdue > 0 ? 'bad' : 'default',
    })
    tiles.push({
      label: 'Near-miss ratio',
      value: li.near_miss_to_recordable_ratio === null ? '—' : `${li.near_miss_to_recordable_ratio}:1`,
      sub: `${li.near_miss_count} near-misses`,
      tone: (li.near_miss_to_recordable_ratio ?? 0) >= 5 ? 'good' : 'default',
    })
  }

  return (
    <section>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {tiles.map((t) => (
          <div key={t.label} className="bg-zinc-900 border border-white/10 rounded-2xl px-4 py-3">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold truncate">{t.label}</div>
            <div className={`text-2xl font-semibold mt-1 ${TONE[t.tone ?? 'default']}`}>{t.value}</div>
            {t.sub && <div className="text-[11px] text-zinc-500 mt-0.5 truncate">{t.sub}</div>}
          </div>
        ))}
      </div>
    </section>
  )
}
