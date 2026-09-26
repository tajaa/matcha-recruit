import { useCallback, useEffect, useRef, useState } from 'react'
import { DisconnectReason, Room, RoomEvent, Track } from 'livekit-client'
import { getSharedChannelSocket } from '../api/channelSocket'
import {
  getBroadcastStatus, getBroadcastToken, refreshBroadcastToken, setBroadcastPublisher,
  startBroadcast, stopBroadcast, type BroadcastStatus,
} from '../api/channelBroadcasts'
import type { CallParticipant } from './useLiveKitCall'

type ConnectionState = 'idle' | 'connecting' | 'connected'

// Disconnects that are deliberate or final. Anything else (server restart,
// signal loss) gets one reconnect with a freshly minted token.
const FINAL_DISCONNECTS = new Set<DisconnectReason | undefined>([
  DisconnectReason.CLIENT_INITIATED, DisconnectReason.DUPLICATE_IDENTITY,
  DisconnectReason.PARTICIPANT_REMOVED, DisconnectReason.ROOM_DELETED,
])

function mediaStream(tracks: MediaStreamTrack[]): MediaStream | null {
  if (!tracks.length) return null
  const stream = new MediaStream()
  for (const track of tracks) stream.addTrack(track)
  return stream
}

/** Broadcast shares the channel socket and LiveKit room model with calls. */
export function useLiveKitBroadcast(channelId: string | null, userId: string | null, members: { user_id: string; name: string }[]) {
  const [scopedStatus, setScopedStatus] = useState<{ channelId: string; value: BroadcastStatus } | null>(null)
  const status = scopedStatus?.channelId === channelId ? scopedStatus.value : null
  const [connectionState, setConnectionState] = useState<ConnectionState>('idle')
  const [isPublishing, setIsPublishing] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [isVideoEnabled, setIsVideoEnabled] = useState(false)
  const [participants, setParticipants] = useState<CallParticipant[]>([])
  const [localStream, setLocalStream] = useState<MediaStream | null>(null)
  const [error, setError] = useState<string | null>(null)
  const roomRef = useRef<Room | null>(null)
  const serialRef = useRef(0)
  const statusRef = useRef<BroadcastStatus | null>(null)
  const publishingRef = useRef(false)
  const endedRef = useRef(new Set<string>())
  const namesRef = useRef(new Map<string, string>())
  const grantRef = useRef<{ token: string; livekit_url: string; can_publish: boolean } | null>(null)
  const mutedRef = useRef(false)
  const recoverRef = useRef<(reason?: DisconnectReason) => void>(() => {})

  useEffect(() => {
    namesRef.current = new Map(members.map((member) => [member.user_id, member.name]))
  }, [members])

  const saveStatus = useCallback((next: BroadcastStatus) => {
    statusRef.current = next
    if (channelId) setScopedStatus({ channelId, value: next })
  }, [channelId])

  const disconnect = useCallback(() => {
    serialRef.current += 1
    const room = roomRef.current
    roomRef.current = null
    if (room) {
      room.removeAllListeners()
      void room.disconnect()
    }
    publishingRef.current = false
    setConnectionState('idle')
    setIsPublishing(false)
    setIsVideoEnabled(false)
    setParticipants([])
    setLocalStream(null)
  }, [])

  const rebuild = useCallback(() => {
    const room = roomRef.current
    if (!room) return
    const next: CallParticipant[] = []
    room.remoteParticipants.forEach((participant) => {
      const tracks: MediaStreamTrack[] = []
      participant.trackPublications.forEach((publication) => {
        if (publication.track?.mediaStreamTrack) tracks.push(publication.track.mediaStreamTrack)
      })
      next.push({
        userId: participant.identity,
        name: participant.name || namesRef.current.get(participant.identity) || 'Member',
        isSpeaking: participant.isSpeaking,
        stream: mediaStream(tracks),
      })
    })
    setParticipants(next)
    const localVideo: MediaStreamTrack[] = []
    room.localParticipant.trackPublications.forEach((publication) => {
      if (publication.kind === Track.Kind.Video && publication.track?.mediaStreamTrack) {
        localVideo.push(publication.track.mediaStreamTrack)
      }
    })
    setLocalStream(mediaStream(localVideo))
  }, [])

  // Reconnects (a promotion grant, or recovery after a drop) keep the
  // publisher's mute choice; only a fresh join starts unmuted.
  const connect = useCallback(async (url: string, token: string, canPublish: boolean, keepMute = false) => {
    if (!keepMute) { mutedRef.current = false; setIsMuted(false) }
    disconnect()
    const serial = serialRef.current
    const room = new Room({ dynacast: true })
    roomRef.current = room
    setConnectionState('connecting')
    for (const event of [RoomEvent.TrackSubscribed, RoomEvent.TrackUnsubscribed,
      RoomEvent.ParticipantConnected, RoomEvent.ParticipantDisconnected,
      RoomEvent.LocalTrackPublished, RoomEvent.LocalTrackUnpublished]) {
      room.on(event, rebuild)
    }
    room.on(RoomEvent.Disconnected, (reason?: DisconnectReason) => {
      if (serial !== serialRef.current) return
      disconnect()
      if (!FINAL_DISCONNECTS.has(reason)) recoverRef.current(reason)
    })
    try {
      await room.connect(url, token)
      if (serial !== serialRef.current) { void room.disconnect(); return }
      if (canPublish) {
        await room.localParticipant.setMicrophoneEnabled(!mutedRef.current)
        let camera = true
        try { await room.localParticipant.setCameraEnabled(true) } catch { camera = false }
        setIsVideoEnabled(camera)
      }
      if (serial !== serialRef.current) { void room.disconnect(); return }
      publishingRef.current = canPublish
      setIsPublishing(canPublish)
      setConnectionState('connected')
      rebuild()
    } catch (cause) {
      if (serial === serialRef.current) {
        disconnect()
        setError(cause instanceof Error ? cause.message : 'Could not join broadcast')
      }
    }
  }, [disconnect, rebuild])

  const hydrate = useCallback(async () => {
    if (!channelId) return
    try {
      const next = await getBroadcastStatus(channelId)
      if (next.broadcast_id && endedRef.current.has(next.broadcast_id)) return
      if (!next.active || (statusRef.current?.broadcast_id && statusRef.current.broadcast_id !== next.broadcast_id)) {
        grantRef.current = null
      }
      saveStatus(next)
      if (!next.active) disconnect()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load broadcast')
    }
  }, [channelId, disconnect, saveStatus])

  useEffect(() => {
    if (!channelId) return
    const socket = getSharedChannelSocket()
    const ended = endedRef.current
    socket.onBroadcastStarted = (data) => {
      if (data.channel_id !== channelId) return
      if (statusRef.current?.broadcast_id !== data.broadcast_id) grantRef.current = null
      void hydrate()
    }
    socket.onBroadcastEnded = (data) => {
      if (data.channel_id !== channelId || endedRef.current.has(data.broadcast_id)) return
      endedRef.current.add(data.broadcast_id)
      if (statusRef.current?.broadcast_id === data.broadcast_id) {
        grantRef.current = null
        saveStatus({ ...statusRef.current, active: false, weekly_used: statusRef.current.weekly_used,
          weekly_remaining: statusRef.current.weekly_remaining })
        disconnect()
      }
    }
    socket.onBroadcastPublisherChanged = (data) => {
      if (data.channel_id !== channelId) return
      const current = statusRef.current
      if (!current) return
      const ids = new Set(current.publisher_user_ids ?? [])
      if (data.can_publish) ids.add(data.user_id)
      else ids.delete(data.user_id)
      saveStatus({ ...current, publisher_user_ids: [...ids] })
    }
    socket.onBroadcastTokenGrant = (data) => {
      if (data.channel_id !== channelId) return
      // A member can be promoted before pressing Watch. Keep that token until
      // they join; the server has no persisted grant for an offline viewer.
      grantRef.current = data
      if (!roomRef.current) return
      // The new token carries the changed grant. Reconnect to apply it even
      // if the server's best-effort live permission update was missed.
      void connect(data.livekit_url, data.token, data.can_publish, true)
    }
    queueMicrotask(() => { void hydrate() })
    return () => {
      socket.onBroadcastStarted = null
      socket.onBroadcastEnded = null
      socket.onBroadcastPublisherChanged = null
      socket.onBroadcastTokenGrant = null
      disconnect()
      statusRef.current = null
      grantRef.current = null
      ended.clear()
    }
  }, [channelId, connect, disconnect, hydrate, saveStatus])

  // Every broadcast token outlives the ten-minute cap (viewer TTL is the cap
  // plus grace; publisher TTL runs to the cap), and LiveKit keeps a connected
  // session alive past token expiry. So no periodic re-mint: a timer here only
  // dropped the stream for everyone every few minutes. Mint a fresh token only
  // to recover from an unexpected disconnect while the broadcast is still live.
  useEffect(() => {
    recoverRef.current = () => {
      if (!channelId || !statusRef.current?.active) return
      void (async () => {
        try {
          const token = await refreshBroadcastToken(channelId)
          await connect(token.livekit_url, token.token, token.can_publish ?? false, true)
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : 'Lost the broadcast connection')
          void hydrate()
        }
      })()
    }
  }, [channelId, connect, hydrate])

  const start = useCallback(async (title: string) => {
    if (!channelId) return
    setError(null)
    try {
      const result = await startBroadcast(channelId, title)
      await hydrate()
      await connect(result.livekit_url, result.token, true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not start broadcast')
    }
  }, [channelId, connect, hydrate])

  const watch = useCallback(async () => {
    if (!channelId) return
    setError(null)
    try {
      const grant = grantRef.current
      const canPublish = !!userId && !!statusRef.current?.publisher_user_ids?.includes(userId)
      const token = grant ?? (canPublish ? await refreshBroadcastToken(channelId) : await getBroadcastToken(channelId))
      await connect(token.livekit_url, token.token, token.can_publish ?? false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not watch broadcast')
    }
  }, [channelId, connect, userId])

  const stop = useCallback(async () => {
    if (!channelId) return
    try {
      await stopBroadcast(channelId)
      disconnect()
      await hydrate()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not end broadcast')
    }
  }, [channelId, disconnect, hydrate])

  const setPublisher = useCallback(async (userId: string, canPublish: boolean) => {
    if (!channelId) return
    try { await setBroadcastPublisher(channelId, userId, canPublish) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not change publisher') }
  }, [channelId])

  const toggleMute = useCallback(async () => {
    const room = roomRef.current
    if (!room || !publishingRef.current) return
    await room.localParticipant.setMicrophoneEnabled(isMuted)
    mutedRef.current = !isMuted
    setIsMuted(!isMuted)
  }, [isMuted])

  const toggleVideo = useCallback(async () => {
    const room = roomRef.current
    if (!room || !publishingRef.current) return
    await room.localParticipant.setCameraEnabled(!isVideoEnabled)
    setIsVideoEnabled(!isVideoEnabled)
    rebuild()
  }, [isVideoEnabled, rebuild])

  return { status, connectionState, isPublishing, isMuted, isVideoEnabled, participants,
    localStream, error, setError, start, watch, stop, leave: disconnect, setPublisher,
    toggleMute, toggleVideo, refresh: hydrate }
}
