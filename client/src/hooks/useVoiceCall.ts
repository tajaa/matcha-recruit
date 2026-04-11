import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChannelSocket } from '../api/channelSocket'

// ── Types ──────────────────────────────────────────────────────────────

interface UseVoiceCallOptions {
  socket: ChannelSocket | null
  channelId: string | null
  myUserId: string
}

export interface CallParticipant {
  userId: string
  name: string
  isSpeaking: boolean
  stream: MediaStream | null
}

export type CallState = 'idle' | 'joining' | 'active'

// ── Constants ──────────────────────────────────────────────────────────

const ICE_SERVERS: RTCIceServer[] = [
  { urls: 'stun:stun.l.google.com:19302' },
  { urls: 'stun:stun1.l.google.com:19302' },
]

const SPEAKING_THRESHOLD = 15
const SPEAKING_POLL_MS = 100

// ── Hook ───────────────────────────────────────────────────────────────

export function useVoiceCall({ socket, channelId, myUserId }: UseVoiceCallOptions) {
  const [callState, setCallState] = useState<CallState>('idle')
  const [isMuted, setIsMuted] = useState(false)
  const [isVideoEnabled, setIsVideoEnabled] = useState(true)
  const [participants, setParticipants] = useState<CallParticipant[]>([])
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [localStreamState, setLocalStreamState] = useState<MediaStream | null>(null)

  // Refs for WebRTC state (not rendered directly)
  const peerConnections = useRef<Map<string, RTCPeerConnection>>(new Map())
  const localStream = useRef<MediaStream | null>(null)
  const analysers = useRef<Map<string, AnalyserNode>>(new Map())
  const audioCtx = useRef<AudioContext | null>(null)
  const speakingInterval = useRef<ReturnType<typeof setInterval> | null>(null)
  const elapsedInterval = useRef<ReturnType<typeof setInterval> | null>(null)
  const callStateRef = useRef<CallState>('idle')

  // Keep callStateRef in sync
  callStateRef.current = callState

  // Stable refs for socket/channelId so callbacks don't go stale
  const socketRef = useRef(socket)
  const channelIdRef = useRef(channelId)
  socketRef.current = socket
  channelIdRef.current = channelId

  // ── Helpers ────────────────────────────────────────────────────────

  const getOrCreateAudioContext = useCallback((): AudioContext => {
    if (!audioCtx.current || audioCtx.current.state === 'closed') {
      audioCtx.current = new AudioContext()
    }
    return audioCtx.current
  }, [])

  const startSpeakingDetection = useCallback(() => {
    if (speakingInterval.current) return
    speakingInterval.current = setInterval(() => {
      const updates: { userId: string; speaking: boolean }[] = []
      analysers.current.forEach((analyser, userId) => {
        const data = new Uint8Array(analyser.frequencyBinCount)
        analyser.getByteFrequencyData(data)
        let sum = 0
        for (let i = 0; i < data.length; i++) sum += data[i]
        const avg = data.length > 0 ? sum / data.length : 0
        updates.push({ userId, speaking: avg > SPEAKING_THRESHOLD })
      })
      if (updates.length > 0) {
        setParticipants(prev => {
          let changed = false
          const next = prev.map(p => {
            const update = updates.find(u => u.userId === p.userId)
            if (update && update.speaking !== p.isSpeaking) {
              changed = true
              return { ...p, isSpeaking: update.speaking }
            }
            return p
          })
          return changed ? next : prev
        })
      }
    }, SPEAKING_POLL_MS)
  }, [])

  const stopSpeakingDetection = useCallback(() => {
    if (speakingInterval.current) {
      clearInterval(speakingInterval.current)
      speakingInterval.current = null
    }
  }, [])

  const startElapsedTimer = useCallback(() => {
    if (elapsedInterval.current) return
    setElapsedSeconds(0)
    elapsedInterval.current = setInterval(() => {
      setElapsedSeconds(prev => prev + 1)
    }, 1000)
  }, [])

  const stopElapsedTimer = useCallback(() => {
    if (elapsedInterval.current) {
      clearInterval(elapsedInterval.current)
      elapsedInterval.current = null
    }
  }, [])

  const attachRemoteStream = useCallback((peerId: string, stream: MediaStream) => {
    // Store stream on participant so UI <video> elements handle playback
    setParticipants(prev => prev.map(p =>
      p.userId === peerId ? { ...p, stream } : p
    ))

    // Create analyser for speaking detection
    try {
      const ctx = getOrCreateAudioContext()
      const source = ctx.createMediaStreamSource(stream)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 256
      source.connect(analyser)
      analysers.current.set(peerId, analyser)
    } catch {
      // AudioContext may fail in some environments; speaking detection non-critical
    }
  }, [getOrCreateAudioContext])

  const removeRemoteStream = useCallback((peerId: string) => {
    // Clear stream from participant
    setParticipants(prev => prev.map(p =>
      p.userId === peerId ? { ...p, stream: null } : p
    ))
    // Remove analyser
    analysers.current.delete(peerId)
  }, [])

  const createPeerConnection = useCallback((peerId: string): RTCPeerConnection => {
    // If one already exists, close it first
    const existing = peerConnections.current.get(peerId)
    if (existing) {
      existing.close()
    }

    const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS })

    pc.onicecandidate = (e) => {
      if (e.candidate) {
        socketRef.current?.sendVoiceIceCandidate(peerId, e.candidate.toJSON())
      }
    }

    pc.ontrack = (e) => {
      if (e.streams[0]) {
        attachRemoteStream(peerId, e.streams[0])
      }
    }

    // Add local tracks
    if (localStream.current) {
      localStream.current.getTracks().forEach(track => {
        pc.addTrack(track, localStream.current!)
      })
    }

    peerConnections.current.set(peerId, pc)
    return pc
  }, [attachRemoteStream])

  const closePeerConnection = useCallback((peerId: string) => {
    const pc = peerConnections.current.get(peerId)
    if (pc) {
      pc.close()
      peerConnections.current.delete(peerId)
    }
    removeRemoteStream(peerId)
  }, [removeRemoteStream])

  const closeAllConnections = useCallback(() => {
    peerConnections.current.forEach((pc) => {
      pc.close()
    })
    peerConnections.current.clear()
    analysers.current.clear()
  }, [])

  // ── Cleanup ────────────────────────────────────────────────────────

  const cleanup = useCallback(() => {
    closeAllConnections()
    stopSpeakingDetection()
    stopElapsedTimer()

    // Stop local media
    localStream.current?.getTracks().forEach(t => t.stop())
    localStream.current = null

    // Close audio context
    if (audioCtx.current && audioCtx.current.state !== 'closed') {
      audioCtx.current.close().catch(() => {})
    }
    audioCtx.current = null

    setCallState('idle')
    setIsMuted(false)
    setIsVideoEnabled(true)
    setParticipants([])
    setElapsedSeconds(0)
    setLocalStreamState(null)
  }, [closeAllConnections, stopSpeakingDetection, stopElapsedTimer])

  // ── Public methods ─────────────────────────────────────────────────

  const joinCall = useCallback(async () => {
    if (!socketRef.current || !channelIdRef.current) return
    if (callStateRef.current !== 'idle') return

    setCallState('joining')

    try {
      // Try to get both audio and video
      let stream: MediaStream
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true },
          video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
        })
        setIsVideoEnabled(true)
      } catch {
        // Video denied or unavailable — fall back to audio-only
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true },
        })
        setIsVideoEnabled(false)
      }
      localStream.current = stream
      setLocalStreamState(stream)
      setIsMuted(false)
      socketRef.current.voiceJoin(channelIdRef.current)
    } catch (err) {
      console.error('[useVoiceCall] Failed to get microphone:', err)
      setCallState('idle')
    }
  }, [])

  const leaveCall = useCallback(() => {
    if (socketRef.current && channelIdRef.current && callStateRef.current !== 'idle') {
      socketRef.current.voiceLeave(channelIdRef.current)
    }
    cleanup()
  }, [cleanup])

  const toggleMute = useCallback(() => {
    const stream = localStream.current
    if (!stream) return
    const track = stream.getAudioTracks()[0]
    if (track) {
      track.enabled = !track.enabled
      setIsMuted(!track.enabled)
    }
  }, [])

  const toggleVideo = useCallback(() => {
    const stream = localStream.current
    if (!stream) return
    const track = stream.getVideoTracks()[0]
    if (track) {
      track.enabled = !track.enabled
      setIsVideoEnabled(track.enabled)
    }
  }, [])

  // ── Socket callback wiring ─────────────────────────────────────────

  useEffect(() => {
    if (!socket) return

    // voice_participants: list of existing users when we join
    socket.onVoiceParticipants = async (remoteParticipants) => {
      setParticipants(remoteParticipants.map(p => ({
        userId: p.user_id,
        name: p.name,
        isSpeaking: false,
        stream: null,
      })))

      setCallState('active')
      startElapsedTimer()
      startSpeakingDetection()

      // Create peer connections and send offers to each existing participant
      for (const p of remoteParticipants) {
        if (p.user_id === myUserId) continue
        try {
          const pc = createPeerConnection(p.user_id)
          const offer = await pc.createOffer()
          await pc.setLocalDescription(offer)
          socketRef.current?.sendVoiceOffer(p.user_id, offer)
        } catch (err) {
          console.error('[useVoiceCall] Failed to create offer for', p.user_id, err)
        }
      }
    }

    // voice_user_joined: a new user entered the call (they'll send us an offer)
    socket.onVoiceUserJoined = (user) => {
      setParticipants(prev => {
        if (prev.some(p => p.userId === user.user_id)) return prev
        return [...prev, { userId: user.user_id, name: user.name, isSpeaking: false, stream: null }]
      })
    }

    // voice_user_left: a user left the call
    socket.onVoiceUserLeft = (user) => {
      closePeerConnection(user.user_id)
      setParticipants(prev => {
        const next = prev.filter(p => p.userId !== user.user_id)
        // If no participants left, end the call
        if (next.length === 0 && callStateRef.current === 'active') {
          cleanup()
        }
        return next
      })
    }

    // voice_offer: remote peer sent us an SDP offer
    socket.onVoiceOffer = async (data) => {
      try {
        const pc = createPeerConnection(data.from_user_id)
        await pc.setRemoteDescription(new RTCSessionDescription(data.sdp))
        const answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        socketRef.current?.sendVoiceAnswer(data.from_user_id, answer)
      } catch (err) {
        console.error('[useVoiceCall] Failed to handle offer from', data.from_user_id, err)
      }
    }

    // voice_answer: remote peer answered our offer
    socket.onVoiceAnswer = async (data) => {
      const pc = peerConnections.current.get(data.from_user_id)
      if (!pc) return
      try {
        await pc.setRemoteDescription(new RTCSessionDescription(data.sdp))
      } catch (err) {
        console.error('[useVoiceCall] Failed to set answer from', data.from_user_id, err)
      }
    }

    // voice_ice: remote peer sent an ICE candidate
    socket.onVoiceIceCandidate = async (data) => {
      const pc = peerConnections.current.get(data.from_user_id)
      if (!pc) return
      try {
        await pc.addIceCandidate(new RTCIceCandidate(data.candidate))
      } catch (err) {
        console.error('[useVoiceCall] Failed to add ICE candidate from', data.from_user_id, err)
      }
    }

    return () => {
      // Clean up socket callbacks when effect re-runs or unmounts
      socket.onVoiceParticipants = null
      socket.onVoiceUserJoined = null
      socket.onVoiceUserLeft = null
      socket.onVoiceOffer = null
      socket.onVoiceAnswer = null
      socket.onVoiceIceCandidate = null
    }
  }, [socket, myUserId, createPeerConnection, closePeerConnection, cleanup, startElapsedTimer, startSpeakingDetection])

  // ── Unmount cleanup ────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      if (callStateRef.current !== 'idle') {
        if (channelIdRef.current) {
          socketRef.current?.voiceLeave(channelIdRef.current)
        }
        // Inline cleanup to avoid stale closure on the cleanup callback
        peerConnections.current.forEach(pc => pc.close())
        peerConnections.current.clear()
        analysers.current.clear()
        localStream.current?.getTracks().forEach(t => t.stop())
        localStream.current = null
        if (audioCtx.current && audioCtx.current.state !== 'closed') {
          audioCtx.current.close().catch(() => {})
        }
        audioCtx.current = null
        if (speakingInterval.current) clearInterval(speakingInterval.current)
        if (elapsedInterval.current) clearInterval(elapsedInterval.current)
      }
    }
  }, [])

  return { joinCall, leaveCall, toggleMute, toggleVideo, isMuted, isVideoEnabled, callState, participants, elapsedSeconds, localStream: localStreamState }
}
