import { api } from './client'

export interface ChannelSummary {
  id: string
  name: string
  slug: string
  description: string | null
  visibility: string
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
  channel_role: string // owner, moderator, member
  avatar_url: string | null
  joined_at: string
}

export interface ChannelAttachment {
  url: string
  filename: string
  content_type: string
  size: number
}

export interface ChannelMessage {
  id: string
  channel_id: string
  sender_id: string
  sender_name: string
  content: string
  attachments?: ChannelAttachment[]
  created_at: string
  edited_at: string | null
}

export interface ChannelDetail {
  id: string
  name: string
  slug: string
  description: string | null
  visibility: string
  is_archived: boolean
  created_by: string
  created_at: string
  member_count: number
  is_member: boolean
  my_role: string | null // owner, moderator, member
  members: ChannelMember[]
  messages: ChannelMessage[]
}

export const listChannels = () =>
  api.get<ChannelSummary[]>('/channels')

export const createChannel = (name: string, description?: string, visibility: string = 'public') =>
  api.post<ChannelDetail>('/channels', { name, description, visibility })

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

export async function uploadChannelFiles(channelId: string, files: File[]): Promise<ChannelAttachment[]> {
  const BASE = import.meta.env.VITE_API_URL ?? '/api'
  const token = localStorage.getItem('matcha_access_token')
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  const res = await fetch(`${BASE}/channels/${channelId}/upload`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })
  if (!res.ok) throw new Error('Upload failed')
  const data = await res.json()
  return data.attachments
}

export const kickMember = (channelId: string, userId: string) =>
  api.delete(`/channels/${channelId}/members/${userId}`)

export const setMemberRole = (channelId: string, userId: string, role: 'moderator' | 'member') =>
  api.patch(`/channels/${channelId}/members/${userId}`, { role })

export const transferOwnership = (channelId: string, userId: string) =>
  api.post(`/channels/${channelId}/transfer-ownership`, { user_id: userId })

export const searchInvitableUsers = (q: string, channelId?: string) =>
  api.get<{ id: string; name: string; email: string; role: string; avatar_url: string | null }[]>(
    `/channels/invitable-users?q=${encodeURIComponent(q)}${channelId ? `&channel_id=${channelId}` : ''}`
  )
