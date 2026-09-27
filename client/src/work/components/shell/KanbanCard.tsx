import { Paperclip, RefreshCw, Calendar, ListChecks, CheckCircle2, Circle, Clock, MoreHorizontal, GitPullRequest, Bot, Layers, Sparkles } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { MWProjectTask } from '../../types'
import Avatar from '../../../components/shared/Avatar'
import { KANBAN_TEMPLATES } from '../../utils/kanbanTemplates'
import { autoPRProgressBanner, type AutoPRProgressKind } from '../../utils/autoprProgress'

/** Category label — reuses the same per-template color and icon the "+"
 *  compose menu uses (KANBAN_TEMPLATES), so a "Bug" card and the Bug template
 *  entry always agree. Unrecognized/manual categories fall back to neutral. */
function categoryLabel(category: string | null | undefined): { label: string; colorClass: string; icon: LucideIcon | null } | null {
  if (!category || category === 'manual') return null
  const tpl = KANBAN_TEMPLATES.find((t) => t.key === category)
  return { label: tpl?.displayName ?? category, colorClass: tpl?.colorClass ?? 'text-w-dim', icon: tpl?.icon ?? null }
}

/** AutoPR strip tone: green when a PR is ready, blue for informational, orange when a human must act. */
function autoPRTone(kind: AutoPRProgressKind): string {
  if (kind === 'ready') return 'bg-emerald-500/[0.07] text-emerald-400'
  if (kind === 'already_fixed' || kind === 'status') return 'bg-sky-500/[0.07] text-sky-400'
  return 'bg-orange-500/[0.07] text-orange-400'
}

// Mirrors the desktop `elevatedCard`: a hairline highlight on top (only
// visible on dark themes) plus a tight contact shadow and a soft ambient one,
// so cards lift off the lane instead of blending into it.
const CARD_SHADOW =
  'shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_1px_2px_rgba(0,0,0,0.16),0_4px_12px_-6px_rgba(0,0,0,0.3)]'
const CARD_SHADOW_HOVER =
  'hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_2px_4px_rgba(0,0,0,0.18),0_10px_22px_-10px_rgba(0,0,0,0.45)]'

