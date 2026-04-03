import { useEffect, useState, useCallback, useRef } from 'react'
import { MessageSquare, Mail, Loader2 } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import {
  listConversations,
  getConversation,
  sendMessage,
  markRead as apiMarkRead,
  getUnreadCount,
} from '../../api/inbox'
import type { ConversationSummary, Conversation } from '../../api/inbox'
import { ConversationList } from '../../components/inbox/ConversationList'
import { MessageThread } from '../../components/inbox/MessageThread'
import { ComposeModal } from '../../components/inbox/ComposeModal'

export default function Inbox() {
  const { me, loading: meLoading } = useMe()

  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null)
  const [loading, setLoading] = useState(true)
  const [threadLoading, setThreadLoading] = useState(false)
  const [composeOpen, setComposeOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Mobile: track whether the user is viewing the thread panel
  const [mobileShowThread, setMobileShowThread] = useState(false)

  const pollRef = useRef<ReturnType<typeof setInterval>>(null)

  const currentUserId = me?.user?.id ?? ''

  // Load conversation list
  const loadConversations = useCallback(async () => {
    try {
      const data = await listConversations()
      setConversations(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conversations')
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    if (meLoading) return
    loadConversations()
  }, [meLoading, loadConversations])

  // Poll unread count every 60 seconds and refresh list
  useEffect(() => {
    if (meLoading) return

    pollRef.current = setInterval(async () => {
      try {
        await getUnreadCount()
        // Refresh conversation list to pick up new messages / unread counts
        const data = await listConversations()
        setConversations(data)
      } catch {
        // Non-critical -- swallow errors from polling
      }
    }, 60_000)

    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [meLoading])

  // Load a conversation thread
  const loadThread = useCallback(async (id: string) => {
    setThreadLoading(true)
    try {
      const convo = await getConversation(id)
      setActiveConversation(convo)
    } catch {
      setActiveConversation(null)
    } finally {
      setThreadLoading(false)
    }
  }, [])

  // Select a conversation
  function handleSelect(id: string) {
    setSelectedId(id)
    setMobileShowThread(true)
    loadThread(id)
  }

  // Send a message in the active conversation
  async function handleSendMessage(content: string, files?: File[]) {
    if (!activeConversation) return
    const msg = await sendMessage(activeConversation.id, content, files)
    // Append the new message locally
    setActiveConversation((prev) =>
      prev ? { ...prev, messages: [...prev.messages, msg] } : prev,
    )
    // Update the preview in the conversation list
    const preview = content || (msg.attachments.length ? `[${msg.attachments.length} attachment${msg.attachments.length > 1 ? 's' : ''}]` : '')
    setConversations((prev) =>
      prev.map((c) =>
        c.id === activeConversation.id
          ? { ...c, last_message_preview: preview, last_message_at: msg.created_at, unread_count: 0 }
          : c,
      ),
    )
  }

  // Mark conversation as read
  const handleMarkRead = useCallback(() => {
    if (!selectedId) return
    apiMarkRead(selectedId).catch(() => {})
    setConversations((prev) =>
      prev.map((c) => (c.id === selectedId ? { ...c, unread_count: 0 } : c)),
    )
  }, [selectedId])

  // Handle new conversation created via compose
  function handleConversationCreated(convo: Conversation) {
    // Add to top of list or refresh
    setConversations((prev) => {
      const exists = prev.some((c) => c.id === convo.id)
      if (exists) return prev
      const summary: ConversationSummary = {
        id: convo.id,
        title: convo.title,
        is_group: convo.is_group,
        last_message_at: convo.last_message_at,
        last_message_preview: convo.last_message_preview,
        participants: convo.participants,
        unread_count: 0,
      }
      return [summary, ...prev]
    })
    setSelectedId(convo.id)
    setActiveConversation(convo)
    setMobileShowThread(true)
  }

  // Mobile back
  function handleMobileBack() {
    setMobileShowThread(false)
    // Refresh list in case unread counts changed
    loadConversations()
  }

  if (meLoading || loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 text-zinc-500 animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <p className="text-sm text-red-400">{error}</p>
        <button
          onClick={loadConversations}
          className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          Try again
        </button>
      </div>
    )
  }

  return (
    <div className="h-[calc(100vh-64px)] flex">
      {/* Left panel: Conversation list */}
      <div
        className={`w-full md:w-80 md:shrink-0 border-r border-zinc-800 bg-zinc-950 ${
          mobileShowThread ? 'hidden md:flex md:flex-col' : 'flex flex-col'
        }`}
      >
        {conversations.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-4 px-6">
            <Mail className="w-10 h-10 text-zinc-600" />
            <div className="text-center">
              <p className="text-sm text-zinc-400">No messages yet</p>
              <p className="text-xs text-zinc-500 mt-1">Start a conversation to get going.</p>
            </div>
            <button
              onClick={() => setComposeOpen(true)}
              className="rounded-lg bg-zinc-800 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-700 transition-colors"
            >
              New Message
            </button>
          </div>
        ) : (
          <ConversationList
            conversations={conversations}
            selectedId={selectedId}
            currentUserId={currentUserId}
            onSelect={handleSelect}
            onCompose={() => setComposeOpen(true)}
          />
        )}
      </div>

      {/* Right panel: Message thread */}
      <div
        className={`flex-1 bg-zinc-950 ${
          mobileShowThread ? 'flex flex-col' : 'hidden md:flex md:flex-col'
        }`}
      >
        {threadLoading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-5 h-5 text-zinc-500 animate-spin" />
          </div>
        ) : activeConversation ? (
          <MessageThread
            conversation={activeConversation}
            currentUserId={currentUserId}
            onSendMessage={handleSendMessage}
            onMarkRead={handleMarkRead}
            onBack={handleMobileBack}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <MessageSquare className="w-10 h-10 text-zinc-700" />
            <p className="text-sm text-zinc-500">Select a conversation</p>
          </div>
        )}
      </div>

      {/* Compose modal */}
      <ComposeModal
        isOpen={composeOpen}
        onClose={() => setComposeOpen(false)}
        onCreated={handleConversationCreated}
      />
    </div>
  )
}
