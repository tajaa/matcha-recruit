import { useEffect, useState } from 'react'
import { listChannels, listPendingConnections, CHANNELS_CHANGED_EVENT } from '../../../api/channels'
import type { ChannelSummary } from '../../../api/channels'
import { listThreads, listProjects, THREADS_CHANGED_EVENT } from '../../../api/matchaWork'
import type { MWThread, MWProject } from '../../../types'
import { getUnreadCount } from '../../../api/inbox'
import { useLoggedEventsCount } from '../../../hooks/useLoggedEventsCount'
import { listJournals, JOURNALS_CHANGED_EVENT, type Journal } from '../../../api/matchaWork/journals'
import { publishSearchSource } from '../../../utils/searchIndex'

/** Loads + polls the sidebar's server state: channels, projects, threads, inbox
 *  unread, pending connections, and logged-events count.
 *  `emsEnabled` gates the events fetch — false for any
 *  caller without both the `ems` flag and events-review permission, so a
 *  regular employee never fires a request the backend would just 403. */
export function useSidebarData(
  base: string,
  pathname: string,
  emsEnabled: boolean,
  showChannels: boolean,
  userId?: string,
) {
  const [channels, setChannels] = useState<ChannelSummary[]>([])
  const [projects, setProjects] = useState<MWProject[]>([])
  const [threads, setThreads] = useState<MWThread[]>([])
  const [journals, setJournals] = useState<Journal[]>([])
  const [inboxUnread, setInboxUnread] = useState(0)
  const [pendingConnections, setPendingConnections] = useState(0)
  const loggedEventsCount = useLoggedEventsCount(emsEnabled)
  useEffect(() => {
    const channelRequest = showChannels ? listChannels().then(setChannels).catch(() => {}) : Promise.resolve()
    const projectRequest = listProjects().then(setProjects).catch(() => {})
    const threadRequest = listThreads('active').then(setThreads).catch(() => {})
    const journalRequest = listJournals().then(setJournals).catch(() => {})
    void Promise.allSettled([channelRequest, projectRequest, threadRequest, journalRequest]).then(() => publishSearchSource(userId, 'catalog-ready', [], true))
    getUnreadCount().then((r) => setInboxUnread(r.count)).catch(() => {})
    listPendingConnections().then((p) => setPendingConnections(p.length)).catch(() => {})
  }, [showChannels, userId])

  useEffect(() => { publishSearchSource(userId, 'channels', channels.map((item) => ({ kind: 'channel', id: item.id, title: item.name, updatedAt: item.last_message_at ?? undefined }))) }, [userId, channels])
  useEffect(() => { publishSearchSource(userId, 'projects', projects.map((item) => ({ kind: 'project', id: item.id, title: item.title, updatedAt: item.updated_at }))) }, [userId, projects])
  useEffect(() => { publishSearchSource(userId, 'threads', threads.map((item) => ({ kind: 'thread', id: item.id, title: item.title, updatedAt: item.updated_at }))) }, [userId, threads])
  useEffect(() => { publishSearchSource(userId, 'journals', journals.map((item) => ({ kind: 'journal', id: item.id, title: item.title, updatedAt: item.updated_at }))) }, [userId, journals])

  useEffect(() => {
    const onChanged = () => { void listJournals().then(setJournals).catch(() => {}) }
    window.addEventListener(JOURNALS_CHANGED_EVENT, onChanged)
    return () => window.removeEventListener(JOURNALS_CHANGED_EVENT, onChanged)
  }, [])

  useEffect(() => {
    if (showChannels && pathname === base) {
      listChannels().then(setChannels).catch(() => {})
    }
  }, [pathname, showChannels, base])

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
    journals,
    inboxUnread,
    pendingConnections,
    loggedEventsCount,
  }
}
