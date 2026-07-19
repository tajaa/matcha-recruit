import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { UserPlus, Settings, Heart, BarChart2, Briefcase, LogOut } from 'lucide-react'
import {
  getChannel,
  joinChannel,
  leaveChannel,
  uploadChannelFiles,
  getChannelPaymentInfo,
  createChannelCheckout,
  deleteChannelMessage,
} from '../../api/channels'
import type { ChannelDetail, ChannelMessage, ChannelMember, ChannelAttachment, ChannelPaymentInfo } from '../../api/channels'
import { ChannelSocket } from '../../api/channelSocket'
import { useMe } from '../../../hooks/useMe'
import { listOpenPostings } from '../../api/channelJobPostings'
import type { OpenPostingSummary } from '../../api/channelJobPostings'
import { useLiveKitCall } from '../../hooks/useLiveKitCall'
import { useWorkBase, useWorkBrand } from '../../routes/WorkSurfaceContext'
import { handleFromEmail, detectMentionToken } from './mentions'
import { useChannelSocket } from './useChannelSocket'
import type { HeaderAction } from './types'

/**
 * @param channelIdOverride  Render a specific channel instead of the one in the
 *   route. Used by the collab project view, which embeds the project's own
 *   discussion channel at `/werk/projects/:projectId` — a path that has no
 *   `:channelId` param at all.
 * @param embedded  True when rendered inside another surface (the project view)
 *   rather than as the `/channels/:id` page. Suppresses actions that only make
 *   sense for a channel you navigated to on purpose — see `secondaryActions`.
 */
export function useChannelView(channelIdOverride?: string | null, embedded = false) {
  const { channelId: routeChannelId } = useParams<{ channelId: string }>()
  const channelId = channelIdOverride ?? routeChannelId
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

  useChannelSocket({
    channelId,
    isMember,
    userId,
    scrollToBottom,
    socketRef,
    messagesContainerRef,
    setMessages,
    setTypingUsers,
    setOnlineUsers,
  })

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

  const isOwner = channel?.my_role === 'owner'
  const isOwnerOrMod = !!channel?.my_role && ['owner', 'moderator'].includes(channel.my_role)
  const isPaid = !!paymentInfo?.is_paid
  const secondaryActions: HeaderAction[] = ([
    isOwnerOrMod && { key: 'add', icon: UserPlus, label: 'Add members', onClick: () => setShowAddMembers(true), hover: 'hover:text-w-accent' },
    ((isOwnerOrMod && isPaid) || (!isOwnerOrMod && isMember)) && { key: 'jobs', icon: Briefcase, label: 'Job postings', active: showJobPostings, onClick: () => { setShowJobPostings(!showJobPostings); setShowSettings(false); setShowAnalytics(false) }, hover: 'hover:text-w-accent' },
    isOwner && isPaid && { key: 'analytics', icon: BarChart2, label: 'Channel analytics', active: showAnalytics, onClick: () => { setShowAnalytics(!showAnalytics); setShowSettings(false); setShowJobPostings(false) }, hover: 'hover:text-w-accent' },
    isOwner && isPaid && { key: 'settings', icon: Settings, label: 'Channel settings', active: showSettings, onClick: () => { setShowSettings(!showSettings); setShowAnalytics(false); setShowJobPostings(false) }, hover: 'hover:text-w-accent' },
    !isOwner && isMember && { key: 'tip', icon: Heart, label: 'Send a tip', onClick: () => setShowTip(true), hover: 'hover:text-pink-400' },
    // NOT offered on the embedded project chat. The discussion channel is
    // created `visibility='private'`, and join_channel 403s private channels
    // (werk/routes/channels.py) — members are only ever added at channel
    // creation or on collaborator-accept. So "Leave", which reads like "close
    // this chat", would lock a collaborator out of their own project's primary
    // chat permanently, with no self-serve way back in.
    !isOwner && !embedded && { key: 'leave', icon: LogOut, label: 'Leave channel', onClick: handleLeave, hover: 'hover:text-red-400' },
  ].filter(Boolean) as HeaderAction[])

  return {
    channelId,
    navigate,
    base,
    brand,
    userId,
    channel,
    setChannel,
    messages,
    input,
    loading,
    error,
    typingUsers,
    onlineUsers,
    showMembers,
    setShowMembers,
    isMember,
    joining,
    showAddMembers,
    setShowAddMembers,
    pendingFiles,
    setPendingFiles,
    uploading,
    mentionQuery,
    mentionMatches,
    inputTextareaRef,
    paymentInfo,
    warningDismissed,
    setWarningDismissed,
    showSettings,
    setShowSettings,
    showAnalytics,
    setShowAnalytics,
    showTip,
    setShowTip,
    showJobPostings,
    setShowJobPostings,
    activePostingId,
    setActivePostingId,
    openPostings,
    showMobileActions,
    setShowMobileActions,
    fileInputRef,
    messagesEndRef,
    messagesContainerRef,
    voice,
    postingParam,
    canModerate,
    handleDeleteMessage,
    handleSend,
    applyMention,
    handleKeyDown,
    handleInputChange,
    handleJoin,
    typingText,
    secondaryActions,
  }
}
