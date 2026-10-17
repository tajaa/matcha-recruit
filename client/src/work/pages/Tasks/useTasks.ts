import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  cancelAgentTask, deleteAgentTask, getAgentTask, getAgentTaskItem, getAgentTaskStatus, listAgentTasks,
  startAgentTaskRound, updateAgentTaskItem, type AgentTaskRoundKind,
} from '../../api/matchaWork/agentTasks'
import type { AgentTask, AgentTaskDetail, AgentTaskItemDetail, AgentTaskList } from '../../types'
import { documentJournalId, errorText, isLive, pollMs, statusChanged } from '../../components/tasks/tasksLogic'

/** The list refreshes on this slower beat, for tasks other than the open one. */
const LIST_MS = 30_000

/**
 * The Tasks page's state: the person's tasks and allowance, the open task's
 * findings, and the open finding. Like the macOS app, a live task polls its
 * cheap status every few seconds and reloads only when its fingerprint or
 * status changes; the list refreshes every 30 seconds. The URL owns which task
 * and finding are open; an answer is dropped if the person has moved on by the
 * time it arrives, and what is kept per task or per finding is tagged with its
 * id, so another one starts clean.
 */
export function useTasks(taskId: string | undefined, itemId: string | null) {
  const [list, setList] = useState<AgentTaskList | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [loadedDetail, setDetail] = useState<AgentTaskDetail | null>(null)
  const [detailFailure, setDetailFailure] = useState<Tagged | null>(null)
  const [loadedItem, setItem] = useState<AgentTaskItemDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Tagged | null>(null)

  const detail = loadedDetail && loadedDetail.id === taskId ? loadedDetail : null
  const detailError = detailFailure && detailFailure.id === taskId ? detailFailure.message : null
  const item = loadedItem && loadedItem.id === itemId ? loadedItem : null
  const error = failure && failure.id === taskId ? failure.message : null

  const taskRef = useRef(taskId)
  const itemRef = useRef(itemId)
  const detailRef = useRef(detail)
  const busyRef = useRef(false)
  // Before any effect below reads them.
  useLayoutEffect(() => {
    taskRef.current = taskId
    itemRef.current = itemId
    detailRef.current = detail
  })

  const setError = useCallback((message: string | null) => {
    setFailure(message === null ? null : { id: taskRef.current, message })
  }, [])

  /** The list again. The open task stays seen while it is on screen. */
  const loadList = useCallback(() => listAgentTasks().then(
    (loaded) => {
      setList({ ...loaded, tasks: loaded.tasks.map((t) => (t.id === taskRef.current ? { ...t, unseen: false } : t)) })
      setListError(null)
    },
    (e: unknown) => { setListError(errorText(e, "Couldn't load your tasks.")) },
  ), [])

  /** A task as the server has it now: on screen if it's still the open one,
   *  and in the list either way (opening it is what marks it seen). */
  const apply = useCallback((loaded: AgentTaskDetail) => {
    if (taskRef.current === loaded.id) {
      setDetail(loaded)
      setDetailFailure(null)
    }
    const seen = { ...rowOf(loaded), unseen: false }
    setList((prev) => prev && {
      ...prev,
      tasks: prev.tasks.some((t) => t.id === loaded.id)
        ? prev.tasks.map((t) => (t.id === loaded.id ? seen : t))
        : [seen, ...prev.tasks],
    })
  }, [])

  const loadDetail = useCallback((id: string) => getAgentTask(id).then(
    apply,
    (e: unknown) => {
      if (taskRef.current === id) setDetailFailure({ id, message: errorText(e, "Couldn't load this task.") })
    },
  ), [apply])

  const refreshItem = useCallback(async (id: string) => {
    const task = taskRef.current
    if (!task) return
    try {
      const loaded = await getAgentTaskItem(task, id)
      if (taskRef.current === task && itemRef.current === id) setItem(loaded)
    } catch (e) {
      if (itemRef.current === id) setError(errorText(e, "Couldn't load this finding."))
    }
  }, [setError])

  useEffect(() => { void loadList() }, [loadList])

  useEffect(() => {
    if (taskId) void loadDetail(taskId)
  }, [taskId, loadDetail])

  useEffect(() => {
    if (itemId && taskId) void refreshItem(itemId)
  }, [taskId, itemId, refreshItem])

  // The poll: a live task's cheap status, a full reload only on a change; the
  // list on its slower beat. One timer, re-armed for the open task's pace.
  const live = !!detail && isLive(detail)
  useEffect(() => {
    let polling = false
    let sinceList = 0
    const every = pollMs(live)
    const timer = window.setInterval(async () => {
      if (polling || document.hidden) return
      polling = true
      try {
        const current = detailRef.current
        const id = taskRef.current
        if (id && current && current.id === id && isLive(current)) {
          const status = await getAgentTaskStatus(id)
          if (taskRef.current === id && statusChanged(current, status)) {
            await loadDetail(id)
            if (itemRef.current) await refreshItem(itemRef.current)
            if (!isLive(status)) await loadList()
          }
        }
        sinceList += every
        if (sinceList >= LIST_MS) {
          sinceList = 0
          await loadList()
        }
      } catch {
        // A missed poll is retried on the next tick.
      } finally {
        polling = false
      }
    }, every)
    return () => window.clearInterval(timer)
  }, [live, loadDetail, refreshItem, loadList])

  const perform = useCallback(async (fallback: string, action: () => Promise<void>) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (e) {
      setError(errorText(e, fallback))
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }, [setError])

  /** A save's answer replaces the open finding only if it is still open:
   *  clicking another while it saved must not put the old one back. */
  const show = useCallback((updated: AgentTaskItemDetail) => {
    if (itemRef.current === updated.id) setItem(updated)
  }, [])

  /** Saved / Chosen / Dismissed (or back to New) for the finding acted on. */
  const setItemState = useCallback((state: string, id: string) => {
    const task = taskRef.current
    if (!task) return Promise.resolve()
    return perform("Couldn't save that.", async () => {
      show(await updateAgentTaskItem(task, id, { user_state: state }))
      await loadDetail(task)
    })
  }, [perform, show, loadDetail])

  const saveNotes = useCallback((notes: string, id: string) => {
    const task = taskRef.current
    if (!task) return Promise.resolve()
    return perform("Couldn't save your notes.", async () => {
      show(await updateAgentTaskItem(task, id, { notes }))
    })
  }, [perform, show])

  /** A refine, "search more" or a document. Resolves to the document's journal
   *  id when one was written, so the page can offer to open it. Each click is
   *  its own request, like the Mac. */
  const startRound = useCallback(async (kind: AgentTaskRoundKind, directive = '', itemIds: string[] = []) => {
    const task = taskRef.current
    let journal: string | null = null
    if (!task) return journal
    await perform(kind === 'document' ? "Couldn't make the document." : "Couldn't start that.", async () => {
      const updated = await startAgentTaskRound(task, {
        request_id: crypto.randomUUID(), kind, directive, item_ids: itemIds,
      })
      apply(updated)
      if (kind === 'document') journal = documentJournalId(updated)
      void loadList()
    })
    return journal
  }, [perform, apply, loadList])

  const cancel = useCallback(() => {
    const task = taskRef.current
    if (!task) return Promise.resolve()
    return perform("Couldn't cancel this task.", async () => { apply(await cancelAgentTask(task)) })
  }, [perform, apply])

  /** Delete a task. Resolves true once it's gone, so the page leaves it only
   *  then (a failure stays on screen). */
  const remove = useCallback(async (id: string): Promise<boolean> => {
    let deleted = false
    await perform("Couldn't delete this task.", async () => {
      await deleteAgentTask(id)
      deleted = true
      setList((prev) => prev && { ...prev, tasks: prev.tasks.filter((t) => t.id !== id) })
      void loadList()
    })
    return deleted
  }, [perform, loadList])

  return {
    list, listError, loadList,
    detail, detailError, loadDetail,
    item, reloadItem: () => (itemRef.current ? refreshItem(itemRef.current) : Promise.resolve()),
    busy, error, setError,
    setItemState, saveNotes, startRound, cancel, remove,
  }
}

/** A task's row in the list: its detail without the plan, rounds and findings. */
function rowOf(detail: AgentTaskDetail): AgentTask {
  const row: Partial<AgentTaskDetail> & AgentTask = { ...detail }
  delete row.fingerprint
  delete row.plan
  delete row.rounds
  delete row.items
  return row
}

/** Something kept for one task, so another task doesn't show it. */
type Tagged = { id: string | undefined; message: string }
