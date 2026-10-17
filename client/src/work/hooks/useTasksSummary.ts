import { useEffect, useState } from 'react'
import { getAgentTasksSummary } from '../api/matchaWork/agentTasks'
import { badge } from '../components/tasks/tasksLogic'

const POLL_MS = 60_000
const CHANGED_EVENT = 'espresso-tasks-changed'

/** The Tasks page has just loaded the list (or changed a task): the sidebar's
 *  count catches up now rather than on its next tick. */
export function notifyTasksChanged() {
  window.dispatchEvent(new Event(CHANGED_EVENT))
}

/** The sidebar's Tasks badge, as on the Mac: how many tasks run, and a dot
 *  when one needs the person or has something they haven't seen. `enabled`
 *  gates the fetch entirely (personal accounts with Tasks or Job search). */
export function useTasksSummary(enabled: boolean): { count: number; attention: boolean } {
  const [state, setState] = useState({ count: 0, attention: false })

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    const load = () => {
      if (document.hidden) return
      getAgentTasksSummary().then((summary) => { if (!cancelled) setState(badge(summary)) }).catch(() => {})
    }
    load()
    const id = window.setInterval(load, POLL_MS)
    window.addEventListener(CHANGED_EVENT, load)
    window.addEventListener('focus', load)
    return () => {
      cancelled = true
      window.clearInterval(id)
      window.removeEventListener(CHANGED_EVENT, load)
      window.removeEventListener('focus', load)
    }
  }, [enabled])

  return enabled ? state : { count: 0, attention: false }
}
