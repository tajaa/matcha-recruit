import { ShieldCheck, AlertTriangle, Clock, HelpCircle } from 'lucide-react'
import type { GateDomain, RequirementStatus } from '../../types/workforceCompliance'

// The requirements backstop, per section: the jurisdiction requirements that apply
// to this company, and whether its tracker data satisfies each. Silent when no
// requirement applies (gate === undefined) — no banner, no noise.

const STATUS: Record<RequirementStatus, { tone: string; dot: string; label: string; Icon: typeof ShieldCheck }> = {
  compliant: { tone: 'text-emerald-400', dot: 'bg-emerald-400', label: 'Compliant', Icon: ShieldCheck },
  non_compliant: { tone: 'text-red-400', dot: 'bg-red-400', label: 'Out of compliance', Icon: AlertTriangle },
  in_progress: { tone: 'text-amber-400', dot: 'bg-amber-400', label: 'In progress', Icon: Clock },
  unknown: { tone: 'text-zinc-400', dot: 'bg-zinc-500', label: 'Not yet assessed', Icon: HelpCircle },
}

// Border/background tint keyed to the worst requirement — a red backstop should
// read as a warning frame, a clean one should stay quiet.
const FRAME: Record<RequirementStatus, string> = {
  compliant: 'border-emerald-500/20 bg-emerald-500/[0.03]',
  non_compliant: 'border-red-500/25 bg-red-500/[0.04]',
  in_progress: 'border-amber-500/20 bg-amber-500/[0.03]',
  unknown: 'border-white/10 bg-white/[0.02]',
}

export function RequirementBanner({ gate }: { gate?: GateDomain }) {
  if (!gate || gate.requirements.length === 0) return null
  const head = STATUS[gate.status]
  return (
    <div className={`rounded-xl border px-3 py-2.5 mb-3 ${FRAME[gate.status]}`}>
      <div className="flex items-center gap-1.5 mb-1.5">
        <head.Icon className={`h-3.5 w-3.5 ${head.tone}`} />
        <span className="text-[10px] uppercase tracking-widest font-bold text-zinc-500">
          Applicable requirements
        </span>
        <span className={`text-[11px] font-semibold ml-1 ${head.tone}`}>{head.label}</span>
      </div>
      <ul className="space-y-1">
        {gate.requirements.map((r, i) => {
          const s = STATUS[r.status]
          return (
            <li key={`${r.jurisdiction}-${r.title}-${i}`} className="flex items-start gap-2 text-[12px]">
              <span className={`h-1.5 w-1.5 rounded-full mt-1.5 flex-shrink-0 ${s.dot}`} />
              <span className="flex-1 min-w-0">
                <span className="text-zinc-300">{r.title}</span>
                <span className="text-zinc-600"> · {r.jurisdiction}</span>
                {r.source_url && (
                  <a href={r.source_url} target="_blank" rel="noreferrer"
                     className="text-zinc-600 hover:text-zinc-400 ml-1 underline decoration-dotted">source</a>
                )}
                <div className={`text-[11px] ${r.status === 'compliant' ? 'text-zinc-500' : s.tone}`}>{r.reason}</div>
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
