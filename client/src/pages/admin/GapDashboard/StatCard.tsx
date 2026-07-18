export default function StatCard({ label, value, tone }: { label: string; value: number | string; tone?: 'gap' | 'ok' }) {
  const valueColor = tone === 'gap' ? 'text-amber-300' : tone === 'ok' ? 'text-emerald-300' : 'text-zinc-100'
  return (
    <div className="rounded-lg border border-vsc-border bg-vsc-panel p-3">
      <div className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${valueColor}`}>{value}</div>
    </div>
  )
}
