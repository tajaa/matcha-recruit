import type { ReactNode } from 'react'
import { ChevronDown, ChevronRight, type LucideIcon } from 'lucide-react'

// The sidebar's collapsible lists (Chats, Channels, Workspaces) share this
// header and this cap, so they read as one system: a chevron and a label you
// click to fold, the section's own actions (new, browse) shown on hover or
// keyboard focus instead of crowding every header, and a long list cut to its
// first few rows with a "Show N more" row under it.

export function SidebarSection({ label, open, onToggle, badge, actions, children }: {
  label: string
  open: boolean
  onToggle: () => void
  /** Shown while folded (an unread count), so nothing is missed. */
  badge?: ReactNode
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="pt-3" aria-label={label}>
      <div className="group/section flex items-center gap-1 pr-1">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-1 rounded px-1.5 py-1 text-[11px] font-semibold text-w-faint transition-colors hover:text-w-text"
        >
          {open ? <ChevronDown size={11} className="shrink-0" /> : <ChevronRight size={11} className="shrink-0" />}
          <span className="truncate">{label}</span>
          {!open && badge}
        </button>
        {actions && (
          <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover/section:opacity-100">
            {actions}
          </div>
        )}
      </div>
      {open && <div className="mt-0.5 space-y-px">{children}</div>}
    </section>
  )
}

export function SectionAction({ icon: Icon, label, onClick }: { icon: LucideIcon; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="rounded p-1 text-w-faint transition-colors hover:bg-w-surface2 hover:text-w-text"
    >
      <Icon size={12} />
    </button>
  )
}

export function EmptyRow({ children }: { children: ReactNode }) {
  return <p className="px-2.5 py-1 text-[11px] text-w-faint">{children}</p>
}

export function ShowMoreRow({ hidden, expanded, onToggle }: { hidden: number; expanded: boolean; onToggle: () => void }) {
  if (!expanded && hidden <= 0) return null
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-center gap-1 rounded px-2.5 py-1 text-left text-[11px] text-w-faint transition-colors hover:text-w-text"
    >
      {expanded ? 'Show less' : `Show ${hidden} more`}
    </button>
  )
}
