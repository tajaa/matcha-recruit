import { useState } from 'react'
import { ChevronDown, Copy, Check } from 'lucide-react'
import type { UnifiedTask } from './TaskBoard'
import TaskRow from './TaskRow'

interface Props {
  label: string
  items: UnifiedTask[]
  defaultOpen?: boolean
  accent?: string
  onComplete?: (id: string) => Promise<void>
  onUncomplete?: (id: string) => Promise<void>
  onDismiss?: (category: string, id: string) => Promise<void>
  onDelete?: (id: string) => Promise<void>
}

export default function TaskSection({ label, items, defaultOpen = false, accent, onComplete, onUncomplete, onDismiss, onDelete }: Props) {
  const [open, setOpen] = useState(defaultOpen)
  const [copied, setCopied] = useState(false)

  if (items.length === 0) return null

  const critCount = items.filter((i) => i.severity === 'critical').length
  const warnCount = items.filter((i) => i.severity === 'warning').length

  function handleCopy(e: React.MouseEvent) {
    e.stopPropagation()
    const text = items
      .map((i) => `[${i.status === 'completed' ? 'x' : ' '}] ${i.title}${i.subtitle ? ` — ${i.subtitle}` : ''} (${i.days_until < 0 ? Math.abs(i.days_until) + 'd overdue' : i.days_until === 0 ? 'today' : i.days_until + 'd'})`)
      .join('\n')
    navigator.clipboard.writeText(`${label} (${items.length})\n${text}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="border border-zinc-800 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-zinc-800/30 transition-colors"
      >
        <ChevronDown
          size={14}
          className={`text-zinc-500 transition-transform ${open ? '' : '-rotate-90'}`}
        />
        <span className={`text-sm font-medium ${accent ?? 'text-zinc-200'}`}>
          {label}
        </span>
        <span className="text-xs text-zinc-500">({items.length})</span>

        <div className="flex items-center gap-1 ml-1">
          {critCount > 0 && (
            <span className="flex items-center gap-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
              <span className="text-[10px] text-red-400">{critCount}</span>
            </span>
          )}
          {warnCount > 0 && (
            <span className="flex items-center gap-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              <span className="text-[10px] text-amber-400">{warnCount}</span>
            </span>
          )}
        </div>

        <div className="ml-auto">
          <button
            onClick={handleCopy}
            className="p-1 rounded text-zinc-600 hover:text-zinc-300 transition-colors"
            title="Copy to clipboard"
          >
            {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
          </button>
        </div>
      </button>

      {open && (
        <div className="px-1 pb-2 space-y-0.5">
          {items.map((item) => (
            <TaskRow
              key={item.id}
              item={item}
              onComplete={onComplete}
              onUncomplete={onUncomplete}
              onDismiss={onDismiss}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </div>
  )
}
