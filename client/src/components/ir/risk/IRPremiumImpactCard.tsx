import { DollarSign, TrendingDown, TrendingUp } from 'lucide-react'
import type { WcPremiumImpact } from './IRWcMetricsCard'

// Only the fields this card actually reads. Both the client-side WcMetrics
// (IRWcMetricsCard.tsx) and the broker-side WcMetrics (types/broker.ts) are
// structurally assignable to this, so the same card renders on the IR Risk
// Insights page and the broker Book-of-Business client drill-down.
export type PremiumImpactMetrics = {
  premium_impact: WcPremiumImpact | null
  benchmark: { trir: number } | null
  trir: number | null
  headcount: number | null
}

function fmtMoney(n: number): string {
  const abs = Math.abs(n)
  if (abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  if (abs >= 10_000) return `$${Math.round(n / 1000)}K`
  return `$${Math.round(n).toLocaleString()}`
}

export function IRPremiumImpactCard({ metrics }: { metrics: PremiumImpactMetrics }) {
  const impact = metrics.premium_impact
  if (!impact) return null

  const { annual_impact_dollars, base_premium_estimate, mod_swing, direction } = impact
  const isIncrease = direction === 'increase'
  const isDecrease = direction === 'decrease'

  const tone = isIncrease ? 'text-red-400' : isDecrease ? 'text-emerald-400' : 'text-zinc-400'
  const bgTone = isIncrease ? 'bg-red-500/5 border-red-500/20' : isDecrease ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-zinc-900 border-white/10'
  const Icon = isIncrease ? TrendingUp : isDecrease ? TrendingDown : DollarSign

  const swingPts = Math.abs(mod_swing) * 100  // mod_swing 0.18 → 18 points
  const ratio = metrics.benchmark && metrics.trir
    ? (metrics.trir / metrics.benchmark.trir).toFixed(2)
    : null

  return (
    <div className={`rounded-2xl border p-6 ${bgTone}`}>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-start gap-4 min-w-0">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
            isIncrease ? 'bg-red-500/10' : isDecrease ? 'bg-emerald-500/10' : 'bg-zinc-800'
          }`}>
            <Icon className={`w-5 h-5 ${tone}`} />
          </div>
          <div className="min-w-0">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold flex items-center gap-1.5">
              <DollarSign className="w-3 h-3" />
              Premium Impact Estimate
            </div>
            <div className="mt-1.5 flex items-baseline gap-2 flex-wrap">
              <span className={`text-3xl font-light font-mono ${tone}`}>
                {isIncrease ? '+' : isDecrease ? '−' : ''}{fmtMoney(Math.abs(annual_impact_dollars))}
              </span>
              <span className="text-xs text-zinc-500">/ year directional</span>
            </div>
            <p className="text-[12px] text-zinc-400 mt-2 leading-relaxed">
              {isIncrease && (
                <>Current TRIR trend points to a <strong className="text-red-400">~{swingPts.toFixed(0)}pt mod increase</strong> on next renewal{ratio && ` (you're at ${ratio}× the sector median)`}. Estimated extra premium: <strong className="text-red-400">{fmtMoney(annual_impact_dollars)}/yr</strong>.</>
              )}
              {isDecrease && (
                <>Below-median TRIR supports a <strong className="text-emerald-400">~{swingPts.toFixed(0)}pt mod credit</strong> case at renewal{ratio && ` (you're at ${ratio}× the sector median)`}. Potential premium savings: <strong className="text-emerald-400">{fmtMoney(Math.abs(annual_impact_dollars))}/yr</strong>.</>
              )}
              {!isIncrease && !isDecrease && (
                <>TRIR sits at the sector median — neutral mod posture going into renewal.</>
              )}
            </p>
            <p className="text-[10px] text-zinc-600 mt-3 leading-relaxed">
              Base premium estimate: {fmtMoney(base_premium_estimate)}/yr ({metrics.headcount} FTE × sector avg). Mod sensitivity: 10pts per 1.0× TRIR deviation. <strong>Not a quote.</strong> Confirm with your broker — actual impact depends on NCCI class, payroll, state, carrier rate tables, and 3-year experience period.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
