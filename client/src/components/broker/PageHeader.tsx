import type { ReactNode } from 'react'
import { HelpHint } from './HelpHint'

/**
 * Consistent broker page header — title (+ optional hint), subtitle, and a
 * right-aligned actions slot. Used standalone on simple pages and as the masthead
 * above the tab bar on hub pages (Clients, Account).
 */
export function PageHeader({
  title,
  subtitle,
  hint,
  actions,
}: {
  title: string
  subtitle?: string
  hint?: string
  actions?: ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-zinc-100">
          {title}
          {hint && <HelpHint text={hint} />}
        </h1>
        {subtitle && <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}
