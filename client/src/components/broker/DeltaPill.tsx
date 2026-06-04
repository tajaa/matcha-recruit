import { TrendingDown, TrendingUp, Minus } from 'lucide-react'

/** Trailing-trend pill: down = green (improving), up = red (worsening).
 *  Extracted from BrokerWcPortfolio so Book of Business + Action Center share it.
 *  `pct` is a delta percentage (negative = better for safety metrics). */
export function DeltaPill({ pct }: { pct: number | null | undefined }) {
  if (pct === null || pct === undefined) return <span className="text-zinc-700 text-[10px]">—</span>
  const Icon = pct < -1 ? TrendingDown : pct > 1 ? TrendingUp : Minus
  const tone = pct < -5 ? 'text-emerald-400' : pct > 5 ? 'text-red-400' : 'text-zinc-500'
  const sign = pct > 0 ? '+' : ''
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-mono ${tone}`}>
      <Icon className="w-3 h-3" />
      {sign}{pct.toFixed(0)}%
    </span>
  )
}

export default DeltaPill
