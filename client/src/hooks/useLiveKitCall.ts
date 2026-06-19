import { useCallback, useEffect, useRef, useState } from 'react'
import { Room, RoomEvent, Track } from 'livekit-client'
import { getSharedChannelSocket } from '../api/channelSocket'
import { startCall, getCallToken, getCallStatus, stopCall } from '../api/channelCalls'

// LiveKit SFU call hook for the werk-lite surface. Deliberately exposes the
// SAME shape as useVoiceCall (the homegrown WebRTC P2P hook) so ChannelView can
// swap between them with a one-line surface conditional and feed either into
// the shared <VoiceCallBar>.
//
// Unlike the P2P hook there's a real server-side room with an owner: joinCall
// transparently starts a call if none is active, else joins the existing one.
// Symmetric small-group video uses the 4-person /call room (everyone publishes
// mic + camera — the server grant was widened to allow camera).

export interface CallParticipant {
  userId: string
  name: string
  isSpeaking: boolean
  stream: MediaStream | null
}

export type CallState = 'idle' | 'joining' | 'active'

interface UseLiveKitCallOptions {
  channelId: string | null
  // Only wire effects/socket handlers when this surface actually uses LiveKit.
  // ChannelView calls this hook unconditionally (hooks rule) but passes
  // enabled=false on /work + /werk so it stays fully inert there.
  enabled: boolean
  // Channel members, used to resolve participant ids → names for the
  // "call active — join?" banner when we're not connected to the room.
  members?: { user_id: string; name: string }[]
  // Surface a failed start/join (e.g. a 403 when only admins may start) so the
  // caller can tell the user, instead of silently snapping back to idle.
  onError?: (message: string) => void
}

function buildStream(tracks: MediaStreamTrack[]): MediaStream | null {
  if (tracks.length === 0) return null
  const ms = new MediaStream()
  for (const t of tracks) ms.addTrack(t)
  return ms
}

