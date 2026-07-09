export function Sparkline({ points }: { points: number[] }) {
  if (points.length === 0) return null
  const max = Math.max(...points, 1)
  const w = 240
  const h = 32
  const step = points.length > 1 ? w / (points.length - 1) : 0
  const path = points
    .map((v, i) => `${i === 0 ? 'M' : 'L'} ${(i * step).toFixed(1)} ${(h - (v / max) * h).toFixed(1)}`)
    .join(' ')
  return (
    <svg width={w} height={h} className="block">
      <path d={path} stroke="#059669" strokeWidth={1.5} fill="none" />
    </svg>
  )
}

export function Stat({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <p className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-xl font-semibold text-slate-900">{value}</p>
      {sub && <p className="text-[10px] text-slate-400 mt-0.5">{sub}</p>}
    </div>
  )
}
