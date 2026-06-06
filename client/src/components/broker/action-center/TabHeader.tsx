import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * Compact, full-width header for an Action Center tab body. Keeps the visual
 * scale of the tab nav (the page already owns the one big "Action Center" h1) —
 * a small icon + title + optional count pill on the left, actions on the right.
 */
export default function TabHeader({
  icon: Icon,
  title,
  hint,
  badge,
  actions,
}: {
  icon: LucideIcon
  title: string
  hint?: string
  badge?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <div className="flex items-center gap-2 min-w-0">
        <Icon className="w-4 h-4 text-emerald-400 shrink-0" />
        <h2 className="text-sm font-medium text-zinc-200">{title}</h2>
        {badge}
        {hint && <span className="hidden sm:inline text-xs text-zinc-600 truncate">· {hint}</span>}
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </div>
  )
}
