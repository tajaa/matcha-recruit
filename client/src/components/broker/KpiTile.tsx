import type { LucideIcon } from 'lucide-react'
import { LABEL } from '../ui/typography'

/**
 * Compact portfolio KPI tile — label, big value, optional sub-line. Deliberately
 * flat (no oversized watermark icon) so a row of them reads as a clean metric
 * strip rather than decorative cards.
 */
export function KpiTile({
  label,
  value,
  sub,
  icon: Icon,
  tone = 'text-zinc-100',
  dot,
  urgent,
}: {
  label: string
  value: number | string
  sub?: string
  icon?: LucideIcon
  /** Color class for the value (e.g. an at-risk count in red). */
  tone?: string
  /** Small status dot before the value (e.g. risk-band color). */
  dot?: string
  /** Red ring + border to flag an attention metric. */
  urgent?: boolean
}) {
  return (
    <div
      className={`rounded-2xl border bg-zinc-950 px-5 py-4 ${
        urgent ? 'border-red-900/50 ring-1 ring-red-500/20' : 'border-white/[0.06]'
      }`}
    >
      <div className="flex items-center gap-1.5">
        {Icon && <Icon className="h-3.5 w-3.5 text-zinc-600" strokeWidth={1.6} />}
        <span className={LABEL}>{label}</span>
      </div>
      <div className="mt-2 flex items-center gap-2">
        {dot && <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />}
        <span className={`font-mono text-[28px] font-semibold leading-none tabular-nums ${tone}`}>{value}</span>
      </div>
      {sub && <p className="mt-1.5 text-[11px] text-zinc-500">{sub}</p>}
    </div>
  )
}
