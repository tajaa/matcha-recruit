export function Sparkline({ points }: { points: number[] }) {
  if (points.length === 0) return null
  const max = Math.max(...points, 1)
  const w = 240
  const h = 32
  const step = points.length > 1 ? w / (points.length - 1) : 0
  const pts = points.map((v, i) => [i * step, h - (v / max) * h] as const)
  const line = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')
  // Close the path down to the baseline for a soft area fill under the line.
  const area = `${line} L ${w} ${h} L 0 ${h} Z`
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="block w-full my-1.5" height={h} role="img" aria-label="Subscriber growth trend">
      <path d={area} fill="#059669" fillOpacity={0.08} />
      <path d={line} stroke="#059669" strokeWidth={1.5} fill="none" vectorEffect="non-scaling-stroke" />
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
