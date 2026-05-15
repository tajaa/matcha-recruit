import { HelpCircle, Shield, Calendar, Activity, Heart, TrendingDown, TrendingUp, Minus } from 'lucide-react'

export type WcMetrics = {
  period_days: number
  headcount: number | null
  hours_worked_assumed: number | null
  recordable_cases: number
  dart_cases: number
  lost_days: number
  restricted_days: number
  deaths: number
  trir: number | null
  dart_rate: number | null
  days_since_last_recordable: number | null
  ever_recordable: boolean
  prior: {
    recordable_cases: number
    dart_cases: number
    lost_days: number
    trir: number | null
    dart_rate: number | null
    trir_delta_pct: number | null
    dart_delta_pct: number | null
    lost_days_delta_pct: number | null
    recordable_delta_pct: number | null
  }
  data_quality: {
    insufficient_population: boolean
    headcount_missing: boolean
  }
  generated_at: string
}

function DeltaPill({ pct }: { pct: number | null }) {
  if (pct === null) return null
  const Icon = pct < -1 ? TrendingDown : pct > 1 ? TrendingUp : Minus
  // Lower is better for incident metrics, so negative delta = good (emerald).
  const tone = pct < -5 ? 'text-emerald-400' : pct > 5 ? 'text-red-400' : 'text-zinc-500'
  const sign = pct > 0 ? '+' : ''
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-mono ${tone}`}>
      <Icon className="w-3 h-3" />
      {sign}{pct.toFixed(0)}% vs prior
    </span>
  )
}

// US BLS private-industry medians (2023). Used as a coarse benchmark when
// we don't know the company's NAICS class. Actual NCCI E-Mod expected
// loss tables are class-specific — this is a directional indicator only.
const TRIR_MEDIAN = 2.7
const DART_MEDIAN = 1.7

function HelpTooltip({ text }: { text: string }) {
  return (
    <span className="relative group/help inline-flex">
      <HelpCircle className="w-3 h-3 text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity cursor-help" />
      <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-60 px-3 py-2 text-[10px] leading-relaxed text-zinc-300 bg-zinc-900 border border-white/10 shadow-xl opacity-0 group-hover/help:opacity-100 transition-opacity z-50">
        {text}
      </span>
    </span>
  )
}

function rateTone(value: number | null, median: number): string {
  if (value === null) return 'text-zinc-700'
  if (value === 0) return 'text-emerald-400'
  if (value < median * 0.75) return 'text-emerald-400'
  if (value < median) return 'text-amber-400'
  if (value < median * 1.5) return 'text-orange-400'
  return 'text-red-400'
}

function rateLabel(value: number | null, median: number): string {
  if (value === null) return ''
  if (value === 0) return 'no recordables'
  const ratio = value / median
  if (ratio < 0.75) return `${Math.round((1 - ratio) * 100)}% below median`
  if (ratio < 1) return `${Math.round((1 - ratio) * 100)}% below median`
  if (ratio < 1.05) return 'at median'
  return `${Math.round((ratio - 1) * 100)}% above median`
}

function streakTone(days: number | null): string {
  if (days === null) return 'text-emerald-400'
  if (days >= 365) return 'text-emerald-400'
  if (days >= 90) return 'text-amber-400'
  if (days >= 30) return 'text-orange-400'
  return 'text-red-400'
}

function streakDisplay(days: number | null): { value: string; unit: string } {
  if (days === null) return { value: '∞', unit: 'no recordables ever' }
  if (days < 60) return { value: String(days), unit: days === 1 ? 'day' : 'days' }
  if (days < 730) {
    const months = Math.floor(days / 30)
    return { value: String(months), unit: months === 1 ? 'month' : 'months' }
  }
  const years = (days / 365).toFixed(1)
  return { value: years, unit: 'years' }
}

export function IRWcMetricsCard({ metrics }: { metrics: WcMetrics }) {
  const { trir, dart_rate, lost_days, days_since_last_recordable, deaths, data_quality } = metrics

  // Suppress entirely if missing headcount AND no recordables — nothing
  // useful to say, hide the section to avoid confusion.
  if (data_quality.headcount_missing && metrics.recordable_cases === 0) {
    return null
  }

  return (
    <div>
      <div className="flex items-end justify-between mb-3">
        <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold flex items-center gap-1.5">
          <Shield className="w-3 h-3" />
          Workers Comp Posture · trailing {Math.round(metrics.period_days / 30)} mo
        </h2>
        {data_quality.insufficient_population && (
          <span className="text-[10px] text-zinc-600 uppercase tracking-widest font-mono">
            sample too small for stable rates
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
        {/* TRIR */}
        <div className="bg-zinc-900 p-6 flex flex-col justify-between group">
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold flex items-center gap-1.5">
            <Activity className="w-3 h-3" /> TRIR
            <HelpTooltip text="Total Recordable Incident Rate per 100 FTEs. OSHA standard: (recordable × 200,000) / hours worked. US private-industry median ≈ 2.7." />
          </div>
          <div className={`text-4xl font-light font-mono mt-2 ${rateTone(trir, TRIR_MEDIAN)}`}>
            {trir === null ? '—' : trir.toFixed(2)}
          </div>
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest mt-2 font-mono">
            {trir === null ? 'needs headcount' : `vs ${TRIR_MEDIAN} median`}
          </div>
          {trir !== null && (
            <div className={`text-[10px] mt-1 ${rateTone(trir, TRIR_MEDIAN)}`}>
              {rateLabel(trir, TRIR_MEDIAN)}
            </div>
          )}
          <div className="mt-2"><DeltaPill pct={metrics.prior.trir_delta_pct} /></div>
        </div>

        {/* DART */}
        <div className="bg-zinc-900 p-6 flex flex-col justify-between group">
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold flex items-center gap-1.5">
            <Activity className="w-3 h-3" /> DART
            <HelpTooltip text="Days Away, Restricted, or Transferred rate. Same formula as TRIR but only cases involving lost or restricted time. Workers-comp adjusters track this directly. US median ≈ 1.7." />
          </div>
          <div className={`text-4xl font-light font-mono mt-2 ${rateTone(dart_rate, DART_MEDIAN)}`}>
            {dart_rate === null ? '—' : dart_rate.toFixed(2)}
          </div>
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest mt-2 font-mono">
            {dart_rate === null ? 'needs headcount' : `vs ${DART_MEDIAN} median`}
          </div>
          {dart_rate !== null && (
            <div className={`text-[10px] mt-1 ${rateTone(dart_rate, DART_MEDIAN)}`}>
              {rateLabel(dart_rate, DART_MEDIAN)}
            </div>
          )}
          <div className="mt-2"><DeltaPill pct={metrics.prior.dart_delta_pct} /></div>
        </div>

        {/* Lost days */}
        <div className="bg-zinc-900 p-6 flex flex-col justify-between group">
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold flex items-center gap-1.5">
            <Calendar className="w-3 h-3" /> Lost Days
            <HelpTooltip text="Total days away from work across all OSHA-recordable incidents in this period. High totals push severity component of E-Mod up." />
          </div>
          <div className={`text-4xl font-light font-mono mt-2 ${lost_days > 0 ? 'text-orange-400' : 'text-emerald-400'}`}>
            {lost_days}
          </div>
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest mt-2 font-mono">
            +{metrics.restricted_days} restricted
          </div>
          {deaths > 0 && (
            <div className="text-[10px] text-red-400 font-bold uppercase tracking-widest mt-1">
              {deaths} fatality{deaths === 1 ? '' : 's'}
            </div>
          )}
          <div className="mt-2"><DeltaPill pct={metrics.prior.lost_days_delta_pct} /></div>
        </div>

        {/* Claims-free streak */}
        <div className="bg-zinc-900 p-6 flex flex-col justify-between group">
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold flex items-center gap-1.5">
            <Heart className="w-3 h-3" /> Claims-Free Streak
            <HelpTooltip text="Days since the last OSHA-recordable incident (any time). Long streaks support an E-Mod credit case at renewal." />
          </div>
          {(() => {
            const s = streakDisplay(days_since_last_recordable)
            return (
              <>
                <div className={`text-4xl font-light font-mono mt-2 ${streakTone(days_since_last_recordable)}`}>
                  {s.value}
                </div>
                <div className="text-[9px] text-zinc-600 uppercase tracking-widest mt-2 font-mono">
                  {s.unit}
                </div>
              </>
            )
          })()}
          {days_since_last_recordable !== null && days_since_last_recordable >= 365 && (
            <div className="text-[10px] text-emerald-400 mt-1">
              E-Mod credit candidate
            </div>
          )}
        </div>
      </div>

      <p className="text-[10px] text-zinc-600 mt-3 leading-relaxed">
        Approximation. Hours worked assumed at headcount × 2,000 prorated to period. Benchmark medians from US BLS private industry,
        not your specific NCCI class code. Verify any premium-impact conclusions with your broker.
      </p>
    </div>
  )
}
