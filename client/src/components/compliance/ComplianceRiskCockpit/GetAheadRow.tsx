export function GetAheadRow({ title, days, kind, loc }: { title: string; days: number | null; kind: string; loc?: string | null }) {
  const urgent = days != null && days <= 30
  const lead = days == null ? 0 : Math.max(0, Math.min(100, 100 - (days / 180) * 100))
  return (
    <div className="px-3 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs text-zinc-200 line-clamp-2">{title}</p>
          <span className="text-[10px] text-zinc-600 uppercase tracking-wide">
            {kind === 'legislation' ? 'New law' : 'Deadline'}{loc ? ` · ${loc}` : ''}
          </span>
        </div>
        <span className={`shrink-0 font-mono text-sm font-semibold tabular-nums ${urgent ? 'text-amber-400' : 'text-zinc-400'}`}>
          {days != null ? `${days}d` : '—'}
        </span>
      </div>
      <div className="mt-1.5 h-1 rounded-full bg-white/[0.05] overflow-hidden">
        <div className={`h-full ${urgent ? 'bg-amber-500/70' : 'bg-zinc-600'}`} style={{ width: `${lead}%` }} />
      </div>
    </div>
  )
}
