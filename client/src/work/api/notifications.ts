import { api } from '../../api/client'

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

// `typePrefix` narrows to one feature's types, e.g. `hr_case_`.
export function getNotifications(unreadOnly = false, limit = 30, typePrefix?: string) {
  const prefix = typePrefix ? `&type_prefix=${encodeURIComponent(typePrefix)}` : ''
  return api.get<{ notifications: MWNotification[]; total: number }>(
    `/matcha-work/notifications?unread_only=${unreadOnly}&limit=${limit}${prefix}`
  )
}

export function getNotificationUnreadCount(typePrefix?: string) {
  const prefix = typePrefix ? `?type_prefix=${encodeURIComponent(typePrefix)}` : ''
  return api.get<{ count: number }>(`/matcha-work/notifications/unread-count${prefix}`)
}

/** Clear everything about one HR case once its owner has opened it. */
export function markHrCaseNotificationsRead(hrCaseId: string) {
  return api.post('/matcha-work/notifications/mark-read-by', { hr_case_id: hrCaseId })
}

export function markNotificationsRead(notificationIds: string[]) {
  return api.post('/matcha-work/notifications/mark-read', { notification_ids: notificationIds })
}

export function markAllNotificationsRead() {
  return api.post('/matcha-work/notifications/mark-all-read')
}
