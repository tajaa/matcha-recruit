import { useState } from 'react'
import { Search, Plus, Menu } from 'lucide-react'
import type { ConversationSummary } from '../../api/inbox'
import Avatar from '../Avatar'

type Props = {
  conversations: ConversationSummary[]
  selectedId: string | null
  currentUserId: string
  onSelect: (id: string) => void
  onCompose: () => void
  onMenuToggle?: () => void
}

function relativeTime(iso: string | null): string {
  if (!iso) return ''
  const now = Date.now()
  const then = new Date(iso).getTime()
  const diffSec = Math.floor((now - then) / 1000)

  if (diffSec < 60) return 'Just now'
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`

  const today = new Date()
  const date = new Date(iso)

  // Yesterday check
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  if (
    date.getFullYear() === yesterday.getFullYear() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getDate() === yesterday.getDate()
  ) {
    return 'Yesterday'
  }

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function displayName(convo: ConversationSummary, currentUserId: string): string {
  if (convo.title) return convo.title

  const others = convo.participants.filter((p) => p.user_id !== currentUserId)
  if (others.length === 0) return 'You'
  if (others.length === 1) return others[0].name
  if (others.length === 2) return `${others[0].name}, ${others[1].name}`
  return `${others[0].name}, ${others[1].name} +${others.length - 2}`
}

export function ConversationList({ conversations, selectedId, currentUserId, onSelect, onCompose, onMenuToggle }: Props) {
  const [filter, setFilter] = useState('')

  const filtered = filter.trim()
    ? conversations.filter((c) => {
        const q = filter.toLowerCase()
        const name = displayName(c, currentUserId).toLowerCase()
        const preview = (c.last_message_preview ?? '').toLowerCase()
        return name.includes(q) || preview.includes(q)
      })
    : conversations

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          {onMenuToggle && (
            <button
              onClick={onMenuToggle}
              className="sm:hidden text-zinc-400 hover:text-zinc-100"
            >
              <Menu size={18} />
            </button>
          )}
          <h2 className="text-lg font-semibold text-zinc-100">Inbox</h2>
        </div>
        <button
          onClick={onCompose}
          className="flex items-center gap-1.5 rounded-lg bg-zinc-800 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100 transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span className="hidden sm:inline">New</span>
        </button>
      </div>

      {/* Search */}
      <div className="px-3 py-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            type="text"
            placeholder="Search conversations..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="w-full rounded-lg border border-zinc-800 bg-zinc-900 pl-9 pr-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-600 transition-colors"
          />
        </div>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 && (
          <div className="px-4 py-8 text-center text-sm text-zinc-500">
            {filter.trim() ? 'No matching conversations' : 'No messages yet'}
          </div>
        )}

        {filtered.map((convo) => {
          const isSelected = convo.id === selectedId
          const hasUnread = convo.unread_count > 0

          return (
            <button
              key={convo.id}
              onClick={() => onSelect(convo.id)}
              className={`w-full text-left px-4 py-3 border-b border-zinc-800/50 transition-colors ${
                isSelected
                  ? 'bg-zinc-800/80'
                  : 'hover:bg-zinc-900/80'
              }`}
            >
              <div className="flex items-start gap-3">
                {/* Avatar with unread indicator */}
                <div className="relative shrink-0">
                  {(() => {
                    const other = convo.participants.find((p) => p.user_id !== currentUserId)
                    return (
                      <Avatar
                        name={displayName(convo, currentUserId)}
                        avatarUrl={other?.avatar_url}
                        size="sm"
                      />
                    )
                  })()}
                  {hasUnread && (
                    <div className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-blue-500 ring-2 ring-zinc-950" />
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className={`text-sm truncate ${hasUnread ? 'font-semibold text-zinc-100' : 'font-medium text-zinc-300'}`}>
                      {displayName(convo, currentUserId)}
                    </span>
                    <span className="text-xs text-zinc-500 shrink-0">
                      {relativeTime(convo.last_message_at)}
                    </span>
                  </div>

                  {convo.last_message_preview && (
                    <p className={`text-xs mt-0.5 truncate ${hasUnread ? 'text-zinc-400' : 'text-zinc-500'}`}>
                      {convo.last_message_preview.length > 60
                        ? convo.last_message_preview.slice(0, 60) + '...'
                        : convo.last_message_preview}
                    </p>
                  )}
                </div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
