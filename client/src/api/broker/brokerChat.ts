// Broker-side REST client for the broker↔company chat (endpoints under /broker/chat).
import { api } from '../client'
import type {
  ChatMessage,
  ChatTarget,
  Conversation,
  ConversationListResponse,
  SendMessageBody,
} from '../../types/brokerChat'

export const fetchBrokerConversations = (includeArchived = false) =>
  api.get<ConversationListResponse>(
    `/broker/chat/conversations?include_archived=${includeArchived}`,
  )

export const fetchBrokerChatTargets = () =>
  api.get<ChatTarget[]>('/broker/chat/targets')

export const fetchBrokerMessages = (conversationId: string, before?: string) =>
  api.get<ChatMessage[]>(
    `/broker/chat/conversations/${conversationId}/messages` +
      (before ? `?before=${encodeURIComponent(before)}` : ''),
  )

export const sendBrokerMessage = (conversationId: string, body: SendMessageBody) =>
  api.post<ChatMessage>(`/broker/chat/conversations/${conversationId}/messages`, body)

export interface CreateBrokerConversationBody {
  company_id: string
  subject?: string | null
  reference?: SendMessageBody['reference']
  body?: string | null
}

export const createBrokerConversation = (body: CreateBrokerConversationBody) =>
  api.post<Conversation>('/broker/chat/conversations', body)

export const markBrokerConversationRead = (
  conversationId: string,
  lastReadMessageId?: string,
) =>
  api.put<{ ok: boolean }>(`/broker/chat/conversations/${conversationId}/read`, {
    last_read_message_id: lastReadMessageId ?? null,
  })

export const archiveBrokerConversation = (conversationId: string, archived: boolean) =>
  api.post<Conversation>(
    `/broker/chat/conversations/${conversationId}/archive?archived=${archived}`,
  )

export const fetchBrokerChatUnread = () =>
  api.get<{ unread: number }>('/broker/chat/unread-count')
