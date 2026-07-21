import { useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import { LABEL } from '../ui'

/** The minimum shape a source-meta row needs to render in the strip. Each pilot's
 *  SOURCE_META may carry extra fields (e.g. Broker's `darkHint`) — the generic
 *  keeps those visible to the pilot's own `titleFor` closure. */
export type PilotSourceMeta = { key: string; label: string; icon: LucideIcon }

/** The docket "systems strip": an "In scope / N / records" cell followed by one
 *  cell per grounding subsystem, each with a staggered fade-in reveal, an
 *  active/dark icon+label, and a live record count. Shared by Broker Pilot and
 *  Legal Pilot — the two Mastheads' inner strips were structurally identical.
 *
 *  Parameterized by the source-meta list, a `countFor` accessor (each pilot
 *  buckets its own corpus), the total, and a `titleFor` tooltip builder (the one
 *  place the two diverge — Broker keys off `darkHint`/native systems, Legal off
 *  its research/subject-filter wording). `total === null` renders the loading dot. */
export function SystemsStrip<SM extends PilotSourceMeta>({ sourceMeta, total, countFor, titleFor }: {
  sourceMeta: readonly SM[]
  total: number | null
  countFor: (key: string) => number
  titleFor: (meta: SM, count: number) => string
}) {
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(id)
  }, [])

  return (
    <div className="mt-3 flex items-stretch divide-x divide-white/[0.06] overflow-x-auto border-t border-white/[0.06]">
      <div className="flex shrink-0 items-center gap-2.5 py-2.5 pl-5 pr-4">
        <span className={LABEL}>In scope</span>
        <span className="font-mono text-sm font-semibold tabular-nums text-emerald-400">
          {total !== null ? total : '·'}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-wide text-zinc-600">records</span>
      </div>
      {sourceMeta.map((s, i) => {
        const count = countFor(s.key)
        const active = count > 0
        const Icon = s.icon
        return (
          <div
            key={s.key}
            className={`flex shrink-0 items-center gap-2 px-4 py-2.5 transition-opacity duration-300 motion-reduce:transition-none ${shown ? 'opacity-100' : 'opacity-0'}`}
            style={{ transitionDelay: `${i * 40}ms` }}
            title={titleFor(s, count)}
          >
            <Icon className={`h-3.5 w-3.5 ${active ? 'text-emerald-400' : 'text-zinc-700'}`} />
            <span className={`text-[10px] font-medium uppercase tracking-[0.15em] ${active ? 'text-zinc-300' : 'text-zinc-600'}`}>
              {s.label}
            </span>
            <span className={`font-mono text-xs tabular-nums ${active ? 'text-zinc-100' : 'text-zinc-700'}`}>
              {active ? count : '—'}
            </span>
          </div>
        )
      })}
    </div>
  )
}
