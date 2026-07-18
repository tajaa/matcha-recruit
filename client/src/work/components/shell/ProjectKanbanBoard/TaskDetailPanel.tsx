import { useState, useEffect } from 'react'
import { Loader2, X, Trash2, ListChecks, Undo2, CheckCircle2, Plus } from 'lucide-react'
import {
  updateProjectTask,
  rejectProjectTask,
  approveProjectTask,
  listSubtasks,
  createSubtask,
  updateSubtask,
  deleteSubtask,
} from '../../../api/matchaWork'
import type { MWProjectTask, MWSubtask, BoardColumn, TaskPriority } from '../../../types'
import { KANBAN_COLUMNS } from '../../../utils/kanbanColumns'
import { PRIORITIES } from './constants'

interface TaskDetailPanelProps {
  projectId: string
  task: MWProjectTask
  onClose: () => void
  onPatched: (updated: MWProjectTask) => void
  onDelete: () => void
  onSubtaskCountChange: (total: number, done: number) => void
}

export default function TaskDetailPanel({
  projectId,
  task,
  onClose,
  onPatched,
  onDelete,
  onSubtaskCountChange,
}: TaskDetailPanelProps) {
  const [subtasks, setSubtasks] = useState<MWSubtask[]>([])
  const [subtasksLoading, setSubtasksLoading] = useState(true)
  const [newSubtask, setNewSubtask] = useState('')
  const [savingField, setSavingField] = useState(false)

  // Review send-back / approve — only surfaced while the card sits in Review.
  const [showRejectNote, setShowRejectNote] = useState(false)
  const [rejectNote, setRejectNote] = useState('')
  const [reviewBusy, setReviewBusy] = useState(false)

  async function handleApprove() {
    setReviewBusy(true)
    try {
      const updated = await approveProjectTask(projectId, task.id)
      onPatched(updated)
    } catch {
      /* surfaced via the board's own error path */
    } finally {
      setReviewBusy(false)
    }
  }

  async function handleReject() {
    const note = rejectNote.trim()
    if (!note || reviewBusy) return
    setReviewBusy(true)
    try {
      const updated = await rejectProjectTask(projectId, task.id, note)
      onPatched(updated)
      setShowRejectNote(false)
      setRejectNote('')
    } catch {
      /* surfaced via the board's own error path */
    } finally {
      setReviewBusy(false)
    }
  }

  // Local editable copies of the inline fields.
  const [description, setDescription] = useState(task.description ?? '')

  useEffect(() => {
    setDescription(task.description ?? '')
  }, [task.id, task.description])

  useEffect(() => {
    let active = true
    setSubtasksLoading(true)
    listSubtasks(projectId, task.id)
      .then((rows) => {
        if (active) setSubtasks(rows)
      })
      .catch(() => {})
      .finally(() => {
        if (active) setSubtasksLoading(false)
      })
    return () => {
      active = false
    }
  }, [projectId, task.id])

  function reportCounts(rows: MWSubtask[]) {
    onSubtaskCountChange(rows.length, rows.filter((s) => s.is_done).length)
  }

  async function patchField(patch: Partial<{ priority: TaskPriority; description: string | null; board_column: BoardColumn }>) {
    setSavingField(true)
    try {
      const updated = await updateProjectTask(projectId, task.id, patch)
      onPatched(updated)
    } catch {
      /* surfaced on the board via its own error path on reload; keep panel quiet */
    } finally {
      setSavingField(false)
    }
  }

  async function addSubtask() {
    const title = newSubtask.trim()
    if (!title) return
    try {
      const created = await createSubtask(projectId, task.id, title)
      const next = [...subtasks, created]
      setSubtasks(next)
      reportCounts(next)
      setNewSubtask('')
    } catch {
      /* ignore — input retains the text for retry */
    }
  }

  async function toggleSubtask(sub: MWSubtask) {
    const next = subtasks.map((s) => (s.id === sub.id ? { ...s, is_done: !s.is_done } : s))
    setSubtasks(next)
    reportCounts(next)
    try {
      await updateSubtask(projectId, task.id, sub.id, { is_done: !sub.is_done })
    } catch {
      // Revert on failure.
      const reverted = subtasks.map((s) => (s.id === sub.id ? { ...s, is_done: sub.is_done } : s))
      setSubtasks(reverted)
      reportCounts(reverted)
    }
  }

  async function removeSubtask(sub: MWSubtask) {
    const next = subtasks.filter((s) => s.id !== sub.id)
    setSubtasks(next)
    reportCounts(next)
    try {
      await deleteSubtask(projectId, task.id, sub.id)
    } catch {
      setSubtasks(subtasks)
      reportCounts(subtasks)
    }
  }

  return (
    <>
      {/* Scrim */}
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />
      {/* Panel */}
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-w-line bg-w-bg shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b border-w-line px-5 py-4">
          <h2 className="text-base font-semibold leading-snug text-w-text">{task.title}</h2>
          <button onClick={onClose} className="shrink-0 text-w-dim hover:text-w-text">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          {/* Lane + priority */}
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-w-dim">Column</span>
              <select
                value={task.board_column}
                disabled={savingField}
                onChange={(e) => patchField({ board_column: e.target.value as BoardColumn })}
                className="w-full rounded-lg border border-w-line bg-w-surface px-2.5 py-1.5 text-sm text-w-text outline-none focus:border-w-line"
              >
                {KANBAN_COLUMNS.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-w-dim">Priority</span>
              <select
                value={task.priority}
                disabled={savingField}
                onChange={(e) => patchField({ priority: e.target.value as TaskPriority })}
                className="w-full rounded-lg border border-w-line bg-w-surface px-2.5 py-1.5 text-sm capitalize text-w-text outline-none focus:border-w-line"
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p} className="capitalize">
                    {p}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {/* Review send-back / approve — only while sitting in Review */}
          {task.board_column === 'review' && (
            <div className="rounded-lg border border-w-line bg-w-surface/60 p-3">
              {!showRejectNote ? (
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleApprove}
                    disabled={reviewBusy}
                    className="flex items-center gap-1.5 rounded-lg bg-w-accent px-2.5 py-1.5 text-xs font-medium text-white transition-colors hover:bg-w-accent-hi disabled:opacity-50"
                  >
                    {reviewBusy ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <CheckCircle2 className="h-3.5 w-3.5" />
                    )}
                    Approve
                  </button>
                  <button
                    onClick={() => setShowRejectNote(true)}
                    disabled={reviewBusy}
                    className="flex items-center gap-1.5 rounded-lg border border-w-line px-2.5 py-1.5 text-xs font-medium text-w-text transition-colors hover:bg-w-surface2 disabled:opacity-50"
                  >
                    <Undo2 className="h-3.5 w-3.5" />
                    Send back
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  <textarea
                    value={rejectNote}
                    onChange={(e) => setRejectNote(e.target.value)}
                    autoFocus
                    rows={2}
                    placeholder="What needs to change?"
                    className="w-full resize-none rounded-lg border border-w-line bg-w-surface px-2.5 py-1.5 text-sm text-w-text placeholder-w-faint outline-none focus:border-w-line"
                  />
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleReject}
                      disabled={reviewBusy || !rejectNote.trim()}
                      className="flex items-center gap-1.5 rounded-lg bg-orange-600 px-2.5 py-1.5 text-xs font-medium text-white transition-colors hover:bg-orange-500 disabled:opacity-50"
                    >
                      {reviewBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                      Send back
                    </button>
                    <button
                      onClick={() => {
                        setShowRejectNote(false)
                        setRejectNote('')
                      }}
                      className="rounded-lg px-2.5 py-1.5 text-xs text-w-dim transition-colors hover:text-w-text"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Assignee (read-only — no people-picker on the lite surface yet) */}
          {(task.assigned_name || task.assigned_email) && (
            <div>
              <span className="mb-1 block text-xs font-medium text-w-dim">Assignee</span>
              <p className="text-sm text-w-text">{task.assigned_name ?? task.assigned_email}</p>
            </div>
          )}

          {/* Description */}
          <div>
            <span className="mb-1 block text-xs font-medium text-w-dim">Description</span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              onBlur={() => {
                if ((description ?? '') !== (task.description ?? '')) {
                  patchField({ description: description.trim() ? description : null })
                }
              }}
              rows={4}
              placeholder="Add a description…"
              className="w-full resize-y rounded-lg border border-w-line bg-w-surface px-3 py-2 text-sm text-w-text placeholder-w-faint outline-none focus:border-w-line"
            />
          </div>

          {/* Subtasks */}
          <div>
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-w-dim">
              <ListChecks className="h-3.5 w-3.5" />
              Checklist
              {subtasks.length > 0 && (
                <span className="text-w-faint">
                  ({subtasks.filter((s) => s.is_done).length}/{subtasks.length})
                </span>
              )}
            </div>

            {subtasksLoading ? (
              <Loader2 className="h-4 w-4 animate-spin text-w-faint" />
            ) : (
              <div className="space-y-1.5">
                {subtasks.map((sub) => (
                  <div key={sub.id} className="group flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={sub.is_done}
                      onChange={() => toggleSubtask(sub)}
                      className="h-4 w-4 shrink-0 rounded border-w-line bg-w-surface text-w-accent focus:ring-0 focus:ring-offset-0"
                    />
                    <span
                      className={`flex-1 text-sm ${
                        sub.is_done ? 'text-w-faint line-through' : 'text-w-text'
                      }`}
                    >
                      {sub.title}
                    </span>
                    <button
                      onClick={() => removeSubtask(sub)}
                      className="shrink-0 text-w-faint opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}

                <div className="flex items-center gap-2 pt-1">
                  <input
                    value={newSubtask}
                    onChange={(e) => setNewSubtask(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addSubtask()
                      }
                    }}
                    placeholder="Add an item…"
                    className="flex-1 rounded-lg border border-w-line bg-w-surface px-2.5 py-1.5 text-sm text-w-text placeholder-w-faint outline-none focus:border-w-line"
                  />
                  <button
                    onClick={addSubtask}
                    disabled={!newSubtask.trim()}
                    className="shrink-0 rounded-lg bg-w-surface2 px-2 py-1.5 text-w-text transition-colors hover:bg-w-surface2 disabled:opacity-40"
                  >
                    <Plus className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer actions */}
        <div className="border-t border-w-line px-5 py-3">
          <button
            onClick={onDelete}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-red-400 transition-colors hover:bg-red-950/40"
          >
            <Trash2 className="h-4 w-4" />
            Delete card
          </button>
        </div>
      </aside>
    </>
  )
}
