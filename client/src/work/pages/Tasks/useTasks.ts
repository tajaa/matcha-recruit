import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  cancelAgentTask, deleteAgentTask, getAgentTask, getAgentTaskItem, getAgentTaskStatus, listAgentTasks,
  startAgentTaskRound, updateAgentTaskItem, type AgentTaskRoundKind,
} from '../../api/matchaWork/agentTasks'
import type { AgentTask, AgentTaskDetail, AgentTaskItemDetail, AgentTaskList } from '../../types'
import { documentJournalId, errorText, isJobSearch, isLive, pollMs, statusChanged } from '../../components/tasks/tasksLogic'

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
 *
 * Reads are numbered, per kind (the list, the open task, the open finding). An
 * answer is kept only if nothing newer was asked since: neither a later read
 * nor a change the person made. A change takes a number when it starts and
 * again when its answer lands, so a poll that left before "Search more" can't
 * put the old finished task back (and stop the polling), and a finding read
 * that left before a Save can't undo it.
 */
export function useTasks(taskId: string | undefined, itemId: string | null) {
  const [list, setList] = useState<AgentTaskList | null>(null)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [olderError, setOlderError] = useState<string | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [loadedDetail, setDetail] = useState<AgentTaskDetail | null>(null)
  const [detailFailure, setDetailFailure] = useState<Tagged | null>(null)
  const [loadedItem, setItem] = useState<AgentTaskItemDetail | null>(null)
  const [itemLoadFailure, setItemLoadFailure] = useState<Tagged | null>(null)
  const [itemFailure, setItemFailure] = useState<Tagged | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Tagged | null>(null)

  const detail = loadedDetail && loadedDetail.id === taskId ? loadedDetail : null
  const detailError = detailFailure && detailFailure.id === taskId ? detailFailure.message : null
  const item = loadedItem && loadedItem.id === itemId ? loadedItem : null
  const itemLoadError = !item && itemLoadFailure && itemLoadFailure.id === itemId ? itemLoadFailure.message : null
  const itemError = itemFailure && itemFailure.id === itemId ? itemFailure.message : null
  const error = failure && failure.id === taskId ? failure.message : null

  const open = detail ?? list?.tasks.find((task) => task.id === taskId)
  const jobSearchId = open && isJobSearch(open) ? open.job_search_id : null
  const chainDetail = jobSearchId ? null : detail

  const taskRef = useRef(taskId)
  const itemRef = useRef(itemId)
  const detailRef = useRef(chainDetail)
  const shownItemRef = useRef<string | null>(item?.id ?? null)
  const busyRef = useRef(false)
  const listSeq = useRef(0)
  const historySeq = useRef(0)
  const olderBusy = useRef(false)
  const historyLoaded = useRef(false)
  const seen = useRef(new Map<string, string>())
  const bundledItem = useRef<{ task: string; item: string | null } | null>(null)
  const listRef = useRef(list)
  const detailSeq = useRef(0)
  const detailOut = useRef(0)
  const itemSeq = useRef(0)
  // Before any effect below reads them.
  useLayoutEffect(() => {
    listRef.current = list
    taskRef.current = taskId
    itemRef.current = itemId
    detailRef.current = chainDetail
    shownItemRef.current = item?.id ?? null
  })

  const setError = useCallback((message: string | null) => {
    setFailure(message === null ? null : { id: taskRef.current, message })
  }, [])

  const setItemError = useCallback((message: string | null) => {
    setItemFailure(message === null ? null : { id: itemRef.current ?? undefined, message })
  }, [])

  /** A change is starting or has landed: reads already on their way are older
   *  than it, so their answers are dropped. */
  const supersede = useCallback((finding = false) => {
    listSeq.current += 1
    historySeq.current += 1
    detailSeq.current += 1
    if (finding) itemSeq.current += 1
  }, [])

  /** Refresh recent tasks, keeping any older history the person has opened. */
  const loadList = useCallback(() => {
    const seq = ++listSeq.current
    return listAgentTasks().then(
      (loaded) => {
        if (seq !== listSeq.current) return null
        loaded = { ...loaded, tasks: loaded.tasks.map((task) =>
          task.completed_at && seen.current.get(task.id) === task.completed_at ? { ...task, unseen: false } : task) }
        setList((prev) => {
          if (!prev || !historyLoaded.current || !loaded.next_cursor) return loaded
          const last = loaded.tasks.at(-1)
          const older = last ? prev.tasks.filter((t) =>
            !loaded.tasks.some((fresh) => fresh.id === t.id)
            && ((t.created_at ?? '') < (last.created_at ?? '')
              || (t.created_at === last.created_at && t.id < last.id))) : []
          return { ...loaded, tasks: [...loaded.tasks, ...older], next_cursor: prev.next_cursor }
        })
        setListError(null)
        return loaded
      },
      (e: unknown) => {
        if (seq === listSeq.current) setListError(errorText(e, "Couldn't load your tasks."))
        return null
      },
    )
  }, [])

  const loadOlder = useCallback(async () => {
    const cursor = listRef.current?.next_cursor
    if (!cursor || olderBusy.current) return
    olderBusy.current = true
    historyLoaded.current = true
    setLoadingOlder(true)
    setOlderError(null)
    const asked = historySeq.current
    try {
      const loaded = await listAgentTasks(cursor)
      if (asked !== historySeq.current) return
      setList((prev) => prev && prev.next_cursor === cursor ? {
        ...prev, next_cursor: loaded.next_cursor,
        tasks: [...prev.tasks, ...loaded.tasks.filter((t) => !prev.tasks.some((old) => old.id === t.id))],
      } : prev)
    } catch (e) {
      setOlderError(errorText(e, "Couldn't load older tasks."))
    } finally {
      olderBusy.current = false
      setLoadingOlder(false)
    }
  }, [])

  /** A task as the server has it now: on screen if it's still the open one,
   *  and in the list either way (opening it is what marks it seen). */
  const apply = useCallback((loaded: AgentTaskDetail) => {
    if (loaded.completed_at && loaded.unseen === false) seen.current.set(loaded.id, loaded.completed_at)
    if (taskRef.current === loaded.id) {
      setDetail(loaded)
      setDetailFailure(null)
    }
    const row = rowOf(loaded)
    setList((prev) => prev && {
      ...prev,
      tasks: prev.tasks.some((t) => t.id === loaded.id)
        ? prev.tasks.map((t) => (t.id === loaded.id ? row : t))
        : [row, ...prev.tasks],
    })
  }, [])

  const loadDetail = useCallback((id: string, withItem = true) => {
    const seq = ++detailSeq.current
    detailOut.current = seq
    const selected = withItem && taskRef.current === id ? itemRef.current : null
    if (withItem) bundledItem.current = { task: id, item: selected }
    const findingSeq = withItem ? ++itemSeq.current : itemSeq.current
    return getAgentTask(id, selected).then(
      (loaded) => {
        if (seq !== detailSeq.current) return
        apply(loaded)
        if (selected && findingSeq === itemSeq.current && taskRef.current === id && itemRef.current === selected) {
          if (loaded.selected_item) { setItem(loaded.selected_item); setItemLoadFailure(null) }
          if (loaded.selected_item_error) setItemLoadFailure({ id: selected, message: loaded.selected_item_error })
        }
      },
      (e: unknown) => {
        if (seq === detailSeq.current && taskRef.current === id) {
          setDetailFailure({ id, message: errorText(e, "Couldn't load this task.") })
        }
      },
    ).finally(() => { if (detailOut.current === seq) detailOut.current = 0 })
  }, [apply])

  /** The open finding again. A failure is shown in its pane only when there is
   *  nothing of it on screen; a background refresh that misses keeps what's there. */
  const refreshItem = useCallback(async (id: string) => {
    const task = taskRef.current
    if (!task) return
    const seq = ++itemSeq.current
    setItemLoadFailure((f) => (f && f.id === id ? null : f))
    try {
      const loaded = await getAgentTaskItem(task, id)
      if (seq === itemSeq.current && taskRef.current === task && itemRef.current === id) setItem(loaded)
    } catch (e) {
      if (seq === itemSeq.current && itemRef.current === id && shownItemRef.current !== id) {
        setItemLoadFailure({ id, message: errorText(e, "Couldn't load this finding.") })
      }
    }
  }, [])

  useEffect(() => { void loadList() }, [loadList])

  useEffect(() => {
    if (taskId) void loadDetail(taskId)
  }, [taskId, loadDetail])

  // A deep link bundles its finding with the initial workspace read. Later
  // finding selections use the item endpoint; searches own their lead reads.
  useEffect(() => {
    if (!itemId || !taskId || !chainDetail) return
    if (bundledItem.current?.task === taskId && bundledItem.current.item === itemId) return
    void refreshItem(itemId)
  }, [taskId, itemId, chainDetail, refreshItem])

  // The poll: a live task's cheap status, a full reload only on a change; the
  // list on its slower beat. One timer, re-armed for the open task's pace.
  const live = !!chainDetail && isLive(chainDetail)
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
          const asked = detailSeq.current
          const status = await getAgentTaskStatus(id)
          // Something newer than this status landed while it was out: the next tick looks again.
          if (taskRef.current === id && detailSeq.current === asked && statusChanged(current, status)) {
            await loadDetail(id)
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

  const syncSearchStatus = useCallback(async (status: string) => {
    if (busyRef.current || detailOut.current) return
    const mapped = ['done', 'failed', 'cancelled', 'queued'].includes(status) ? status : 'running'
    const current = listRef.current?.tasks.find((t) => t.id === taskRef.current)
    if (taskRef.current && (!current || current.status !== mapped || current.unseen)) {
      await loadDetail(taskRef.current)
    }
  }, [loadDetail])

  /** One change at a time. A change made from a finding's pane reports there
   *  (`finding`), since below the widest layout the pane covers the task. */
  const perform = useCallback(async (fallback: string, action: () => Promise<void>, finding?: string) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setError(null)
    setItemFailure(null)
    try {
      await action()
    } catch (e) {
      const message = errorText(e, fallback)
      if (finding) setItemFailure({ id: finding, message })
      else setError(message)
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

  /** Change the open task: drop older reads, then keep what the change returned. */
  const change = useCallback(async (request: () => Promise<AgentTaskDetail>) => {
    supersede()
    const updated = await request()
    supersede()
    apply(updated)
    return updated
  }, [supersede, apply])

  /** Change a finding: drop older reads of it, then show what the save returned. */
  const changeItem = useCallback(async (request: () => Promise<AgentTaskItemDetail>) => {
    supersede(true)
    const updated = await request()
    supersede(true)
    show(updated)
  }, [supersede, show])

  /** Saved / Chosen / Dismissed (or back to New) for the finding acted on. */
  const setItemState = useCallback((state: string, id: string) => {
    const task = taskRef.current
    if (!task) return Promise.resolve()
    return perform("Couldn't save that.", async () => {
      await changeItem(() => updateAgentTaskItem(task, id, { user_state: state }))
      await loadDetail(task, false)
    }, id)
  }, [perform, changeItem, loadDetail])

  const saveNotes = useCallback((notes: string, id: string) => {
    const task = taskRef.current
    if (!task) return Promise.resolve()
    return perform("Couldn't save your notes.", async () => {
      await changeItem(() => updateAgentTaskItem(task, id, { notes }))
    }, id)
  }, [perform, changeItem])

  /** A refine, "search more" or a document. Resolves to the document's journal
   *  id when one was written, so the page can offer to open it. Each click is
   *  its own request, like the Mac. `fromItem` is the finding whose pane asked
   *  ("More like this"), so a failure shows there. */
  const startRound = useCallback(async (
    kind: AgentTaskRoundKind, directive = '', itemIds: string[] = [], fromItem?: string,
  ) => {
    const task = taskRef.current
    let journal: string | null = null
    if (!task) return journal
    await perform(kind === 'document' ? "Couldn't make the document." : "Couldn't start that.", async () => {
      const updated = await change(() => startAgentTaskRound(task, {
        request_id: crypto.randomUUID(), kind, directive, item_ids: itemIds,
      }))
      if (kind === 'document') journal = documentJournalId(updated)
      void loadList()
    }, fromItem)
    return journal
  }, [perform, change, loadList])

  const cancel = useCallback(() => {
    const task = taskRef.current
    if (!task) return Promise.resolve()
    return perform("Couldn't cancel this task.", async () => { await change(() => cancelAgentTask(task)) })
  }, [perform, change])

  /** Delete a task. Resolves true once it's gone, so the page leaves it only
   *  then (a failure stays on screen). */
  const remove = useCallback(async (id: string): Promise<boolean> => {
    let deleted = false
    await perform("Couldn't delete this task.", async () => {
      supersede()
      await deleteAgentTask(id)
      deleted = true
      supersede() // a list read already out still has it
      setList((prev) => prev && { ...prev, tasks: prev.tasks.filter((t) => t.id !== id) })
      void loadList()
    })
    return deleted
  }, [perform, supersede, loadList])

  return {
    list, listError, loadList, loadingOlder, olderError, loadOlder,
    open, jobSearchId, chainDetail, syncSearchStatus,
    detail, detailError, loadDetail,
    item, itemLoadError, itemError, setItemError,
    reloadItem: () => (itemRef.current ? refreshItem(itemRef.current) : Promise.resolve()),
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
  delete row.selected_item
  delete row.selected_item_id
  delete row.selected_item_error
  return row
}

/** Something kept for one task, so another task doesn't show it. */
type Tagged = { id: string | undefined; message: string }
