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
      className={`relative overflow-hidden rounded-xl bg-zinc-800 p-5 text-left transition-colors ${
        href ? 'cursor-pointer hover:bg-zinc-700/80' : 'cursor-default'
      } ${urgent ? 'ring-1 ring-red-500/40' : ''}`}
    >
      <Icon className="absolute -top-1 -right-1 h-16 w-16 text-zinc-700/30" />
      <p className="text-2xl font-semibold text-zinc-100">{value}</p>
      <p className="text-xs text-zinc-500 mt-1">{label}</p>
      {subtitle && <p className="text-[10px] text-zinc-600 mt-0.5">{subtitle}</p>}
    </button>
  )
}
