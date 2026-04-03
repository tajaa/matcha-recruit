import { useState } from 'react'
import { Plus } from 'lucide-react'
import type { UpcomingItem } from '../../types/dashboard'
import type { ManualTask } from '../../api/matchaWork'
import TaskSection from './TaskSection'
import TaskCreateForm from './TaskCreateForm'

type TimeHorizon = 'overdue' | 'today' | 'this_week' | 'this_month' | 'this_quarter'

export interface UnifiedTask {
  id: string
  source: 'auto' | 'manual'
  source_id?: string
  category: string
  title: string
  subtitle: string | null
  date: string | null
  days_until: number
  severity: string
  link: string | null
  status?: string
  priority?: string
}

function groupByHorizon(items: UnifiedTask[]): Record<TimeHorizon, UnifiedTask[]> {
  const now = new Date()
  const dayOfWeek = now.getDay()
  const daysUntilEndOfWeek = 7 - dayOfWeek

  const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0)
  const daysUntilEndOfMonth = Math.ceil((endOfMonth.getTime() - now.getTime()) / 86400000)

  const quarterMonth = Math.ceil((now.getMonth() + 1) / 3) * 3
  const endOfQuarter = new Date(now.getFullYear(), quarterMonth, 0)
  const daysUntilEndOfQuarter = Math.ceil((endOfQuarter.getTime() - now.getTime()) / 86400000)

  const groups: Record<TimeHorizon, UnifiedTask[]> = {
    overdue: [], today: [], this_week: [], this_month: [], this_quarter: [],
  }

  for (const item of items) {
    if (item.days_until < 0) groups.overdue.push(item)
    else if (item.days_until === 0) groups.today.push(item)
    else if (item.days_until <= daysUntilEndOfWeek) groups.this_week.push(item)
    else if (item.days_until <= daysUntilEndOfMonth) groups.this_month.push(item)
    else if (item.days_until <= daysUntilEndOfQuarter) groups.this_quarter.push(item)
  }

  return groups
}

function priorityToSeverity(p: string): string {
  if (p === 'critical') return 'critical'
  if (p === 'high') return 'warning'
  return 'info'
}

interface Props {
  autoItems: UpcomingItem[]
  manualItems: ManualTask[]
  dismissedIds: string[]
  onCreateTask: (body: { title: string; description?: string; due_date?: string; priority?: string }) => Promise<void>
  onCompleteTask: (id: string) => Promise<void>
  onUncompleteTask: (id: string) => Promise<void>
  onDismiss: (category: string, id: string) => Promise<void>
  onDeleteTask: (id: string) => Promise<void>
}

export default function TaskBoard({
  autoItems, manualItems, dismissedIds, onCreateTask, onCompleteTask, onUncompleteTask, onDismiss, onDeleteTask,
}: Props) {
  const [showCreate, setShowCreate] = useState(false)

  // Filter out dismissed auto items
  const dismissedSet = new Set(dismissedIds)
  const filteredAuto: UnifiedTask[] = autoItems
    .filter((item) => {
      const sid = (item as unknown as Record<string, unknown>).source_id as string || ''
      return !dismissedSet.has(`${item.category}:${sid}`)
    })
    .map((item, i) => {
      const sid = (item as unknown as Record<string, unknown>).source_id as string || ''
      return {
        id: `auto-${item.category}-${i}`,
        source: 'auto' as const,
        source_id: sid,
        category: item.category,
        title: item.title,
        subtitle: item.subtitle,
        date: item.date,
        days_until: item.days_until,
        severity: item.severity,
        link: item.link,
      }
    })

  // Pending manual tasks
  const pendingManual: UnifiedTask[] = manualItems
    .filter((t) => t.status === 'pending')
    .map((t) => ({
      id: t.id,
      source: 'manual' as const,
      category: 'manual',
      title: t.title,
      subtitle: t.description,
      date: t.date,
      days_until: t.days_until ?? 999,
      severity: priorityToSeverity(t.priority),
      link: t.link,
      status: t.status,
      priority: t.priority,
    }))

  // Completed manual tasks
  const completedManual = manualItems.filter((t) => t.status === 'completed')

  const allPending = [...filteredAuto, ...pendingManual].sort((a, b) => a.days_until - b.days_until)
  const groups = groupByHorizon(allPending)
  const totalCount = allPending.length

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-zinc-500">
          {totalCount} item{totalCount !== 1 ? 's' : ''} across all horizons
        </span>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition-colors"
        >
          <Plus size={14} />
          New Task
        </button>
      </div>

      {showCreate && (
        <TaskCreateForm
          onSubmit={async (body) => {
            await onCreateTask(body)
            setShowCreate(false)
          }}
          onCancel={() => setShowCreate(false)}
        />
      )}

      <TaskSection label="Overdue" items={groups.overdue} defaultOpen accent="text-red-400"
        onComplete={onCompleteTask} onUncomplete={onUncompleteTask} onDismiss={onDismiss} onDelete={onDeleteTask} />
      <TaskSection label="Today" items={groups.today} defaultOpen accent="text-amber-300"
        onComplete={onCompleteTask} onUncomplete={onUncompleteTask} onDismiss={onDismiss} onDelete={onDeleteTask} />
      <TaskSection label="This Week" items={groups.this_week}
        defaultOpen={groups.overdue.length === 0 && groups.today.length === 0}
        onComplete={onCompleteTask} onUncomplete={onUncompleteTask} onDismiss={onDismiss} onDelete={onDeleteTask} />
      <TaskSection label="This Month" items={groups.this_month}
        onComplete={onCompleteTask} onUncomplete={onUncompleteTask} onDismiss={onDismiss} onDelete={onDeleteTask} />
      <TaskSection label="This Quarter" items={groups.this_quarter}
        onComplete={onCompleteTask} onUncomplete={onUncompleteTask} onDismiss={onDismiss} onDelete={onDeleteTask} />

      {completedManual.length > 0 && (
        <TaskSection
          label="Completed"
          items={completedManual.map((t) => ({
            id: t.id,
            source: 'manual' as const,
            category: 'manual',
            title: t.title,
            subtitle: t.description,
            date: t.date,
            days_until: 0,
            severity: 'info',
            link: t.link,
            status: 'completed',
          }))}
          onComplete={onCompleteTask}
          onUncomplete={onUncompleteTask}
          onDismiss={onDismiss}
          onDelete={onDeleteTask}
          accent="text-zinc-500"
        />
      )}
    </div>
  )
}
