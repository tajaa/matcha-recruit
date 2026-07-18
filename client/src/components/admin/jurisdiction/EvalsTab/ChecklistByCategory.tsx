import { useMemo } from 'react'
import { scoreColor } from './helpers'
import type { CoreChecklist } from './types'

/**
 * The <=30-key must-have list, rendered in full. Small on purpose: the full sweep
 * expects 201 keys for manufacturing, which nobody can check by hand, so a wrong
 * expectation set would never be spotted. Every row here is individually auditable.
 */
/** Shared ✓/✗ checklist grouped by category. Used by both the Core and Baseline
 * checklists so their styling + a11y can't drift. `linkFor` optionally turns each
 * key into an authority link (Baseline); omit it for a plain label (Core). */
export type ChecklistRow = { category: string; key: string; present: boolean }

export function ChecklistByCategory<T extends ChecklistRow>({
  items,
  linkFor,
}: {
  items: T[]
  linkFor?: (item: T) => { href: string; title?: string } | undefined
}) {
  const byCategory = useMemo(() => {
    const groups = new Map<string, T[]>()
    for (const item of items) {
      const bucket = groups.get(item.category)
      if (bucket) bucket.push(item)
      else groups.set(item.category, [item])
    }
    return [...groups.entries()]
  }, [items])

  return (
    <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
      {byCategory.map(([category, rows]) => (
        <div key={category}>
          <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-0.5">{category}</p>
          <ul>
            {rows.map((item) => {
              const link = linkFor?.(item)
              const keyClass = item.present ? 'text-zinc-400' : 'text-red-300'
              return (
                <li key={item.key} className="flex items-baseline gap-1.5 text-xs">
                  <span aria-hidden className={item.present ? 'text-emerald-400' : 'text-red-400'}>
                    {item.present ? '✓' : '✗'}
                  </span>
                  {link ? (
                    <a href={link.href} target="_blank" rel="noreferrer"
                       className={`${keyClass} hover:underline`} title={link.title}>
                      {item.key}
                    </a>
                  ) : (
                    <span className={keyClass}>{item.key}</span>
                  )}
                  <span className="sr-only">{item.present ? 'present' : 'missing'}</span>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </div>
  )
}

export function CoreChecklistPanel({ checklist }: { checklist: CoreChecklist }) {
  return (
    <div className="border border-zinc-800 rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-medium text-zinc-300">
          Core checklist — every miss is critical
        </p>
        <p className={`text-sm font-bold ${scoreColor(checklist.score)}`}>
          {checklist.present}/{checklist.total}
        </p>
      </div>
      <ChecklistByCategory items={checklist.items} />
    </div>
  )
}
