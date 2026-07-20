// The BrokerCompanyChat component is side-agnostic: the broker page and the
// company page each build one of these adapters (wiring the correct REST
// endpoints) and hand it to the shared UI. `targetLabel` names what a "new
// conversation" target is on this side (a client company vs a broker).

import type {
  ChatMessage,
  ChatTarget,
  Conversation,
  ConversationListResponse,
  CreateConversationInput,
  SendMessageBody,
} from '../../../types/brokerChat'

export interface BrokerChatAdapter {
  side: 'broker' | 'company'
  // What the other party is called, for empty-states and labels.
  otherPartyNoun: string
  // Noun for a "new conversation" target ("client" for broker, "broker" for company).
  targetNoun: string
  listConversations: (includeArchived: boolean) => Promise<ConversationListResponse>
  listTargets: () => Promise<ChatTarget[]>
  getMessages: (conversationId: string, before?: string) => Promise<ChatMessage[]>
  sendMessage: (conversationId: string, body: SendMessageBody) => Promise<ChatMessage>
  createConversation: (input: CreateConversationInput) => Promise<Conversation>
  markRead: (conversationId: string, lastReadMessageId?: string) => Promise<void>
  archive?: (conversationId: string, archived: boolean) => Promise<Conversation>
}
