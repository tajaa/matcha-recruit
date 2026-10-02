import { useCallback, useEffect, useRef, useState } from 'react'
import { getSharedChannelSocket } from '../api/channelSocket'
import { getNotificationUnreadCount, getNotifications, markNotificationsRead } from '../api/notifications'
import type { MWNotification } from '../api/notifications'
import { UPDATE_PREFIX } from '../components/panels/hr-cases/hrCaseGuide'

const POLL_MS = 30_000

/** The signed-in user's HR-case notices: the list, the unread count, and a
 *  callback when a new one lands. The bell keeps its own copy; this is the
 *  page-local one, so the board can refresh the moment something changes. */
const fetchUpdates = () =>
  Promise.all([getNotifications(false, 25, UPDATE_PREFIX), getNotificationUnreadCount(UPDATE_PREFIX)])

export function useHrCaseUpdates(onFresh?: (n: MWNotification) => void) {
  const [items, setItems] = useState<MWNotification[]>([])
  const [unread, setUnread] = useState(0)
  const seen = useRef<Set<string>>(new Set())
  const onFreshRef = useRef(onFresh)
  useEffect(() => { onFreshRef.current = onFresh })

  // Best effort: the bell and the board still work without the feed.
  const reload = useCallback(() => fetchUpdates().then(([list, count]) => {
    seen.current = new Set(list.notifications.map((n) => n.id))
    setItems(list.notifications)
    setUnread(count.count)
  }, () => {}), [])

  useEffect(() => {
    void reload()
    const id = setInterval(() => { if (!document.hidden) void reload() }, POLL_MS)
    return () => clearInterval(id)
  }, [reload])

  useEffect(() => {
    const socket = getSharedChannelSocket()
    const listener = (n: MWNotification) => {
      if (!n.type.startsWith(UPDATE_PREFIX) || seen.current.has(n.id)) return
      seen.current.add(n.id)
      setItems((prev) => [n, ...prev.filter((p) => p.id !== n.id)].slice(0, 25))
      if (!n.is_read) setUnread((c) => c + 1)
      onFreshRef.current?.(n)
    }
    socket.addNotificationListener(listener)
    return () => socket.removeNotificationListener(listener)
  }, [])

  const markRead = useCallback((id: string) => {
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)))
    setUnread((c) => Math.max(0, c - 1))
    markNotificationsRead([id]).catch(() => {})
  }, [])

  // Only the HR-case notices listed here: the bell's "Mark all read" is the
  // one that clears the whole account.
  const markAllRead = useCallback(() => {
    const ids = items.filter((n) => !n.is_read).map((n) => n.id)
    if (!ids.length) return
    setItems((prev) => prev.map((n) => ({ ...n, is_read: true })))
    setUnread(0)
    markNotificationsRead(ids).then(() => reload(), () => reload())
  }, [items, reload])

  return { items, unread, reload, markRead, markAllRead }
}
