import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

// One nav row for the expanded sidebar and one icon for the collapsed rail.
// Every top-level sidebar destination uses these instead of a pasted button.

export function SidebarNavButton({ icon: Icon, label, active, onClick, badge }: {
  icon: LucideIcon
  label: string
  active: boolean
  onClick: () => void
  badge?: ReactNode
}) {
  return (
    <button
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={`relative w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
        active
          ? 'bg-w-surface2 text-white font-medium'
          : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
      }`}
    >
      <Icon size={14} strokeWidth={1.6} />
      {label}
      {badge}
    </button>
  )
}

export function RailNavButton({ icon: Icon, label, active, onClick, badge }: {
  icon: LucideIcon
  label: string
  active: boolean
  onClick: () => void
  badge?: ReactNode
}) {
  return (
    <button
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      aria-label={label}
      className={`relative p-2 rounded-lg transition-colors ${active ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
      title={label}
    >
      <Icon size={16} />
      {badge}
    </button>
  )
}
