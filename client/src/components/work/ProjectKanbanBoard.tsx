import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  Loader2,
  Plus,
  X,
  Trash2,
  ListChecks,
  Undo2,
  CheckCircle2,
  Search,
  LayoutGrid,
  List,
} from 'lucide-react'
import {
  listProjectTasks,
  createProjectTask,
  updateProjectTask,
  deleteProjectTask,
  rejectProjectTask,
  approveProjectTask,
  listSubtasks,
  createSubtask,
  updateSubtask,
  deleteSubtask,
  draftTaskFromPrompt,
  listCollaborators,
} from '../../api/matchaWork'
import type {
  MWProjectTask,
  MWSubtask,
  BoardColumn,
  TaskPriority,
  MWTaskDraft,
  MWProjectTaskCreate,
  ProjectCollaborator,
} from '../../types/matcha-work'
import { ProjectSocket } from '../../api/projectSocket'
import { useMe } from '../../hooks/useMe'
import KanbanCard from './KanbanCard'
import TaskProgressBar from './TaskProgressBar'
import AiDraftBar from './AiDraftBar'
import AiDraftReviewModal from './AiDraftReviewModal'
import TemplateComposeModal from './TemplateComposeModal'
import KanbanListView from './KanbanListView'
import { KANBAN_COLUMNS } from '../../utils/kanbanColumns'
import { searchTokens, taskMatches } from '../../utils/kanbanSearch'
import { KANBAN_TEMPLATES, type KanbanTemplate } from '../../utils/kanbanTemplates'

interface ProjectKanbanBoardProps {
  projectId: string
}

const PRIORITIES: TaskPriority[] = ['critical', 'high', 'medium', 'low']

