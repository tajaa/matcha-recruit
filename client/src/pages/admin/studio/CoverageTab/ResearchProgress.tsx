import { Check } from 'lucide-react'
import type { ResearchState } from './types'

// Research progress — pulse-dot live header + a real fill bar (completed/total).
export function ResearchProgress({ r }: { r: ResearchState }) {
  const pct = r.total > 0 ? Math.min(100, Math.round((r.completed / r.total) * 100)) : r.running ? 0 : 100
  return (
    <div className="mt-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
      {r.error ? (
        <div className="font-mono text-[11px] text-red-400">{r.error}</div>
      ) : (
        <>
          <div className="flex items-center gap-2">
            {r.running
              ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
              : <Check className="h-3.5 w-3.5 text-emerald-400" />}
            <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-emerald-300/90">{r.message}</span>
            {r.total > 0 && <span className="ml-auto font-mono text-[10px] tabular-nums text-zinc-500">{r.completed}/{r.total}</span>}
          </div>
          {(r.running || r.total > 0) && (
            <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-white/[0.06]">
              <div className="h-full rounded-full bg-emerald-400 transition-all duration-500" style={{ width: `${pct}%` }} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
