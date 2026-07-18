import type { Summary300A } from './types'

// 300A Summary stat cards
export function Summary300ACards({ summary }: { summary: Summary300A | null }) {
  if (!summary) return null
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-white/[0.06] border border-white/[0.06] rounded-lg overflow-hidden">
      <div className="bg-zinc-900/60 px-4 py-4">
        <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Total Cases</div>
        <div className="text-2xl font-light font-mono mt-1.5 text-zinc-100">{summary.total_cases}</div>
      </div>
      <div className="bg-zinc-900/60 px-4 py-4">
        <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Deaths</div>
        <div className={`text-2xl font-light font-mono mt-1.5 ${summary.total_deaths > 0 ? 'text-red-400' : 'text-zinc-700'}`}>{summary.total_deaths}</div>
      </div>
      <div className="bg-zinc-900/60 px-4 py-4">
        <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Days Away</div>
        <div className="text-2xl font-light font-mono mt-1.5 text-amber-400">{summary.total_days_away}</div>
        <div className="text-[9px] text-zinc-600 uppercase tracking-widest mt-1 font-mono">{summary.total_days_away_cases} cases</div>
      </div>
      <div className="bg-zinc-900/60 px-4 py-4">
        <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Restricted Duty</div>
        <div className="text-2xl font-light font-mono mt-1.5 text-orange-400">{summary.total_days_restricted}</div>
        <div className="text-[9px] text-zinc-600 uppercase tracking-widest mt-1 font-mono">{summary.total_restricted_cases} cases</div>
      </div>
    </div>
  )
}