interface KanbanCardProps {
  task: MWProjectTask
  onClick: () => void
  /** Native HTML5 drag start — the board wires this to set the dragged task id. */
  onDragStart: (e: React.DragEvent) => void
  onDragEnd: () => void
  dragging?: boolean
  /** Moved or created since this user last looked at the board — draws an
   *  amber dot, cleared when the card is opened. */
  ringed?: boolean
  /** Opens the card's action sheet (Move to / Duplicate / Delete). This is the
   *  ONLY way to move a card on touch — the drag handlers above are HTML5
   *  drag events, which never fire from a finger. */
  onMenu?: () => void
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

/**
 * Board card, laid out like the desktop `KanbanCardView`: an optional
 * one-line AutoPR strip, the title, then at most three quiet 10px lines —
 * attention (progress / send-back note), category, and one meta row. The lane
 * is already the card's column, so it isn't repeated on the face.
 */
export default function KanbanCard({ task, onClick, onDragStart, onDragEnd, dragging, ringed, onMenu }: KanbanCardProps) {
  const assignee = displayAssignee(task)
  const completed = task.status === 'completed'

  const subtaskTotal = task.subtask_total ?? 0
  const subtaskDone = task.subtask_done ?? 0
  const subtasksComplete = subtaskTotal > 0 && subtaskDone >= subtaskTotal

  // Defense in depth alongside the server-side scheme check (tasks.py PATCH):
  // never render an href straight from stored data without re-validating it's
  // http(s) here too — a javascript:/data: value must render as inert text,
  // not a clickable link.
  const safePrUrl = task.pr_url && /^https?:\/\//i.test(task.pr_url) ? task.pr_url : null

  const cycles = task.review_cycle_count ?? 0
  const attachmentCount = task.attachments?.length ?? 0
  const reviewNote = task.review_note?.trim()
  const progressNote = task.progress_note?.trim()
  const autoPRBanner = autoPRProgressBanner(task.progress_note, task.pr_number)
  const pendingCommitSubtasks = task.pending_commit_subtask_count ?? 0

  // Left-edge accent — critical/high only. Medium is the default priority, so
  // marking it would put an accent on nearly every card; absence = normal.
  const edgeColor = task.priority === 'critical' ? 'bg-red-500' : task.priority === 'high' ? 'bg-orange-500' : null
  const ageState = aging(task)
  const ageColor = ageState === 'overdue' ? 'text-red-400' : ageState === 'warn' ? 'text-orange-400' : 'text-w-faint'
  const tag = categoryLabel(task.category)
  const TagIcon = tag?.icon

  const added = new Date(task.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onClick}
      className={`group relative cursor-pointer overflow-hidden rounded-lg border border-w-line bg-w-surface transition-[transform,box-shadow] duration-150 ease-out hover:scale-[1.006] ${CARD_SHADOW} ${CARD_SHADOW_HOVER} ${
        dragging ? 'opacity-40' : ''
      }`}
    >
      {edgeColor && <span className={`absolute inset-y-[7px] left-[1.5px] w-[2px] rounded-full ${edgeColor}`} />}

      {ringed && (
        <span
          role="img"
          aria-label="Updated since you last looked"
          className="absolute right-[7px] top-[7px] h-1.5 w-1.5 rounded-full bg-yellow-400 shadow-[0_0_6px_rgba(250,204,21,0.5)]"
        />
      )}

      {autoPRBanner && (
        <div
          className={`flex items-center gap-1.5 border-b border-w-line/50 px-2.5 py-1 text-[10px] ${autoPRTone(autoPRBanner.kind)}`}
          title={task.progress_note ?? undefined}
        >
          <Bot className="h-3 w-3 shrink-0" />
          <span className="truncate">
            <span className="font-medium">Auto setup</span>
            <span className="text-w-dim"> · {autoPRBanner.message}</span>
          </span>
        </div>
      )}

      {/* Title: completion state + title. Right padding keeps the unread dot clear. */}
      <div className="flex items-start gap-2 px-2.5 pb-1.5 pr-4 pt-2.5">
        {completed ? (
          <CheckCircle2 className="mt-[3px] h-3 w-3 shrink-0 text-w-accent" />
        ) : (
          <Circle className="mt-[3px] h-3 w-3 shrink-0 text-w-faint" />
        )}
        <p className={`min-w-0 flex-1 line-clamp-3 text-[13px] leading-snug text-w-text ${completed ? 'line-through text-w-dim' : ''}`}>
          {task.title}
        </p>
      </div>

      <div className="space-y-1.5 px-2.5 pb-2 text-[10px]">
        {/* Where it's at — the AutoPR strip above already says it for automation notes. */}
        {!autoPRBanner && progressNote && <p className="truncate text-w-dim" title={progressNote}>{progressNote}</p>}

        {/* Why it bounced — shown while sitting in the rework lane */}
        {task.board_column === 'changes_requested' && reviewNote && (
          <p className="flex items-start gap-1 text-orange-400/90" title={reviewNote}>
            <RefreshCw className="mt-px h-2.5 w-2.5 shrink-0" />
            <span className="min-w-0 line-clamp-2">{reviewNote}</span>
          </p>
        )}

        {(tag || task.element_name) && (
          <div className="flex min-w-0 items-center gap-2">
            {tag && (
              <span className={`flex min-w-0 items-center gap-1 font-medium ${tag.colorClass}`}>
                {TagIcon && <TagIcon className="h-2.5 w-2.5 shrink-0" />}
                <span className="truncate">{tag.label}</span>
              </span>
            )}
            {task.element_name && (
              <span className="flex min-w-0 items-center gap-1 text-w-accent">
                <Layers className="h-2.5 w-2.5 shrink-0" />
                <span className="truncate">{task.element_name}</span>
              </span>
            )}
          </div>
        )}

        {/* One meta row that never wraps — like the desktop card, the assignee
            name truncates first. Priority is the left-edge accent, not a chip. */}
        <div className="flex items-center gap-2 overflow-hidden text-w-dim">
          {cycles > 0 && (
            <span
              className="flex shrink-0 items-center gap-0.5 text-orange-400"
              title={`Sent back from review ${cycles} time${cycles === 1 ? '' : 's'}`}
            >
              <RefreshCw className="h-2.5 w-2.5" />×{cycles}
            </span>
          )}

          {pendingCommitSubtasks > 0 && (
            <span
              className="flex shrink-0 items-center gap-0.5 text-emerald-400"
              title={`${pendingCommitSubtasks} checklist item${pendingCommitSubtasks === 1 ? '' : 's'} with pending commit suggestions`}
            >
              <Sparkles className="h-2.5 w-2.5" />
              {pendingCommitSubtasks}
            </span>
          )}

          {assignee && (
            <span className="flex min-w-0 items-center gap-1" title={`Assigned to ${assignee}`}>
              <span className="shrink-0">
                <Avatar name={assignee} avatarUrl={task.assigned_avatar_url} size="xs" />
              </span>
              <span className="truncate">{assignee}</span>
            </span>
          )}

          {subtaskTotal > 0 && (
            <span
              className={`flex shrink-0 items-center gap-0.5 ${subtasksComplete ? 'text-w-accent' : ''}`}
              title={`${subtaskDone} of ${subtaskTotal} checklist items complete`}
            >
              {subtasksComplete ? <CheckCircle2 className="h-2.5 w-2.5" /> : <ListChecks className="h-2.5 w-2.5" />}
              {subtaskDone}/{subtaskTotal}
            </span>
          )}

          {attachmentCount > 0 && (
            <span className="flex shrink-0 items-center gap-0.5" title={`${attachmentCount} attachment${attachmentCount === 1 ? '' : 's'}`}>
              <Paperclip className="h-2.5 w-2.5" />
              {attachmentCount}
            </span>
          )}

          {safePrUrl ? (
            <a
              href={safePrUrl}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              title={task.pr_number ? `PR #${task.pr_number}` : 'Pull request'}
              className="flex shrink-0 items-center gap-0.5 font-medium text-purple-400 hover:underline"
            >
              <GitPullRequest className="h-2.5 w-2.5" />
              {task.pr_number ? `#${task.pr_number}` : 'PR'}
            </a>
          ) : task.pr_number ? (
            <span className="flex shrink-0 items-center gap-0.5 text-purple-400" title={`PR #${task.pr_number}`}>
              <GitPullRequest className="h-2.5 w-2.5" />#{task.pr_number}
            </span>
          ) : null}

          {task.due_date && (
            <span className="flex shrink-0 items-center gap-0.5" title={`Due ${task.due_date.slice(0, 10)}`}>
              <Calendar className="h-2.5 w-2.5" />
              {task.due_date.slice(0, 10)}
            </span>
          )}

          <span className="ml-auto flex shrink-0 items-center gap-1">
            {/* Last move replaces the added date rather than adding a second
                timestamp; full detail lives in the tooltip. */}
            <span
              className={`flex items-center gap-0.5 ${ageColor}`}
              title={`Added ${added}${task.created_by_name ? ` by ${task.created_by_name}` : ''}`}
            >
              {ageState !== 'none' && <Clock className="h-2.5 w-2.5" />}
              {task.last_moved_at ? relative(task.last_moved_at) : ageState !== 'none' ? relative(task.created_at) : shortDate(task.created_at)}
            </span>

            {/* Always visible on touch (where it replaces dragging), hover-only
                on pointer devices so the card stays clean. */}
            {onMenu && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onMenu()
                }}
                title="Task actions"
                aria-label="Task actions"
                className="-my-1 -mr-1 shrink-0 rounded p-1 text-w-dim transition-colors hover:bg-w-surface2 hover:text-w-text md:opacity-0 md:group-hover:opacity-100 md:focus-visible:opacity-100"
              >
                <MoreHorizontal className="h-3.5 w-3.5" />
              </button>
            )}
          </span>
        </div>
      </div>
    </div>
  )
}
