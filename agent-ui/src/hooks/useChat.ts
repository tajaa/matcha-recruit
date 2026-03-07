import { useState, useCallback } from 'preact/hooks'
import { api } from '../lib/api'
import type { ChatMessage, Email } from '../lib/api'

export type MessageItem =
  | { type: 'user'; content: string }
  | { type: 'agent'; content: string }
  | { type: 'system'; content: string }
  | { type: 'emails'; emails: Email[] }
  | { type: 'event'; event: Record<string, unknown>; link: string }

export function useChat() {
  const [messages, setMessages] = useState<MessageItem[]>([])
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)

  const addMessage = useCallback((msg: MessageItem) => {
    setMessages((prev) => [...prev, msg])
  }, [])

  const addSystem = useCallback(
    (text: string) => addMessage({ type: 'system', content: text }),
    [addMessage]
  )

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || loading) return
      addMessage({ type: 'user', content: text })
      const newHistory = [...history, { role: 'user' as const, content: text }]
      setHistory(newHistory)
      setLoading(true)

      try {
        const data = await api.chat(text, newHistory)
        addMessage({ type: 'agent', content: data.response })
        setHistory((h) => [...h, { role: 'agent', content: data.response }])
      } catch (e: unknown) {
        addSystem(`Error: ${e instanceof Error ? e.message : 'Unknown error'}`)
      }
      setLoading(false)
    },
    [history, loading, addMessage, addSystem]
  )

  const fetchEmails = useCallback(async () => {
    setLoading(true)
    addSystem('Fetching unread emails...')
    try {
      const data = await api.fetchEmails()
      if (!data.emails?.length) {
        addSystem('No unread emails found.')
      } else {
        addMessage({ type: 'emails', emails: data.emails })
      }
    } catch (e: unknown) {
      addSystem(
        `Email fetch failed: ${e instanceof Error ? e.message : 'Unknown error'}`
      )
    }
    setLoading(false)
  }, [addMessage, addSystem])

  const draftReply = useCallback(
    async (emailId: string, instructions: string) => {
      setLoading(true)
      addSystem('Drafting reply...')
      try {
        const data = await api.draftReply(emailId, instructions)
        addMessage({
          type: 'agent',
          content: `**Draft to ${data.to}**\n\nSubject: ${data.subject}\n\n---\n\n${data.body}\n\n---\n_Saved to Gmail Drafts._`,
        })
      } catch (e: unknown) {
        addSystem(
          `Draft failed: ${e instanceof Error ? e.message : 'Unknown error'}`
        )
      }
      setLoading(false)
    },
    [addMessage, addSystem]
  )

  const createEvent = useCallback(
    async (emailId: string) => {
      setLoading(true)
      addSystem('Extracting event details...')
      try {
        const data = await api.createEvent(emailId)
        addMessage({ type: 'event', event: data.event, link: data.link })
      } catch (e: unknown) {
        addSystem(
          `Calendar error: ${e instanceof Error ? e.message : 'Unknown error'}`
        )
      }
      setLoading(false)
    },
    [addMessage, addSystem]
  )

  const runBriefing = useCallback(async () => {
    setLoading(true)
    addSystem('Generating RSS briefing...')
    try {
      const data = await api.briefing()
      if (data.content) {
        addMessage({ type: 'agent', content: data.content })
      } else {
        addSystem('No briefing generated.')
      }
    } catch (e: unknown) {
      addSystem(
        `Briefing failed: ${e instanceof Error ? e.message : 'Unknown error'}`
      )
    }
    setLoading(false)
  }, [addMessage, addSystem])

  const clear = useCallback(() => {
    setMessages([])
    setHistory([])
  }, [])

  return {
    messages,
    loading,
    sendMessage,
    fetchEmails,
    draftReply,
    createEvent,
    runBriefing,
    clear,
  }
}
