// Company-side REST client for the broker↔company chat (endpoints under /broker-chat).
import { api } from '../client'
import type {
  BrokerChatSummary,
  ChatMessage,
  Conversation,
  ConversationListResponse,
  SendMessageBody,
} from '../../types/brokerChat'

export const fetchCompanyBrokerChatSummary = () =>
  api.get<BrokerChatSummary>('/broker-chat/summary')

export const fetchCompanyConversations = (includeArchived = false) =>
  api.get<ConversationListResponse>(
    `/broker-chat/conversations?include_archived=${includeArchived}`,
  )

export const fetchCompanyMessages = (conversationId: string, before?: string) =>
  api.get<ChatMessage[]>(
    `/broker-chat/conversations/${conversationId}/messages` +
      (before ? `?before=${encodeURIComponent(before)}` : ''),
  )

export const sendCompanyMessage = (conversationId: string, body: SendMessageBody) =>
  api.post<ChatMessage>(`/broker-chat/conversations/${conversationId}/messages`, body)

export interface CreateCompanyConversationBody {
  broker_id?: string | null
  subject?: string | null
  reference?: SendMessageBody['reference']
  body?: string | null
}

export const createCompanyConversation = (body: CreateCompanyConversationBody) =>
  api.post<Conversation>('/broker-chat/conversations', body)

export const markCompanyConversationRead = (
  conversationId: string,
  lastReadMessageId?: string,
) =>
  api.put<{ ok: boolean }>(`/broker-chat/conversations/${conversationId}/read`, {
    last_read_message_id: lastReadMessageId ?? null,
  })

export const fetchCompanyBrokerChatUnread = () =>
  api.get<{ unread: number }>('/broker-chat/unread-count')
