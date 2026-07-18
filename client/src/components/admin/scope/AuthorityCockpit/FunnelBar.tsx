import type { AuthorityIndex } from './types'
import { pct } from './constants'

/** Confirmed / provisional / unclassified for one index. */
export function FunnelBar({ index }: { index: AuthorityIndex }) {
  const total = index.item_count || 0
  // unclassified_count means "no CONFIRMED classification" (classify.py), so
  // confirmed is the complement. Provisional work is inside `unclassified`.
  const confirmed = Math.max(0, total - (index.unclassified_count || 0))
  return (
    <div className="mt-1.5">
      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className="h-full rounded-full bg-emerald-500"
          style={{ width: `${pct(confirmed, total)}%` }}
        />
      </div>
      <div className="mt-1 font-mono text-[10px] tabular-nums text-zinc-500">
        {confirmed}/{total} confirmed
        {index.unclassified_count > 0 && (
          <span className="ml-1 text-amber-400">· {index.unclassified_count} to review</span>
        )}
      </div>
    </div>
  )
}
