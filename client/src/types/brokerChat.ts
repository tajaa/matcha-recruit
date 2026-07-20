// Shared types for the broker↔company chat. Both the broker surface
// (pages/broker/BrokerMessages) and the company surface
// (pages/app/broker-chat/BrokerChat) render the same shapes.

export type ChatReferenceType =
  | 'claim'
  | 'loss_run'
  | 'document'
  | 'flagged_data'
  | 'incident'
  | 'submission'
  | 'policy'
  | 'general'

export type ChatSide = 'broker' | 'company'

export interface MessageReference {
  type: ChatReferenceType
  id?: string | null
  label: string
}

export interface ChatMessage {
  id: string
  conversation_id: string
  sender_user_id: string
  sender_side: ChatSide
  sender_name: string
  body: string
  reference?: MessageReference | null
  client_message_id?: string | null
  created_at: string
  edited_at?: string | null
}

export interface Conversation {
  id: string
  broker_id: string
  company_id: string
  company_name?: string | null
  broker_name?: string | null
  subject?: string | null
  status: 'open' | 'archived'
  reference?: MessageReference | null
  created_by_side: ChatSide
  last_message_at?: string | null
  last_message_preview?: string | null
  unread_count: number
  created_at: string
}

export interface ConversationListResponse {
  conversations: Conversation[]
  total_unread: number
}

export interface ChatTarget {
  id: string
  name: string
}

export interface BrokerChatSummary {
  has_active_broker: boolean
  unread: number
  brokers: ChatTarget[]
}

// Request bodies
export interface SendMessageBody {
  body: string
  reference?: MessageReference | null
  client_message_id?: string | null
}

// Side-agnostic create payload used by the shared component; the per-side
// adapter maps `targetId` to company_id (broker) or broker_id (company).
export interface CreateConversationInput {
  targetId?: string | null
  subject?: string | null
  reference?: MessageReference | null
  body?: string | null
}
