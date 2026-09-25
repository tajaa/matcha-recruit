import { api } from '../../api/client'

export interface BroadcastStatus {
  active: boolean
  max_duration_seconds: number
  weekly_limit: number
  weekly_used: number
  weekly_remaining: number
  broadcast_id?: string
  started_at?: string
  started_by?: string
  title?: string | null
  publisher_user_ids?: string[]
  elapsed_seconds?: number
}

export interface BroadcastToken {
  token: string
  livekit_url: string
  room: string
  max_duration_seconds: number
  elapsed_seconds?: number
  can_publish?: boolean
}

export function getBroadcastStatus(channelId: string) {
  return api.get<BroadcastStatus>(`/channels/${channelId}/broadcast`)
}

export function startBroadcast(channelId: string, title?: string) {
  return api.post<BroadcastToken & { broadcast_id: string; weekly_remaining: number }>(
    `/channels/${channelId}/broadcast/start`, { title: title?.trim() || null },
  )
}

export function stopBroadcast(channelId: string) {
  return api.post<{ ok: boolean }>(`/channels/${channelId}/broadcast/stop`, {})
}

export function getBroadcastToken(channelId: string) {
  return api.get<BroadcastToken>(`/channels/${channelId}/broadcast/token`)
}

export function refreshBroadcastToken(channelId: string) {
  return api.post<BroadcastToken>(`/channels/${channelId}/broadcast/refresh-token`, {})
}

export function setBroadcastPublisher(channelId: string, userId: string, canPublish: boolean) {
  return api.post<{ ok: boolean }>(
    `/channels/${channelId}/broadcast/${canPublish ? 'promote' : 'demote'}`,
    { user_id: userId },
  )
}
