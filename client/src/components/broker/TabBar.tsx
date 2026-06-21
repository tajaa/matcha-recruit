import type { LucideIcon } from 'lucide-react'

export type TabDef = {
  key: string
  label: string
  icon?: LucideIcon
  /** Optional count chip after the label. */
  count?: number
}

/**
 * Underline tab bar for broker hub pages (page-level navigation). Distinct from
 * `ui/PillTabs`, which is a compact boxed segmented control for in-card filters.
 */
export function TabBar({
  tabs,
  active,
  onChange,
}: {
  tabs: TabDef[]
  active: string
  onChange: (key: string) => void
}) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto border-b border-zinc-800/70">
      {tabs.map((t) => {
        const isActive = t.key === active
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className={`relative flex items-center gap-1.5 whitespace-nowrap px-3 py-2.5 text-[13px] font-medium transition-colors ${
              isActive ? 'text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {t.icon && (
              <t.icon
                className={`h-3.5 w-3.5 ${isActive ? 'text-zinc-200' : 'text-zinc-600'}`}
                strokeWidth={1.6}
              />
            )}
            {t.label}
            {typeof t.count === 'number' && t.count > 0 && (
              <span className="rounded bg-zinc-800 px-1.5 text-[10px] font-mono leading-[1.4] text-zinc-400">
                {t.count}
              </span>
            )}
            {isActive && (
              <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-emerald-500" />
            )}
          </button>
        )
      })}
    </div>
  )
}
