import { Paperclip, RefreshCw, Calendar, ListChecks, CheckCircle2 } from 'lucide-react'
import type { MWProjectTask, TaskPriority } from '../../types/matcha-work'

interface KanbanCardProps {
  task: MWProjectTask
  onClick: () => void
  /** Native HTML5 drag start — the board wires this to set the dragged task id. */
  onDragStart: (e: React.DragEvent) => void
  onDragEnd: () => void
  dragging?: boolean
}

const PRIORITY_DOT: Record<TaskPriority, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-zinc-500',
}

const PRIORITY_LABEL: Record<TaskPriority, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

/** Human-readable assignee, mirroring the desktop `displayAssignee`: prefer a
 *  real `assigned_name`, else derive from the email/name local-part
 *  ("jane.doe@…" → "Jane Doe"). Null when unassigned. */
function displayAssignee(task: MWProjectTask): string | null {
  const name = task.assigned_name?.trim()
  if (name && !name.includes('@')) return name
  const raw = task.assigned_email ?? task.assigned_name
  const local = raw?.split('@')[0]
  if (!local) return null
  return local
    .replace(/[._]/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function KanbanCard({ task, onClick, onDragStart, onDragEnd, dragging }: KanbanCardProps) {
  const assignee = displayAssignee(task)
  const assigneeInitial = assignee ? assignee.charAt(0).toUpperCase() : null
  const completed = task.status === 'completed'

  const subtaskTotal = task.subtask_total ?? 0
  const subtaskDone = task.subtask_done ?? 0
  const subtaskFrac = subtaskTotal > 0 ? subtaskDone / subtaskTotal : 0
  const subtasksComplete = subtaskTotal > 0 && subtaskDone >= subtaskTotal

  const cycles = task.review_cycle_count ?? 0
  const attachmentCount = task.attachments?.length ?? 0
  const reviewNote = task.review_note?.trim()

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onClick}
      className={`group cursor-pointer rounded-lg border border-zinc-800 bg-zinc-900 p-3 transition-colors hover:border-zinc-700 ${
        dragging ? 'opacity-40' : ''
      }`}
    >
      {/* Title */}
      <p
        className={`text-sm leading-snug text-zinc-100 ${
          completed ? 'line-through text-zinc-500' : ''
        }`}
      >
        {task.title}
      </p>

      {/* Progress note ("where we're at") */}
      {task.progress_note?.trim() && (
        <p className="mt-1.5 truncate text-xs italic text-zinc-500">{task.progress_note}</p>
      )}

      {/* Why it bounced — shown while sitting in the rework lane */}
      {task.board_column === 'changes_requested' && reviewNote && (
        <div className="mt-1.5 flex items-start gap-1 text-xs text-orange-400/90">
          <RefreshCw className="mt-0.5 h-3 w-3 shrink-0" />
          <span className="line-clamp-2">{reviewNote}</span>
        </div>
      )}

      {/* Meta row: priority, churn, column tags */}
      <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <span className="flex items-center gap-1 text-xs text-zinc-400">
          <span className={`h-1.5 w-1.5 rounded-full ${PRIORITY_DOT[task.priority]}`} />
          {PRIORITY_LABEL[task.priority]}
        </span>

        {cycles > 0 && (
          <span
            className="flex items-center gap-0.5 rounded bg-orange-500/15 px-1.5 py-0.5 text-[10px] font-bold text-orange-400"
            title={`Sent back from review ${cycles} time${cycles === 1 ? '' : 's'}`}
          >
            <RefreshCw className="h-2.5 w-2.5" />×{cycles}
          </span>
        )}

        {task.category && task.category !== 'manual' && (
          <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">
            {task.category}
          </span>
        )}

        {task.element_name && (
          <span className="rounded bg-emerald-500/12 px-1.5 py-0.5 text-[10px] font-medium text-emerald-400">
            {task.element_name}
          </span>
        )}
      </div>

      {/* Subtask progress bar */}
      {subtaskTotal > 0 && (
        <div className="mt-2 flex items-center gap-1.5">
          {subtasksComplete ? (
            <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald-500" />
          ) : (
            <ListChecks className="h-3 w-3 shrink-0 text-zinc-500" />
          )}
          <div className="h-[3px] w-14 overflow-hidden rounded-full bg-zinc-700">
            <div
              className={`h-full ${subtasksComplete ? 'bg-emerald-500' : 'bg-emerald-400'}`}
              style={{ width: `${subtaskFrac * 100}%` }}
            />
          </div>
          <span className="text-[10px] font-medium text-zinc-400">
            {subtaskDone}/{subtaskTotal}
          </span>
        </div>
      )}

      {/* Footer: assignee, due date, attachments */}
      {(assignee || task.due_date || attachmentCount > 0) && (
        <div className="mt-2.5 flex items-center gap-2.5 text-xs text-zinc-400">
          {assignee && assigneeInitial && (
            <span className="flex items-center gap-1 truncate">
              <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-500/20 text-[9px] font-semibold text-emerald-400">
                {assigneeInitial}
              </span>
              <span className="truncate">{assignee}</span>
            </span>
          )}
          {task.due_date && (
            <span className="flex shrink-0 items-center gap-1">
              <Calendar className="h-3 w-3" />
              {task.due_date.slice(0, 10)}
            </span>
          )}
          {attachmentCount > 0 && (
            <span className="flex shrink-0 items-center gap-1">
              <Paperclip className="h-3 w-3" />
              {attachmentCount}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
