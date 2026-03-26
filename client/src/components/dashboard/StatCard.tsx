import { useNavigate } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'

interface StatCardProps {
  label: string
  value: number | string
  subtitle?: string
  icon: LucideIcon
  href?: string
  urgent?: boolean
}

export function StatCard({ label, value, subtitle, icon: Icon, href, urgent }: StatCardProps) {
  const navigate = useNavigate()

  return (
    <button
      type="button"
      onClick={href ? () => navigate(href) : undefined}
      className={`group relative overflow-hidden rounded-xl border bg-zinc-900/60 p-5 text-left transition-all duration-200 ${
        href ? 'cursor-pointer hover:bg-zinc-800/80 border-zinc-800 hover:border-zinc-700/70' : 'cursor-default border-zinc-800/60'
      } ${urgent ? 'ring-1 ring-red-500/30 border-red-900/40' : ''}`}
    >
      <Icon className={`absolute -top-1.5 -right-1.5 h-16 w-16 transition-colors duration-200 ${
        href ? 'text-zinc-800/40 group-hover:text-zinc-700/40' : 'text-zinc-800/30'
      }`} />
      <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider">{label}</p>
      <p className="text-3xl font-semibold text-zinc-100 tabular-nums mt-1.5">{value}</p>
      {subtitle && <p className="text-[11px] text-zinc-500 mt-1">{subtitle}</p>}
    </button>
  )
}
