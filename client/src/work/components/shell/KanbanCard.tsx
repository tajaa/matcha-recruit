import { Paperclip, RefreshCw, Calendar, ListChecks, CheckCircle2, Circle, ChevronRight, Clock } from 'lucide-react'
import type { MWProjectTask } from '../../types'
import Avatar from '../../../components/shared/Avatar'
import { KANBAN_COLUMNS } from '../../utils/kanbanColumns'
import { KANBAN_TEMPLATES } from '../../utils/kanbanTemplates'

/** Chip color for a task's category — reuses the same per-template color the
 *  "+" compose menu uses (KANBAN_TEMPLATES.colorClass), so a "Bug" card and
 *  the Bug template entry always agree. Unrecognized/manual categories fall
 *  back to a neutral chip. */
function categoryChip(category: string | null | undefined): { label: string; colorClass: string } | null {
  if (!category || category === 'manual') return null
  const tpl = KANBAN_TEMPLATES.find((t) => t.key === category)
  return { label: tpl?.displayName ?? category, colorClass: tpl?.colorClass ?? 'text-w-dim' }
}

interface KanbanCardProps {
  task: MWProjectTask
  onClick: () => void
  /** Native HTML5 drag start — the board wires this to set the dragged task id. */
  onDragStart: (e: React.DragEvent) => void
  onDragEnd: () => void
  dragging?: boolean
  /** Moved or created since this user last looked at the board — draws a gold
   *  ring, cleared when the card is opened. */
  ringed?: boolean
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

/** "Jun 15" — no time, matches the desktop card's compact footer. */
function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/** "2h ago" / "3d ago", falling back to a short date past 7 days. */
function relative(iso: string): string {
  const secs = (Date.now() - new Date(iso).getTime()) / 1000
  if (secs < 60) return 'just now'
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  if (secs < 7 * 86400) return `${Math.floor(secs / 86400)}d ago`
  return shortDate(iso)
}

/** Staleness bucket — mirrors the desktop `MWProjectTask.aging`: anchor is
 *  last_moved_at ?? created_at so a move resets the clock; done cards never age. */
function aging(task: MWProjectTask): 'none' | 'warn' | 'overdue' {
  if (task.board_column === 'done' || task.status === 'completed') return 'none'
  const anchor = task.last_moved_at ?? task.created_at
  const hours = (Date.now() - new Date(anchor).getTime()) / 3_600_000
  if (hours >= 12) return 'overdue'
  if (hours >= 6) return 'warn'
  return 'none'
}

export default function KanbanCard({ task, onClick, onDragStart, onDragEnd, dragging, ringed }: KanbanCardProps) {
  const assignee = displayAssignee(task)
  const completed = task.status === 'completed'

  const subtaskTotal = task.subtask_total ?? 0
  const subtaskDone = task.subtask_done ?? 0
  const subtaskFrac = subtaskTotal > 0 ? subtaskDone / subtaskTotal : 0
  const subtasksComplete = subtaskTotal > 0 && subtaskDone >= subtaskTotal

  const cycles = task.review_cycle_count ?? 0
  const attachmentCount = task.attachments?.length ?? 0
  const reviewNote = task.review_note?.trim()

  // Left-edge accent — critical/high only. Medium is the default priority, so
  // marking it would put an accent on nearly every card; absence = normal.
  const edgeColor = task.priority === 'critical' ? 'bg-red-500' : task.priority === 'high' ? 'bg-orange-500' : null
  const ageState = aging(task)
  const ageColor = ageState === 'overdue' ? 'text-red-400' : ageState === 'warn' ? 'text-orange-400' : 'text-w-dim'
  const columnLabel = KANBAN_COLUMNS.find((c) => c.key === task.board_column)?.label
  const tag = categoryChip(task.category)

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onClick}
      className={`group relative cursor-pointer overflow-hidden rounded-lg border bg-w-surface p-3 transition-all hover:scale-[1.01] ${
        ringed
          ? 'border-yellow-400/75 shadow-[0_0_10px_rgba(250,204,21,0.35)]'
          : 'border-w-line hover:border-w-accent/40'
      } ${dragging ? 'opacity-40' : ''}`}
    >
      {edgeColor && <span className={`absolute inset-y-1.5 left-0 w-[3px] rounded-full ${edgeColor}`} />}

