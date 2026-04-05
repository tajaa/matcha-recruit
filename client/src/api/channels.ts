import { api } from './client'

export interface ChannelSummary {
  id: string
  name: string
  slug: string
  description: string | null
  member_count: number
  unread_count: number
  last_message_at: string | null
  last_message_preview: string | null
  is_member: boolean
}

export interface ChannelMember {
  user_id: string
  name: string
  email: string
  role: string
  avatar_url: string | null
  joined_at: string
}

export interface ChannelMessage {
  id: string
  channel_id: string
  sender_id: string
  sender_name: string
  content: string
  created_at: string
  edited_at: string | null
}

export interface ChannelDetail {
  id: string
  name: string
  slug: string
  description: string | null
  is_archived: boolean
  created_by: string
  created_at: string
  member_count: number
  is_member: boolean
  members: ChannelMember[]
  messages: ChannelMessage[]
}

export const listChannels = () =>
  api.get<ChannelSummary[]>('/channels')

export const createChannel = (name: string, description?: string) =>
  api.post<ChannelDetail>('/channels', { name, description })

export const getChannel = (id: string) =>
  api.get<ChannelDetail>(`/channels/${id}`)

export const getChannelMessages = (id: string, before?: string) =>
  api.get<ChannelMessage[]>(`/channels/${id}/messages${before ? `?before=${before}` : ''}`)

export const joinChannel = (id: string) =>
  api.post(`/channels/${id}/join`)

export const addChannelMembers = (id: string, userIds: string[]) =>
  api.post(`/channels/${id}/members`, { user_ids: userIds })

export const leaveChannel = (id: string) =>
  api.post(`/channels/${id}/leave`)

export const updateChannel = (id: string, updates: { name?: string; description?: string }) =>
  api.patch<ChannelSummary>(`/channels/${id}`, updates)

export const searchInvitableUsers = (q: string, channelId?: string) =>
  api.get<{ id: string; name: string; email: string; role: string; avatar_url: string | null }[]>(
    `/channels/invitable-users?q=${encodeURIComponent(q)}${channelId ? `&channel_id=${channelId}` : ''}`
  )
