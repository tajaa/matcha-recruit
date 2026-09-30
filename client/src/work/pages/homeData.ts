import { useEffect, useState } from 'react'
import { listOpenTasks, listRecentActivity, type MWActivityItem, type MWOpenTask } from '../api/matchaWork/dashboard'
import type { MWThread } from '../types'
import { chatLabel } from '../utils/chatLabel'

// Home's data: what the two working lists show, kept apart from how they look.

export type TaskGroup = { projectId: string; title: string; tasks: MWOpenTask[] }

/** Tasks by workspace, in the order the server ranked them: a workspace
 *  appears where its first task did, and its tasks keep their order. */
export function groupTasks(tasks: MWOpenTask[]): TaskGroup[] {
  const groups = new Map<string, TaskGroup>()
  for (const task of tasks) {
    let group = groups.get(task.project_id)
    if (!group) {
      group = { projectId: task.project_id, title: task.project_title ?? 'Workspace', tasks: [] }
      groups.set(task.project_id, group)
    }
    group.tasks.push(task)
  }
  return [...groups.values()]
}

export type PickUpItem = {
  key: string
  kind: 'chat' | 'workspace' | 'task' | 'journal'
  title: string
  path: string
  at: string
}

/** Recent activity and recent chats as one list, newest first. Chats count
 *  because they're where most work starts, and they keep the list from being
 *  empty on a quiet day. */
export function pickUpItems(activity: MWActivityItem[], threads: MWThread[], base: string, limit = 6): PickUpItem[] {
  const items = new Map<string, PickUpItem>()
  for (const a of activity) {
    const kind = a.kind === 'thread' ? 'chat' : a.kind === 'project' ? 'workspace' : a.kind
    const path = a.kind === 'journal' ? `${base}/journals/${a.ref_id}`
      : a.kind === 'thread' ? `${base}/${a.ref_id}`
        : `${base}/projects/${a.project_id ?? a.ref_id}`
    items.set(`${kind}:${a.ref_id}`, { key: `${kind}:${a.ref_id}`, kind, title: kind === 'chat' ? chatLabel(a.title) : a.title, path, at: a.updated_at })
  }
  for (const t of threads) {
    if (t.status === 'archived') continue
    const key = `chat:${t.id}`
    if (!items.has(key)) items.set(key, { key, kind: 'chat', title: chatLabel(t.title), path: `${base}/${t.id}`, at: t.updated_at ?? t.created_at })
  }
  return [...items.values()].sort((a, b) => (b.at ?? '').localeCompare(a.at ?? '')).slice(0, limit)
}

/** Open tasks + recent activity. A failed half is said once, not per list. */
export function useHomeInsights() {
  const [tasks, setTasks] = useState<MWOpenTask[]>([])
  const [activity, setActivity] = useState<MWActivityItem[]>([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void Promise.allSettled([listOpenTasks(), listRecentActivity()]).then(([taskResult, activityResult]) => {
      if (!active) return
      if (taskResult.status === 'fulfilled') setTasks(taskResult.value)
      if (activityResult.status === 'fulfilled') setActivity(activityResult.value)
      if (taskResult.status === 'rejected' || activityResult.status === 'rejected') {
        setError('Some of this page could not load. Refresh to try again.')
      }
      setLoaded(true)
    })
    return () => { active = false }
  }, [])

  return { tasks, activity, loaded, error }
}
