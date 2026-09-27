import { api } from '../../../api/client'

// Sym-chat — intent-shaped micro group chats (business /work only).
// Backend: server/app/matcha/routes/matcha_work/sym_chat.py.

export type SymChatKind = 'schedule' | 'decide'
export type SymChatStatus = 'open' | 'resolved' | 'cancelled'

export type ScheduleConfig = {
  date: string
  window_start: string
  window_end: string
  duration_min: number
  step_min?: number
  timezone: string
}

export type DecideConfig = { options: string[] }

export type ScheduleSlot = { start: string; end: string; count: number; preferred: number }

export type ScheduleShape = {
  kind: 'schedule'
  date: string
  timezone: string
  duration_min: number
  total: number
  responded: number
  best: ScheduleSlot | null
  top_slots: ScheduleSlot[]
  consensus: boolean
}

export type DecideOption = { name: string; ok: number; top: number; vetoes: number }

export type DecideShape = {
  kind: 'decide'
  total: number
  responded: number
  options: DecideOption[]
  leading: DecideOption | null
  consensus: boolean
}

export type SymChatShape = ScheduleShape | DecideShape

export type SymChatResolution =
  | { kind: 'schedule'; date: string; start: string; end: string; timezone: string }
  | { kind: 'decide'; choice: string }

export type SymChatSummary = {
  id: string
  kind: SymChatKind
  title: string
  status: SymChatStatus
  summary: string | null
  resolution: SymChatResolution | null
  is_organizer: boolean
  participant_count: number
  responded_count: number
  i_responded: boolean
  created_at: string | null
  updated_at: string | null
}

export type SymChatParticipant = {
  user_id: string
  name: string
  responded: boolean
  is_organizer: boolean
  is_me: boolean
}

export type SymChatUpdate = { seq: number; content: string; created_at: string | null }

export type SymChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string | null
}

export type SymChatDetail = {
  id: string
  kind: SymChatKind
  title: string
  objective: string
  config: ScheduleConfig | DecideConfig
  status: SymChatStatus
  shape: SymChatShape | Record<string, never>
  resolution: SymChatResolution | null
  resolved_at: string | null
  is_organizer: boolean
  created_at: string | null
  participants: SymChatParticipant[]
  updates: SymChatUpdate[]
  messages: SymChatMessage[]
  my_stance: Record<string, unknown> | null
}

export type SymChatPerson = { id: string; name: string; email: string }

export type SymChatCreateInput = {
  kind: SymChatKind
  title: string
  objective: string
  participant_ids: string[]
  config: Partial<ScheduleConfig> | DecideConfig
}

export type SymChatTurnResult = {
  reply: string
  error: boolean
  status: SymChatStatus
  shape: SymChatShape
  resolved: boolean
}

export function listSymChats() {
  return api.get<{ sym_chats: SymChatSummary[] }>('/matcha-work/sym-chats')
}

export function createSymChat(input: SymChatCreateInput) {
  return api.post<SymChatDetail>('/matcha-work/sym-chats', input)
}

export function getSymChat(chatId: string) {
  return api.get<SymChatDetail>(`/matcha-work/sym-chats/${encodeURIComponent(chatId)}`)
}

export function sendSymChatMessage(chatId: string, content: string) {
  return api.post<SymChatTurnResult>(`/matcha-work/sym-chats/${encodeURIComponent(chatId)}/messages`, { content })
}

export function cancelSymChat(chatId: string) {
  return api.post<SymChatDetail>(`/matcha-work/sym-chats/${encodeURIComponent(chatId)}/cancel`, {})
}

export function searchSymChatPeople(q: string) {
  const params = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''
  return api.get<{ people: SymChatPerson[] }>(`/matcha-work/sym-chats/people${params}`)
}
