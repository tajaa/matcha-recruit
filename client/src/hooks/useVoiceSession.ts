import { useCallback, useEffect, useRef, useState } from 'react'

export type VoiceSessionStatus = 'idle' | 'connecting' | 'active' | 'ending' | 'ended' | 'error'

interface UseVoiceSessionOptions {
  websocketUrl: string
  wsAuthToken: string
  maxDurationSeconds?: number
  onTranscript: (role: 'user' | 'assistant', text: string) => void
  onStatusChange?: (status: VoiceSessionStatus) => void
  onSessionEnded?: () => void
}

const CLIENT_AUDIO_PREFIX = 0x01
const SERVER_AUDIO_PREFIX = 0x02
const OUTPUT_SAMPLE_RATE = 24000

export function useVoiceSession(options: UseVoiceSessionOptions | null) {
  const [status, setStatus] = useState<VoiceSessionStatus>('idle')
  const [isMicActive, setIsMicActive] = useState(true)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)

  const wsRef = useRef<WebSocket | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const playbackCtxRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const workletNodeRef = useRef<AudioWorkletNode | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const optionsRef = useRef(options)
  const playbackQueueRef = useRef<AudioBufferSourceNode[]>([])
  const nextPlayTimeRef = useRef(0)
  const statusRef = useRef<VoiceSessionStatus>('idle')
  const autoStopSentRef = useRef(false)

  optionsRef.current = options

  const updateStatus = useCallback((s: VoiceSessionStatus) => {
    statusRef.current = s
    setStatus(s)
    optionsRef.current?.onStatusChange?.(s)
  }, [])

  const flushPlayback = useCallback(() => {
    for (const node of playbackQueueRef.current) {
      try { node.stop() } catch { /* already stopped */ }
    }
    playbackQueueRef.current = []
    nextPlayTimeRef.current = 0
  }, [])

  const playPcmChunk = useCallback((pcmData: ArrayBuffer) => {
    const ctx = playbackCtxRef.current
    if (!ctx || ctx.state === 'closed') return

    const int16 = new Int16Array(pcmData)
    const float32 = new Float32Array(int16.length)
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768
    }

    const buffer = ctx.createBuffer(1, float32.length, OUTPUT_SAMPLE_RATE)
    buffer.copyToChannel(float32, 0)

    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(ctx.destination)

    const now = ctx.currentTime
    const startTime = Math.max(now, nextPlayTimeRef.current)
    source.start(startTime)
    nextPlayTimeRef.current = startTime + buffer.duration

    playbackQueueRef.current.push(source)
    source.onended = () => {
      playbackQueueRef.current = playbackQueueRef.current.filter(n => n !== source)
    }
  }, [])

  const cleanup = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    workletNodeRef.current?.disconnect()
    workletNodeRef.current = null
    streamRef.current?.getTracks().forEach(t => t.stop())
    streamRef.current = null
    if (audioCtxRef.current?.state !== 'closed') {
      audioCtxRef.current?.close().catch(() => {})
    }
    audioCtxRef.current = null
    flushPlayback()
    if (playbackCtxRef.current?.state !== 'closed') {
      playbackCtxRef.current?.close().catch(() => {})
    }
    playbackCtxRef.current = null
  }, [flushPlayback])

  const start = useCallback(async () => {
    if (!optionsRef.current) return
    const { websocketUrl, wsAuthToken, maxDurationSeconds } = optionsRef.current

    updateStatus('connecting')
    setElapsedSeconds(0)
    autoStopSentRef.current = false

    try {
      // Request mic access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
      streamRef.current = stream

      // Create audio contexts
      const audioCtx = new AudioContext({ sampleRate: 48000 })
      audioCtxRef.current = audioCtx
      const playbackCtx = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE })
      playbackCtxRef.current = playbackCtx

      // Load AudioWorklet
      await audioCtx.audioWorklet.addModule('/worklets/pcm-capture-processor.js')

      // Build WebSocket URL
      const base = window.location.origin.replace(/^http/, 'ws')
      const wsUrl = `${base}${websocketUrl}?token=${encodeURIComponent(wsAuthToken)}`
      const ws = new WebSocket(wsUrl)
      ws.binaryType = 'arraybuffer'
      wsRef.current = ws

      ws.onopen = () => {
        updateStatus('active')
        setIsMicActive(true)

        // Wire up mic -> worklet -> WS
        const source = audioCtx.createMediaStreamSource(stream)
        const workletNode = new AudioWorkletNode(audioCtx, 'pcm-capture-processor')
        workletNodeRef.current = workletNode

        workletNode.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
          if (ws.readyState !== WebSocket.OPEN) return
          // Prefix with 0x01 and send
          const pcm = new Uint8Array(e.data)
          const framed = new Uint8Array(1 + pcm.length)
          framed[0] = CLIENT_AUDIO_PREFIX
          framed.set(pcm, 1)
          ws.send(framed.buffer)
        }

        source.connect(workletNode)
        // Connect through a zero-gain node to keep worklet alive without playing mic back
        const silencer = audioCtx.createGain()
        silencer.gain.value = 0
        workletNode.connect(silencer)
        silencer.connect(audioCtx.destination)

        // Start elapsed timer
        timerRef.current = setInterval(() => {
          setElapsedSeconds(prev => {
            const next = prev + 1
            if (maxDurationSeconds && next >= maxDurationSeconds && !autoStopSentRef.current) {
              autoStopSentRef.current = true
              ws.send(JSON.stringify({ type: 'command', command: 'stop_session' }))
            }
            return next
          })
        }, 1000)
      }

      ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          const bytes = new Uint8Array(event.data)
          if (bytes.length > 1 && bytes[0] === SERVER_AUDIO_PREFIX) {
            // Strip prefix and play
            playPcmChunk(bytes.slice(1).buffer)
          }
        } else if (typeof event.data === 'string') {
          try {
            const msg = JSON.parse(event.data)
            if (msg.type === 'user' || msg.type === 'assistant') {
              optionsRef.current?.onTranscript(msg.type, msg.content || msg.text || '')
            } else if (msg.type === 'status') {
              if (msg.message === 'interrupted') {
                flushPlayback()
              } else if (msg.message === 'session_ending' || msg.message === 'session_ended') {
                updateStatus('ending')
              }
            }
          } catch { /* ignore malformed */ }
        }
      }

      ws.onclose = () => {
        updateStatus('ended')
        optionsRef.current?.onSessionEnded?.()
        cleanup()
      }

      ws.onerror = () => {
        updateStatus('error')
        cleanup()
      }
    } catch (err) {
      console.error('[useVoiceSession] Failed to start:', err)
      updateStatus('error')
      cleanup()
    }
  }, [updateStatus, playPcmChunk, flushPlayback, cleanup])

  const stop = useCallback(() => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'command', command: 'stop_session' }))
      updateStatus('ending')
    }
  }, [updateStatus])

  const cancel = useCallback(() => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'command', command: 'cancel_session' }))
    }
    cleanup()
    updateStatus('ended')
  }, [cleanup, updateStatus])

  const toggleMic = useCallback(() => {
    const stream = streamRef.current
    if (!stream) return
    const track = stream.getAudioTracks()[0]
    if (track) {
      track.enabled = !track.enabled
      setIsMicActive(track.enabled)
    }
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close()
      }
      cleanup()
    }
  }, [cleanup])

  return { start, stop, cancel, toggleMic, isMicActive, elapsedSeconds, status }
}
