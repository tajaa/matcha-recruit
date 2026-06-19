import { useState, useEffect, useCallback, useRef } from 'react'
import { Loader2, Plus, X, Trash2, ListChecks } from 'lucide-react'
import {
  listProjectTasks,
  createProjectTask,
  updateProjectTask,
  deleteProjectTask,
  listSubtasks,
  createSubtask,
  updateSubtask,
  deleteSubtask,
} from '../../api/matchaWork'
import type {
  MWProjectTask,
  MWSubtask,
  BoardColumn,
  TaskPriority,
} from '../../types/matcha-work'
import KanbanCard from './KanbanCard'

interface ProjectKanbanBoardProps {
  projectId: string
}

// Board lane order — matches the desktop `kanbanColumns` (todo → in_progress →
// review → changes_requested → done).
const COLUMNS: { key: BoardColumn; label: string }[] = [
  { key: 'todo', label: 'Todo' },
  { key: 'in_progress', label: 'In Progress' },
  { key: 'review', label: 'Review' },
  { key: 'changes_requested', label: 'Changes Requested' },
  { key: 'done', label: 'Done' },
]

const PRIORITIES: TaskPriority[] = ['critical', 'high', 'medium', 'low']

export default function ProjectKanbanBoard({ projectId }: ProjectKanbanBoardProps) {
  const [tasks, setTasks] = useState<MWProjectTask[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Native drag-and-drop state.
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [dragOverColumn, setDragOverColumn] = useState<BoardColumn | null>(null)

  // Per-column inline "add card".
  const [addingColumn, setAddingColumn] = useState<BoardColumn | null>(null)
  const [newTitle, setNewTitle] = useState('')
  const [creating, setCreating] = useState(false)

  // Card detail side panel.
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listProjectTasks(projectId)
      setTasks(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load board')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

  const selectedTask = selectedId ? tasks.find((t) => t.id === selectedId) ?? null : null

  // ── Drag to move ──
  // Optimistic: move the card locally, PATCH only { board_column }, revert on
  // error. Sending a single key sidesteps the 400 the column validator throws
  // when board_column arrives null inside a wider null-filled patch.
  async function moveTask(taskId: string, toColumn: BoardColumn) {
    const task = tasks.find((t) => t.id === taskId)
    if (!task || task.board_column === toColumn) return

    const prevColumn = task.board_column
    const prevStatus = task.status
    setTasks((prev) =>
      prev.map((t) =>
        t.id === taskId
          ? {
              ...t,
              board_column: toColumn,
              // Keep the local checkbox/strikethrough honest with the lane.
              status: toColumn === 'done' ? 'completed' : t.status === 'completed' ? 'pending' : t.status,
            }
          : t,
      ),
    )
    try {
      const updated = await updateProjectTask(projectId, taskId, { board_column: toColumn })
      // Merge the server row, but preserve list-only aggregates the PATCH
      // RETURNING clause doesn't carry (subtask counts, attachments, etc.).
      setTasks((prev) => prev.map((t) => (t.id === taskId ? mergeTask(t, updated) : t)))
    } catch (e) {
      // Revert BOTH the column and the optimistic status flip — reverting only
      // the column leaves the card in its lane with the wrong status.
      setTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, board_column: prevColumn, status: prevStatus } : t)))
      setError(e instanceof Error ? e.message : 'Failed to move task')
    }
  }

  async function handleCreate(column: BoardColumn) {
    const title = newTitle.trim()
    if (!title || creating) return
    setCreating(true)
    try {
      const created = await createProjectTask(projectId, { title, board_column: column })
      setTasks((prev) => [...prev, created])
      setNewTitle('')
      setAddingColumn(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create task')
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(taskId: string) {
    const prev = tasks
    setTasks((p) => p.filter((t) => t.id !== taskId))
    if (selectedId === taskId) setSelectedId(null)
    try {
      await deleteProjectTask(projectId, taskId)
    } catch (e) {
      setTasks(prev)
      setError(e instanceof Error ? e.message : 'Failed to delete task')
    }
  }

  // Patch a single task in place (used by the detail panel for field edits).
  function patchLocal(taskId: string, updated: MWProjectTask) {
    setTasks((prev) => prev.map((t) => (t.id === taskId ? mergeTask(t, updated) : t)))
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {error && (
        <div className="mx-4 mt-3 flex items-center justify-between rounded-lg border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-300">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-200">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <div className="flex flex-1 gap-3 overflow-x-auto p-4">
        {COLUMNS.map((col) => {
          const colTasks = tasks.filter((t) => t.board_column === col.key)
          const isDropTarget = dragOverColumn === col.key
          return (
            <div
              key={col.key}
              onDragOver={(e) => {
                e.preventDefault()
                if (dragOverColumn !== col.key) setDragOverColumn(col.key)
              }}
              onDragLeave={(e) => {
                // Only clear when the pointer actually leaves the column subtree.
                if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                  setDragOverColumn((c) => (c === col.key ? null : c))
                }
              }}
              onDrop={(e) => {
                e.preventDefault()
                setDragOverColumn(null)
                if (draggingId) moveTask(draggingId, col.key)
              }}
              className={`flex w-72 shrink-0 flex-col rounded-xl border bg-zinc-900/40 transition-colors ${
                isDropTarget ? 'border-emerald-600/60 bg-emerald-950/10' : 'border-zinc-800'
              }`}
            >
              {/* Column header */}
              <div className="flex items-center justify-between px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wide text-zinc-400">
                    {col.label}
                  </span>
                  <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">
                    {colTasks.length}
                  </span>
                </div>
                <button
                  onClick={() => {
                    setAddingColumn(col.key)
                    setNewTitle('')
                  }}
                  className="text-zinc-500 transition-colors hover:text-zinc-300"
                  title="Add card"
                >
                  <Plus className="h-4 w-4" />
                </button>
              </div>

              {/* Cards */}
              <div className="flex flex-1 flex-col gap-2 px-2 pb-2">
                {addingColumn === col.key && (
                  <AddCardInput
                    value={newTitle}
                    onChange={setNewTitle}
                    onSubmit={() => handleCreate(col.key)}
                    onCancel={() => {
                      setAddingColumn(null)
                      setNewTitle('')
                    }}
                    busy={creating}
                  />
                )}

                {colTasks.map((task) => (
                  <KanbanCard
                    key={task.id}
                    task={task}
                    dragging={draggingId === task.id}
                    onClick={() => setSelectedId(task.id)}
                    onDragStart={(e) => {
                      setDraggingId(task.id)
                      e.dataTransfer.effectAllowed = 'move'
                      // Some browsers require data to be set for a drag to start.
                      e.dataTransfer.setData('text/plain', task.id)
                    }}
                    onDragEnd={() => {
                      setDraggingId(null)
                      setDragOverColumn(null)
                    }}
                  />
                ))}

                {colTasks.length === 0 && addingColumn !== col.key && (
                  <div className="rounded-lg border border-dashed border-zinc-800 py-6 text-center text-xs text-zinc-600">
                    No cards
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {selectedTask && (
        <TaskDetailPanel
          projectId={projectId}
          task={selectedTask}
          onClose={() => setSelectedId(null)}
          onPatched={(updated) => patchLocal(selectedTask.id, updated)}
          onDelete={() => handleDelete(selectedTask.id)}
          onSubtaskCountChange={(total, done) =>
            setTasks((prev) =>
              prev.map((t) =>
                t.id === selectedTask.id ? { ...t, subtask_total: total, subtask_done: done } : t,
              ),
            )
          }
        />
      )}
    </div>
  )
}

// Preserve the list-only aggregate fields a PATCH/create RETURNING clause omits
// (they'd otherwise be clobbered to undefined when merging the server row).
function mergeTask(local: MWProjectTask, server: MWProjectTask): MWProjectTask {
  return {
    ...server,
    subtask_total: server.subtask_total ?? local.subtask_total,
    subtask_done: server.subtask_done ?? local.subtask_done,
    review_cycle_count: server.review_cycle_count ?? local.review_cycle_count,
    last_moved_at: server.last_moved_at ?? local.last_moved_at,
    assigned_name: server.assigned_name ?? local.assigned_name,
    assigned_email: server.assigned_email ?? local.assigned_email,
    element_name: server.element_name ?? local.element_name,
    attachments: server.attachments ?? local.attachments,
  }
}

// ── Inline add-card input ──

interface AddCardInputProps {
  value: string
  onChange: (v: string) => void
  onSubmit: () => void
  onCancel: () => void
  busy: boolean
}

function AddCardInput({ value, onChange, onSubmit, onCancel, busy }: AddCardInputProps) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    ref.current?.focus()
  }, [])
  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-2">
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            onSubmit()
          } else if (e.key === 'Escape') {
            onCancel()
          }
        }}
        rows={2}
        placeholder="Card title…"
        className="w-full resize-none bg-transparent text-sm text-zinc-100 placeholder-zinc-600 outline-none"
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          onClick={onSubmit}
          disabled={busy || !value.trim()}
          className="flex items-center gap-1 rounded bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-50"
        >
          {busy && <Loader2 className="h-3 w-3 animate-spin" />}
          Add
        </button>
        <button
          onClick={onCancel}
          className="rounded px-2 py-1 text-xs text-zinc-400 transition-colors hover:text-zinc-200"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ── Card detail side panel ──

interface TaskDetailPanelProps {
  projectId: string
  task: MWProjectTask
  onClose: () => void
  onPatched: (updated: MWProjectTask) => void
  onDelete: () => void
  onSubtaskCountChange: (total: number, done: number) => void
}

function TaskDetailPanel({
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
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-zinc-800 bg-zinc-950 shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b border-zinc-800 px-5 py-4">
          <h2 className="text-base font-semibold leading-snug text-zinc-100">{task.title}</h2>
          <button onClick={onClose} className="shrink-0 text-zinc-500 hover:text-zinc-300">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          {/* Lane + priority */}
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-zinc-500">Column</span>
              <select
                value={task.board_column}
                disabled={savingField}
                onChange={(e) => patchField({ board_column: e.target.value as BoardColumn })}
                className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-1.5 text-sm text-zinc-200 outline-none focus:border-zinc-700"
              >
                {COLUMNS.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-zinc-500">Priority</span>
              <select
                value={task.priority}
                disabled={savingField}
                onChange={(e) => patchField({ priority: e.target.value as TaskPriority })}
                className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-1.5 text-sm capitalize text-zinc-200 outline-none focus:border-zinc-700"
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p} className="capitalize">
                    {p}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {/* Assignee (read-only — no people-picker on the lite surface yet) */}
          {(task.assigned_name || task.assigned_email) && (
            <div>
              <span className="mb-1 block text-xs font-medium text-zinc-500">Assignee</span>
              <p className="text-sm text-zinc-300">{task.assigned_name ?? task.assigned_email}</p>
            </div>
          )}

          {/* Description */}
          <div>
            <span className="mb-1 block text-xs font-medium text-zinc-500">Description</span>
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
              className="w-full resize-y rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-zinc-700"
            />
          </div>

          {/* Subtasks */}
          <div>
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-zinc-500">
              <ListChecks className="h-3.5 w-3.5" />
              Checklist
              {subtasks.length > 0 && (
                <span className="text-zinc-600">
                  ({subtasks.filter((s) => s.is_done).length}/{subtasks.length})
                </span>
              )}
            </div>

            {subtasksLoading ? (
              <Loader2 className="h-4 w-4 animate-spin text-zinc-600" />
            ) : (
              <div className="space-y-1.5">
                {subtasks.map((sub) => (
                  <div key={sub.id} className="group flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={sub.is_done}
                      onChange={() => toggleSubtask(sub)}
                      className="h-4 w-4 shrink-0 rounded border-zinc-700 bg-zinc-900 text-emerald-500 focus:ring-0 focus:ring-offset-0"
                    />
                    <span
                      className={`flex-1 text-sm ${
                        sub.is_done ? 'text-zinc-600 line-through' : 'text-zinc-300'
                      }`}
                    >
                      {sub.title}
                    </span>
                    <button
                      onClick={() => removeSubtask(sub)}
                      className="shrink-0 text-zinc-700 opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100"
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
                    className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-zinc-700"
                  />
                  <button
                    onClick={addSubtask}
                    disabled={!newSubtask.trim()}
                    className="shrink-0 rounded-lg bg-zinc-800 px-2 py-1.5 text-zinc-300 transition-colors hover:bg-zinc-700 disabled:opacity-40"
                  >
                    <Plus className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer actions */}
        <div className="border-t border-zinc-800 px-5 py-3">
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
