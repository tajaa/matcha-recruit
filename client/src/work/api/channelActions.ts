import { api } from '../../api/client'

export type ChannelActionKind = 'event_draft' | 'event' | 'event_assignment' | 'project_task' | 'schedule_proposal' | 'inventory_order'

export interface ChannelAction {
  id: string
  kind: ChannelActionKind
  title: string
  summary: string
  status: string
  source_message_id: string | null
  allowed_actions: string[]
  href: string | null
  created_at: string
}

export function listChannelActions(channelId: string, status = 'open') {
  return api.get<{ actions: ChannelAction[]; total: number }>(
    `/channels/${channelId}/actions?status=${encodeURIComponent(status)}`,
  )
}
