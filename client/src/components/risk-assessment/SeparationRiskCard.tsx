import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { ShieldAlert } from 'lucide-react'
import {
  BAND_COLOR, BAND_LABEL, getBandForScore,
  type Band, type PreTermAnalytics,
} from '../../types/risk-assessment'

const OUTCOME_COLORS: Record<string, string> = {
  proceeded: '#ef4444',
  modified: '#f59e0b',
  abandoned: '#10b981',
  pending: '#71717a',
}

const OUTCOME_LABELS: Record<string, string> = {
  proceeded: 'Proceeded',
  modified: 'Modified',
  abandoned: 'Abandoned',
  pending: 'Pending',
}

export function SeparationRiskCard() {
  const [analytics, setAnalytics] = useState<PreTermAnalytics | null>(null)

  useEffect(() => {
    api.get<PreTermAnalytics>('/employees/pre-termination-checks/analytics?period=12m')
      .then(setAnalytics)
      .catch(() => {}) // Graceful degradation
  }, [])

  if (!analytics || analytics.total_checks === 0) return null

  const avgBand = getBandForScore(analytics.avg_score)
  const overrideRateColor = analytics.override_rate > 25
    ? 'text-red-400'
    : analytics.override_rate > 10
    ? 'text-amber-400'
    : 'text-emerald-400'

  const highCritical = (analytics.by_band['high'] || 0) + (analytics.by_band['critical'] || 0)

  const bandTotal = Object.values(analytics.by_band).reduce((sum, n) => sum + n, 0) || 1
  const bandEntries: { band: Band; count: number; pct: number }[] = (
    ['low', 'moderate', 'high', 'critical'] as Band[]
  ).map(band => ({
    band,
    count: analytics.by_band[band] || 0,
    pct: ((analytics.by_band[band] || 0) / bandTotal) * 100,
  }))

  const outcomeEntries = Object.entries(analytics.by_outcome)
    .filter(([, count]) => count > 0)
    .sort(([, a], [, b]) => b - a)

  const topFlags = analytics.most_common_red_flags.slice(0, 5)

  return (
    <div>
      <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-4">Separation Analytics</div>
      <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 flex flex-col gap-6">
        {/* Header */}
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-orange-400" />
          <span className="text-sm text-zinc-200 font-medium">Separation Risk</span>
          <span className="text-[9px] text-zinc-600 font-mono uppercase tracking-widest ml-auto">{analytics.period} period</span>
        </div>

        {/* Key Metrics */}
        <div className="grid grid-cols-4 gap-px bg-white/10 rounded-lg overflow-hidden">
          <div className="bg-zinc-800 px-3 py-2">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Checks Run</div>
            <div className="mt-1 text-xl font-light font-mono text-zinc-200">{analytics.total_checks}</div>
          </div>
          <div className="bg-zinc-800 px-3 py-2">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Avg Risk Score</div>
            <div className={`mt-1 text-xl font-light font-mono ${BAND_COLOR[avgBand].text}`}>
              {Math.round(analytics.avg_score)}
            </div>
          </div>
          <div className="bg-zinc-800 px-3 py-2">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Override Rate</div>
            <div className={`mt-1 text-xl font-light font-mono ${overrideRateColor}`}>
              {Math.round(analytics.override_rate)}%
            </div>
          </div>
          <div className="bg-zinc-800 px-3 py-2">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">High / Critical</div>
            <div className={`mt-1 text-xl font-light font-mono ${highCritical > 0 ? 'text-orange-400' : 'text-zinc-300'}`}>
              {highCritical}
            </div>
          </div>
        </div>

        {/* Band Distribution */}
        <div>
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-2">Band Distribution</div>
          <div className="h-3 w-full flex rounded-lg overflow-hidden">
            {bandEntries.map(({ band, pct }) => (
              pct > 0 ? (
                <div
                  key={band}
                  className={`${BAND_COLOR[band].bar} transition-all duration-500`}
                  style={{ width: `${pct}%` }}
                  title={`${BAND_LABEL[band]}: ${analytics.by_band[band] || 0}`}
                />
              ) : null
            ))}
          </div>
          <div className="flex gap-4 mt-2">
            {bandEntries.map(({ band, count }) => (
              <div key={band} className="flex items-center gap-1.5 text-[9px] text-zinc-500">
                <span className={`w-1.5 h-1.5 rounded-full ${BAND_COLOR[band].dot}`} />
                <span>{BAND_LABEL[band]}</span>
                <span className="font-mono text-zinc-400">{count}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Most Common Red Flags */}
          {topFlags.length > 0 && (
            <div>
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-2">Top Red Flags</div>
              <div className="flex flex-col gap-1.5">
                {topFlags.map((flag, i) => {
                  const maxCount = topFlags[0].count
                  const barWidth = maxCount > 0 ? (flag.count / maxCount) * 100 : 0
                  return (
                    <div key={i} className="flex items-center gap-3 text-[11px]">
                      <span className="text-zinc-400 capitalize w-24 truncate shrink-0">{flag.dimension.replace(/_/g, ' ')}</span>
                      <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden">
                        <div className="h-full bg-orange-500/60 rounded-full" style={{ width: `${barWidth}%` }} />
                      </div>
                      <span className="font-mono text-zinc-400 w-6 text-right shrink-0">{flag.count}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Outcome Distribution */}
          {outcomeEntries.length > 0 && (
            <div>
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-2">Outcome Distribution</div>
              <div className="flex flex-col gap-1.5">
                {outcomeEntries.map(([outcome, count]) => (
                  <div key={outcome} className="flex items-center justify-between text-[11px]">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: OUTCOME_COLORS[outcome] || '#71717a' }}
                      />
                      <span className="text-zinc-400 capitalize">{OUTCOME_LABELS[outcome] || outcome.replace(/_/g, ' ')}</span>
                    </div>
                    <span className="font-mono text-zinc-300">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
