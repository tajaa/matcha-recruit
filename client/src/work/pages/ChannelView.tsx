import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Hash, Users, Send, Loader2, LogIn, LogOut, UserPlus, Paperclip, X, FileText, Image as ImageIcon, Crown, Shield, Settings, Heart, Phone, BarChart2, Briefcase, Trash2, MoreHorizontal } from 'lucide-react'
import { getChannel, getChannelMessages, joinChannel, leaveChannel, uploadChannelFiles, kickMember, setMemberRole, getChannelPaymentInfo, createChannelCheckout, deleteChannelMessage } from '../api/channels'
import type { ChannelDetail, ChannelMessage, ChannelMember, ChannelAttachment, ChannelPaymentInfo } from '../api/channels'
import { ChannelSocket, getSharedChannelSocket } from '../api/channelSocket'
import { useMe } from '../../hooks/useMe'
import AddMembersModal from '../components/channels/AddMembersModal'
import PaidChannelJoinWizard from '../components/channels/PaidChannelJoinWizard'
import InactivityWarningBanner from '../components/channels/InactivityWarningBanner'
import ChannelSettingsPanel from '../components/channels/ChannelSettingsPanel'
import ChannelAnalytics from '../components/channels/ChannelAnalytics'
import TipModal from '../components/channels/TipModal'
import JobPostingsPanel from '../components/channels/JobPostingsPanel'
import JobPostingDetail from '../components/channels/JobPostingDetail'
import JobInviteBanner from '../components/channels/JobInviteBanner'
import ChannelOpenRoleBanner from '../components/channels/ChannelOpenRoleBanner'
import { listOpenPostings } from '../api/channelJobPostings'
import type { OpenPostingSummary } from '../api/channelJobPostings'
import VoiceCallBar from '../components/channels/VoiceCallBar'
import { useLiveKitCall } from '../hooks/useLiveKitCall'
import { useWorkBase, useWorkBrand } from '../routes/WorkSurfaceContext'

// @-mention rendering — splits message content into plain-text + mention-chip
// nodes. Server stamps `mentioned_user_ids` on the broadcast payload so we can
// confirm a handle resolved to a real channel member; unresolved `@foo`
// substrings render as plain text.
const MENTION_PATTERN = /(?:^|\s)(@[A-Za-z0-9._-]{2,32})\b/g

function handleFromEmail(email: string): string {
  return (email.split('@')[0] || '').toLowerCase()
}

function renderMessageContent(
  content: string,
  members: ChannelMember[],
  mentionedUserIds: string[] | undefined,
  currentUserId: string | undefined,
): React.ReactNode {
  if (!content) return null
  const validHandles = new Set(
    members
      .filter((m) => !mentionedUserIds || mentionedUserIds.includes(m.user_id))
      .map((m) => handleFromEmail(m.email || ''))
      .filter(Boolean),
  )
  const parts: React.ReactNode[] = []
  let lastIdx = 0
  for (const match of content.matchAll(MENTION_PATTERN)) {
    const fullMatch = match[0]
    const handleToken = match[1]
    const handle = handleToken.slice(1).toLowerCase()
    const idx = match.index ?? 0
    const tokenStart = idx + (fullMatch.length - handleToken.length)
    if (tokenStart > lastIdx) parts.push(content.slice(lastIdx, tokenStart))
    if (validHandles.has(handle)) {
      const mentioned = members.find((m) => handleFromEmail(m.email || '') === handle)
      const isMe = mentioned?.user_id === currentUserId
      parts.push(
        <span
          key={`m-${tokenStart}`}
          className={
            isMe
              ? 'inline-block px-1 rounded bg-yellow-500/25 text-yellow-200 font-medium'
              : 'inline-block px-1 rounded bg-w-accent/20 text-w-accent-hi font-medium'
          }
        >
          {handleToken}
        </span>,
      )
    } else {
      parts.push(handleToken)
    }
    lastIdx = idx + fullMatch.length
  }
  if (lastIdx < content.length) parts.push(content.slice(lastIdx))
  return parts
}

