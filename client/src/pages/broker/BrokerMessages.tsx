import { useMemo } from 'react'
import BrokerCompanyChat from '../../components/broker/chat/BrokerCompanyChat'
import type { BrokerChatAdapter } from '../../components/broker/chat/adapter'
import {
  archiveBrokerConversation,
  createBrokerConversation,
  fetchBrokerChatTargets,
  fetchBrokerConversations,
  fetchBrokerMessages,
  markBrokerConversationRead,
  sendBrokerMessage,
} from '../../api/broker/brokerChat'

export default function BrokerMessages() {
  const adapter: BrokerChatAdapter = useMemo(
    () => ({
      side: 'broker',
      otherPartyNoun: 'client',
      targetNoun: 'client',
      listConversations: (inc) => fetchBrokerConversations(inc),
      listTargets: () => fetchBrokerChatTargets(),
      getMessages: (id, before) => fetchBrokerMessages(id, before),
      sendMessage: (id, body) => sendBrokerMessage(id, body),
      createConversation: (input) =>
        createBrokerConversation({
          company_id: input.targetId ?? '',
          subject: input.subject ?? null,
          reference: input.reference ?? null,
          body: input.body ?? null,
        }),
      markRead: async (id, last) => {
        await markBrokerConversationRead(id, last)
      },
      archive: (id, archived) => archiveBrokerConversation(id, archived),
    }),
    [],
  )

  return (
    <div className="p-6">
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-zinc-100">Client Messages</h1>
        <p className="text-sm text-zinc-500">
          Chat with your clients about flagged data, claims and shared documents.
        </p>
      </div>
      <BrokerCompanyChat adapter={adapter} />
    </div>
  )
}
