import { HelpHint } from './HelpHint'
import { LABEL } from '../ui/typography'
import type { WcPortfolioResponse } from '../../types/broker'

function Chip({ label, value, tone = 'text-zinc-300' }: { label: string; value: number; tone?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.06] bg-white/[0.03] px-2.5 py-1.5 text-[11px]">
      <span className="text-zinc-500">{label}</span>
      <span className={`font-mono tabular-nums ${value > 0 ? tone : 'text-zinc-600'}`}>{value}</span>
    </span>
  )
}

/**
 * WC claim-depth chip strip for the Book of Business — cost-driver counts
 * (cumulative-trauma / post-termination / open lost-time claims) across the
 * broker's book. The WC / EPL Readiness / Risk Index distribution bars this
 * panel used to carry, plus the Rate ↑ states and Recordables chips, were
 * removed per the 2026-08-18 product spec — the KPI filter cards above cover
 * at-risk and renewal-urgency triage, and per-client detail lives in the
 * Book of Business table below.
 */
export function RiskPosturePanel({ wc }: { wc: WcPortfolioResponse | null }) {
  const hasWc = !!wc && wc.summary.client_count > 0
  if (!hasWc) return null

  return (
    <section className="overflow-hidden rounded-2xl border border-white/[0.06] bg-zinc-950">
      <header className="flex items-center gap-1.5 border-b border-white/[0.06] px-5 py-3.5">
        <h2 className={LABEL}>WC claim depth</h2>
        <HelpHint text="Workers'-comp cost-driver counts across your book — claims that carry outsized reserve or litigation risk regardless of overall TRIR." />
      </header>
      <div className="flex flex-wrap items-center gap-2 px-5 py-3.5">
        <Chip label="Cumulative trauma" value={wc!.summary.total_ct_cases ?? 0} tone="text-red-400" />
        <Chip label="Post-termination" value={wc!.summary.total_post_termination ?? 0} tone="text-red-400" />
        <Chip label="Open lost-time" value={wc!.summary.total_open_lost_time ?? 0} tone="text-orange-400" />
      </div>
    </section>
  )
}
