import { api } from './client'

export interface MWNotification {
  id: string
  type: string
  title: string
  body: string | null
  link: string | null
  metadata: Record<string, unknown> | null
  is_read: boolean
  created_at: string
}

export function getNotifications(unreadOnly = false, limit = 30) {
  return api.get<{ notifications: MWNotification[] }>(
    `/matcha-work/notifications?unread_only=${unreadOnly}&limit=${limit}`
  )
}

export function getNotificationUnreadCount() {
  return api.get<{ count: number }>('/matcha-work/notifications/unread-count')
}

export function markNotificationsRead(notificationIds: string[]) {
  return api.post('/matcha-work/notifications/mark-read', { notification_ids: notificationIds })
}

export function markAllNotificationsRead() {
  return api.post('/matcha-work/notifications/mark-all-read')
}
