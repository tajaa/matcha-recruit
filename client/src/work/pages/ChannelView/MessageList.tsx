import { FileText, Reply, Trash2 } from 'lucide-react'
import type { ChannelMessage, ChannelMember } from '../../api/channels'
import { HuumeAvatar } from '../../components/channels/HuumeAvatar'
import { renderMessageContent } from './mentions'
import { isUrgentSystemContent, renderSystemContent, stripEmphasis } from './systemContent'

interface MessageListProps {
  messages: ChannelMessage[]
  messagesContainerRef: React.RefObject<HTMLDivElement | null>
  messagesEndRef: React.RefObject<HTMLDivElement | null>
  userId: string | undefined
  canModerate: boolean
  members: ChannelMember[]
  onDelete: (msg: ChannelMessage) => void
  onReply: (msg: ChannelMessage) => void
}

function ReplyPreviewStub({ preview }: { preview: NonNullable<ChannelMessage['reply_preview']> }) {
  return (
    <div className="mb-0.5 pl-2 border-l-2 border-w-line text-xs text-w-dim truncate">
      <span className="font-medium">{preview.sender_name}</span> {stripEmphasis(preview.content)}
    </div>
  )
}

export default function MessageList({
  messages,
  messagesContainerRef,
  messagesEndRef,
  userId,
  canModerate,
  members,
  onDelete,
  onReply,
}: MessageListProps) {
  return (
    <div ref={messagesContainerRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-1">
      {messages.length === 0 && (
        <div className="text-center py-12 text-w-faint text-sm">
          No messages yet. Start the conversation!
        </div>
      )}
      {messages.map((msg, i) => {
        // Stable key across the optimistic→confirmed swap: pending row and
        // its server echo share `client_message_id`, so React keeps the
        // DOM node instead of unmounting/remounting on echo.
        const rowKey = msg.client_message_id ? `cmid:${msg.client_message_id}` : `id:${msg.id}`

        // System (Huume) messages have no sender and the backend 403s any
        // edit/delete/react attempt on them — render them attributed to
        // Huume, on the same avatar/name/body grid as a human row so the
        // pill reads as the agent talking rather than as disembodied
        // chrome, but keep the bubble treatment so it stays visually
        // distinct from a person's message. `sender_id` is null on these
        // rows, so the normal initial-letter avatar would render "?" —
        // hence <HuumeAvatar>. Every affordance is dropped EXCEPT reply,
        // which is how a Huume clarification question gets answered (see
        // channels_ws.py _bg_ems_clarify — it fires on any reply whose
        // reply_to_id names an outstanding ems_events.clarify_message_id).
        // This branch returns early and has no `group` wrapper, so the
        // button is always visible rather than hover-revealed like the
        // delete button below.
        // Mirrored to the right (avatar/name/bubble all flip side via
        // flex-row-reverse) — the one bucket in this list that isn't a
        // human's own message but still gets the "other side" treatment,
        // so the pane reads as two parties talking rather than one long
        // left-aligned column with an agent's asides mixed in.
        if (msg.message_type === 'system') {
          const urgent = isUrgentSystemContent(msg.content)
          return (
            <div key={rowKey} className="mt-3 flex flex-row-reverse gap-2.5">
              <HuumeAvatar />
              <div className="min-w-0 flex-1 flex flex-col items-end">
                <div className="flex flex-row-reverse items-baseline gap-2 mb-0.5">
                  <span className="text-sm font-medium text-w-accent">Huume</span>
                  <span className="text-[10px] text-w-faint">
                    {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
                <div className="flex flex-row-reverse items-start gap-1.5">
                  <span className={`max-w-[85%] text-xs rounded-2xl px-3 py-1.5 whitespace-pre-wrap text-left ${
                    urgent
                      ? 'text-red-200 bg-red-500/10 border border-red-500/40'
                      : 'text-w-dim bg-w-surface2/60 border border-w-line'
                  }`}>
                    {renderSystemContent(msg.content)}
                  </span>
                  {!msg.pending && (
                    <button
                      onClick={() => onReply(msg)}
                      className="text-w-faint hover:text-w-text shrink-0 mt-1.5"
                      title="Reply"
                    >
                      <Reply size={12} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          )
        }

        const showAuthor = i === 0 || messages[i - 1].sender_id !== msg.sender_id
        const isOwn = msg.sender_id === userId
        const isDeleted = !!msg.deleted_at
        const canDelete = !isDeleted && (isOwn || canModerate)
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
              {!isDeleted && msg.reply_preview && <ReplyPreviewStub preview={msg.reply_preview} />}
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
            {!isDeleted && (
              <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 shrink-0 self-start mt-0.5">
                <button
                  onClick={() => onReply(msg)}
                  className="text-w-dim hover:text-w-text"
                  title="Reply"
                >
                  <Reply size={13} />
                </button>
                {canDelete && (
                  <button
                    onClick={() => onDelete(msg)}
                    className="text-w-dim hover:text-red-400"
                    title={isOwn ? 'Delete message' : 'Delete as moderator'}
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            )}
          </div>
        )
      })}
      <div ref={messagesEndRef} />
    </div>
  )
}
