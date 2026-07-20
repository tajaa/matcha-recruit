import { useEffect, useMemo, useState } from 'react'
import { Loader2, MessageSquare } from 'lucide-react'
import BrokerCompanyChat from '../../../components/broker/chat/BrokerCompanyChat'
import type { BrokerChatAdapter } from '../../../components/broker/chat/adapter'
import {
  createCompanyConversation,
  fetchCompanyBrokerChatSummary,
  fetchCompanyConversations,
  fetchCompanyMessages,
  markCompanyConversationRead,
  sendCompanyMessage,
} from '../../../api/broker-chat/brokerChat'
import type { BrokerChatSummary } from '../../../types/brokerChat'

export default function BrokerChat() {
  const [summary, setSummary] = useState<BrokerChatSummary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchCompanyBrokerChatSummary()
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false))
  }, [])

  const adapter: BrokerChatAdapter = useMemo(
    () => ({
      side: 'company',
      otherPartyNoun: 'broker',
      targetNoun: 'broker',
      listConversations: (inc) => fetchCompanyConversations(inc),
      listTargets: () => fetchCompanyBrokerChatSummary().then((s) => s.brokers),
      getMessages: (id, before) => fetchCompanyMessages(id, before),
      sendMessage: (id, body) => sendCompanyMessage(id, body),
      createConversation: (input) =>
        createCompanyConversation({
          broker_id: input.targetId ?? null,
          subject: input.subject ?? null,
          reference: input.reference ?? null,
          body: input.body ?? null,
        }),
      markRead: async (id, last) => {
        await markCompanyConversationRead(id, last)
      },
      // Company side has no archive control — brokers own thread lifecycle.
    }),
    [],
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center p-16 text-zinc-500">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    )
  }

  if (!summary?.has_active_broker) {
    return (
      <div className="p-6">
        <h1 className="mb-1 text-xl font-semibold text-zinc-100">Broker Messages</h1>
        <div className="mt-8 flex flex-col items-center justify-center gap-2 rounded-xl border border-zinc-800 bg-zinc-950 py-16 text-center text-zinc-500">
          <MessageSquare className="h-8 w-8" />
          <p className="text-sm">Your company isn't connected to a broker yet.</p>
          <p className="text-xs text-zinc-600">
            Once a broker manages your account, you can message them here.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6">
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-zinc-100">Broker Messages</h1>
        <p className="text-sm text-zinc-500">
          Message your broker about flagged data, claims and shared documents.
        </p>
      </div>
      <BrokerCompanyChat adapter={adapter} />
    </div>
  )
}
