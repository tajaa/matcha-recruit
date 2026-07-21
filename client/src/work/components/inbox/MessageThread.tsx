import { Send, BellOff, Bell, ArrowLeft, Paperclip, X, FileText, Download } from 'lucide-react'
import type { Conversation, Attachment } from '../../api/inbox'
import Avatar from '../../../components/shared/Avatar'
import { useMessageThread, ALLOWED_EXTENSIONS } from './useMessageThread'

type Props = {
  conversation: Conversation
  currentUserId: string
  onSendMessage: (content: string, files?: File[]) => Promise<void>
  onMarkRead: () => void
  onBack?: () => void
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  })
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function isImageType(ct: string): boolean {
  return ct.startsWith('image/')
}

function AttachmentDisplay({ attachment }: { attachment: Attachment }) {
  if (isImageType(attachment.content_type)) {
    return (
      <a href={attachment.url} target="_blank" rel="noopener noreferrer" className="block mt-1.5">
        <img
          src={attachment.url}
          alt={attachment.filename}
          className="rounded-lg max-w-[280px] max-h-[200px] object-cover border border-zinc-700/50"
          loading="lazy"
        />
      </a>
    )
  }

  return (
    <a
      href={attachment.url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-2 mt-1.5 px-3 py-2 rounded-lg bg-zinc-800/60 border border-zinc-700/50 hover:bg-zinc-700/60 transition-colors max-w-[280px]"
    >
      <FileText className="w-4 h-4 text-zinc-400 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-xs text-zinc-300 truncate">{attachment.filename}</p>
        <p className="text-[10px] text-zinc-500">{formatFileSize(attachment.size)}</p>
      </div>
      <Download className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
    </a>
  )
}

export function MessageThread({ conversation, currentUserId, onSendMessage, onMarkRead, onBack }: Props) {
  const {
    draft,
    setDraft,
    pendingFiles,
    fileError,
    sending,
    muted,
    messagesEndRef,
    textareaRef,
    fileInputRef,
    getBlobUrl,
    addFiles,
    removeFile,
    handleSend,
    handleKeyDown,
    handleToggleMute,
    groupedMessages,
    displayTitle,
  } = useMessageThread({ conversation, currentUserId, onSendMessage, onMarkRead })

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
        {(() => {
          const other = conversation.participants.find((p) => p.user_id !== currentUserId)
          return other ? <Avatar name={other.name} avatarUrl={other.avatar_url} size="sm" /> : null
        })()}
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
                const sender = conversation.participants.find((p) => p.user_id === msg.sender_id)

                return (
                  <div
                    key={msg.id}
                    className={`flex ${isMine ? 'justify-end' : 'justify-start'}`}
                  >
                    {!isMine && (
                      <div className="mt-auto mr-2 shrink-0">
                        <Avatar name={msg.sender_name} avatarUrl={sender?.avatar_url} size="sm" />
                      </div>
                    )}
                    <div className={`max-w-[75%] ${isMine ? 'items-end' : 'items-start'}`}>
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
                        {msg.content && <p className="whitespace-pre-wrap break-words">{msg.content}</p>}
                        {msg.attachments?.length > 0 && (
                          <div className={`${msg.content ? 'mt-1.5' : ''} space-y-1.5`}>
                            {msg.attachments.map((att, i) => (
                              <AttachmentDisplay key={i} attachment={att} />
                            ))}
                          </div>
                        )}
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
        {/* Pending files */}
        {pendingFiles.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-2">
            {pendingFiles.map((f, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-800 border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300"
              >
                {f.type.startsWith('image/') ? (
                  <img
                    src={getBlobUrl(f)}
                    alt=""
                    className="w-5 h-5 rounded object-cover"
                  />
                ) : (
                  <FileText className="w-3.5 h-3.5 text-zinc-500" />
                )}
                <span className="max-w-[120px] truncate">{f.name}</span>
                <span className="text-zinc-500">{formatFileSize(f.size)}</span>
                <button
                  onClick={() => removeFile(i)}
                  className="text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        )}

        {fileError && (
          <p className="text-xs text-red-400 mb-1.5">{fileError}</p>
        )}

        <div className="flex items-end gap-2">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="shrink-0 rounded-xl p-2.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
            title="Attach files"
          >
            <Paperclip className="w-4 h-4" />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ALLOWED_EXTENSIONS.join(',')}
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.length) addFiles(e.target.files)
              e.target.value = ''
            }}
          />
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
            disabled={(!draft.trim() && pendingFiles.length === 0) || sending}
            className="shrink-0 rounded-xl bg-emerald-700 p-2.5 text-white hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
