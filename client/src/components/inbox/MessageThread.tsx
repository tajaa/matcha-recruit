import { useEffect, useRef, useState, useCallback } from 'react'
import { Send, BellOff, Bell, ArrowLeft } from 'lucide-react'
import type { Conversation, Participant } from '../../api/inbox'
import { toggleMute as apiToggleMute } from '../../api/inbox'

type Props = {
  conversation: Conversation
  currentUserId: string
  onSendMessage: (content: string) => Promise<void>
  onMarkRead: () => void
  onBack?: () => void
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  })
}

function dateLabel(iso: string): string {
  const date = new Date(iso)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)

  if (
    date.getFullYear() === today.getFullYear() &&
    date.getMonth() === today.getMonth() &&
    date.getDate() === today.getDate()
  ) {
    return 'Today'
  }

  if (
    date.getFullYear() === yesterday.getFullYear() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getDate() === yesterday.getDate()
  ) {
    return 'Yesterday'
  }

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function threadDisplayName(participants: Participant[], currentUserId: string, title: string | null): string {
  if (title) return title

  const others = participants.filter((p) => p.user_id !== currentUserId)
  if (others.length === 0) return 'You'
  if (others.length === 1) return others[0].name
  return others.map((p) => p.name).join(', ')
}

export function MessageThread({ conversation, currentUserId, onSendMessage, onMarkRead, onBack }: Props) {
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [muted, setMuted] = useState(() =>
    conversation.participants.find((p) => p.user_id === currentUserId)?.is_muted ?? false,
  )
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const hasMarkedRead = useRef(false)

  // Mark read on mount / conversation change
  useEffect(() => {
    if (!hasMarkedRead.current) {
      onMarkRead()
      hasMarkedRead.current = true
    }
    return () => {
      hasMarkedRead.current = false
    }
  }, [conversation.id, onMarkRead])

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversation.messages])

  // Auto-resize textarea
  const autoResize = useCallback(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px'
  }, [])

  useEffect(() => {
    autoResize()
  }, [draft, autoResize])

  // Sync muted state when conversation changes
  useEffect(() => {
    const me = conversation.participants.find((p) => p.user_id === currentUserId)
    setMuted(me?.is_muted ?? false)
  }, [conversation.id, conversation.participants, currentUserId])

  async function handleSend() {
    const content = draft.trim()
    if (!content || sending) return
    setSending(true)
    try {
      await onSendMessage(content)
      setDraft('')
    } finally {
      setSending(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  async function handleToggleMute() {
    try {
      const result = await apiToggleMute(conversation.id)
      setMuted(result.is_muted)
    } catch {
      // Silently fail -- not critical
    }
  }

  // Group messages by date
  const groupedMessages: { label: string; messages: typeof conversation.messages }[] = []
  let currentLabel = ''

  for (const msg of conversation.messages) {
    const label = dateLabel(msg.created_at)
    if (label !== currentLabel) {
      currentLabel = label
      groupedMessages.push({ label, messages: [msg] })
    } else {
      groupedMessages[groupedMessages.length - 1].messages.push(msg)
    }
  }

  const displayTitle = threadDisplayName(conversation.participants, currentUserId, conversation.title)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-800">
        {onBack && (
          <button
            onClick={onBack}
            className="p-1 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors md:hidden"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
        )}
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-zinc-100 truncate">{displayTitle}</h3>
          {conversation.is_group && (
            <p className="text-xs text-zinc-500">
              {conversation.participants.length} participants
            </p>
          )}
        </div>
        <button
          onClick={handleToggleMute}
          className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          title={muted ? 'Unmute conversation' : 'Mute conversation'}
        >
          {muted ? <BellOff className="w-4 h-4" /> : <Bell className="w-4 h-4" />}
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {conversation.messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-sm text-zinc-500">
            No messages yet. Say hello!
          </div>
        )}

        {groupedMessages.map((group) => (
          <div key={group.label}>
            {/* Date divider */}
            <div className="flex items-center gap-3 my-4">
              <div className="flex-1 h-px bg-zinc-800" />
              <span className="text-xs text-zinc-500 shrink-0">{group.label}</span>
              <div className="flex-1 h-px bg-zinc-800" />
            </div>

            <div className="space-y-2">
              {group.messages.map((msg) => {
                const isMine = msg.sender_id === currentUserId

                return (
                  <div
                    key={msg.id}
                    className={`flex ${isMine ? 'justify-end' : 'justify-start'}`}
                  >
                    <div className={`max-w-[75%] ${isMine ? 'items-end' : 'items-start'}`}>
                      {/* Sender name for group conversations (received messages only) */}
                      {conversation.is_group && !isMine && (
                        <p className="text-xs text-zinc-500 mb-0.5 px-1">{msg.sender_name}</p>
                      )}
                      <div
                        className={`rounded-2xl px-3.5 py-2 text-sm ${
                          isMine
                            ? 'bg-emerald-900/60 text-emerald-50'
                            : 'bg-zinc-800 text-zinc-200'
                        }`}
                      >
                        <p className="whitespace-pre-wrap break-words">{msg.content}</p>
                      </div>
                      <p className={`text-[10px] text-zinc-600 mt-0.5 px-1 ${isMine ? 'text-right' : ''}`}>
                        {formatTime(msg.created_at)}
                        {msg.edited_at && <span className="ml-1">(edited)</span>}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ))}

        <div ref={messagesEndRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-zinc-800 px-4 py-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            rows={1}
            className="flex-1 rounded-xl border border-zinc-700 bg-zinc-900 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-500 transition-colors resize-none"
            style={{ maxHeight: 160 }}
          />
          <button
            onClick={handleSend}
            disabled={!draft.trim() || sending}
            className="shrink-0 rounded-xl bg-emerald-700 p-2.5 text-white hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
