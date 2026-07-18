import { useEffect, useState } from 'react'
import { listChannels, listPendingConnections, CHANNELS_CHANGED_EVENT } from '../../../api/channels'
import type { ChannelSummary } from '../../../api/channels'
import { listThreads, listProjects, getMWSubscription } from '../../../api/matchaWork'
import type { MWThread, MWProject } from '../../../types'
import { getUnreadCount } from '../../../api/inbox'

/** Loads + polls the sidebar's server state: channels, projects, threads, inbox
 *  unread, pending connections, and (personal only) Plus subscription status. */
export function useSidebarData(isPersonal: boolean, base: string, pathname: string) {
  const [channels, setChannels] = useState<ChannelSummary[]>([])
  const [projects, setProjects] = useState<MWProject[]>([])
  const [threads, setThreads] = useState<MWThread[]>([])
  const [inboxUnread, setInboxUnread] = useState(0)
  const [pendingConnections, setPendingConnections] = useState(0)
  const [plusActive, setPlusActive] = useState<boolean | null>(null)

  useEffect(() => {
    listChannels().then(setChannels).catch(() => {})
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
  }, [])

  useEffect(() => {
    if (pathname === base) {
      listChannels().then(setChannels).catch(() => {})
    }
  }, [pathname])

  // Refetch channels when anywhere in the app creates/joins/leaves one.
  useEffect(() => {
    const handler = () => {
      listChannels().then(setChannels).catch(() => {})
    }
    window.addEventListener(CHANNELS_CHANGED_EVENT, handler)
    return () => window.removeEventListener(CHANNELS_CHANGED_EVENT, handler)
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
  }
}