export default function ChannelView() {
  const { channelId } = useParams<{ channelId: string }>()
  const navigate = useNavigate()
  const { me } = useMe()
  const base = useWorkBase()
  const brand = useWorkBrand()
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
  const [mentionQuery, setMentionQuery] = useState<string | null>(null)
  const [mentionCursor, setMentionCursor] = useState(0)
  const inputTextareaRef = useRef<HTMLTextAreaElement>(null)
  const [paymentInfo, setPaymentInfo] = useState<ChannelPaymentInfo | null>(null)
  const [warningDismissed, setWarningDismissed] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showAnalytics, setShowAnalytics] = useState(false)
  const [showTip, setShowTip] = useState(false)
  const [showJobPostings, setShowJobPostings] = useState(false)
  const [activePostingId, setActivePostingId] = useState<string | null>(null)
  const [openPostings, setOpenPostings] = useState<OpenPostingSummary[]>([])
  const [showMobileActions, setShowMobileActions] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const socketRef = useRef<ChannelSocket | null>(null)
  const lastTypingSentRef = useRef(0)

  // Calls: unified on the LiveKit SFU across every surface (/work, /werk,
  // /werk-lite) — the homegrown WebRTC P2P mesh (useVoiceCall) is retired,
  // it silently failed cross-worker under uvicorn --workers 2.
  const voice = useLiveKitCall({
    channelId: channelId || null,
    enabled: true,
    members: channel?.members?.map((m) => ({ user_id: m.user_id, name: m.name })),
    onError: (m) => alert(m),
  })

  const postingParam = new URLSearchParams(window.location.search).get('posting')

  const myChannelRole = channel?.my_role ?? 'member'
  const canModerate = myChannelRole === 'owner' || myChannelRole === 'moderator'

  async function handleDeleteMessage(msg: ChannelMessage) {
    if (!channelId) return
    if (!window.confirm('Delete this message? This cannot be undone.')) return
    try {
      await deleteChannelMessage(channelId, msg.id)
      // Optimistic — the WebSocket event also arrives, but we don't wait.
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msg.id
            ? { ...m, content: '', attachments: [], deleted_at: new Date().toISOString(), deleted_by: userId ?? null }
            : m
        )
      )
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete message')
    }
  }

  useEffect(() => {
    if (postingParam) setActivePostingId(postingParam)
  }, [postingParam])

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

  // WebSocket connection — uses the process-wide shared socket so the global
  // notification listener and this view share one connection and one set of
  // joined rooms. We only subscribe to events; we don't disconnect on unmount.
  useEffect(() => {
    if (!channelId || !isMember) return

    const socket = getSharedChannelSocket()
    socketRef.current = socket

    const handleMessage = (msg: ChannelMessage) => {
      if (msg.channel_id !== channelId) return
      setMessages((prev) => {
        // Reconcile optimistic-pending entries first. The sender's own echo
        // carries the client_message_id we generated on send; replace the
        // pending row (whose `id` is the client UUID) with the server-
        // confirmed one so the row keeps its position but flips pending=false
        // and gets the real server id + timestamp.
        if (msg.client_message_id) {
          const idx = prev.findIndex(
            (m) => m.client_message_id === msg.client_message_id && m.pending,
          )
          if (idx >= 0) {
            const next = prev.slice()
            next[idx] = msg
            return next
          }
        }
        // Normal dedup by server id (reconnect replays, other senders).
        return prev.some((m) => m.id === msg.id) ? prev : [...prev, msg]
      })
      // Auto-scroll if near bottom
      const container = messagesContainerRef.current
      if (container) {
        const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 150
        if (nearBottom) setTimeout(scrollToBottom, 50)
      }
    }

    socket.addMessageListener(handleMessage)

    socket.onTyping = (user) => {
      if (user.id === userId) return
      setTypingUsers((prev) => {
        const next = new Map(prev)
        next.set(user.id, user.name)
        return next
      })
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
    socket.onMessageDeleted = (data) => {
      if (data.channel_id !== channelId) return
      setMessages((prev) =>
        prev.map((m) =>
          m.id === data.message_id
            ? { ...m, content: '', attachments: [], deleted_at: new Date().toISOString(), deleted_by: data.deleted_by }
            : m
        )
      )
    }

    socket.onMessageEdited = (data) => {
      if (data.channel_id !== channelId) return
      setMessages((prev) =>
        prev.map((m) =>
          m.id === data.message_id ? { ...m, content: data.content, edited_at: data.edited_at } : m
        )
      )
    }

    socket.onReactionUpdate = (data) => {
      if (data.channel_id !== channelId) return
      setMessages((prev) =>
        prev.map((m) => (m.id === data.message_id ? { ...m, reactions: data.reactions } : m))
      )
    }

    // Reconnect catch-up: onopen only fires on a genuine reconnect (not on
    // this effect's initial mount, since the shared socket is usually already
    // open) — refetch and merge by id so messages missed during the drop
    // aren't silently gone. Optimistic-pending sends not yet echoed are kept.
    socket.onConnected = () => {
      getChannelMessages(channelId)
        .then((fetched) => {
          setMessages((prev) => {
            const fetchedIds = new Set(fetched.map((m) => m.id))
            const stillPending = prev.filter((m) => m.pending && !fetchedIds.has(m.id))
            return [...fetched, ...stillPending]
          })
        })
        .catch(() => {})
    }

    // Global hook should already have joined this room, but joinRoom is
    // idempotent on the client and the server allows duplicate joins.
    socket.joinRoom(channelId)

    return () => {
      socket.removeMessageListener(handleMessage)
      // Null the singular handlers on the shared socket so this unmounted
      // component's state setters aren't held in stale closures.
      socket.onTyping = null
      socket.onOnlineUsers = null
      socket.onUserJoined = null
      socket.onUserLeft = null
      socket.onMessageDeleted = null
      socket.onMessageEdited = null
      socket.onReactionUpdate = null
      socket.onConnected = null
      socketRef.current = null
      // Do NOT call disconnect() or leaveRoom() — the shared socket persists.
    }
  }, [channelId, isMember, userId, scrollToBottom])

  // Fetch channel-wide (open-to-all) job postings so the banner can render
  // without a URL param. Refetches whenever the user opens / comes back to
  // the channel, and when they dismiss the detail view (in case they just
  // applied).
  useEffect(() => {
    if (!channelId || !isMember) {
      setOpenPostings([])
      return
    }
    listOpenPostings(channelId)
      .then(setOpenPostings)
      .catch(() => setOpenPostings([]))
  }, [channelId, isMember, activePostingId])

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

    const cmid = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `cmid-${Date.now()}-${Math.random().toString(36).slice(2)}`
    if (me?.user) {
      const optimistic: ChannelMessage = {
        id: cmid,
        channel_id: channelId,
        sender_id: me.user.id,
        sender_name: me.profile?.name ?? me.user.email,
        sender_avatar_url: me.user.avatar_url ?? null,
        content,
        attachments: attachments ?? [],
        created_at: new Date().toISOString(),
        edited_at: null,
        client_message_id: cmid,
        pending: true,
      }
      setMessages((prev) => {
        // Loopback race: WS echo may resolve before this updater runs. If a
        // message with our cmid is already present, don't append a duplicate.
        if (prev.some((m) => m.client_message_id === cmid)) return prev
        return [...prev, optimistic]
      })
      const container = messagesContainerRef.current
      if (container) {
        const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 150
        if (nearBottom) setTimeout(scrollToBottom, 50)
      }
    }
    socketRef.current?.sendMessage(channelId, content, attachments, cmid)
    setInput('')
  }

  // Autocomplete candidates for the active @-token. Empty when no token open.
  const mentionMatches: ChannelMember[] = (() => {
    if (mentionQuery === null || !channel) return []
    const q = mentionQuery.toLowerCase()
    return channel.members
      .filter((m) => m.user_id !== userId)
      .filter((m) => {
        const handle = handleFromEmail(m.email || '')
        const name = (m.name || '').toLowerCase()
        return handle.startsWith(q) || name.startsWith(q)
      })
      .slice(0, 6)
  })()

  function applyMention(member: ChannelMember) {
    const handle = handleFromEmail(member.email || '')
    if (!handle || mentionQuery === null) return
    // Replace the active "@partial" with "@handle " and place caret after.
    const head = input.slice(0, mentionCursor)
    const tail = input.slice(mentionCursor + mentionQuery.length)
    const replaced = head + handle + ' ' + tail
    setInput(replaced)
    setMentionQuery(null)
    requestAnimationFrame(() => {
      const ta = inputTextareaRef.current
      if (!ta) return
      ta.focus()
      const pos = head.length + handle.length + 1
      ta.setSelectionRange(pos, pos)
    })
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // When the mention dropdown is open, Tab/Enter selects the first match
    // and Escape closes it.
    if (mentionQuery !== null && mentionMatches.length > 0) {
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        applyMention(mentionMatches[0])
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setMentionQuery(null)
        return
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function detectMentionToken(value: string, caret: number): { query: string; tokenStart: number } | null {
    // Look back from caret to find the active @-token. A token starts at @ and
    // is preceded by start-of-string or whitespace. Stops at first whitespace.
    let i = caret - 1
    while (i >= 0 && !/\s/.test(value[i])) {
      if (value[i] === '@') {
        const before = i === 0 ? '' : value[i - 1]
        if (i === 0 || /\s/.test(before)) {
          return { query: value.slice(i + 1, caret), tokenStart: i + 1 }
        }
        return null
      }
      i--
    }
    return null
  }

  function handleInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const value = e.target.value
    setInput(value)
    const caret = e.target.selectionStart ?? value.length
    const token = detectMentionToken(value, caret)
    if (token && token.query.length <= 32 && /^[A-Za-z0-9._-]*$/.test(token.query)) {
      setMentionQuery(token.query)
      setMentionCursor(token.tokenStart)
    } else {
      setMentionQuery(null)
    }
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
      if (channel?.is_paid) {
        // Redirect to Stripe checkout for paid channels
        const { checkout_url } = await createChannelCheckout(channelId)
        window.location.href = checkout_url
        // Reset after 5s in case redirect fails (popup blocker, etc.)
        setTimeout(() => setJoining(false), 5000)
        return
      }
      await joinChannel(channelId)
      setIsMember(true)
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

  async function handleLeave() {
    if (!channelId) return
    try {
      await leaveChannel(channelId)
      navigate(base)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to leave channel')
    }
  }

  const typingText = Array.from(typingUsers.values()).join(', ')

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="animate-spin text-w-dim" size={24} />
      </div>
    )
  }

  // Not a member — show join prompt or invite-only message
  if (!isMember && !error) {
    // Paid channel — show payment gate
    if (paymentInfo?.is_paid) {
      return (
        <PaidChannelJoinWizard
          channelName={channel?.name ?? 'Channel'}
          channelDescription={channel?.description ?? null}
          memberCount={channel?.member_count ?? 0}
          priceCents={paymentInfo.price_cents ?? 0}
          currency={paymentInfo.currency ?? 'usd'}
          inactivityDays={paymentInfo.inactivity_threshold_days ?? null}
          cooldownUntil={paymentInfo.cooldown_until ?? null}
          canRejoin={paymentInfo.can_rejoin ?? true}
          onJoin={handleJoin}
          joining={joining}
          onBack={() => navigate(base)}
        />
      )
    }
    // Free channel — existing join prompt
    const isPublic = !channel?.visibility || channel.visibility === 'public'
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <Hash size={48} className="text-w-faint" />
        <p className="text-w-dim text-sm">
          {isPublic ? "You're not a member of this channel" : "This channel requires an invitation to join"}
        </p>
        {isPublic && (
          <button
            onClick={handleJoin}
            disabled={joining}
            className="flex items-center gap-2 px-4 py-2 bg-w-accent hover:bg-w-accent-hi text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            {joining ? <Loader2 size={14} className="animate-spin" /> : <LogIn size={14} />}
            Join Channel
          </button>
        )}
        <button onClick={() => navigate(base)} className="text-w-dim text-xs hover:text-w-text">
          Back to {brand}
        </button>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <p className="text-red-400 text-sm">{error}</p>
        <button onClick={() => navigate(base)} className="text-w-dim text-xs hover:text-w-text">
          Back to {brand}
        </button>
      </div>
    )
  }

  const isOwner = channel?.my_role === 'owner'
  const isOwnerOrMod = !!channel?.my_role && ['owner', 'moderator'].includes(channel.my_role)
  const isPaid = !!paymentInfo?.is_paid
  type HeaderAction = { key: string; icon: React.ElementType; label: string; onClick: () => void; active?: boolean; hover: string }
  const secondaryActions: HeaderAction[] = ([
    isOwnerOrMod && { key: 'add', icon: UserPlus, label: 'Add members', onClick: () => setShowAddMembers(true), hover: 'hover:text-w-accent' },
    ((isOwnerOrMod && isPaid) || (!isOwnerOrMod && isMember)) && { key: 'jobs', icon: Briefcase, label: 'Job postings', active: showJobPostings, onClick: () => { setShowJobPostings(!showJobPostings); setShowSettings(false); setShowAnalytics(false) }, hover: 'hover:text-w-accent' },
    isOwner && isPaid && { key: 'analytics', icon: BarChart2, label: 'Channel analytics', active: showAnalytics, onClick: () => { setShowAnalytics(!showAnalytics); setShowSettings(false); setShowJobPostings(false) }, hover: 'hover:text-w-accent' },
    isOwner && isPaid && { key: 'settings', icon: Settings, label: 'Channel settings', active: showSettings, onClick: () => { setShowSettings(!showSettings); setShowAnalytics(false); setShowJobPostings(false) }, hover: 'hover:text-w-accent' },
    !isOwner && isMember && { key: 'tip', icon: Heart, label: 'Send a tip', onClick: () => setShowTip(true), hover: 'hover:text-pink-400' },
    !isOwner && { key: 'leave', icon: LogOut, label: 'Leave channel', onClick: handleLeave, hover: 'hover:text-red-400' },
  ].filter(Boolean) as HeaderAction[])

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-w-line shrink-0">
        <Hash size={18} className="text-w-accent shrink-0" />
        <div className="flex-1 min-w-0">
          <h2 className="text-white font-semibold truncate flex items-center gap-1.5">
            {channel?.name}
            {paymentInfo?.is_paid && (
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-w-accent/15 text-w-accent">$</span>
            )}
          </h2>
          {channel?.description && (
            <p className="text-xs text-w-dim truncate">{channel.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {onlineUsers.length > 0 && (
            <span className="hidden sm:flex items-center gap-1 text-xs text-w-dim">
              <span className="w-2 h-2 bg-w-accent rounded-full" />
              {onlineUsers.length} online
            </span>
          )}
          {/* Primary actions — always inline */}
          <button
            onClick={() => setShowMembers(!showMembers)}
            className={`p-1.5 rounded hover:bg-w-surface2 ${showMembers ? 'text-w-accent' : 'text-w-dim'}`}
            title="Members"
          >
            <Users size={16} />
          </button>
          {isMember && (
            <button
              onClick={voice.callState === 'idle' ? voice.joinCall : undefined}
              className="p-1.5 rounded hover:bg-w-surface2 text-w-dim hover:text-w-accent"
              title="Voice call"
            >
              <Phone size={16} />
            </button>
          )}
          {/* Secondary actions — inline on desktop */}
          <div className="hidden sm:flex items-center gap-2">
            {secondaryActions.map((a) => (
              <button
                key={a.key}
                onClick={a.onClick}
                className={`p-1.5 rounded hover:bg-w-surface2 ${a.hover} ${a.active ? 'text-w-accent' : 'text-w-dim'}`}
                title={a.label}
              >
                <a.icon size={16} />
              </button>
            ))}
          </div>
          {/* Secondary actions — kebab dropdown on mobile */}
          {secondaryActions.length > 0 && (
            <div className="relative sm:hidden">
              <button
                onClick={() => setShowMobileActions((v) => !v)}
                className={`p-1.5 rounded hover:bg-w-surface2 ${showMobileActions ? 'text-w-accent' : 'text-w-dim'}`}
                title="More"
              >
                <MoreHorizontal size={18} />
              </button>
              {showMobileActions && (
                <>
                  <div className="fixed inset-0 z-20" onClick={() => setShowMobileActions(false)} />
                  <div className="absolute right-0 top-full mt-1 z-30 min-w-[180px] py-1 bg-w-surface border border-w-line rounded-lg shadow-xl">
                    {secondaryActions.map((a) => (
                      <button
                        key={a.key}
                        onClick={() => { a.onClick(); setShowMobileActions(false) }}
                        className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left hover:bg-w-surface2 ${a.active ? 'text-w-accent' : 'text-w-text'} ${a.hover}`}
                      >
                        <a.icon size={16} className="shrink-0" />
                        <span className="flex-1">{a.label}</span>
                        {a.active && <span className="w-1.5 h-1.5 rounded-full bg-w-accent shrink-0" />}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {paymentInfo?.days_until_removal != null && paymentInfo.days_until_removal <= (paymentInfo.inactivity_warning_days ?? 3) && !warningDismissed && (
        <InactivityWarningBanner
          daysUntilRemoval={Math.ceil(paymentInfo.days_until_removal)}
          onDismiss={() => setWarningDismissed(true)}
        />
      )}

      {isMember && paymentInfo?.is_paid && (
        <div className="flex items-center gap-4 px-4 py-1.5 border-b border-w-line/50 bg-w-surface/60 text-xs text-w-dim">
          <span className="text-w-accent font-medium">${((paymentInfo.price_cents ?? 0) / 100).toFixed(2)}/mo</span>
          <span>{channel?.member_count ?? 0} members</span>
          {onlineUsers.length > 0 && <span>{onlineUsers.length} online</span>}
          {paymentInfo.subscription_status === 'active' && (
            <button
              onClick={() => navigate(`${base}/billing`)}
              className="ml-auto text-w-faint"
            >
              Manage subscription
            </button>
          )}
        </div>
      )}

      {(voice.callState !== 'idle' || voice.participants.length > 0) && (
        <VoiceCallBar
          callState={voice.callState}
          participants={voice.participants}
          isMuted={voice.isMuted}
          isVideoEnabled={voice.isVideoEnabled}
          elapsedSeconds={voice.elapsedSeconds}
          localStream={voice.localStream}
          onJoin={voice.joinCall}
          onLeave={voice.leaveCall}
          onToggleMute={voice.toggleMute}
          onToggleVideo={voice.toggleVideo}
          activeCallUsers={voice.participants.map(p => ({ user_id: p.userId, name: p.name }))}
        />
      )}

      {postingParam && !activePostingId && channelId && (
        <JobInviteBanner
          channelId={channelId}
          postingId={postingParam}
          onView={() => setActivePostingId(postingParam)}
        />
      )}

      {openPostings.length > 0 && !activePostingId && (
        <ChannelOpenRoleBanner
          postings={openPostings}
          onView={(id) => setActivePostingId(id)}
        />
      )}

      <div className="flex flex-1 min-h-0">
        {/* Messages */}
        <div className="flex-1 flex flex-col min-w-0">
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
                          channel?.members ?? [],
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
                      onClick={() => handleDeleteMessage(msg)}
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

          {/* Typing indicator */}
          {typingText && (
            <div className="px-4 pb-1 text-xs text-w-dim italic">
              {typingText} {typingUsers.size === 1 ? 'is' : 'are'} typing...
            </div>
          )}

          {/* Input */}
          <div className="px-4 py-3 border-t border-w-line shrink-0">
            {/* Pending file previews */}
            {pendingFiles.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2">
                {pendingFiles.map((f, i) => (
                  <div key={i} className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-w-surface2 border border-w-line text-xs text-w-text">
                    {f.type.startsWith('image/') ? <ImageIcon size={11} /> : <FileText size={11} />}
                    <span className="truncate max-w-[150px]">{f.name}</span>
                    <button onClick={() => setPendingFiles(prev => prev.filter((_, j) => j !== i))} className="text-w-dim hover:text-w-text">
                      <X size={10} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex items-end gap-2">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="p-2 text-w-dim hover:text-w-text transition-colors shrink-0"
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
              <div className="flex-1 relative">
                {mentionQuery !== null && mentionMatches.length > 0 && (
                  <div className="absolute bottom-full left-0 mb-1 w-full max-w-xs bg-w-surface border border-w-line rounded-lg shadow-xl z-20 overflow-hidden">
                    <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-w-dim border-b border-w-line">
                      Mention a member
                    </div>
                    {mentionMatches.map((m, i) => {
                      const handle = handleFromEmail(m.email || '')
                      return (
                        <button
                          key={m.user_id}
                          type="button"
                          onMouseDown={(e) => { e.preventDefault(); applyMention(m) }}
                          className={`w-full text-left px-3 py-1.5 text-sm flex items-center justify-between hover:bg-w-surface2 ${i === 0 ? 'bg-w-surface2/60' : ''}`}
                        >
                          <span className="text-w-text truncate">{m.name}</span>
                          <span className="text-w-accent text-xs ml-2 shrink-0">@{handle}</span>
                        </button>
                      )
                    })}
                  </div>
                )}
                <textarea
                  ref={inputTextareaRef}
                  value={input}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  placeholder={`Message #${channel?.name ?? 'channel'}...`}
                  rows={1}
                  className="w-full px-3 py-2 bg-w-surface2 border border-w-line rounded-lg text-white text-sm placeholder:text-w-dim focus:outline-none focus:border-w-accent resize-none max-h-32"
                  style={{ minHeight: '38px' }}
                />
              </div>
              <button
                onClick={handleSend}
                disabled={(!input.trim() && pendingFiles.length === 0) || uploading}
                className="p-2 bg-w-accent hover:bg-w-accent-hi text-white rounded-lg transition-colors disabled:opacity-30 shrink-0"
              >
                {uploading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
              </button>
            </div>
          </div>
        </div>

        {/* Members sidebar */}
        {showMembers && (
          <div className="w-64 border-l border-w-line overflow-y-auto px-3 py-3 hidden sm:block">
            <h3 className="text-xs font-medium text-w-dim uppercase mb-2">
              Members ({channel?.member_count ?? 0})
            </h3>
            <div className="space-y-0.5">
              {channel?.members.map((m: ChannelMember) => {
                const isOnline = onlineUsers.some((u) => u.id === m.user_id)
                const canManage = channel.my_role === 'owner' || (channel.my_role === 'moderator' && m.channel_role === 'member')
                const isMe = m.user_id === userId
                return (
                  <div key={m.user_id} className="group flex items-center gap-2 py-1.5 px-1 rounded hover:bg-w-surface2/50">
                    <span className={`w-2 h-2 rounded-full shrink-0 ${isOnline ? 'bg-w-accent' : 'bg-w-surface2'}`} />
                    <span className="text-sm text-w-text truncate flex-1">{m.name}</span>
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
                            className="p-0.5 text-w-dim hover:text-blue-400"
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
                          className="p-0.5 text-w-dim hover:text-red-400"
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

      {showAnalytics && channel && (
        <ChannelAnalytics
          channelId={channel.id}
          channelName={channel.name}
          onClose={() => setShowAnalytics(false)}
        />
      )}

      {showTip && channel && (
        <TipModal
          channelId={channel.id}
          channelName={channel.name}
          onClose={() => setShowTip(false)}
        />
      )}

      {showJobPostings && channel && (
        <JobPostingsPanel
          channelId={channel.id}
          myRole={channel.my_role ?? 'member'}
          onClose={() => setShowJobPostings(false)}
          onOpenDetail={(id) => { setActivePostingId(id); setShowJobPostings(false) }}
        />
      )}

      {activePostingId && channel && (
        <JobPostingDetail
          channelId={channel.id}
          postingId={activePostingId}
          myRole={channel.my_role ?? 'member'}
          onClose={() => setActivePostingId(null)}
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
