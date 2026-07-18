import { useEffect, useRef, useState } from 'react'
import { Loader2, Send } from 'lucide-react'
import { getProjectDetail, getThread, sendMessageStream, createProjectChat } from '../../api/matchaWork'
import type { MWMessage, MWStreamEvent, MWSendResponse } from '../../types/matchaWork'
import MessageBubble from '../matcha-work/MessageBubble'

interface BoardChatTabProps {
  projectId: string
}

function makeLocalMsg(threadId: string, role: 'user' | 'assistant', content: string): MWMessage {
  return {
    id: crypto.randomUUID(),
    thread_id: threadId,
    role,
    content,
    metadata: null,
    version_created: null,
    created_at: new Date().toISOString(),
  }
}

/** The board's discussion — reuses the project's own AI chat thread (every
 *  project gets one auto-created on creation) rather than a separate data
 *  model. Lean composer adapted from ProjectView.tsx, without that page's
 *  placeholder-fill/recruiting/tour machinery — a board doesn't need any of it. */
export default function BoardChatTab({ projectId }: BoardChatTabProps) {
  const [threadId, setThreadId] = useState<string | null>(null)
  const [messages, setMessages] = useState<MWMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const prevLen = useRef(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    getProjectDetail(projectId)
      .then(async (project) => {
        let chat = project.chats?.[0]
        if (!chat) chat = await createProjectChat(projectId)
        if (!active) return
        setThreadId(chat.id)
        const thread = await getThread(chat.id)
        if (!active) return
        setMessages(thread.messages)
      })
      .catch(() => {
        if (active) setError('Failed to load chat')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [projectId])

  useEffect(() => {
    if (messages.length > prevLen.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
    prevLen.current = messages.length
  }, [messages.length])

  function handleSend() {
    const content = input.trim()
    if (!content || !threadId || streaming) return
    setInput('')
    setStreaming(true)
    setError('')

    const tempMsg = makeLocalMsg(threadId, 'user', content)
    setMessages((prev) => [...prev, tempMsg])

    sendMessageStream(threadId, content, {
      onEvent: (_event: MWStreamEvent) => {},
      onComplete: (data: MWSendResponse) => {
        setMessages((prev) => {
          const withoutTemp = prev.filter((m) => m.id !== tempMsg.id)
          return [...withoutTemp, data.user_message, data.assistant_message]
        })
        setStreaming(false)
      },
      onError: (err) => {
        setError(err)
        setStreaming(false)
      },
    })
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-w-dim" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {error && (
        <div className="mx-4 mt-3 rounded-lg border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-w-faint">
            No messages yet — say something to get started.
          </div>
        ) : (
          messages.map((m) => <MessageBubble key={m.id} message={m} />)
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="flex items-end gap-2 border-t border-w-line p-3">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          placeholder="Type a message…"
          rows={1}
          disabled={streaming || !threadId}
          className="min-h-[44px] flex-1 resize-none rounded-lg border border-w-line bg-w-surface px-3 py-2.5 text-sm text-w-text placeholder-w-faint outline-none focus:border-w-line disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={streaming || !input.trim() || !threadId}
          className="rounded-lg bg-w-accent p-3 text-white transition-colors hover:bg-w-accent-hi disabled:opacity-40"
        >
          {streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </div>
    </div>
  )
}