function lastSeenKey(userId: string, projectId: string): string {
  return `kanban-lastseen-${userId}-${projectId}`
}

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

  // Search / view mode / done-lane collapse.
  const [searchText, setSearchText] = useState('')
  const [showList, setShowList] = useState(() => localStorage.getItem('mw-kanban-list-layout') === '1')
  const [doneExpanded, setDoneExpanded] = useState(false)

  // Dynamic (empty-collapsing) columns + the "+" template menu.
  const [hoveredEmptyColumn, setHoveredEmptyColumn] = useState<BoardColumn | null>(null)
  const [menuColumn, setMenuColumn] = useState<BoardColumn | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  // AI draft + template compose modals (share the same lazily-fetched
  // collaborator list for the assignee picker).
  const [templateCompose, setTemplateCompose] = useState<{ template: KanbanTemplate; column: BoardColumn } | null>(null)
  const [aiDrafting, setAiDrafting] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)
  const [aiDraft, setAiDraft] = useState<MWTaskDraft | null>(null)
  const [collaborators, setCollaborators] = useState<ProjectCollaborator[]>([])
  const collabLoadedRef = useRef(false)
  const [modalBusy, setModalBusy] = useState(false)

  // Gold "changed since you last looked" ring, keyed off a per-user localStorage
  // baseline (mirrors the desktop's per-user UserDefaults last-seen snapshot).
  const [changedIds, setChangedIds] = useState<Set<string>>(new Set())
  const didBaselineRef = useRef(false)

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

  // ── Realtime: another collaborator's create/move/delete shows up live ──
  // Mirrors useProjectPresence.ts's subscribe-on-mount pattern. Refs (not plain
  // closure vars) for the current user id and the latest tasks — the socket
  // callbacks are bound once at connect time and would otherwise read whatever
  // `me`/`tasks` were on first render.
  const { me } = useMe()
  const meIdRef = useRef<string | null>(null)
  useEffect(() => {
    meIdRef.current = me?.user.id ?? null
  }, [me])
  const tasksRef = useRef<MWProjectTask[]>([])
  useEffect(() => {
    tasksRef.current = tasks
  }, [tasks])

  useEffect(() => {
    const socket = new ProjectSocket()
    socket.onTaskCreated = (raw) => {
      const actorId = (raw as { actor_id?: string | null }).actor_id ?? null
      if (actorId && actorId === meIdRef.current) return
      const task = raw as unknown as MWProjectTask
      setTasks((prev) => (prev.some((t) => t.id === task.id) ? prev : [...prev, task]))
      setChangedIds((prev) => {
        const next = new Set(prev)
        next.add(task.id)
        return next
      })
    }
    socket.onTaskUpdated = (raw) => {
      const task = raw as unknown as MWProjectTask
      const actorId = (raw as { actor_id?: string | null }).actor_id ?? null
      const isSelf = !!actorId && actorId === meIdRef.current
      const local = tasksRef.current.find((t) => t.id === task.id)
      const columnChanged = !!local && task.board_column !== local.board_column
      setTasks((prev) => prev.map((t) => (t.id === task.id ? mergeTask(t, task) : t)))
      if (!isSelf && columnChanged) {
        setChangedIds((prev) => {
          const next = new Set(prev)
          next.add(task.id)
          return next
        })
      }
    }
    socket.onTaskDeleted = (taskId) => {
      setTasks((prev) => prev.filter((t) => t.id !== taskId))
      setSelectedId((id) => (id === taskId ? null : id))
      setChangedIds((prev) => {
        if (!prev.has(taskId)) return prev
        const next = new Set(prev)
        next.delete(taskId)
        return next
      })
    }
    socket.connect()
    socket.joinProject(projectId, 'board')
    return () => socket.disconnect()
  }, [projectId])

  // ── Gold ring — baseline once per mount, then diff against it ──
  useEffect(() => {
    if (didBaselineRef.current) return
    if (loading || tasks.length === 0 || !me?.user.id) return
    didBaselineRef.current = true
    const key = lastSeenKey(me.user.id, projectId)
    let map: Record<string, string> = {}
    try {
      const raw = localStorage.getItem(key)
      map = raw ? JSON.parse(raw) : {}
    } catch {
      map = {}
    }
    if (Object.keys(map).length === 0) {
      // First-ever open on this device — baseline silently, no rings.
      const fresh: Record<string, string> = {}
      tasks.forEach((t) => {
        fresh[t.id] = t.board_column
      })
      try {
        localStorage.setItem(key, JSON.stringify(fresh))
      } catch {
        /* best-effort */
      }
      return
    }
    const changed = tasks.filter((t) => map[t.id] === undefined || map[t.id] !== t.board_column).map((t) => t.id)
    if (changed.length) setChangedIds(new Set(changed))
  }, [loading, tasks, me, projectId])

  function writeLastSeen(taskId: string, column: BoardColumn) {
    if (!me?.user.id) return
    try {
      const key = lastSeenKey(me.user.id, projectId)
      const raw = localStorage.getItem(key)
      const map = raw ? JSON.parse(raw) : {}
      map[taskId] = column
      localStorage.setItem(key, JSON.stringify(map))
    } catch {
      /* best-effort */
    }
  }

  function clearRing(taskId: string) {
    setChangedIds((prev) => {
      if (!prev.has(taskId)) return prev
      const next = new Set(prev)
      next.delete(taskId)
      return next
    })
  }

  /** Opening a card acknowledges it — clears its ring and advances its
   *  baseline entry to the current column. */
  function acknowledge(taskId: string) {
    clearRing(taskId)
    const task = tasks.find((t) => t.id === taskId)
    if (task) writeLastSeen(taskId, task.board_column)
  }

  /** A move/edit *I* made should never leave a ring on my own screen. */
  function noteSelfMove(taskId: string, column: BoardColumn) {
    clearRing(taskId)
    writeLastSeen(taskId, column)
  }

  const selectedTask = selectedId ? tasks.find((t) => t.id === selectedId) ?? null : null

  // ── Search filter ──
  const tokens = useMemo(() => searchTokens(searchText), [searchText])
  const visible = useMemo(
    () => (tokens.length ? tasks.filter((t) => taskMatches(t, tokens)) : tasks),
    [tasks, tokens],
  )

  const role = me?.user?.role
  const canAiDraft = role === 'admin' || role === 'client' || role === 'individual'

  function ensureCollaborators() {
    if (collabLoadedRef.current) return
    collabLoadedRef.current = true
    listCollaborators(projectId)
      .then(setCollaborators)
      .catch(() => {})
  }

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
      patchLocal(taskId, updated)
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

  // Patch a single task in place (used by the detail panel for field edits,
  // and by moveTask above). Notes a self-move when the column actually
  // changed, so the gold ring never lands on a change I made myself.
  function patchLocal(taskId: string, updated: MWProjectTask) {
    const local = tasks.find((t) => t.id === taskId)
    if (local && updated.board_column && updated.board_column !== local.board_column) {
      noteSelfMove(taskId, updated.board_column)
    }
    setTasks((prev) => prev.map((t) => (t.id === taskId ? mergeTask(t, updated) : t)))
  }

  // ── AI draft + template compose ──
  async function handleAiDraft(prompt: string) {
    setAiDrafting(true)
    setAiError(null)
    try {
      const draft = await draftTaskFromPrompt(projectId, prompt)
      ensureCollaborators()
      setAiDraft(draft)
    } catch (e) {
      const msg = e instanceof Error ? e.message : ''
      setAiError(
        /429|limit/i.test(msg)
          ? 'Daily AI limit reached (50 per 24 hours). Create tickets manually or try again later.'
          : "Couldn't draft that — try rephrasing.",
      )
    } finally {
      setAiDrafting(false)
    }
  }

  async function handleCreateFromPayload(payload: MWProjectTaskCreate) {
    setModalBusy(true)
    try {
      const created = await createProjectTask(projectId, payload)
      setTasks((prev) => [...prev, created])
      setAiDraft(null)
      setTemplateCompose(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create task')
    } finally {
      setModalBusy(false)
    }
  }

  // Close the "+" template menu on outside click / Escape.
  useEffect(() => {
    if (!menuColumn) return
    function onDocClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuColumn(null)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setMenuColumn(null)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuColumn])

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-w-dim" />
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

      {tasks.length > 0 && (
        <div className="flex items-center gap-2 px-3 pt-3">
          <Search className="h-3.5 w-3.5 shrink-0 text-w-dim" />
          <input
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Search tasks…"
            title='space = AND, "quotes" = exact phrase'
            className="min-w-0 flex-1 bg-transparent text-[13px] text-w-text placeholder-w-faint outline-none"
          />
          {searchText && (
            <button onClick={() => setSearchText('')} className="shrink-0 text-w-dim hover:text-w-text">
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}

      {tasks.length > 0 && <TaskProgressBar tasks={tasks} />}

      <div className="flex items-center gap-1 px-3 pb-2">
        <button
          onClick={() => {
            setShowList(false)
            localStorage.setItem('mw-kanban-list-layout', '0')
          }}
          className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium transition-colors ${
            !showList ? 'bg-w-accent/15 text-w-accent' : 'text-w-dim hover:text-w-text'
          }`}
        >
          <LayoutGrid className="h-3 w-3" />
          Board
        </button>
        <button
          onClick={() => {
            setShowList(true)
            localStorage.setItem('mw-kanban-list-layout', '1')
          }}
          className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium transition-colors ${
            showList ? 'bg-w-accent/15 text-w-accent' : 'text-w-dim hover:text-w-text'
          }`}
        >
          <List className="h-3 w-3" />
          List
        </button>
      </div>

      {canAiDraft && <AiDraftBar drafting={aiDrafting} error={aiError} onDraft={handleAiDraft} />}

      {showList ? (
        <KanbanListView
          tasks={visible}
          searchTokens={tokens}
          myUserId={me?.user.id ?? null}
          changedIds={changedIds}
          onOpen={(t) => {
            acknowledge(t.id)
            setSelectedId(t.id)
          }}
        />
      ) : (
        <div className="flex flex-1 gap-2 overflow-x-auto p-2.5 max-md:snap-x max-md:snap-mandatory">
          {KANBAN_COLUMNS.map((col) => {
            let colTasks = visible.filter((t) => t.board_column === col.key)
            if (col.key === 'done') {
              colTasks = [...colTasks].sort((a, b) => (b.completed_at ?? '').localeCompare(a.completed_at ?? ''))
            }
            const totalInColumn = colTasks.length
            const shownTasks = col.key === 'done' && !doneExpanded && totalInColumn > 5 ? colTasks.slice(0, 5) : colTasks
            const isEmpty = totalInColumn === 0
            const isDropTarget = dragOverColumn === col.key
            const collapsed =
              isEmpty && addingColumn !== col.key && hoveredEmptyColumn !== col.key && !isDropTarget

            return (
              <div
                key={col.key}
                onMouseEnter={() => {
                  if (isEmpty) setHoveredEmptyColumn(col.key)
                }}
                onMouseLeave={() => setHoveredEmptyColumn((c) => (c === col.key ? null : c))}
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
                className={`flex shrink-0 flex-col rounded-lg border bg-w-surface transition-[width] duration-150 ease-out max-md:w-[85vw] max-md:snap-center ${
                  collapsed ? 'w-[136px]' : 'w-[240px]'
                } ${isDropTarget ? 'border-w-accent/60 bg-w-accent/10' : 'border-w-line'}`}
              >
                {/* Column header */}
                <div className="relative flex items-center justify-between gap-1.5 px-2.5 py-2">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <span className="min-w-0 truncate whitespace-nowrap text-[10px] font-semibold uppercase tracking-wider text-w-dim" title={col.label}>
                      {col.label}
                    </span>
                    <span className="shrink-0 rounded bg-w-surface2 px-1.5 py-0.5 text-[10px] text-w-dim">
                      {totalInColumn}
                    </span>
                  </div>
                  <button
                    onClick={() => setMenuColumn((c) => (c === col.key ? null : col.key))}
                    className="shrink-0 text-w-dim transition-colors hover:text-w-text"
                    title="Add card"
                  >
                    <Plus className="h-4 w-4" />
                  </button>

                  {menuColumn === col.key && (
                    <div
                      ref={menuRef}
                      className="absolute right-0 top-full z-20 mt-1 w-44 rounded-lg border border-w-line bg-w-surface py-1 shadow-xl"
                    >
                      <button
                        onClick={() => {
                          setAddingColumn(col.key)
                          setNewTitle('')
                          setMenuColumn(null)
                        }}
                        className="block w-full px-3 py-1.5 text-left text-xs text-w-text hover:bg-w-surface2"
                      >
                        Blank task
                      </button>
                      <div className="my-1 border-t border-w-line" />
                      {KANBAN_TEMPLATES.map((t) => {
                        const TIcon = t.icon
                        return (
                          <button
                            key={t.key}
                            onClick={() => {
                              ensureCollaborators()
                              setTemplateCompose({ template: t, column: col.key })
                              setMenuColumn(null)
                            }}
                            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-w-text hover:bg-w-surface2"
                          >
                            <TIcon className={`h-3.5 w-3.5 shrink-0 ${t.colorClass}`} />
                            {t.displayName}
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>

                {/* Cards — collapsed empty columns show header only */}
                {!collapsed && (
                  <div className="flex flex-1 flex-col gap-2 px-2 pb-2 min-h-0 max-md:overflow-y-auto">
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

                    {shownTasks.map((task) => (
                      <KanbanCard
                        key={task.id}
                        task={task}
                        ringed={changedIds.has(task.id)}
                        dragging={draggingId === task.id}
                        onClick={() => {
                          acknowledge(task.id)
                          setSelectedId(task.id)
                        }}
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

                    {col.key === 'done' && totalInColumn > 5 && (
                      <button
                        onClick={() => setDoneExpanded((v) => !v)}
                        className="w-full rounded bg-w-surface2/60 py-1 text-[10px] font-medium text-w-dim transition-colors hover:text-w-text"
                      >
                        {doneExpanded ? 'Show less' : `Show ${totalInColumn - 5} more`}
                      </button>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

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

      {aiDraft && (
        <AiDraftReviewModal
          draft={aiDraft}
          collaborators={collaborators}
          busy={modalBusy}
          onCreate={handleCreateFromPayload}
          onClose={() => setAiDraft(null)}
        />
      )}

      {templateCompose && (
        <TemplateComposeModal
          template={templateCompose.template}
          column={templateCompose.column}
          collaborators={collaborators}
          busy={modalBusy}
          onCreate={handleCreateFromPayload}
          onClose={() => setTemplateCompose(null)}
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
    <div className="rounded-lg border border-w-line bg-w-surface p-2">
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
        className="w-full resize-none bg-transparent text-sm text-w-text placeholder-w-faint outline-none"
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          onClick={onSubmit}
          disabled={busy || !value.trim()}
          className="flex items-center gap-1 rounded bg-w-accent px-2.5 py-1 text-xs font-medium text-white transition-colors hover:bg-w-accent-hi disabled:opacity-50"
        >
          {busy && <Loader2 className="h-3 w-3 animate-spin" />}
          Add
        </button>
        <button
          onClick={onCancel}
          className="rounded px-2 py-1 text-xs text-w-dim transition-colors hover:text-w-text"
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
