import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Hash, Users, Send, Loader2, LogIn, LogOut, UserPlus, Paperclip, X, FileText, Image as ImageIcon, Crown, Shield, Settings } from 'lucide-react'
import { getChannel, joinChannel, leaveChannel, uploadChannelFiles, kickMember, setMemberRole, getChannelPaymentInfo, createChannelCheckout } from '../../api/channels'
import type { ChannelDetail, ChannelMessage, ChannelMember, ChannelAttachment, ChannelPaymentInfo } from '../../api/channels'
import { ChannelSocket } from '../../api/channelSocket'
import { useMe } from '../../hooks/useMe'
import AddMembersModal from '../../components/channels/AddMembersModal'
import PaidChannelGate from '../../components/channels/PaidChannelGate'
import InactivityWarningBanner from '../../components/channels/InactivityWarningBanner'
import ChannelSettingsPanel from '../../components/channels/ChannelSettingsPanel'

export default function ChannelView() {
  const { channelId } = useParams<{ channelId: string }>()
  const navigate = useNavigate()
  const { me } = useMe()
  const userId = me?.user?.id

  const [channel, setChannel] = useState<ChannelDetail | null>(null)
  const [messages, setMessages] = useState<ChannelMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [typingUsers, setTypingUsers] = useState<Map<string, string>>(new Map())
  const [onlineUsers, setOnlineUsers] = useState<{ id: string; name: string; avatar_url: string | null }[]>([])
  const [showMembers, setShowMembers] = useState(false)
  const [isMember, setIsMember] = useState(false)
  const [joining, setJoining] = useState(false)
  const [showAddMembers, setShowAddMembers] = useState(false)
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [paymentInfo, setPaymentInfo] = useState<ChannelPaymentInfo | null>(null)
  const [checkingOut, setCheckingOut] = useState(false)
  const [warningDismissed, setWarningDismissed] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const socketRef = useRef<ChannelSocket | null>(null)
  const lastTypingSentRef = useRef(0)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  // Load channel data
  useEffect(() => {
    if (!channelId) return
    setLoading(true)
    setError('')
    getChannel(channelId)
      .then((data) => {
        setChannel(data)
        setMessages(data.messages)
        setIsMember(data.is_member)
        if (data.is_member) setTimeout(scrollToBottom, 100)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to load channel')
      })
      .finally(() => setLoading(false))
  }, [channelId, scrollToBottom])

  // Load payment info
  useEffect(() => {
    if (!channelId) return
    getChannelPaymentInfo(channelId).then(setPaymentInfo).catch(() => {})
  }, [channelId])

  // WebSocket connection
  useEffect(() => {
    if (!channelId || !isMember) return

    const socket = new ChannelSocket()
    socketRef.current = socket

    socket.onMessage = (msg) => {
      setMessages((prev) => [...prev, msg])
      // Auto-scroll if near bottom
      const container = messagesContainerRef.current
      if (container) {
        const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 150
        if (nearBottom) setTimeout(scrollToBottom, 50)
      }
    }

    socket.onTyping = (user) => {
      if (user.id === userId) return
      setTypingUsers((prev) => {
        const next = new Map(prev)
        next.set(user.id, user.name)
        return next
      })
      // Clear after 3s
      setTimeout(() => {
        setTypingUsers((prev) => {
          const next = new Map(prev)
          next.delete(user.id)
          return next
        })
      }, 3000)
    }

    socket.onOnlineUsers = (users) => setOnlineUsers(users)
    socket.onUserJoined = (user) => {
      setOnlineUsers((prev) => prev.some((u) => u.id === user.id) ? prev : [...prev, { ...user, avatar_url: null }])
    }
    socket.onUserLeft = (user) => {
      setOnlineUsers((prev) => prev.filter((u) => u.id !== user.id))
    }

    socket.connect()
    // Small delay for WS to open before joining room
    const joinTimer = setTimeout(() => socket.joinRoom(channelId), 500)

    return () => {
      clearTimeout(joinTimer)
      socket.leaveRoom(channelId)
      socket.disconnect()
      socketRef.current = null
    }
  }, [channelId, isMember, userId, scrollToBottom])

  async function handleSend() {
    const content = input.trim()
    if ((!content && pendingFiles.length === 0) || !channelId) return

    let attachments: ChannelAttachment[] | undefined
    if (pendingFiles.length > 0) {
      setUploading(true)
      try {
        attachments = await uploadChannelFiles(channelId, pendingFiles)
      } catch {
        setUploading(false)
        return
      }
      setUploading(false)
      setPendingFiles([])
    }

    socketRef.current?.sendMessage(channelId, content, attachments)
    setInput('')
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value)
    // Throttle typing indicator to once per 2s
    if (channelId && Date.now() - lastTypingSentRef.current > 2000) {
      socketRef.current?.sendTyping(channelId)
      lastTypingSentRef.current = Date.now()
    }
  }

  async function handleJoin() {
    if (!channelId) return
    setJoining(true)
    try {
      await joinChannel(channelId)
      setIsMember(true)
      // Reload channel data
      const data = await getChannel(channelId)
      setChannel(data)
      setMessages(data.messages)
      setTimeout(scrollToBottom, 100)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to join')
    } finally {
      setJoining(false)
    }
  }

  async function handleCheckout() {
    if (!channelId) return
    setCheckingOut(true)
    try {
      const { checkout_url } = await createChannelCheckout(channelId)
      window.location.href = checkout_url
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Checkout failed')
      setCheckingOut(false)
    }
  }

  async function handleLeave() {
    if (!channelId) return
    try {
      await leaveChannel(channelId)
      navigate('/work')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to leave channel')
    }
  }

  const typingText = Array.from(typingUsers.values()).join(', ')

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="animate-spin text-zinc-500" size={24} />
      </div>
    )
  }

  // Not a member — show join prompt or invite-only message
  if (!isMember && !error) {
    // Paid channel — show payment gate
    if (paymentInfo?.is_paid) {
      return (
        <div className="flex items-center justify-center h-full">
          <PaidChannelGate
            channelName={channel?.name ?? 'Channel'}
            priceCents={paymentInfo.price_cents ?? 0}
            currency={paymentInfo.currency ?? 'usd'}
            inactivityDays={paymentInfo.inactivity_threshold_days ?? null}
            cooldownUntil={paymentInfo.cooldown_until ?? null}
            canRejoin={paymentInfo.can_rejoin ?? true}
            onCheckout={handleCheckout}
            checkingOut={checkingOut}
            onBack={() => navigate('/work')}
          />
        </div>
      )
    }
    // Free channel — existing join prompt
    const isPublic = !channel?.visibility || channel.visibility === 'public'
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <Hash size={48} className="text-zinc-600" />
        <p className="text-zinc-400 text-sm">
          {isPublic ? "You're not a member of this channel" : "This channel requires an invitation to join"}
        </p>
        {isPublic && (
          <button
            onClick={handleJoin}
            disabled={joining}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            {joining ? <Loader2 size={14} className="animate-spin" /> : <LogIn size={14} />}
            Join Channel
          </button>
        )}
        <button onClick={() => navigate('/work')} className="text-zinc-500 text-xs hover:text-zinc-300">
          Back to Matcha Work
        </button>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <p className="text-red-400 text-sm">{error}</p>
        <button onClick={() => navigate('/work')} className="text-zinc-500 text-xs hover:text-zinc-300">
          Back to Matcha Work
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-800 shrink-0">
        <button onClick={() => navigate('/work')} className="text-zinc-500 hover:text-white sm:hidden">
          <ArrowLeft size={18} />
        </button>
        <Hash size={18} className="text-emerald-500 shrink-0" />
        <div className="flex-1 min-w-0">
          <h2 className="text-white font-semibold truncate flex items-center gap-1.5">
            {channel?.name}
            {paymentInfo?.is_paid && (
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-600/20 text-emerald-400">$</span>
            )}
          </h2>
          {channel?.description && (
            <p className="text-xs text-zinc-500 truncate">{channel.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {onlineUsers.length > 0 && (
            <span className="flex items-center gap-1 text-xs text-zinc-500">
              <span className="w-2 h-2 bg-emerald-500 rounded-full" />
              {onlineUsers.length} online
            </span>
          )}
          {channel?.my_role && ['owner', 'moderator'].includes(channel.my_role) && (
            <button
              onClick={() => setShowAddMembers(true)}
              className="p-1.5 rounded hover:bg-zinc-800 text-zinc-500 hover:text-emerald-400"
              title="Add members"
            >
              <UserPlus size={16} />
            </button>
          )}
          {channel?.my_role === 'owner' && paymentInfo?.is_paid && (
            <button
              onClick={() => setShowSettings(!showSettings)}
              className={`p-1.5 rounded hover:bg-zinc-800 ${showSettings ? 'text-emerald-400' : 'text-zinc-500'}`}
              title="Channel settings"
            >
              <Settings size={16} />
            </button>
          )}
          <button
            onClick={() => setShowMembers(!showMembers)}
            className={`p-1.5 rounded hover:bg-zinc-800 ${showMembers ? 'text-emerald-400' : 'text-zinc-500'}`}
            title="Members"
          >
            <Users size={16} />
          </button>
          {channel?.my_role !== 'owner' && (
            <button
              onClick={handleLeave}
              className="p-1.5 rounded hover:bg-zinc-800 text-zinc-500 hover:text-red-400"
              title="Leave channel"
            >
              <LogOut size={16} />
            </button>
          )}
        </div>
      </div>

      {paymentInfo?.days_until_removal != null && paymentInfo.days_until_removal <= (paymentInfo.inactivity_warning_days ?? 3) && !warningDismissed && (
        <InactivityWarningBanner
          daysUntilRemoval={Math.ceil(paymentInfo.days_until_removal)}
          onDismiss={() => setWarningDismissed(true)}
        />
      )}

      <div className="flex flex-1 min-h-0">
        {/* Messages */}
        <div className="flex-1 flex flex-col min-w-0">
          <div ref={messagesContainerRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-1">
            {messages.length === 0 && (
              <div className="text-center py-12 text-zinc-600 text-sm">
                No messages yet. Start the conversation!
              </div>
            )}
            {messages.map((msg, i) => {
              const showAuthor = i === 0 || messages[i - 1].sender_id !== msg.sender_id
              const isOwn = msg.sender_id === userId
              return (
                <div key={msg.id} className={`${showAuthor && i > 0 ? 'mt-3' : ''}`}>
                  {showAuthor && (
                    <div className="flex items-baseline gap-2 mb-0.5">
                      <span className={`text-sm font-medium ${isOwn ? 'text-emerald-400' : 'text-blue-400'}`}>
                        {msg.sender_name}
                      </span>
                      <span className="text-[10px] text-zinc-600">
                        {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  )}
                  {msg.content && (
                    <p className="text-sm text-zinc-200 whitespace-pre-wrap break-words pl-0">
                      {msg.content}
                    </p>
                  )}
                  {msg.attachments && msg.attachments.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-1">
                      {msg.attachments.map((att, ai) =>
                        att.content_type.startsWith('image/') ? (
                          <a key={ai} href={att.url} target="_blank" rel="noopener noreferrer">
                            <img src={att.url} alt={att.filename} className="max-w-xs max-h-48 rounded-md border border-zinc-700" />
                          </a>
                        ) : (
                          <a
                            key={ai}
                            href={att.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-zinc-800 border border-zinc-700 text-xs text-zinc-300 hover:text-white hover:border-zinc-600 transition-colors"
                          >
                            <FileText size={12} className="shrink-0" />
                            <span className="truncate max-w-[200px]">{att.filename}</span>
                            <span className="text-zinc-500 shrink-0">
                              {att.size >= 1_000_000 ? `${(att.size / 1_000_000).toFixed(1)}MB` : `${Math.round(att.size / 1_000)}KB`}
                            </span>
                          </a>
                        )
                      )}
                    </div>
                  )}
                </div>
              )
            })}
            <div ref={messagesEndRef} />
          </div>

          {/* Typing indicator */}
          {typingText && (
            <div className="px-4 pb-1 text-xs text-zinc-500 italic">
              {typingText} {typingUsers.size === 1 ? 'is' : 'are'} typing...
            </div>
          )}

          {/* Input */}
          <div className="px-4 py-3 border-t border-zinc-800 shrink-0">
            {/* Pending file previews */}
            {pendingFiles.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2">
                {pendingFiles.map((f, i) => (
                  <div key={i} className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-zinc-800 border border-zinc-700 text-xs text-zinc-300">
                    {f.type.startsWith('image/') ? <ImageIcon size={11} /> : <FileText size={11} />}
                    <span className="truncate max-w-[150px]">{f.name}</span>
                    <button onClick={() => setPendingFiles(prev => prev.filter((_, j) => j !== i))} className="text-zinc-500 hover:text-zinc-300">
                      <X size={10} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex items-end gap-2">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="p-2 text-zinc-500 hover:text-zinc-300 transition-colors shrink-0"
                title="Attach files"
              >
                <Paperclip size={16} />
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                hidden
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? [])
                  if (files.length) setPendingFiles(prev => [...prev, ...files].slice(0, 5))
                  e.target.value = ''
                }}
              />
              <textarea
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder={`Message #${channel?.name ?? 'channel'}...`}
                rows={1}
                className="flex-1 px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600 resize-none max-h-32"
                style={{ minHeight: '38px' }}
              />
              <button
                onClick={handleSend}
                disabled={(!input.trim() && pendingFiles.length === 0) || uploading}
                className="p-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition-colors disabled:opacity-30 shrink-0"
              >
                {uploading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
              </button>
            </div>
          </div>
        </div>

        {/* Members sidebar */}
        {showMembers && (
          <div className="w-64 border-l border-zinc-800 overflow-y-auto px-3 py-3 hidden sm:block">
            <h3 className="text-xs font-medium text-zinc-500 uppercase mb-2">
              Members ({channel?.member_count ?? 0})
            </h3>
            <div className="space-y-0.5">
              {channel?.members.map((m: ChannelMember) => {
                const isOnline = onlineUsers.some((u) => u.id === m.user_id)
                const canManage = channel.my_role === 'owner' || (channel.my_role === 'moderator' && m.channel_role === 'member')
                const isMe = m.user_id === userId
                return (
                  <div key={m.user_id} className="group flex items-center gap-2 py-1.5 px-1 rounded hover:bg-zinc-800/30">
                    <span className={`w-2 h-2 rounded-full shrink-0 ${isOnline ? 'bg-emerald-500' : 'bg-zinc-600'}`} />
                    <span className="text-sm text-zinc-300 truncate flex-1">{m.name}</span>
                    {m.channel_role === 'owner' && (
                      <Crown size={12} className="text-amber-500 shrink-0" aria-label="Owner" />
                    )}
                    {m.channel_role === 'moderator' && (
                      <Shield size={12} className="text-blue-400 shrink-0" aria-label="Moderator" />
                    )}
                    {!isMe && canManage && (
                      <div className="opacity-0 group-hover:opacity-100 flex items-center gap-0.5 shrink-0">
                        {channel.my_role === 'owner' && m.channel_role !== 'owner' && (
                          <button
                            onClick={async () => {
                              try {
                                const newRole = m.channel_role === 'moderator' ? 'member' : 'moderator'
                                await setMemberRole(channel.id, m.user_id, newRole)
                                const data = await getChannel(channel.id)
                                setChannel(data)
                              } catch {}
                            }}
                            className="p-0.5 text-zinc-500 hover:text-blue-400"
                            title={m.channel_role === 'moderator' ? 'Remove moderator' : 'Make moderator'}
                          >
                            <Shield size={11} />
                          </button>
                        )}
                        <button
                          onClick={async () => {
                            try {
                              await kickMember(channel.id, m.user_id)
                              const data = await getChannel(channel.id)
                              setChannel(data)
                            } catch {}
                          }}
                          className="p-0.5 text-zinc-500 hover:text-red-400"
                          title="Remove from channel"
                        >
                          <X size={11} />
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {showSettings && channel && (
        <ChannelSettingsPanel
          channelId={channel.id}
          channelName={channel.name}
          isPaid={paymentInfo?.is_paid ?? false}
          onClose={() => setShowSettings(false)}
        />
      )}

      {showAddMembers && channel && (
        <AddMembersModal
          channelId={channel.id}
          channelName={channel.name}
          existingMemberIds={channel.members.map((m) => m.user_id)}
          onClose={() => setShowAddMembers(false)}
          onAdded={async () => {
            setShowAddMembers(false)
            // Refresh channel to update member list
            if (channelId) {
              const data = await getChannel(channelId)
              setChannel(data)
            }
          }}
        />
      )}
    </div>
  )
}
