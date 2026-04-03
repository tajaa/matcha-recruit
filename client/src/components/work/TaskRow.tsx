import { useNavigate } from 'react-router-dom'
import { X, Trash2 } from 'lucide-react'
import type { UnifiedTask } from './TaskBoard'

const SEV_DOT: Record<string, string> = {
  critical: 'bg-red-500',
  warning: 'bg-amber-500',
  info: 'bg-zinc-500',
}

const CATEGORY_LABEL: Record<string, string> = {
  compliance: 'Compliance',
  credential: 'Credential',
  training: 'Training',
  cobra: 'COBRA',
  policy: 'Policy',
  ir: 'Incident',
  er: 'ER Case',
  i9: 'I-9',
  separation: 'Separation',
  onboarding: 'Onboarding',
  legislation: 'Legislation',
  requirement: 'Requirement',
  manual: 'Task',
}

function daysLabel(d: number): string {
  if (d < 0) return `${Math.abs(d)}d overdue`
  if (d === 0) return 'Today'
  if (d === 1) return 'Tomorrow'
  if (d >= 999) return ''
  return `${d}d`
}

function daysColor(d: number): string {
  if (d < 0) return 'text-red-400'
  if (d <= 7) return 'text-amber-400'
  if (d <= 30) return 'text-yellow-400'
  return 'text-zinc-500'
}

interface Props {
  item: UnifiedTask
  onComplete?: (id: string) => Promise<void>
  onUncomplete?: (id: string) => Promise<void>
  onDismiss?: (category: string, id: string) => Promise<void>
  onDelete?: (id: string) => Promise<void>
}

export default function TaskRow({ item, onComplete, onUncomplete, onDismiss, onDelete }: Props) {
  const navigate = useNavigate()
  const isCompleted = item.status === 'completed'
  const isManual = item.source === 'manual'

  function handleClick() {
    if (item.link) navigate(item.link)
  }

  function handleCheck(e: React.MouseEvent) {
    e.stopPropagation()
    if (isCompleted) {
      onUncomplete?.(item.id)
    } else {
      onComplete?.(item.id)
    }
  }

  function handleDismiss(e: React.MouseEvent) {
    e.stopPropagation()
    onDismiss?.(item.category, item.source_id || item.title)
  }

  function handleDelete(e: React.MouseEvent) {
    e.stopPropagation()
    onDelete?.(item.id)
  }

  return (
    <div
      onClick={handleClick}
      className={`flex items-center gap-3 px-3 py-2.5 rounded-md hover:bg-zinc-800/50 transition-colors group ${
        item.link ? 'cursor-pointer' : ''
      } ${isCompleted ? 'opacity-50' : ''}`}
    >
      {/* Checkbox for manual tasks, severity dot for auto */}
      {isManual ? (
        <button
          onClick={handleCheck}
          className={`w-4 h-4 rounded border shrink-0 flex items-center justify-center transition-colors ${
            isCompleted
              ? 'bg-emerald-600 border-emerald-600'
              : 'border-zinc-600 hover:border-zinc-400'
          }`}
        >
          {isCompleted && (
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
              <path d="M2 5L4 7L8 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </button>
      ) : (
        <div className={`w-2 h-2 rounded-full shrink-0 ${SEV_DOT[item.severity] ?? SEV_DOT.info}`} />
      )}

      <div className="flex-1 min-w-0">
        <div className={`text-sm truncate ${isCompleted ? 'line-through text-zinc-500' : 'text-zinc-200'}`}>
          {item.title}
        </div>
        {item.subtitle && (
          <div className="text-xs text-zinc-500 truncate mt-0.5">{item.subtitle}</div>
        )}
      </div>

      <span className="shrink-0 px-2 py-0.5 text-[10px] font-medium rounded-full bg-zinc-800 text-zinc-400">
        {CATEGORY_LABEL[item.category] ?? item.category}
      </span>

      {!isCompleted && item.days_until < 999 && (
        <span className={`shrink-0 text-xs font-medium tabular-nums ${daysColor(item.days_until)}`}>
          {daysLabel(item.days_until)}
        </span>
      )}

      {/* Actions */}
      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
        {isManual && !isCompleted && onDelete && (
          <button
            onClick={handleDelete}
            className="p-1 rounded text-zinc-600 hover:text-red-400 transition-colors"
            title="Delete task"
          >
            <Trash2 size={12} />
          </button>
        )}
        {!isManual && onDismiss && (
          <button
            onClick={handleDismiss}
            className="p-1 rounded text-zinc-600 hover:text-zinc-300 transition-colors"
            title="Dismiss"
          >
            <X size={12} />
          </button>
        )}
      </div>
    </div>
  )
}
