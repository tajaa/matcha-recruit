import { useEffect, useRef, useState, useCallback } from 'react'
import type { Conversation, Participant } from '../../api/inbox'
import { toggleMute as apiToggleMute } from '../../api/inbox'

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10 MB
const MAX_FILE_COUNT = 5
export const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.pdf', '.txt', '.csv', '.doc', '.docx']

type Args = {
  conversation: Conversation
  currentUserId: string
  onSendMessage: (content: string, files?: File[]) => Promise<void>
  onMarkRead: () => void
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

export function useMessageThread({ conversation, currentUserId, onSendMessage, onMarkRead }: Args) {
  const [draft, setDraft] = useState('')
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const [fileError, setFileError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [muted, setMuted] = useState(() =>
    conversation.participants.find((p) => p.user_id === currentUserId)?.is_muted ?? false,
  )
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
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

  // Track blob URLs for cleanup
  const blobUrlsRef = useRef<string[]>([])

  // Clear pending files when conversation changes
  useEffect(() => {
    setPendingFiles([])
    setFileError(null)
    return () => {
      blobUrlsRef.current.forEach(URL.revokeObjectURL)
      blobUrlsRef.current = []
    }
  }, [conversation.id])

  function getBlobUrl(file: File): string {
    const url = URL.createObjectURL(file)
    blobUrlsRef.current.push(url)
    return url
  }

  function addFiles(newFiles: FileList | File[]) {
    setFileError(null)
    const incoming = Array.from(newFiles)

    // Validate count
    if (pendingFiles.length + incoming.length > MAX_FILE_COUNT) {
      setFileError(`Maximum ${MAX_FILE_COUNT} files per message`)
      return
    }

    // Validate each file
    for (const f of incoming) {
      if (f.size > MAX_FILE_SIZE) {
        setFileError(`${f.name} is too large (max 10 MB)`)
        return
      }
      const ext = '.' + f.name.split('.').pop()?.toLowerCase()
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        setFileError(`${f.name}: file type not supported`)
        return
      }
    }

    setPendingFiles((prev) => [...prev, ...incoming])
  }

  function removeFile(index: number) {
    setPendingFiles((prev) => prev.filter((_, i) => i !== index))
    setFileError(null)
  }

  async function handleSend() {
    const content = draft.trim()
    if (!content && pendingFiles.length === 0) return
    if (sending) return
    setSending(true)
    try {
      await onSendMessage(content, pendingFiles.length > 0 ? pendingFiles : undefined)
      setDraft('')
      setPendingFiles([])
      setFileError(null)
      blobUrlsRef.current.forEach(URL.revokeObjectURL)
      blobUrlsRef.current = []
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

  return {
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
  }
}
