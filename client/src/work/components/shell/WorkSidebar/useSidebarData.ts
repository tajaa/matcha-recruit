import { useEffect, useState } from 'react'
import { listChannels, listPendingConnections, CHANNELS_CHANGED_EVENT } from '../../../api/channels'
import type { ChannelSummary } from '../../../api/channels'
import { listThreads, listProjects, getMWSubscription, THREADS_CHANGED_EVENT } from '../../../api/matchaWork'
import type { MWThread, MWProject } from '../../../types'
import { getUnreadCount } from '../../../api/inbox'
import { useLoggedEventsCount } from '../../../hooks/useLoggedEventsCount'

/** Loads + polls the sidebar's server state: channels, projects, threads, inbox
 *  unread, pending connections, logged-events count, and (personal only) Plus
 *  subscription status. `emsEnabled` gates the events fetch — false for any
 *  caller without both the `ems` flag and events-review permission, so a
 *  regular employee never fires a request the backend would just 403. */
export function useSidebarData(isPersonal: boolean, base: string, pathname: string, emsEnabled = false) {
  const [channels, setChannels] = useState<ChannelSummary[]>([])
  const [projects, setProjects] = useState<MWProject[]>([])
  const [threads, setThreads] = useState<MWThread[]>([])
  const [inboxUnread, setInboxUnread] = useState(0)
  const [pendingConnections, setPendingConnections] = useState(0)
  const [plusActive, setPlusActive] = useState<boolean | null>(null)
  const loggedEventsCount = useLoggedEventsCount(emsEnabled)
  const showChannels = base !== '/work'

  useEffect(() => {
    if (showChannels) listChannels().then(setChannels).catch(() => {})
    listProjects().then(setProjects).catch(() => {})
    listThreads('active').then(setThreads).catch(() => {})
    getUnreadCount().then((r) => setInboxUnread(r.count)).catch(() => {})
    listPendingConnections().then((p) => setPendingConnections(p.length)).catch(() => {})
    if (isPersonal) {
      getMWSubscription()
        .then((s) => setPlusActive(
          !!s.active && s.pack_id === 'matcha_work_personal'
        ))
        .catch(() => setPlusActive(false))
    }
  }, [showChannels])

  useEffect(() => {
    if (showChannels && pathname === base) {
      listChannels().then(setChannels).catch(() => {})
    }
  }, [pathname, showChannels])

  // Refetch channels when anywhere in the app creates/joins/leaves one.
  useEffect(() => {
    if (!showChannels) return
    const handler = () => {
      listChannels().then(setChannels).catch(() => {})
    }
    window.addEventListener(CHANNELS_CHANGED_EVENT, handler)
    return () => window.removeEventListener(CHANNELS_CHANGED_EVENT, handler)
  }, [showChannels])

  // Refetch threads when a title changes (auto-title landing, manual rename)
  // or any other thread-list-affecting change fires.
  useEffect(() => {
    const handler = () => {
      listThreads('active').then(setThreads).catch(() => {})
    }
    window.addEventListener(THREADS_CHANGED_EVENT, handler)
    return () => window.removeEventListener(THREADS_CHANGED_EVENT, handler)
  }, [])

  // Poll inbox unread
  useEffect(() => {
    const id = setInterval(() => {
      getUnreadCount().then((r) => setInboxUnread(r.count)).catch(() => {})
    }, 60_000)
    return () => clearInterval(id)
  }, [])

  return {
    channels,
    setChannels,
    projects,
    setProjects,
    threads,
    setThreads,
    inboxUnread,
    pendingConnections,
    plusActive,
    loggedEventsCount,
  }
}
