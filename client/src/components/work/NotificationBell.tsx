import { useEffect, useRef, useState } from 'react'
import { Bell, Check, ExternalLink, FolderOpen, Hash, Mail, UserPlus, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import {
  getNotifications,
  getNotificationUnreadCount,
  markNotificationsRead,
  markAllNotificationsRead,
} from '../../api/notifications'
import type { MWNotification } from '../../api/notifications'

const TYPE_ICONS: Record<string, typeof Bell> = {
  project_invite: UserPlus,
  project_invite_accepted: FolderOpen,
  project_invite_declined: FolderOpen,
  channel_added: Hash,
  channel_message: Hash,
  inbox_message: Mail,
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

export default function NotificationBell() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [notifications, setNotifications] = useState<MWNotification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  // Poll unread count
  useEffect(() => {
    const fetch = () => getNotificationUnreadCount().then((r) => setUnreadCount(r.count)).catch(() => {})
    fetch()
    const id = setInterval(fetch, 15_000)
    return () => clearInterval(id)
  }, [])

  // Load notifications when panel opens
  useEffect(() => {
    if (!open) return
    setLoading(true)
    getNotifications(false, 20)
      .then((r) => setNotifications(r.notifications))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [open])

  // Close on click outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  async function handleMarkAllRead() {
    await markAllNotificationsRead()
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })))
    setUnreadCount(0)
  }

  async function handleClick(notif: MWNotification) {
    if (!notif.is_read) {
      markNotificationsRead([notif.id]).catch(() => {})
      setNotifications((prev) => prev.map((n) => n.id === notif.id ? { ...n, is_read: true } : n))
      setUnreadCount((c) => Math.max(0, c - 1))
    }
    if (notif.link) {
      setOpen(false)
      navigate(notif.link)
    }
  }

  return (
    <div ref={panelRef} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="relative flex items-center text-zinc-400 hover:text-white transition-colors"
      >
        <Bell size={16} />
        {unreadCount > 0 && (
          <span className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-red-500 text-[9px] font-bold text-white flex items-center justify-center">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute top-full right-0 mt-2 z-50 w-80 bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
            <span className="text-xs font-medium text-zinc-200">Notifications</span>
            <div className="flex items-center gap-2">
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllRead}
                  className="text-[10px] text-emerald-400 hover:text-emerald-300"
                >
                  Mark all read
                </button>
              )}
              <button onClick={() => setOpen(false)} className="text-zinc-500 hover:text-zinc-300">
                <X size={14} />
              </button>
            </div>
          </div>

          {/* List */}
          <div className="max-h-96 overflow-y-auto">
            {loading && (
              <div className="px-4 py-6 text-center text-xs text-zinc-500 animate-pulse">Loading...</div>
            )}

            {!loading && notifications.length === 0 && (
              <div className="px-4 py-8 text-center text-xs text-zinc-500">
                No notifications yet
              </div>
            )}

            {!loading && notifications.map((n) => {
              const Icon = TYPE_ICONS[n.type] || Bell
              return (
                <button
                  key={n.id}
                  onClick={() => handleClick(n)}
                  className={`w-full text-left px-4 py-3 hover:bg-zinc-800/50 transition-colors border-b border-zinc-800/50 ${
                    !n.is_read ? 'bg-zinc-800/30' : ''
                  }`}
                >
                  <div className="flex gap-2.5">
                    <div className={`shrink-0 mt-0.5 ${!n.is_read ? 'text-emerald-400' : 'text-zinc-600'}`}>
                      <Icon size={14} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className={`text-xs truncate ${!n.is_read ? 'text-zinc-100 font-medium' : 'text-zinc-400'}`}>
                          {n.title}
                        </p>
                        {!n.is_read && (
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
                        )}
                      </div>
                      {n.body && (
                        <p className="text-[11px] text-zinc-500 truncate mt-0.5">{n.body}</p>
                      )}
                      <p className="text-[10px] text-zinc-600 mt-0.5">{timeAgo(n.created_at)}</p>
                    </div>
                    {n.link && (
                      <ExternalLink size={10} className="shrink-0 text-zinc-600 mt-1" />
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
