import { useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { getSharedChannelSocket } from '../api/channelSocket'
import { listChannels, type ChannelMessage, type ChannelSummary } from '../api/channels'
import { useToast } from '../components/ui/Toast'
import { useMe } from './useMe'
import { getChannelSoundEnabled, getChannelToastEnabled } from './useNotificationSettings'
import { playNotificationSound } from '../utils/notificationSound'

/**
 * Mount once at the top of WorkLayout. Owns:
 * - Subscribing to the shared ChannelSocket
 * - Joining every channel the current user is a member of (so the server
 *   broadcasts messages for all of them, not just the one being viewed)
 * - Dispatching a sound + toast when a new message arrives, unless:
 *     - The message was sent by the current user
 *     - The user is actively viewing that channel (`/work/channels/<id>`)
 *     - The corresponding setting is disabled
 * - Clicking the toast navigates to the channel
 *
 * Settings live in localStorage and are managed by useNotificationSettings.
 * Both default to ON.
 */
export function useChannelNotifications() {
  const { me } = useMe()
  const { toast } = useToast()
  const navigate = useNavigate()
  const location = useLocation()

  // Keep pathname in a ref so the message listener (set up once) always
  // reads the current value without needing to re-subscribe on every nav.
  const pathnameRef = useRef(location.pathname)
  useEffect(() => {
    pathnameRef.current = location.pathname
  }, [location.pathname])

  // Channel name lookup, populated after the initial list fetch. Used so
  // the toast can show "#leadership" instead of a bare UUID.
  const channelNamesRef = useRef<Map<string, string>>(new Map())

  const userId = me?.user?.id ?? null

  useEffect(() => {
    if (!userId) return

    const socket = getSharedChannelSocket()

    let cancelled = false
    // Load membership list and join every room
    listChannels()
      .then((channels: ChannelSummary[]) => {
        if (cancelled) return
        for (const ch of channels) {
          if (ch.is_member) {
            channelNamesRef.current.set(ch.id, ch.name)
            socket.joinRoom(ch.id)
          }
        }
      })
      .catch(() => {})

    const handleMessage = (msg: ChannelMessage) => {
      // Skip our own messages
      if (msg.sender_id === userId) return

      // Skip if the user is currently viewing this channel
      if (pathnameRef.current.includes(`/work/channels/${msg.channel_id}`)) return

      const channelName = channelNamesRef.current.get(msg.channel_id) ?? 'a channel'
      const preview = truncate(msg.content || '(attachment)', 80)
      const message = `#${channelName}  ·  ${msg.sender_name}: ${preview}`

      if (getChannelSoundEnabled()) {
        playNotificationSound()
      }
      if (getChannelToastEnabled()) {
        toast(message, {
          type: 'info',
          duration: 5000,
          onClick: () => navigate(`/work/channels/${msg.channel_id}`),
        })
      }
    }

    socket.addMessageListener(handleMessage)

    return () => {
      cancelled = true
      socket.removeMessageListener(handleMessage)
      // Note: we don't leave rooms or disconnect — the shared socket lives
      // for the app's lifetime and other components may still depend on it.
    }
  }, [userId, toast, navigate])
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s
  return s.slice(0, n - 1).trimEnd() + '…'
}
