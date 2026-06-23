// Capture-only mic dictation for the IR create form. Reuses the existing
// pcm-capture-processor AudioWorklet (16 kHz mono Int16 PCM) and assembles a WAV
// blob client-side (Gemini accepts WAV, not MediaRecorder's webm/opus). No
// WebSocket / playback — this is a one-shot record→blob, unlike useVoiceSession.

import { useCallback, useEffect, useRef, useState } from 'react'
import { pcmFramesToWavBlob } from '../../utils/pcmToWav'

export type DictationStatus = 'idle' | 'recording' | 'denied' | 'error'

export function useVoiceDictation(opts: { maxDurationSeconds?: number; onMaxDuration?: () => void } = {}) {
  const maxDur = opts.maxDurationSeconds ?? 120
  const onMaxRef = useRef(opts.onMaxDuration)
  useEffect(() => { onMaxRef.current = opts.onMaxDuration }, [opts.onMaxDuration])

  const [status, setStatus] = useState<DictationStatus>('idle')
  const [elapsedSeconds, setElapsedSeconds] = useState(0)

  const streamRef = useRef<MediaStream | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const nodeRef = useRef<AudioWorkletNode | null>(null)
  const framesRef = useRef<ArrayBuffer[]>([])
  const timerRef = useRef<number | null>(null)

  const cleanup = useCallback(() => {
    if (timerRef.current !== null) { clearInterval(timerRef.current); timerRef.current = null }
    try { nodeRef.current?.disconnect() } catch { /* noop */ }
    nodeRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    ctxRef.current?.close().catch(() => { /* noop */ })
    ctxRef.current = null
  }, [])

  useEffect(() => cleanup, [cleanup]) // tear down on unmount

  const start = useCallback(async () => {
    framesRef.current = []
    setElapsedSeconds(0)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
      streamRef.current = stream
      const ctx = new AudioContext({ sampleRate: 48000 })
      ctxRef.current = ctx
      await ctx.audioWorklet.addModule('/worklets/pcm-capture-processor.js')

      const source = ctx.createMediaStreamSource(stream)
      const node = new AudioWorkletNode(ctx, 'pcm-capture-processor')
      nodeRef.current = node
      node.port.onmessage = (e: MessageEvent<ArrayBuffer>) => { framesRef.current.push(e.data) }
      source.connect(node)
      // zero-gain sink keeps the worklet pulling without echoing the mic
      const silencer = ctx.createGain()
      silencer.gain.value = 0
      node.connect(silencer)
      silencer.connect(ctx.destination)

      setStatus('recording')
      timerRef.current = window.setInterval(() => {
        setElapsedSeconds((prev) => {
          const next = prev + 1
          if (next >= maxDur) onMaxRef.current?.()
          return next
        })
      }, 1000)
    } catch (err) {
      const denied = err instanceof DOMException && (err.name === 'NotAllowedError' || err.name === 'SecurityError')
      setStatus(denied ? 'denied' : 'error')
      cleanup()
    }
  }, [maxDur, cleanup])

  // Stop recording, flush the worklet's partial tail, and assemble the WAV.
  const stop = useCallback(async (): Promise<Blob | null> => {
    const node = nodeRef.current
    if (!node) { setStatus('idle'); return null }
    return new Promise<Blob | null>((resolve) => {
      node.port.postMessage('flush')
      // give the flushed tail one tick to arrive before we tear down
      window.setTimeout(() => {
        const frames = framesRef.current
        framesRef.current = []
        cleanup()
        setStatus('idle')
        resolve(frames.length ? pcmFramesToWavBlob(frames, 16000) : null)
      }, 80)
    })
  }, [cleanup])

  return { start, stop, status, elapsedSeconds }
}