      {/* Title row: completion state (left) + title + creator avatar (right) */}
      <div className="flex items-start gap-2">
        {completed ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-w-accent" />
        ) : (
          <Circle className="mt-0.5 h-4 w-4 shrink-0 text-w-faint" />
        )}
        <p className={`min-w-0 flex-1 line-clamp-3 text-sm leading-snug text-w-text ${completed ? 'line-through text-w-dim' : ''}`}>
          {task.title}
        </p>
        {task.created_by_name && (
          <div className="shrink-0" title={`Created by ${task.created_by_name}`}>
            <Avatar name={task.created_by_name} avatarUrl={task.created_by_avatar_url} size="xs" />
          </div>
        )}
      </div>

      {/* Status row: column + assignee */}
      <div className="mt-1.5 flex items-center gap-1 pl-6 text-xs text-w-dim">
        <ChevronRight className="h-3 w-3 shrink-0" />
        <span className="truncate">{columnLabel}</span>
        {assignee && (
          <span className="ml-1.5 flex min-w-0 items-center gap-1 truncate">
            <Avatar name={assignee} avatarUrl={task.assigned_avatar_url} size="xs" />
            <span className="truncate">{assignee}</span>
          </span>
        )}
      </div>

      {/* Progress note ("where we're at") */}
      {task.progress_note?.trim() && (
        <p className="mt-1.5 truncate pl-6 text-xs italic text-w-dim">{task.progress_note}</p>
      )}

      {/* Why it bounced — shown while sitting in the rework lane */}
      {task.board_column === 'changes_requested' && reviewNote && (
        <div className="mt-1.5 flex items-start gap-1 pl-6 text-xs text-orange-400/90">
          <RefreshCw className="mt-0.5 h-3 w-3 shrink-0" />
          <span className="line-clamp-2">{reviewNote}</span>
        </div>
      )}

      {/* Tag chip + churn. Priority is the left-edge accent above (critical/high
          only) — no dot/label here, it read as noise on every card since medium
          (the default) would otherwise tag along too. */}
      {(cycles > 0 || tag || task.element_name) && (
        <div className="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-1.5 pl-6">
          {tag && (
            <span className={`rounded bg-current/10 px-1.5 py-0.5 text-[10px] font-semibold ${tag.colorClass}`}>
              {tag.label}
            </span>
          )}

          {cycles > 0 && (
            <span
              className="flex items-center gap-0.5 rounded bg-orange-500/15 px-1.5 py-0.5 text-[10px] font-bold text-orange-400"
              title={`Sent back from review ${cycles} time${cycles === 1 ? '' : 's'}`}
            >
              <RefreshCw className="h-2.5 w-2.5" />×{cycles}
            </span>
          )}

          {task.element_name && (
            <span className="rounded bg-w-accent/12 px-1.5 py-0.5 text-[10px] font-medium text-w-accent">
              {task.element_name}
            </span>
          )}
        </div>
      )}

      {/* Subtask progress bar */}
      {subtaskTotal > 0 && (
        <div className="mt-2 flex items-center gap-1.5 pl-6">
          {subtasksComplete ? (
            <CheckCircle2 className="h-3 w-3 shrink-0 text-w-accent" />
          ) : (
            <ListChecks className="h-3 w-3 shrink-0 text-w-dim" />
          )}
          <div className="h-[3px] flex-1 max-w-24 overflow-hidden rounded-full bg-w-surface2">
            <div className="h-full bg-w-accent" style={{ width: `${subtaskFrac * 100}%` }} />
          </div>
          <span className="ml-auto text-[10px] font-medium text-w-dim">
            {subtaskDone}/{subtaskTotal}
          </span>
        </div>
      )}

      {/* Due date / attachments */}
      {(task.due_date || attachmentCount > 0) && (
        <div className="mt-2 flex items-center gap-2.5 pl-6 text-xs text-w-dim">
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

      {/* Timestamps — compact date + aging-tinted elapsed time, full detail
          in the title attr (matches the desktop card's tooltip convention). */}
      <div
        className="mt-2 flex items-center gap-1 pl-6 text-[10px] text-w-faint"
        title={`Added ${new Date(task.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}`}
      >
        <span>{shortDate(task.created_at)}</span>
        {task.last_moved_at ? (
          <span className={`flex items-center gap-0.5 ${ageColor}`}>
            {ageState !== 'none' && <Clock className="h-2.5 w-2.5" />}
            <span>· moved {relative(task.last_moved_at)}</span>
          </span>
        ) : (
          ageState !== 'none' && (
            <span className={`flex items-center gap-0.5 ${ageColor}`}>
              <Clock className="h-2.5 w-2.5" />
              <span>{relative(task.created_at)}</span>
            </span>
          )
        )}
      </div>
    </div>
  )
}
