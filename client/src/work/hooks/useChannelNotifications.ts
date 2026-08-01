import { useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { getSharedChannelSocket } from '../api/channelSocket'
import { listChannels, CHANNELS_CHANGED_EVENT, type ChannelMessage, type ChannelSummary } from '../api/channels'
import { useToast } from '../../components/ui/Toast'
import { useMe } from '../../hooks/useMe'
import { getChannelSoundEnabled, getChannelToastEnabled } from './useNotificationSettings'
import { playNotificationSound } from '../utils/notificationSound'
import { useWorkBase } from '../routes/WorkSurfaceContext'

/**
 * Mount once at the top of WorkLayout. Owns:
 * - Subscribing to the shared ChannelSocket
 * - Joining every channel the current user is a member of (so the server
 *   broadcasts messages for all of them, not just the one being viewed)
 * - Dispatching a sound + toast when a new message arrives, unless:
 *     - The message was sent by the current user
 *     - The user is actively viewing that channel (`<base>/channels/<id>`, /work or /werk)
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
  const base = useWorkBase()

  // Keep pathname in a ref so the message listener (set up once) always
  // reads the current value without needing to re-subscribe on every nav.
  const pathnameRef = useRef(location.pathname)
  useEffect(() => {
    pathnameRef.current = location.pathname
  }, [location.pathname])

  // Channel name lookup, populated after the initial list fetch. Used so
  // the toast can show "#leadership" instead of a bare UUID.
  const channelNamesRef = useRef<Map<string, string>>(new Map())
  // Per-member mute (channel_members.is_muted) — kept in sync with
  // CHANNELS_CHANGED_EVENT so a mute toggled elsewhere takes effect without
  // a remount.
  const mutedChannelsRef = useRef<Set<string>>(new Set())
  const lastBadgeRefreshRef = useRef(0)

  const userId = me?.user?.id ?? null

  useEffect(() => {
    if (!userId) return

    const socket = getSharedChannelSocket()

    let cancelled = false
    // Load membership list, join every room, and track mute state.
    const loadChannels = () => {
      listChannels()
        .then((channels: ChannelSummary[]) => {
          if (cancelled) return
          for (const ch of channels) {
            if (ch.is_member) {
              channelNamesRef.current.set(ch.id, ch.name)
              socket.joinRoom(ch.id)
            }
            if (ch.is_muted) mutedChannelsRef.current.add(ch.id)
            else mutedChannelsRef.current.delete(ch.id)
          }
        })
        .catch(() => {})
    }
    loadChannels()
    window.addEventListener(CHANNELS_CHANGED_EVENT, loadChannels)

    const handleMessage = (msg: ChannelMessage) => {
      // Sidebar unread badges only refresh on navigation/mount today — nudge
      // the existing CHANNELS_CHANGED_EVENT refetch (debounced to 1/5s) so a
      // message arriving on any channel keeps the badge fresh. Fires even
      // for own messages / muted channels — the count is server-computed,
      // not derived from this listener's own filtering below.
      if (Date.now() - lastBadgeRefreshRef.current > 5000) {
        lastBadgeRefreshRef.current = Date.now()
        window.dispatchEvent(new CustomEvent(CHANNELS_CHANGED_EVENT))
      }

      // Skip our own messages
      if (msg.sender_id === userId) return

      // Skip if the user is currently viewing this channel
      if (pathnameRef.current.includes(`${base}/channels/${msg.channel_id}`)) return

      // Muted channel: no sound, no toast (mentions still notify via the
      // server-side bell/push exception; the sidebar badge still ticks).
      if (mutedChannelsRef.current.has(msg.channel_id)) return

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
          onClick: () => navigate(`${base}/channels/${msg.channel_id}`),
        })
      }
    }

    socket.addMessageListener(handleMessage)
    // Another of this user's devices marked a channel read — refresh the
    // sidebar so this device's badge zeroes to match.
    socket.onChannelRead = () => {
      window.dispatchEvent(new CustomEvent(CHANNELS_CHANGED_EVENT))
    }

    return () => {
      cancelled = true
      socket.removeMessageListener(handleMessage)
      socket.onChannelRead = null
      window.removeEventListener(CHANNELS_CHANGED_EVENT, loadChannels)
      // Note: we don't leave rooms or disconnect — the shared socket lives
      // for the app's lifetime and other components may still depend on it.
    }
  }, [userId, toast, navigate, base])
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s
  return s.slice(0, n - 1).trimEnd() + '…'
}
