import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  listProjectTasks,
  createProjectTask,
  updateProjectTask,
  deleteProjectTask,
  draftTaskFromPrompt,
  listCollaborators,
} from '../../../api/matchaWork'
import type {
  MWProjectTask,
  BoardColumn,
  MWTaskDraft,
  MWProjectTaskCreate,
  ProjectCollaborator,
} from '../../../types'
import { ProjectSocket } from '../../../api/projectSocket'
import { useMe } from '../../../../hooks/useMe'
import { searchTokens, taskMatches } from '../../../utils/kanbanSearch'
import type { KanbanTemplate } from '../../../utils/kanbanTemplates'
import { mergeTask } from './mergeTask'
import { lastSeenKey } from './constants'

export function useKanbanBoard(projectId: string) {
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

  return {
    tasks,
    setTasks,
    loading,
    error,
    setError,
    draggingId,
    setDraggingId,
    dragOverColumn,
    setDragOverColumn,
    addingColumn,
    setAddingColumn,
    newTitle,
    setNewTitle,
    creating,
    selectedId,
    setSelectedId,
    searchText,
    setSearchText,
    showList,
    setShowList,
    doneExpanded,
    setDoneExpanded,
    hoveredEmptyColumn,
    setHoveredEmptyColumn,
    menuColumn,
    setMenuColumn,
    menuRef,
    templateCompose,
    setTemplateCompose,
    aiDrafting,
    aiError,
    aiDraft,
    setAiDraft,
    collaborators,
    modalBusy,
    changedIds,
    me,
    selectedTask,
    tokens,
    visible,
    canAiDraft,
    ensureCollaborators,
    acknowledge,
    moveTask,
    handleCreate,
    handleDelete,
    patchLocal,
    handleAiDraft,
    handleCreateFromPayload,
  }
}
