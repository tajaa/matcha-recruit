// Conversational IR-intake chat — one REST call per turn (POST
// /ir/incidents/chat/turn). Stateless server-side: this hook holds the
// transcript + accumulated fields and echoes both each turn. Never submits
// the incident itself — caller merges `fields` into the create wizard's form
// on `complete` and the user reviews/submits as normal, same invariant as
// voice dictation.

import { useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { ChatIntakeFields, ChatIntakeMessage, ChatIntakeTurnResponse } from '../../types/ir'

const OPENING = "Hi — tell me what happened, in your own words."

const EMPTY_CHAT_FIELDS: ChatIntakeFields = {
  reported_by_name: null,
  occurred_at_text: null,
  location_id: null,
  description: null,
  witnesses: [],
}

function openingMessages(): ChatIntakeMessage[] {
  return [{ role: 'assistant', content: OPENING }]
}

export function useChatIntake() {
  const [messages, setMessages] = useState<ChatIntakeMessage[]>(openingMessages)
  const [fields, setFields] = useState<ChatIntakeFields>(EMPTY_CHAT_FIELDS)
  const [sending, setSending] = useState(false)
  const [complete, setComplete] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)

  async function send(text: string) {
    const trimmed = text.trim()
    if (!trimmed || sending) return
    const next = [...messages, { role: 'user' as const, content: trimmed }]
    setMessages(next)
    setSending(true)
    setChatError(null)
    try {
      const res = await api.post<ChatIntakeTurnResponse>('/ir/incidents/chat/turn', {
        transcript: next,
        known_fields: fields,
      })
      setMessages((m) => [...m, { role: 'assistant', content: res.assistant_message }])
      setFields(res.fields)
      setComplete(res.complete)
      if (res.error) setChatError('Having trouble — you can finish in the form below.')
    } catch (err) {
      const tooMany = err instanceof ApiError && err.status === 429
      setChatError(tooMany ? 'Too many messages — wait a moment, or finish in the form below.' : 'Failed to send — try again.')
    } finally {
      setSending(false)
    }
  }

  function reset() {
    setMessages(openingMessages())
    setFields(EMPTY_CHAT_FIELDS)
    setComplete(false)
    setChatError(null)
    setSending(false)
  }

  return { messages, fields, sending, complete, chatError, send, reset }
}
