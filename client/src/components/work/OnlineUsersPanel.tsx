import { useState } from 'react'
import { Users, X, Send, MessageSquare } from 'lucide-react'
import { useOnlineUsers } from '../../hooks/useOnlineUsers'
import { createConversation } from '../../api/inbox'
import Avatar from '../shared/Avatar'

export function OnlineUsersPanel() {
  const { users, loading } = useOnlineUsers()
  const [open, setOpen] = useState(false)
  const [chatTarget, setChatTarget] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState<string | null>(null)

  async function handleSend(userId: string) {
    if (!message.trim() || sending) return
    setSending(true)
    try {
      await createConversation([userId], message.trim())
      setSent(userId)
      setMessage('')
      setChatTarget(null)
      setTimeout(() => setSent(null), 3000)
    } catch {}
    setSending(false)
  }

  const count = users.length

  return (
    <div className="relative">
      {/* Inline trigger */}
      <button
        onClick={() => setOpen(!open)}
        className="relative flex items-center gap-1.5 text-sm text-w-dim hover:text-white transition-colors"
      >
        <div className="relative">
          <Users className="w-4 h-4" />
          {count > 0 && (
            <div className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-w-accent text-[7px] font-bold text-white flex items-center justify-center">
              {count}
            </div>
          )}
        </div>
        <span className="hidden sm:inline text-xs">
          {count > 0 ? `${count} online` : 'Online'}
        </span>
      </button>

      {/* Panel */}
      {open && (
        <div className="absolute top-full right-0 mt-2 z-40 w-72 bg-w-surface border border-w-line rounded-xl shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-w-line">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-w-accent animate-pulse" />
              <span className="text-xs font-medium text-w-text">Online Now</span>
            </div>
            <button onClick={() => setOpen(false)} className="text-w-dim hover:text-w-text transition-colors">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* User list */}
          <div className="max-h-80 overflow-y-auto">
            {loading && (
              <div className="px-4 py-6 text-center text-xs text-w-dim animate-pulse">Loading...</div>
            )}

            {!loading && count === 0 && (
              <div className="px-4 py-6 text-center">
                <p className="text-xs text-w-dim">No one else online right now</p>
              </div>
            )}

            {!loading && users.map((user) => (
              <div key={user.id} className="px-3 py-2 hover:bg-w-surface2/50 transition-colors">
                <div className="flex items-center gap-2.5">
                  <div className="relative">
                    <Avatar name={user.name} avatarUrl={user.avatar_url} size="sm" />
                    <div className="absolute bottom-0 right-0 w-2 h-2 rounded-full bg-w-accent ring-2 ring-w-line" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-w-text truncate">{user.name}</p>
                    <p className="text-[10px] text-w-dim">Active now</p>
                  </div>
                  {sent === user.id ? (
                    <span className="text-[10px] text-w-accent">Sent!</span>
                  ) : (
                    <button
                      onClick={() => setChatTarget(chatTarget === user.id ? null : user.id)}
                      className="text-w-dim hover:text-w-text transition-colors p-1"
                      title="Send message"
                    >
                      <MessageSquare className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                {/* Inline message input */}
                {chatTarget === user.id && (
                  <div className="flex items-center gap-1.5 mt-2 ml-9">
                    <input
                      type="text"
                      value={message}
                      onChange={(e) => setMessage(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') handleSend(user.id) }}
                      placeholder="Say hi..."
                      autoFocus
                      className="flex-1 rounded-lg border border-w-line bg-w-surface2 px-2.5 py-1.5 text-xs text-w-text placeholder-w-faint outline-none focus:border-w-line"
                    />
                    <button
                      onClick={() => handleSend(user.id)}
                      disabled={!message.trim() || sending}
                      className="shrink-0 rounded-lg bg-w-accent p-1.5 text-white hover:bg-w-accent-hi disabled:opacity-40 transition-colors"
                    >
                      <Send className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
