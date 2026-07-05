import type { ReactNode } from 'react'
import { HelpHint } from './HelpHint'
import { LABEL } from '../ui/typography'
import { fmtMoney } from '../../utils/brokerFormat'
import type { WcPortfolioResponse, EplPortfolioResponse } from '../../types/broker'
import type { RiskIndexPortfolio } from '../../types/riskIndex'

type Seg = { label: string; count: number; bar: string; dot: string }

/** Best→worst band palette, shared by every posture dimension. */
const GOOD = { bar: 'bg-emerald-500', dot: 'bg-emerald-400' }
const FAIR = { bar: 'bg-amber-500', dot: 'bg-amber-400' }
const WARN = { bar: 'bg-orange-500', dot: 'bg-orange-400' }
const BAD = { bar: 'bg-red-500', dot: 'bg-red-400' }

function DistributionBar({ segments }: { segments: Seg[] }) {
  const total = segments.reduce((s, x) => s + x.count, 0)
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-white/[0.06]">
        {total > 0 &&
          segments.map((s) =>
            s.count > 0 ? (
              <div
                key={s.label}
                className={`h-full ${s.bar}`}
                style={{ width: `${(s.count / total) * 100}%` }}
                title={`${s.label}: ${s.count}`}
              />
            ) : null,
          )}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {segments.map((s) => (
          <span key={s.label} className="inline-flex items-center gap-1 text-[10px]">
            <span className={`h-1.5 w-1.5 rounded-full ${s.count > 0 ? s.dot : 'bg-zinc-700'}`} />
            <span className="text-zinc-500">{s.label}</span>
            <span className={`font-mono tabular-nums ${s.count > 0 ? 'text-zinc-300' : 'text-zinc-600'}`}>
              {s.count}
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}

function PostureRow({
  name,
  hint,
  segments,
  headline,
}: {
  name: string
  hint: string
  segments: Seg[]
  headline: ReactNode
}) {
  return (
    <div className="grid grid-cols-1 gap-y-2.5 py-3.5 md:grid-cols-[150px_1fr_minmax(92px,auto)] md:items-center md:gap-x-5">
      <div className="flex items-center gap-1.5">
        <span className="text-sm font-medium text-zinc-200">{name}</span>
        <HelpHint text={hint} />
      </div>
      <DistributionBar segments={segments} />
      {headline}
    </div>
  )
}

function Headline({ label, value, tone = 'text-zinc-100' }: { label: string; value: string; tone?: string }) {
  return (
    <div className="md:text-right">
      <div className={LABEL}>{label}</div>
      <div className={`font-mono text-lg leading-tight tabular-nums ${tone}`}>{value}</div>
    </div>
  )
}

function Chip({ label, value, tone = 'text-zinc-300' }: { label: string; value: number; tone?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.06] bg-white/[0.03] px-2.5 py-1.5 text-[11px]">
      <span className="text-zinc-500">{label}</span>
      <span className={`font-mono tabular-nums ${value > 0 ? tone : 'text-zinc-600'}`}>{value}</span>
    </span>
  )
}

/**
 * The Book of Business risk-posture panel: one card that stacks WC, EPL and the
 * composite Risk Index as proportional distribution bars (best→worst), with WC
 * claim-depth cost-drivers as a chip footer. Replaces four near-identical tile
 * strips with a single dense, scannable view.
 */
export function RiskPosturePanel({
  wc,
  epl,
  riskIndex,
  netPremiumExposure,
}: {
  wc: WcPortfolioResponse | null
  epl: EplPortfolioResponse | null
  riskIndex: RiskIndexPortfolio | null
  netPremiumExposure: number
}) {
  const hasWc = !!wc && wc.summary.client_count > 0
  const hasEpl = !!epl && epl.summary.client_count > 0
  const hasRisk = !!riskIndex && riskIndex.summary.client_count > 0

  if (!hasWc && !hasEpl && !hasRisk) return null

  return (
    <section className="overflow-hidden rounded-2xl border border-white/[0.06] bg-zinc-950">
      <header className="flex items-center gap-1.5 border-b border-white/[0.06] px-5 py-3.5">
        <h2 className={LABEL}>Risk posture</h2>
        <HelpHint text="Every client banded best→worst across the three lenses carriers price on — workers' comp safety, EPL readiness, and the composite risk index. The bar shows where your book sits; the number on the right is your headline for a renewal conversation." />
      </header>

      <div className="divide-y divide-white/[0.06] px-5">
        {hasWc && (
          <PostureRow
            name="Workers' Comp"
            hint="Each client's WC safety, banded by their injury rate vs their industry. The number is the modeled annual premium swing across the book — your renewal-savings story."
            segments={[
              { label: 'Good', count: wc!.summary.good, ...GOOD },
              { label: 'Fair', count: wc!.summary.fair, ...FAIR },
              { label: 'At risk', count: wc!.summary.at_risk, ...WARN },
              { label: 'Critical', count: wc!.summary.critical, ...BAD },
            ]}
            headline={
              <Headline
                label="Premium Δ"
                value={`${netPremiumExposure > 0 ? '+' : ''}${fmtMoney(netPremiumExposure)}`}
                tone={
                  netPremiumExposure > 0
                    ? 'text-red-400'
                    : netPremiumExposure < 0
                      ? 'text-emerald-400'
                      : 'text-zinc-300'
                }
              />
            }
          />
        )}

        {hasEpl && (
          <PostureRow
            name="EPL Readiness"
            hint="Employment-practices-liability readiness across the book. Spot who's hard to place and what to shore up before renewal."
            segments={[
              { label: 'Strong', count: epl!.summary.strong, ...GOOD },
              { label: 'Adequate', count: epl!.summary.adequate, ...FAIR },
              { label: 'Developing', count: epl!.summary.developing, ...WARN },
              { label: 'Exposed', count: epl!.summary.exposed, ...BAD },
            ]}
            headline={<Headline label="Avg" value={String(epl!.summary.avg_score)} />}
          />
        )}

        {hasRisk && (
          <PostureRow
            name="Risk Index"
            hint="One composite 0–100 per client (workers'-comp + EPL + compliance) — the single benchmarkable number to lead a renewal with, and the basis of the client-facing risk portal."
            segments={[
              { label: 'Strong', count: riskIndex!.summary.strong, ...GOOD },
              { label: 'Adequate', count: riskIndex!.summary.adequate, ...FAIR },
              { label: 'Developing', count: riskIndex!.summary.developing, ...WARN },
              { label: 'Exposed', count: riskIndex!.summary.exposed, ...BAD },
            ]}
            headline={<Headline label="Avg" value={String(riskIndex!.summary.avg_index)} />}
          />
        )}
      </div>

      {hasWc && (
        <div className="flex flex-wrap items-center gap-2 border-t border-white/[0.06] px-5 py-3.5">
          <span className={`mr-1 ${LABEL}`}>
            WC claim depth
          </span>
          <Chip label="Cumulative trauma" value={wc!.summary.total_ct_cases ?? 0} tone="text-red-400" />
          <Chip label="Post-termination" value={wc!.summary.total_post_termination ?? 0} tone="text-red-400" />
          <Chip label="Open lost-time" value={wc!.summary.total_open_lost_time ?? 0} tone="text-orange-400" />
          <Chip label="Rate ↑ states" value={wc!.summary.clients_in_rate_increase_states ?? 0} tone="text-amber-400" />
          <Chip label="Recordables" value={wc!.summary.total_recordable_cases} />
        </div>
      )}
    </section>
  )
}
