import { TrendingDown, AlertCircle, ChevronRight } from 'lucide-react'
import type { WageGapSummary } from '../../types/dashboard'

interface Props {
  data: WageGapSummary
  onOpenDetails?: () => void
}

/**
 * Wage Gap card — §3.1 of QSR_RETENTION_PLAN.md
 *
 * Frames retention as a P&L bet:
 *   "X of Y baristas are paid below local BLS market.
 *    Closing the gap costs $A/yr; replacing them at $5,864 each costs $B/yr."
 *
 * The widget is hidden when there's nothing to evaluate (no hourly employees
 * matched to a SOC code) — the backend already returns null in that case.
 */
export function WageGapCard({ data, onOpenDetails }: Props) {
  const {
    employees_below_market: below,
    employees_evaluated: evaluated,
    employees_unclassified: unclassified,
    median_delta_percent,
    dollars_per_hour_to_close_gap,
    annual_cost_to_lift,
    max_replacement_cost_exposure,
  } = data

  const allCovered = below === 0 && evaluated > 0
  const accent = allCovered ? 'emerald' : below > 0 ? 'amber' : 'zinc'

  const accentClasses = {
    emerald: { ring: 'border-emerald-900/40', text: 'text-emerald-400', bgIcon: 'text-emerald-700/30' },
    amber:   { ring: 'border-amber-900/40 ring-1 ring-amber-500/20', text: 'text-amber-400', bgIcon: 'text-amber-700/30' },
    zinc:    { ring: 'border-zinc-800/60', text: 'text-zinc-300', bgIcon: 'text-zinc-700/30' },
  }[accent]

  const medianPct = median_delta_percent != null ? Math.round(median_delta_percent * 100) : null
  const headlineNumber = `${below}/${evaluated}`

  const clickable = !!onOpenDetails && evaluated > 0
  const Wrapper: any = clickable ? 'button' : 'div'
  const wrapperProps = clickable
    ? { onClick: onOpenDetails, type: 'button', 'aria-label': 'View wage gap details' }
    : {}

  return (
    <Wrapper
      {...wrapperProps}
      className={`group relative overflow-hidden rounded-xl border bg-zinc-900/60 p-5 w-full text-left ${accentClasses.ring} ${
        clickable ? 'cursor-pointer hover:bg-zinc-900/80 transition-colors' : ''
      }`}
    >
      <TrendingDown className={`absolute -top-2 -right-2 h-20 w-20 ${accentClasses.bgIcon}`} />
      {clickable && (
        <div className="absolute top-3 right-3 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider text-zinc-500 group-hover:text-zinc-300">
          View employees
          <ChevronRight className="h-3 w-3" />
        </div>
      )}

      {/* Headline row */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              Wage Gap vs. Market
            </p>
            <span className="text-[9px] uppercase tracking-wider px-1.5 py-[1px] rounded bg-zinc-800/80 text-zinc-400 font-mono">
              BLS OEWS
            </span>
          </div>
          <div className="flex items-baseline gap-3 mt-1.5">
            <span className={`text-3xl font-semibold tabular-nums ${accentClasses.text}`}>
              {headlineNumber}
            </span>
            <span className="text-xs text-zinc-500">
              {allCovered ? 'all hourly staff at or above market' : 'hourly employees ≥10% below market'}
            </span>
          </div>
          {medianPct !== null && (
            <p className="text-[11px] text-zinc-500 mt-1">
              Median delta: <span className={medianPct < 0 ? 'text-amber-500/90' : 'text-emerald-400/90'}>
                {medianPct >= 0 ? '+' : ''}{medianPct}% vs. local p50
              </span>
              {unclassified > 0 && (
                <span className="text-zinc-600"> · {unclassified} unclassified</span>
              )}
            </p>
          )}
        </div>
      </div>

      {/* P&L math — only when there's actually a gap */}
      {below > 0 && (
        <div className="mt-4 pt-4 border-t border-zinc-800/60 grid grid-cols-3 gap-4">
          <Stat
            label="Close the gap"
            value={`$${dollars_per_hour_to_close_gap.toFixed(2)}/hr`}
            sub="combined raises across roster"
          />
          <Stat
            label="Annual cost to lift"
            value={`$${annual_cost_to_lift.toLocaleString()}`}
            sub="2,080 hr/employee basis"
          />
          <Stat
            label="Max exposure"
            value={`$${max_replacement_cost_exposure.toLocaleString()}`}
            sub="upper bound — $5,864 × headcount if all quit"
            warning
          />
        </div>
      )}

      {/* Empty / no-data hint */}
      {evaluated === 0 && unclassified > 0 && (
        <p className="text-[11px] text-zinc-500 mt-3 flex items-start gap-1.5">
          <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-zinc-600" />
          <span>
            <strong className="text-zinc-400">{unclassified}</strong> employees couldn&apos;t be matched to a market role yet.
            Add SOC mappings or normalize job titles to enable benchmarking.
          </span>
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
