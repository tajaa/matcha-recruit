import { Users, AlertCircle, ChevronRight } from 'lucide-react'
import type { FlightRiskWidgetSummary } from '../../types/dashboard'

interface Props {
  data: FlightRiskWidgetSummary
  onOpenDetails?: () => void
}

const DRIVER_LABELS: Record<string, string> = {
  wage_gap: 'below-market wage',
  tenure: 'early tenure window',
  er_case: 'open ER case',
  ir_incident: 'recent IR incident',
  cohort: 'cohort hot-spot',
  manager: 'manager turnover',
}

/**
 * Flight-Risk card — §3.3 of QSR_RETENTION_PLAN.md
 *
 * Companion to WageGapCard. Same dollar-math language:
 *   "X of Y employees flight-risk ≥high.
 *    Expected loss = $A at $5,864 fully-loaded replacement cost."
 *
 * Hidden when there's nothing to evaluate (backend returns null on empty rosters).
 */
export function FlightRiskCard({ data, onOpenDetails }: Props) {
  const {
    employees_evaluated: evaluated,
    critical_count: critical,
    high_count: high,
    expected_loss_at_replacement: expectedLoss,
    top_driver: topDriver,
    top_driver_count: topDriverCount,
    early_tenure_count: earlyCount,
    manager_hotspots: hotspots,
  } = data

  const flagged = critical + high
  const accent = flagged === 0 ? 'emerald' : critical > 0 ? 'red' : 'amber'

  const accentClasses = {
    emerald: { ring: 'border-emerald-900/40', text: 'text-emerald-400', bgIcon: 'text-emerald-700/30' },
    amber: { ring: 'border-amber-900/40 ring-1 ring-amber-500/20', text: 'text-amber-400', bgIcon: 'text-amber-700/30' },
    red: { ring: 'border-red-900/50 ring-1 ring-red-500/30', text: 'text-red-400', bgIcon: 'text-red-700/30' },
  }[accent]

  const headlineNumber = `${flagged}/${evaluated}`
  const driverLabel = topDriver ? DRIVER_LABELS[topDriver] ?? topDriver : null

  const clickable = !!onOpenDetails && evaluated > 0
  const Wrapper: any = clickable ? 'button' : 'div'
  const wrapperProps = clickable
    ? { onClick: onOpenDetails, type: 'button', 'aria-label': 'View flight-risk details' }
    : {}

  return (
    <Wrapper
      {...wrapperProps}
      className={`group relative overflow-hidden rounded-xl border bg-zinc-900/60 p-5 w-full text-left ${accentClasses.ring} ${
        clickable ? 'cursor-pointer hover:bg-zinc-900/80 transition-colors' : ''
      }`}
    >
      <Users className={`absolute -top-2 -right-2 h-20 w-20 ${accentClasses.bgIcon}`} />
      {clickable && (
        <div className="absolute top-3 right-3 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider text-zinc-500 group-hover:text-zinc-300">
          View employees
          <ChevronRight className="h-3 w-3" />
        </div>
      )}

      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              Flight Risk
            </p>
            <span className="text-[9px] uppercase tracking-wider px-1.5 py-[1px] rounded bg-zinc-800/80 text-zinc-400 font-mono">
              6-signal composite
            </span>
          </div>
          <div className="flex items-baseline gap-3 mt-1.5">
            <span className={`text-3xl font-semibold tabular-nums ${accentClasses.text}`}>
              {headlineNumber}
            </span>
            <span className="text-xs text-zinc-500">
              {flagged === 0 ? 'no high-risk employees' : 'employees scored ≥ high'}
            </span>
          </div>
          {driverLabel && (
            <p className="text-[11px] text-zinc-500 mt-1">
              Top driver: <span className="text-zinc-300">{driverLabel}</span>
              <span className="text-zinc-600"> · {topDriverCount} of {flagged} cases</span>
            </p>
          )}
        </div>
      </div>

      {flagged > 0 && (
        <div className="mt-4 pt-4 border-t border-zinc-800/60 grid grid-cols-3 gap-4">
          <Stat
            label="Critical"
            value={String(critical)}
            sub="score ≥ 80 — act this week"
          />
          <Stat
            label="In 30-180 day window"
            value={String(earlyCount)}
            sub="QSR peak quit zone"
          />
          <Stat
            label="Expected loss"
            value={`$${expectedLoss.toLocaleString()}`}
            sub="upper bound — $5,864 × flagged"
            warning
          />
        </div>
      )}

      {flagged > 0 && hotspots.length > 0 && (
        <div className="mt-4 pt-4 border-t border-zinc-800/60">
          <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-500 mb-2">
            Manager hot-spots
          </p>
          <div className="flex flex-wrap gap-1.5">
            {hotspots.slice(0, 4).map((h) => (
              <span
                key={h.manager_id}
                className="text-[11px] text-zinc-300 px-2 py-0.5 rounded-full bg-zinc-800/80"
              >
                {h.manager_name} <span className="text-zinc-500">· {h.flagged_count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {evaluated === 0 && (
        <p className="text-[11px] text-zinc-500 mt-3 flex items-start gap-1.5">
          <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-zinc-600" />
          <span>No active employees to score yet.</span>
        </p>
      )}
    </Wrapper>
  )
}

function Stat({ label, value, sub, warning }: { label: string; value: string; sub: string; warning?: boolean }) {
  return (
    <div>
      <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-500">{label}</p>
      <p className={`text-lg font-semibold tabular-nums mt-0.5 ${warning ? 'text-amber-400' : 'text-zinc-100'}`}>
        {value}
      </p>
      <p className="text-[10px] text-zinc-600 mt-0.5">{sub}</p>
    </div>
  )
}
