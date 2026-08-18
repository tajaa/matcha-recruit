import { useCallback, useEffect, useRef, useState } from 'react'
import { pcmFramesToWavBlob } from '../utils/pcmToWav'

export type ChunkedRecorderStatus = 'idle' | 'recording' | 'denied' | 'error'

type Options = {
  chunkSeconds?: number
  maxDurationSeconds?: number
  initialChunkIndex?: number
  onChunk: (blob: Blob, index: number) => void | Promise<void>
  onMaxDuration?: () => void
}

/**
 * Continuous PCM mic capture that drains a WAV chunk without stopping the
 * AudioWorklet. The server can transcribe each chunk while the meeting keeps
 * recording, avoiding a large one-shot upload and preserving progress if the
 * browser closes unexpectedly.
 */
export function useChunkedVoiceRecorder({
  chunkSeconds = 60,
  maxDurationSeconds = 3600,
  initialChunkIndex = 0,
  onChunk,
  onMaxDuration,
}: Options) {
  const [status, setStatus] = useState<ChunkedRecorderStatus>('idle')
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const onChunkRef = useRef(onChunk)
  const onMaxRef = useRef(onMaxDuration)
  const streamRef = useRef<MediaStream | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const nodeRef = useRef<AudioWorkletNode | null>(null)
  const framesRef = useRef<ArrayBuffer[]>([])
  const chunkIndexRef = useRef(initialChunkIndex)
  const timerRef = useRef<number | null>(null)
  const maxFiredRef = useRef(false)
  const stoppingRef = useRef(false)

  useEffect(() => { onChunkRef.current = onChunk }, [onChunk])
  useEffect(() => { onMaxRef.current = onMaxDuration }, [onMaxDuration])
  useEffect(() => {
    if (status === 'idle') {
      chunkIndexRef.current = Math.max(chunkIndexRef.current, initialChunkIndex)
    }
  }, [initialChunkIndex, status])

  const cleanup = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    try { nodeRef.current?.disconnect() } catch { /* noop */ }
    nodeRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    ctxRef.current?.close().catch(() => { /* noop */ })
    ctxRef.current = null
  }, [])

  useEffect(() => cleanup, [cleanup])

  const emitBufferedChunk = useCallback(() => {
    const frames = framesRef.current.splice(0)
    if (!frames.length) return
    const blob = pcmFramesToWavBlob(frames, 16000)
    const index = chunkIndexRef.current++
    void onChunkRef.current(blob, index)
  }, [])

  const start = useCallback(async () => {
    if (status === 'recording') return
    framesRef.current = []
    maxFiredRef.current = false
    stoppingRef.current = false
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
      node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        if (!stoppingRef.current) framesRef.current.push(event.data)
      }
      source.connect(node)
      const silencer = ctx.createGain()
      silencer.gain.value = 0
      node.connect(silencer)
      silencer.connect(ctx.destination)

      setStatus('recording')
      timerRef.current = window.setInterval(() => {
        setElapsedSeconds((previous) => previous + 1)
        const bufferedSeconds = framesRef.current.reduce((total, frame) => total + frame.byteLength, 0) / 32000
        if (bufferedSeconds >= chunkSeconds) emitBufferedChunk()
      }, 1000)
    } catch (error) {
      const denied = error instanceof DOMException && (error.name === 'NotAllowedError' || error.name === 'SecurityError')
      setStatus(denied ? 'denied' : 'error')
      cleanup()
    }
  }, [chunkSeconds, cleanup, emitBufferedChunk, status])

  useEffect(() => {
    if (elapsedSeconds >= maxDurationSeconds && !maxFiredRef.current) {
      maxFiredRef.current = true
      onMaxRef.current?.()
    }
  }, [elapsedSeconds, maxDurationSeconds])

  const stop = useCallback(async () => {
    const node = nodeRef.current
    if (!node) {
      setStatus('idle')
      return
    }
    await new Promise<void>((resolve) => {
      node.port.postMessage('flush')
      window.setTimeout(() => {
        stoppingRef.current = true
        emitBufferedChunk()
        cleanup()
        setStatus('idle')
        resolve()
      }, 80)
    })
  }, [cleanup, emitBufferedChunk])

  return { start, stop, status, elapsedSeconds }
}
