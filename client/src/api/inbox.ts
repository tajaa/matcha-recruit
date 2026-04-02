import { api } from './client'

// ── Types ──

export interface Message {
  id: string
  conversation_id: string
  sender_id: string
  sender_name: string
  content: string
  created_at: string
  edited_at: string | null
}

export interface Participant {
  user_id: string
  name: string
  email: string
  role: string
  avatar_url?: string | null
  last_read_at: string | null
  is_muted: boolean
}

export interface ConversationSummary {
  id: string
  title: string | null
  is_group: boolean
  last_message_at: string | null
  last_message_preview: string | null
  participants: Participant[]
  unread_count: number
}

export interface Conversation extends ConversationSummary {
  created_by: string
  messages: Message[]
  created_at: string
}

export interface UserSearchResult {
  id: string
  email: string
  name: string
  role: string
  avatar_url?: string | null
  company_name: string | null
}

// ── API calls ──

export function listConversations(limit = 50, offset = 0) {
  const params = new URLSearchParams()
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return api.get<ConversationSummary[]>(`/inbox/conversations?${params}`)
}

export function getConversation(id: string, limit = 50) {
  const params = new URLSearchParams()
  params.set('limit', String(limit))
  return api.get<Conversation>(`/inbox/conversations/${id}?${params}`)
}

export function createConversation(participantIds: string[], message: string, title?: string) {
  return api.post<Conversation>('/inbox/conversations', {
    participant_ids: participantIds,
    message,
    ...(title ? { title } : {}),
  })
}

export function sendMessage(conversationId: string, content: string) {
  return api.post<Message>(`/inbox/conversations/${conversationId}/messages`, { content })
}

export function markRead(conversationId: string) {
  return api.post<{ success: boolean }>(`/inbox/conversations/${conversationId}/read`)
}

export function toggleMute(conversationId: string) {
  return api.post<{ is_muted: boolean }>(`/inbox/conversations/${conversationId}/mute`)
}

export function getUnreadCount() {
  return api.get<{ count: number }>('/inbox/unread-count')
}

export function searchUsers(query: string) {
  return api.get<UserSearchResult[]>(`/inbox/search-users?q=${encodeURIComponent(query)}`)
}
