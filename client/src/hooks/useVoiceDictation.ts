// Capture-only mic dictation — one-shot record→blob (no WebSocket/playback,
// unlike work/hooks/useVoiceSession). Reuses the existing pcm-capture-processor
// AudioWorklet (16 kHz mono Int16 PCM) and assembles a WAV blob client-side
// (Gemini accepts WAV, not MediaRecorder's webm/opus). Shared: used by IR's
// dictate-a-report flow and the inventory Audit sheet's dictate-a-count flow.

import { useCallback, useEffect, useRef, useState } from 'react'
import { pcmFramesToWavBlob } from '../utils/pcmToWav'

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
  const maxFiredRef = useRef(false)
  const mountedRef = useRef(true)
  const startPendingRef = useRef(false)
  const startGenerationRef = useRef(0)

  const cleanup = useCallback(() => {
    startGenerationRef.current += 1
    startPendingRef.current = false
    if (timerRef.current !== null) { clearInterval(timerRef.current); timerRef.current = null }
    try { nodeRef.current?.disconnect() } catch { /* noop */ }
    nodeRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    ctxRef.current?.close().catch(() => { /* noop */ })
    ctxRef.current = null
  }, [])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      cleanup()
    }
  }, [cleanup])

  // Fires onMaxDuration exactly once per recording (maxFiredRef reset in
  // start()) — doing this as a side effect from elapsedSeconds instead of
  // inline in the interval's setState updater avoids a StrictMode double-
  // invoke calling stop() twice, which clobbers a real result with "no
  // audio captured" on the second, frame-less call.
  useEffect(() => {
    if (elapsedSeconds >= maxDur && !maxFiredRef.current) {
      maxFiredRef.current = true
      onMaxRef.current?.()
    }
  }, [elapsedSeconds, maxDur])

  const start = useCallback(async () => {
    if (startPendingRef.current || nodeRef.current) return
    startPendingRef.current = true
    const generation = ++startGenerationRef.current
    framesRef.current = []
    maxFiredRef.current = false
    setElapsedSeconds(0)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
      if (!mountedRef.current || generation !== startGenerationRef.current) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      streamRef.current = stream
      const ctx = new AudioContext({ sampleRate: 48000 })
      ctxRef.current = ctx
      await ctx.audioWorklet.addModule('/worklets/pcm-capture-processor.js')
      if (!mountedRef.current || generation !== startGenerationRef.current) {
        stream.getTracks().forEach((track) => track.stop())
        await ctx.close().catch(() => { /* noop */ })
        return
      }

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
        setElapsedSeconds((prev) => prev + 1)
      }, 1000)
      startPendingRef.current = false
    } catch (err) {
      const denied = err instanceof DOMException && (err.name === 'NotAllowedError' || err.name === 'SecurityError')
      if (mountedRef.current && generation === startGenerationRef.current) setStatus(denied ? 'denied' : 'error')
      cleanup()
    }
  }, [cleanup])

  // Stop recording, flush the worklet's partial tail, and assemble the WAV.
  const stop = useCallback(async (): Promise<Blob | null> => {
    const node = nodeRef.current
    if (!node) {
      if (mountedRef.current) setStatus('idle')
      return null
    }
    return new Promise<Blob | null>((resolve) => {
      node.port.postMessage('flush')
      // give the flushed tail one tick to arrive before we tear down
      window.setTimeout(() => {
        const frames = framesRef.current
        framesRef.current = []
        cleanup()
        if (!mountedRef.current) {
          resolve(null)
          return
        }
        setStatus('idle')
        resolve(frames.length ? pcmFramesToWavBlob(frames, 16000) : null)
      }, 80)
    })
  }, [cleanup])

  return { start, stop, status, elapsedSeconds }
}
