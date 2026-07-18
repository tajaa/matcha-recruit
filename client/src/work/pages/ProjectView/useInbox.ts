import { useEffect, useState, useCallback } from 'react'
import { listConversations, getUnreadCount } from '../../api/inbox'
import type { ConversationSummary, Conversation } from '../../api/inbox'

/**
 * Inbox (DM) state for the project view sidebar: conversation list, active
 * conversation, unread badge, compose modal. The unread count polls every 60s;
 * the list (re)loads whenever the sidebar switches into inbox mode.
 */
export function useInbox(sidebarMode: 'chats' | 'inbox') {
  const [inboxConversations, setInboxConversations] = useState<ConversationSummary[]>([])
  const [inboxActiveConvo, setInboxActiveConvo] = useState<Conversation | null>(null)
  const [inboxLoading, setInboxLoading] = useState(false)
  const [inboxUnread, setInboxUnread] = useState(0)
  const [inboxComposeOpen, setInboxComposeOpen] = useState(false)

  const loadInbox = useCallback(async () => {
    setInboxLoading(true)
    try {
      const data = await listConversations()
      setInboxConversations(data)
    } catch {}
    setInboxLoading(false)
  }, [])

  useEffect(() => {
    getUnreadCount().then((r) => setInboxUnread(r.count)).catch(() => {})
    const id = setInterval(() => {
      getUnreadCount().then((r) => setInboxUnread(r.count)).catch(() => {})
    }, 60_000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    if (sidebarMode === 'inbox') loadInbox()
  }, [sidebarMode, loadInbox])

  return {
    inboxConversations,
    setInboxConversations,
    inboxActiveConvo,
    setInboxActiveConvo,
    inboxLoading,
    inboxUnread,
    inboxComposeOpen,
    setInboxComposeOpen,
    loadInbox,
  }
}
