import { useState } from 'react'
import { API_BASE } from '../../api/client'
import type { PublicChatIntakeFields, PublicChatIntakeMessage, PublicChatIntakeTurnResponse } from '../../types/ir'

type PublicChatKind = 'report' | 'intake'

const EMPTY_FIELDS: PublicChatIntakeFields = {
  reported_by_name: null,
  occurred_at_text: null,
  location: null,
  description: null,
  witnesses: [],
  involved_parties: null,
  contact_info: null,
  corrective_actions: null,
}

function openingMessages(kind: PublicChatKind): PublicChatIntakeMessage[] {
  return [{
    role: 'assistant',
    content: kind === 'report'
      ? 'Tell me what happened, in your own words. You can leave out anything that could identify you.'
      : 'Tell me what happened, in your own words.',
  }]
}

export function usePublicChatIntake(kind: PublicChatKind, token: string | undefined) {
  const [messages, setMessages] = useState<PublicChatIntakeMessage[]>(() => openingMessages(kind))
  const [fields, setFields] = useState<PublicChatIntakeFields>(EMPTY_FIELDS)
  const [sending, setSending] = useState(false)
  const [complete, setComplete] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function send(text: string) {
    const content = text.trim()
    if (!content || sending || !token) return
    const transcript = [...messages, { role: 'user' as const, content }]
    setMessages(transcript)
    setSending(true)
    setError(null)
    try {
      const endpoint = kind === 'report'
        ? `${API_BASE}/report/${token}/chat/turn`
        : `${API_BASE}/intake/${token}/chat/turn`
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript, known_fields: fields }),
      })
      if (!response.ok) {
        if (response.status === 429) throw new Error('Too many messages. Please wait a moment, then try again.')
        if (response.status === 403) throw new Error('AI chat is not enabled for this reporting link.')
        throw new Error('We could not continue the chat. You can review what you have.')
      }
      const result = await response.json() as PublicChatIntakeTurnResponse
      setMessages((current) => [...current, { role: 'assistant', content: result.assistant_message }])
      setFields(result.fields)
      setComplete(result.complete)
      if (result.error) setError('We could not continue the chat. You can review what you have.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'We could not continue the chat. You can review what you have.')
    } finally {
      setSending(false)
    }
  }

  function reset() {
    setMessages(openingMessages(kind))
    setFields(EMPTY_FIELDS)
    setComplete(false)
    setError(null)
    setSending(false)
  }

  return { messages, fields, sending, complete, error, send, reset }
}
