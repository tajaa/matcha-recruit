import { AlertTriangle, ShieldCheck } from 'lucide-react'

// ── Verdict banner (the glance-value annunciator) ──
export function VerdictBanner({ critical, totalOpen, clear }: { critical: number; totalOpen: number; clear: boolean }) {
  if (clear) {
    return (
      <div className="flex items-center gap-2.5 rounded-lg border border-emerald-500/30 bg-emerald-500/[0.06] px-4 py-3">
        <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0" />
        <p className="text-sm text-emerald-200">In compliance — no open issues across your roster and jurisdictions.</p>
      </div>
    )
  }
  const urgent = critical > 0
  return (
    <div className={`flex items-center gap-2.5 rounded-lg border px-4 py-3 ${
      urgent ? 'border-red-500/40 bg-red-500/[0.07]' : 'border-amber-500/30 bg-amber-500/[0.06]'
    }`}>
      <AlertTriangle className={`h-4 w-4 shrink-0 ${urgent ? 'text-red-400' : 'text-amber-400'}`} />
      <p className="text-sm text-zinc-100">
        {urgent ? (
          <><b className="font-semibold text-red-300">{critical} critical</b> {critical === 1 ? 'issue needs' : 'issues need'} action now.</>
        ) : (
          <><b className="font-semibold text-amber-300">{totalOpen}</b> open {totalOpen === 1 ? 'issue' : 'issues'} to work through.</>
        )}
        <span className="text-zinc-500"> {totalOpen} total open.</span>
      </p>
    </div>
  )
}
