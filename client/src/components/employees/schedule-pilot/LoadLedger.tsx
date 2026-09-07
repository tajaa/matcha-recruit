import { hoursLabel } from './reviewShape'

/** The house weekly cap (POLICY, not law) — mirrors
 *  `assignment_guard.POLICY_DEFAULT_WEEKLY_CAP_MINUTES`; the rail reads the
 *  live value from planning inputs and passes it down. */
export const POLICY_WEEKLY_MINUTES = 2400

interface LoadBarProps {
  /** Scheduled minutes today (before any proposal). */
  minutes: number
  /** Minutes after the proposal under review. Omit when nothing is proposed. */
  afterMinutes?: number | null
  /** The person's own weekly cap from their scheduling profile. */
  capMinutes?: number | null
  policyMinutes?: number
  allowOvertime?: boolean
  compact?: boolean
  name?: string
}

/** The signature of the workspace: one ruled bar per person, hours as
 *  length, the 40h policy tick and their own cap as marks on the rule, and
 *  the change a proposal makes as a second segment on the same bar. The
 *  same drawing appears in the inputs rail (now) and the review pane
 *  (before → after), so "who is carrying the week" reads at a glance
 *  wherever the number shows up. */
export function LoadBar({ minutes, afterMinutes, capMinutes, policyMinutes = POLICY_WEEKLY_MINUTES, allowOvertime = false, compact = false, name }: LoadBarProps) {
  const after = afterMinutes ?? minutes
  const scale = Math.max(policyMinutes, capMinutes ?? 0, minutes, after) * 1.08 || 1
  const pct = (value: number) => `${Math.min(100, Math.max(0, (value / scale) * 100))}%`
  const base = Math.min(minutes, after)
  const delta = Math.abs(after - minutes)
  const grew = after > minutes
  const overPolicy = after > policyMinutes && !allowOvertime
  const overCap = capMinutes != null && after > capMinutes
  const changed = afterMinutes != null && afterMinutes !== minutes
  const label = changed
    ? `${name ?? 'Load'}: ${hoursLabel(minutes)} now, ${hoursLabel(after)} after this change`
    : `${name ?? 'Load'}: ${hoursLabel(minutes)} this week`
  return (
    <div className="flex items-center gap-2" aria-label={label} role="img">
      <div className={`relative min-w-0 flex-1 overflow-hidden rounded-sm bg-white/[0.05] ${compact ? 'h-1.5' : 'h-2'}`}>
        <div className="absolute inset-y-0 left-0 bg-zinc-500/80" style={{ width: pct(base) }} />
        {delta > 0 && (
          <div
            className={`absolute inset-y-0 ${grew ? 'bg-emerald-400' : 'bg-red-400/70 [background-image:repeating-linear-gradient(135deg,transparent_0_3px,rgba(0,0,0,.35)_3px_5px)]'}`}
            style={{ left: pct(base), width: pct(delta) }}
          />
        )}
        <span
          className={`absolute inset-y-0 w-px ${overPolicy ? 'bg-amber-400' : 'bg-zinc-400/70'}`}
          style={{ left: pct(policyMinutes) }}
          title={`${hoursLabel(policyMinutes)} house policy${allowOvertime ? ' (overtime allowed)' : ''}`}
        />
        {capMinutes != null && capMinutes !== policyMinutes && (
          <span
            className={`absolute inset-y-0 w-px ${overCap ? 'bg-red-400' : 'bg-sky-400/70'}`}
            style={{ left: pct(capMinutes) }}
            title={`${hoursLabel(capMinutes)} personal cap`}
          />
        )}
      </div>
      <span className={`shrink-0 font-mono tabular-nums ${compact ? 'text-[10px]' : 'text-[11px]'} ${overCap ? 'text-red-300' : overPolicy ? 'text-amber-300' : 'text-zinc-300'}`}>
        {changed ? <><span className="text-zinc-500">{hoursLabel(minutes)}</span> → {hoursLabel(after)}</> : hoursLabel(minutes)}
      </span>
    </div>
  )
}
