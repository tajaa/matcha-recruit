import { LABEL } from '../../../components/ui/typography'
import type { SubStats, GrowthPoint } from './types'
import { Sparkline } from './Sparkline'

export function NewsletterStatsBar({ stats, growth }: { stats: SubStats; growth: GrowthPoint[] }) {
  return (
    <div className="flex flex-wrap items-end gap-3 mb-6">
      <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-4 py-2">
        <p className={LABEL}>Active</p>
        <p className="text-lg font-mono font-bold tabular-nums text-zinc-100">{stats.active}</p>
      </div>
      {Object.entries(stats.by_source).slice(0, 5).map(([src, cnt]) => (
        <div key={src} className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-4 py-2">
          <p className={LABEL}>{src}</p>
          <p className="text-lg font-mono font-bold tabular-nums text-zinc-100">{cnt}</p>
        </div>
      ))}
      {growth.length > 0 && (
        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-4 py-2 flex-1 min-w-[280px]">
          <p className={LABEL}>90-day growth</p>
          <Sparkline points={growth.map((p) => p.subscribed)} />
          <p className="text-[10px] text-zinc-500 mt-1">
            +{growth.reduce((sum, p) => sum + p.subscribed, 0)} in last {growth.length} days
          </p>
        </div>
      )}
    </div>
  )
}
