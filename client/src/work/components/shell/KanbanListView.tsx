import { useState } from 'react'
import { MoreHorizontal } from 'lucide-react'
import type { MWProjectTask, TaskPriority } from '../../types'
import { KANBAN_COLUMNS } from '../../utils/kanbanColumns'
import { taskMatches } from '../../utils/kanbanSearch'

interface KanbanListViewProps {
  tasks: MWProjectTask[]
  searchTokens: string[]
  myUserId: string | null
  changedIds: Set<string>
  onOpen: (task: MWProjectTask) => void
  /** Opens a row's action sheet (Move to / Duplicate / Delete). */
  onMenu?: (taskId: string) => void
}

const PRIORITY_DOT: Record<TaskPriority, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-w-dim',
}

function displayAssignee(task: MWProjectTask): string | null {
  const name = task.assigned_name?.trim()
  if (name && !name.includes('@')) return name
  const raw = task.assigned_email ?? task.assigned_name
  const local = raw?.split('@')[0]
  if (!local) return null
  return local.replace(/[._]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function KanbanListView({ tasks, searchTokens, myUserId, changedIds, onOpen, onMenu }: KanbanListViewProps) {
  const [mineOnly, setMineOnly] = useState(() => localStorage.getItem('mw-kanban-list-mine') === '1')

  function toggleMine(value: boolean) {
    setMineOnly(value)
    localStorage.setItem('mw-kanban-list-mine', value ? '1' : '0')
  }

  const filtered = tasks
    .filter((t) => searchTokens.length === 0 || taskMatches(t, searchTokens))
    .filter((t) => !mineOnly || t.assigned_to === myUserId)

  return (
    <div className="flex h-full flex-col overflow-y-auto px-3 py-2">
      <div className="mb-2 flex items-center gap-1.5">
        <button
          onClick={() => toggleMine(false)}
          className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
            !mineOnly ? 'bg-w-accent/15 text-w-accent' : 'text-w-dim hover:text-w-text'
          }`}
        >
          All
        </button>
        <button
          onClick={() => toggleMine(true)}
          className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
            mineOnly ? 'bg-w-accent/15 text-w-accent' : 'text-w-dim hover:text-w-text'
          }`}
        >
          Mine
        </button>
        <span className="ml-auto text-xs text-w-dim">
          {filtered.length} ticket{filtered.length === 1 ? '' : 's'}
        </span>
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-1 items-center justify-center text-sm text-w-faint">
          {mineOnly ? 'Nothing assigned to you here.' : 'No tickets yet.'}
        </div>
      ) : (
        <div className="space-y-4">
          {KANBAN_COLUMNS.map((col) => {
            const rows = filtered.filter((t) => t.board_column === col.key)
            if (rows.length === 0) return null
            return (
              <div key={col.key}>
                <div className="mb-1 flex items-center gap-2 px-1">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-w-dim">
                    {col.label}
                  </span>
                  <span className="rounded bg-w-surface2 px-1.5 py-0.5 text-[10px] text-w-dim">
                    {rows.length}
                  </span>
                </div>
                <div className="overflow-hidden rounded-lg border border-w-line">
                  {rows.map((task, i) => {
                    const assignee = displayAssignee(task)
                    const isMe = task.assigned_to === myUserId
                    const total = task.subtask_total ?? 0
                    const done = task.subtask_done ?? 0
                    return (
                      <div
                        key={task.id}
                        className={`group flex items-center transition-colors hover:bg-w-surface ${
                          i > 0 ? 'border-t border-w-line' : ''
                        } ${changedIds.has(task.id) ? 'bg-yellow-500/5' : 'bg-w-bg'}`}
                      >
                      <button
                        onClick={() => onOpen(task)}
                        className="flex min-w-0 flex-1 items-center gap-2.5 py-2 pl-3 text-left text-sm"
                      >
                        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${PRIORITY_DOT[task.priority]}`} />
                        <span
                          className={`min-w-0 flex-1 truncate ${
                            changedIds.has(task.id) ? 'font-semibold text-w-text' : 'text-w-text'
                          } ${task.status === 'completed' ? 'text-w-dim line-through' : ''}`}
                        >
                          {task.title}
                        </span>
                        {task.category && task.category !== 'manual' && (
                          <span className="shrink-0 rounded bg-w-surface2 px-1.5 py-0.5 text-[10px] font-medium text-w-dim">
                            {task.category}
                          </span>
                        )}
                        {total > 0 && (
                          <span className="shrink-0 font-mono text-[10px] text-w-dim">
                            {done}/{total}
                          </span>
                        )}
                        {assignee && (
                          <span className={`shrink-0 truncate text-xs ${isMe ? 'text-w-accent' : 'text-w-dim'}`}>
                            {assignee}
                          </span>
                        )}
                      </button>
                      {onMenu && (
                        <button
                          onClick={() => onMenu(task.id)}
                          title="Task actions"
                          aria-label="Task actions"
                          className="shrink-0 px-2 py-2 text-w-dim transition-colors hover:text-w-text md:opacity-0 md:group-hover:opacity-100"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </button>
                      )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
