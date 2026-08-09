// Camera QR scanning for the counter-device page (pages/Scan.tsx).
//
// Two decode backends: the native BarcodeDetector where it exists (Chrome /
// Android, hardware-accelerated), and a lazily-imported jsQR everywhere else
// (Safari/iOS) so the ~40kB decoder never lands in the initial bundle for the
// consumer pages that share this build.
import { useCallback, useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'

// BarcodeDetector is not in TypeScript's lib.dom as of 5.9 — minimal surface only.
type DetectedBarcode = { rawValue: string }
type BarcodeDetectorLike = { detect: (source: CanvasImageSource) => Promise<DetectedBarcode[]> }
type BarcodeDetectorCtor = new (opts: { formats: string[] }) => BarcodeDetectorLike

type JsQrFn = (typeof import('jsqr'))['default']

export type QrScannerState = 'idle' | 'starting' | 'scanning' | 'denied' | 'unsupported' | 'error'

const POLL_MS = 150
// Same code re-decodes ~7x/second while the card sits in frame; one redeem per
// card per 3s window is plenty for a human moving cards across a counter.
const DEDUPE_MS = 3000

export function useQrScanner(opts: { onDecode: (text: string) => void; paused: boolean }): {
  videoRef: RefObject<HTMLVideoElement | null>
  start: () => Promise<void>
  stop: () => void
  state: QrScannerState
} {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<number | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const detectorRef = useRef<BarcodeDetectorLike | null>(null)
  const jsQrRef = useRef<JsQrFn | null>(null)
  const lastDecodeRef = useRef<{ value: string; at: number }>({ value: '', at: 0 })
  const decodingRef = useRef(false)
  const [state, setState] = useState<QrScannerState>('idle')

  // Read through refs so the polling loop always sees the current callback and
  // pause flag without being torn down and rebuilt on every render.
  const onDecodeRef = useRef(opts.onDecode)
  onDecodeRef.current = opts.onDecode
  const pausedRef = useRef(opts.paused)
  pausedRef.current = opts.paused

  const tick = useCallback(async () => {
    if (pausedRef.current || decodingRef.current) return
    const video = videoRef.current
    if (!video || video.readyState < 2 || !video.videoWidth) return
    decodingRef.current = true
    try {
      const canvas = (canvasRef.current ??= document.createElement('canvas'))
      const ctx = canvas.getContext('2d', { willReadFrequently: true })
      if (!ctx) return
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

      let text: string | null = null
      if (detectorRef.current) {
        try {
          const codes = await detectorRef.current.detect(canvas)
          text = codes[0]?.rawValue ?? null
        } catch {
          // Some builds expose the constructor but fail at detect() — drop to
          // jsQR permanently rather than burning a frame every poll.
          detectorRef.current = null
        }
      }
      if (!detectorRef.current && text === null) {
        jsQrRef.current ??= (await import('jsqr')).default
        const img = ctx.getImageData(0, 0, canvas.width, canvas.height)
        text = jsQrRef.current(img.data, img.width, img.height, { inversionAttempts: 'dontInvert' })?.data ?? null
      }
      if (!text) return

      const now = Date.now()
      const last = lastDecodeRef.current
      if (last.value === text && now - last.at < DEDUPE_MS) return
      lastDecodeRef.current = { value: text, at: now }
      onDecodeRef.current(text)
    } catch {
      // Transient frame/decode failure — keep polling.
    } finally {
      decodingRef.current = false
    }
  }, [])

  const stop = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    const video = videoRef.current
    if (video) video.srcObject = null
    setState('idle')
  }, [])

  const start = useCallback(async () => {
    if (streamRef.current) return
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setState('unsupported')
      return
    }
    setState('starting')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      const video = videoRef.current
      if (!video) {
        stream.getTracks().forEach((t) => t.stop())
        setState('error')
        return
      }
      streamRef.current = stream
      video.srcObject = stream
      // iOS rejects play() in some states even with playsInline+muted; the
      // frames still arrive, so a rejection here isn't fatal to decoding.
      await video.play().catch(() => {})

      const Ctor = (window as unknown as { BarcodeDetector?: BarcodeDetectorCtor }).BarcodeDetector
      if (Ctor) {
        try {
          detectorRef.current = new Ctor({ formats: ['qr_code'] })
        } catch {
          detectorRef.current = null
        }
      }

      setState('scanning')
      timerRef.current = window.setInterval(() => { void tick() }, POLL_MS)
    } catch (e) {
      const name = (e as { name?: string } | null)?.name
      setState(name === 'NotAllowedError' || name === 'SecurityError' ? 'denied' : 'error')
    }
  }, [tick])

  // Release the camera when the page unmounts — the tablet's indicator light
  // staying on after navigating away is the visible symptom of skipping this.
  const stopRef = useRef(stop)
  stopRef.current = stop
  useEffect(() => () => stopRef.current(), [])

  return { videoRef, start, stop, state }
}
