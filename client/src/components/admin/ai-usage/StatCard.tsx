export function StatCard({
  label,
  value,
  sub,
  onClick,
  active,
}: {
  label: string
  value: string
  sub?: string
  onClick?: () => void
  active?: boolean
}) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag
      onClick={onClick}
      className={`text-left p-3 rounded-lg border transition-colors ${
        active
          ? 'bg-zinc-800 border-zinc-600'
          : 'border-zinc-800 bg-zinc-900/40' + (onClick ? ' hover:border-zinc-700' : '')
      }`}
    >
      <p className="text-[11px] text-zinc-500">{label}</p>
      <p className="text-2xl font-semibold mt-0.5 text-zinc-100">{value}</p>
      {sub && <p className="text-[11px] text-zinc-500 mt-0.5">{sub}</p>}
    </Tag>
  )
}
