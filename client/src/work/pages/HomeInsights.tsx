import { Link } from 'react-router-dom'
import { Circle, FileText, KanbanSquare, MessageSquare, NotebookPen } from 'lucide-react'
import type { MWOpenTask } from '../api/matchaWork/dashboard'
import { relativeTime, shortDate } from '../../utils/format'
import { groupTasks, type PickUpItem } from './homeData'

// Home's two working lists. Everything here is plain data in, links out; the
// page decides where they sit.

const MONO = "font-['JetBrains_Mono',ui-monospace,monospace]"

function todayKey(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

function dueLabel(due: string | null): { text: string; late: boolean } | null {
  if (!due) return null
  const day = due.slice(0, 10)
  const [y, m, d] = day.split('-').map(Number)
  if (!y || !m || !d) return null
  return { text: shortDate(new Date(y, m - 1, d)), late: day < todayKey() }
}

/** "Up next": the tasks assigned to you, one short run per workspace. */
export function UpNext({ tasks, base, perGroup = 4 }: { tasks: MWOpenTask[]; base: string; perGroup?: number }) {
  if (tasks.length === 0) {
    return <p className="py-2 text-sm text-w-faint">Nothing assigned to you. Tasks people give you on a board show up here.</p>
  }
  return (
    <div className="space-y-5">
      {groupTasks(tasks).map((group) => {
        const hidden = group.tasks.length - perGroup
        return (
          <div key={group.projectId}>
            <Link
              to={`${base}/projects/${group.projectId}`}
              className="mb-1 flex items-baseline justify-between gap-3 px-2 text-xs font-semibold text-w-dim hover:text-w-text"
            >
              <span className="truncate">{group.title}</span>
              <span className={`${MONO} shrink-0 text-[10px] font-normal text-w-faint`}>{group.tasks.length}</span>
            </Link>
            <ul>
              {group.tasks.slice(0, perGroup).map((task) => {
                const due = dueLabel(task.due_date)
                return (
                  <li key={`${task.is_subtask ? 'subtask' : 'task'}:${task.id}`}>
                    <Link
                      to={`${base}/projects/${task.project_id}`}
                      className="group flex items-start gap-2.5 rounded-lg px-2 py-1.5 hover:bg-w-surface2/70"
                    >
                      <Circle size={13} strokeWidth={1.75} className="mt-[3px] shrink-0 text-w-faint group-hover:text-w-accent" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm text-w-text">{task.title}</span>
                        {task.is_subtask && (
                          <span className="block truncate text-[11px] text-w-faint">Subtask of {task.parent_title ?? 'a task'}</span>
                        )}
                      </span>
                      {due && (
                        <span className={`${MONO} mt-[3px] shrink-0 text-[10px] ${due.late ? 'text-w-accent' : 'text-w-faint'}`}>
                          {due.late ? 'Late · ' : ''}{due.text}
                        </span>
                      )}
                    </Link>
                  </li>
                )
              })}
            </ul>
            {hidden > 0 && (
              <Link to={`${base}/projects/${group.projectId}`} className="ml-8 text-[11px] text-w-faint hover:text-w-accent">
                {hidden} more in {group.title}
              </Link>
            )}
          </div>
        )
      })}
    </div>
  )
}

const KIND_ICON = { chat: MessageSquare, workspace: KanbanSquare, task: FileText, journal: NotebookPen } as const

export function PickUp({ items }: { items: PickUpItem[] }) {
  if (items.length === 0) {
    return <p className="py-2 text-sm text-w-faint">Nothing yet. Start a chat or open a workspace and it will be here next time.</p>
  }
  return (
    <ul>
      {items.map((item) => {
        const Icon = KIND_ICON[item.kind]
        return (
          <li key={item.key}>
            <Link to={item.path} className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 hover:bg-w-surface2/70">
              <Icon size={13} strokeWidth={1.75} className="shrink-0 text-w-dim" />
              <span className="min-w-0 flex-1 truncate text-sm text-w-text">{item.title}</span>
              <span className={`${MONO} shrink-0 text-[10px] text-w-faint`}>
                {relativeTime(item.at, { empty: '', justNowLabel: 'now', maxRelativeDays: 7, absolute: shortDate })}
              </span>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