export function useLiveKitCall({ channelId, enabled, members, onError }: UseLiveKitCallOptions) {
  const [callState, setCallState] = useState<CallState>('idle')
  const [isMuted, setIsMuted] = useState(false)
  const [isVideoEnabled, setIsVideoEnabled] = useState(true)
  const [participants, setParticipants] = useState<CallParticipant[]>([])
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [localStream, setLocalStream] = useState<MediaStream | null>(null)

  const roomRef = useRef<Room | null>(null)
  const elapsedInterval = useRef<ReturnType<typeof setInterval> | null>(null)
  const callStateRef = useRef<CallState>('idle')
  const isMutedRef = useRef(false)
  const isVideoEnabledRef = useRef(true)
  const isOwnerRef = useRef(false)
  const channelIdRef = useRef(channelId)
  const membersRef = useRef<Map<string, string>>(new Map())
  const onErrorRef = useRef(onError)

  callStateRef.current = callState
  isMutedRef.current = isMuted
  isVideoEnabledRef.current = isVideoEnabled
  channelIdRef.current = channelId
  membersRef.current = new Map((members ?? []).map((m) => [m.user_id, m.name]))
  onErrorRef.current = onError

  // ── Timers ───────────────────────────────────────────────────────────
  const startElapsed = useCallback(() => {
    if (elapsedInterval.current) return
    setElapsedSeconds(0)
    elapsedInterval.current = setInterval(() => setElapsedSeconds((p) => p + 1), 1000)
  }, [])
  const stopElapsed = useCallback(() => {
    if (elapsedInterval.current) {
      clearInterval(elapsedInterval.current)
      elapsedInterval.current = null
    }
  }, [])

  // ── Participant grid, rebuilt from authoritative LiveKit room state ──
  const rebuild = useCallback(() => {
    const room = roomRef.current
    if (!room) return
    const remotes: CallParticipant[] = []
    room.remoteParticipants.forEach((p) => {
      const tracks: MediaStreamTrack[] = []
      p.trackPublications.forEach((pub) => {
        if (pub.track?.mediaStreamTrack) tracks.push(pub.track.mediaStreamTrack)
      })
      remotes.push({
        userId: p.identity,
        name: p.name || membersRef.current.get(p.identity) || 'Member',
        isSpeaking: p.isSpeaking,
        stream: buildStream(tracks),
      })
    })
    setParticipants(remotes)

    // Self-view: local video track only (audio muted in the tile anyway).
    const localVideo: MediaStreamTrack[] = []
    room.localParticipant.trackPublications.forEach((pub) => {
      if (pub.kind === Track.Kind.Video && pub.track?.mediaStreamTrack) {
        localVideo.push(pub.track.mediaStreamTrack)
      }
    })
    setLocalStream(buildStream(localVideo))
  }, [])

  // ── Speaking-state only (no MediaStream rebuild) ─────────────────────
  // Runs on the frequent ActiveSpeakersChanged event. Rebuilding streams here
  // would hand React new MediaStream objects every time someone talks, which
  // re-attaches every <video> and flickers — so stream rebuilds stay on
  // track/participant events and this only flips the isSpeaking flags in place.
  const updateSpeaking = useCallback(() => {
    const room = roomRef.current
    if (!room) return
    const speaking = new Set(room.activeSpeakers.map((p) => p.identity))
    setParticipants((prev) => {
      let changed = false
      const next = prev.map((p) => {
        const s = speaking.has(p.userId)
        if (s !== p.isSpeaking) { changed = true; return { ...p, isSpeaking: s } }
        return p
      })
      return changed ? next : prev
    })
  }, [])

  // ── Teardown (also used as the RoomEvent.Disconnected handler) ───────
  const cleanup = useCallback(() => {
    stopElapsed()
    const room = roomRef.current
    if (room) {
      room.removeAllListeners()
      room.disconnect()
      roomRef.current = null
    }
    isOwnerRef.current = false
    setCallState('idle')
    setParticipants([])
    setLocalStream(null)
    setIsMuted(false)
    setIsVideoEnabled(true)
    setElapsedSeconds(0)
  }, [stopElapsed])

  // ── Roster (the "call active — join?" banner when we're NOT in the room) ──
  const setRosterFromIds = useCallback((ids: string[]) => {
    // While connected, LiveKit room events are authoritative — ignore roster.
    if (callStateRef.current !== 'idle') return
    setParticipants(
      ids.map((id) => ({
        userId: id,
        name: membersRef.current.get(id) ?? 'Member',
        isSpeaking: false,
        stream: null,
      })),
    )
  }, [])

  const hydrate = useCallback(async () => {
    const cid = channelIdRef.current
    if (!cid) return
    try {
      const s = await getCallStatus(cid)
      if (s.active && s.participant_ids?.length) setRosterFromIds(s.participant_ids)
      else if (!s.active && callStateRef.current === 'idle') setParticipants([])
    } catch { /* no active call / not a member — leave roster empty */ }
  }, [setRosterFromIds])

  // ── Connect to a LiveKit room with a server-minted token ─────────────
  const connectRoom = useCallback(async (url: string, token: string) => {
    const room = new Room()
    roomRef.current = room
    room.on(RoomEvent.TrackSubscribed, rebuild)
    room.on(RoomEvent.TrackUnsubscribed, rebuild)
    room.on(RoomEvent.ParticipantConnected, rebuild)
    room.on(RoomEvent.ParticipantDisconnected, rebuild)
    room.on(RoomEvent.ActiveSpeakersChanged, updateSpeaking)
    room.on(RoomEvent.LocalTrackPublished, rebuild)
    room.on(RoomEvent.LocalTrackUnpublished, rebuild)
    room.on(RoomEvent.Disconnected, () => cleanup())

    await room.connect(url, token)
    await room.localParticipant.setMicrophoneEnabled(true)
    await room.localParticipant.setCameraEnabled(true)
    setIsMuted(false)
    setIsVideoEnabled(true)
    setCallState('active')
    startElapsed()
    rebuild()
  }, [rebuild, updateSpeaking, cleanup, startElapsed])

  // ── Public actions (names mirror useVoiceCall) ───────────────────────
  const joinCall = useCallback(async () => {
    const cid = channelIdRef.current
    if (!cid || callStateRef.current !== 'idle') return
    setCallState('joining')
    try {
      const status = await getCallStatus(cid)
      let url: string
      let token: string
      if (status.active) {
        const t = await getCallToken(cid)
        url = t.livekit_url
        token = t.token
      } else {
        try {
          const s = await startCall(cid, { mode: 'members' })
          url = s.livekit_url
          token = s.token
          isOwnerRef.current = true
        } catch {
          // Race: someone started a call between our status check and start
          // (the server enforces one active call per channel). Fall back to join.
          const t = await getCallToken(cid)
          url = t.livekit_url
          token = t.token
        }
      }
      await connectRoom(url, token)
    } catch (err) {
      console.error('[useLiveKitCall] join failed', err)
      cleanup()
      onErrorRef.current?.(err instanceof Error ? err.message : 'Could not start the call')
    }
  }, [connectRoom, cleanup])

  const leaveCall = useCallback(() => {
    const cid = channelIdRef.current
    // Owner explicitly ends the call for everyone; members just disconnect and
    // the server auto-stops once the room empties. stopCall is owner-only (403
    // otherwise), so only the owner calls it.
    if (isOwnerRef.current && cid) stopCall(cid).catch(() => {})
    cleanup()
    // Repopulate the rejoin banner if the call is still live for others.
    void hydrate()
  }, [cleanup, hydrate])

  const toggleMute = useCallback(async () => {
    const room = roomRef.current
    if (!room) return
    const newMuted = !isMutedRef.current
    await room.localParticipant.setMicrophoneEnabled(!newMuted)
    setIsMuted(newMuted)
  }, [])

  const toggleVideo = useCallback(async () => {
    const room = roomRef.current
    if (!room) return
    const newEnabled = !isVideoEnabledRef.current
    await room.localParticipant.setCameraEnabled(newEnabled)
    setIsVideoEnabled(newEnabled)
    rebuild()
  }, [rebuild])

  // ── Socket wiring: drive the join banner + auto-teardown off call.* ──
  useEffect(() => {
    if (!enabled || !channelId) return
    const socket = getSharedChannelSocket()

    socket.onCallStarted = (d) => {
      if (d.channel_id === channelId) setRosterFromIds([d.started_by])
    }
    socket.onCallParticipantsChanged = (d) => {
      if (d.channel_id === channelId) setRosterFromIds(d.participant_ids)
    }
    socket.onCallEnded = (d) => {
      if (d.channel_id !== channelId) return
      cleanup()
    }
    socket.onCallInvited = null // MVP: 'members' mode, no invite prompt

    void hydrate()

    return () => {
      socket.onCallStarted = null
      socket.onCallParticipantsChanged = null
      socket.onCallEnded = null
      socket.onCallInvited = null
    }
  }, [enabled, channelId, setRosterFromIds, cleanup, hydrate])

  // ── Tear down on channel change OR unmount ───────────────────────────
  // ChannelView is NOT remounted when the channel-id route param changes, so
  // without keying this on channelId an active call's Room would stay connected
  // (mic/camera left live) after navigating to another channel. cleanupRef
  // avoids a stale cleanup closure while still resetting call state.
  const cleanupRef = useRef(cleanup)
  cleanupRef.current = cleanup
  useEffect(() => {
    return () => { cleanupRef.current() }
  }, [channelId])

  return {
    joinCall,
    leaveCall,
    toggleMute,
    toggleVideo,
    isMuted,
    isVideoEnabled,
    callState,
    participants,
    elapsedSeconds,
    localStream,
  }
}
