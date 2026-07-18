import { FileText, Trash2 } from 'lucide-react'
import type { ChannelMessage, ChannelMember } from '../../api/channels'
import { renderMessageContent } from './mentions'

interface MessageListProps {
  messages: ChannelMessage[]
  messagesContainerRef: React.RefObject<HTMLDivElement>
  messagesEndRef: React.RefObject<HTMLDivElement>
  userId: string | undefined
  canModerate: boolean
  members: ChannelMember[]
  onDelete: (msg: ChannelMessage) => void
}

export default function MessageList({
  messages,
  messagesContainerRef,
  messagesEndRef,
  userId,
  canModerate,
  members,
  onDelete,
}: MessageListProps) {
  return (
    <div ref={messagesContainerRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-1">
      {messages.length === 0 && (
        <div className="text-center py-12 text-w-faint text-sm">
          No messages yet. Start the conversation!
        </div>
      )}
      {messages.map((msg, i) => {
        const showAuthor = i === 0 || messages[i - 1].sender_id !== msg.sender_id
        const isOwn = msg.sender_id === userId
        const isDeleted = !!msg.deleted_at
        const canDelete = !isDeleted && (isOwn || canModerate)
        // Stable key across the optimistic→confirmed swap: pending row and
        // its server echo share `client_message_id`, so React keeps the
        // DOM node instead of unmounting/remounting on echo.
        const rowKey = msg.client_message_id ? `cmid:${msg.client_message_id}` : `id:${msg.id}`
        return (
          <div key={rowKey} className={`${showAuthor && i > 0 ? 'mt-3' : ''} flex gap-2.5 group ${msg.pending ? 'opacity-60' : ''}`}>
            {showAuthor ? (
              msg.sender_avatar_url ? (
                <img src={msg.sender_avatar_url} alt="" className="w-8 h-8 rounded-full object-cover shrink-0 mt-0.5" />
              ) : (
                <div className="w-8 h-8 rounded-full bg-w-surface2 flex items-center justify-center text-xs font-medium text-w-dim shrink-0 mt-0.5">
                  {(msg.sender_name || '?')[0].toUpperCase()}
                </div>
              )
            ) : (
              <div className="w-8 shrink-0" />
            )}
            <div className="min-w-0 flex-1">
              {showAuthor && (
                <div className="flex items-baseline gap-2 mb-0.5">
                  <span className={`text-sm font-medium ${isOwn ? 'text-w-accent' : 'text-blue-400'}`}>
                    {msg.sender_name}
                  </span>
                  <span className="text-[10px] text-w-faint">
                    {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    {msg.edited_at && !isDeleted ? ' (edited)' : ''}
                  </span>
                </div>
              )}
              {isDeleted ? (
                <p className="text-xs italic text-w-dim">
                  {msg.deleted_by === msg.sender_id
                    ? '[message deleted by author]'
                    : '[message removed by a moderator]'}
                </p>
              ) : msg.content ? (
                <p className="text-sm text-w-text whitespace-pre-wrap break-words">
                  {renderMessageContent(
                    msg.content,
                    members,
                    msg.mentioned_user_ids,
                    userId,
                  )}
                </p>
              ) : null}
            {!isDeleted && msg.attachments && msg.attachments.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-1">
                {msg.attachments.map((att, ai) =>
                  att.content_type.startsWith('image/') ? (
                    <a key={ai} href={att.url} target="_blank" rel="noopener noreferrer">
                      <img src={att.url} alt={att.filename} className="max-w-xs max-h-48 rounded-md border border-w-line" />
                    </a>
                  ) : (
                    <a
                      key={ai}
                      href={att.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-w-surface2 border border-w-line text-xs text-w-text hover:text-white hover:border-w-accent/40 transition-colors"
                    >
                      <FileText size={12} className="shrink-0" />
                      <span className="truncate max-w-[200px]">{att.filename}</span>
                      <span className="text-w-dim shrink-0">
                        {att.size >= 1_000_000 ? `${(att.size / 1_000_000).toFixed(1)}MB` : `${Math.round(att.size / 1_000)}KB`}
                      </span>
                    </a>
                  )
                )}
              </div>
            )}
            {!isDeleted && msg.reactions && msg.reactions.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1">
                {msg.reactions.map((r) => (
                  <span
                    key={r.emoji}
                    className="flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-w-surface2 border border-w-line text-xs"
                    title={r.user_ids.length === 1 ? '1 reaction' : `${r.user_ids.length} reactions`}
                  >
                    <span>{r.emoji}</span>
                    <span className="text-w-dim">{r.count}</span>
                  </span>
                ))}
              </div>
            )}
            </div>
            {canDelete && (
              <button
                onClick={() => onDelete(msg)}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-w-dim hover:text-red-400 shrink-0 self-start mt-0.5"
                title={isOwn ? 'Delete message' : 'Delete as moderator'}
              >
                <Trash2 size={13} />
              </button>
            )}
          </div>
        )
      })}
      <div ref={messagesEndRef} />
    </div>
  )
}
