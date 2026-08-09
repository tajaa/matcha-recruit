// QR rasteriser for the designer.
//
// Two constraints shape this. (1) qrcode.react only draws into a real DOM
// <canvas>, and react-konva runs a custom reconciler where a DOM child is not
// a valid node — so the hidden QRCodeCanvas elements MUST be rendered as a DOM
// sibling of the <Stage>, never inside it. (2) Konva only repaints an image
// when the image object identity changes, so each redraw is copied into a
// FRESH canvas rather than handed back the same element with new pixels.
//
// QR layers deliberately store no URL: the campaign's claim URL is injected at
// render time, so a design saved before the campaign existed still resolves.
import { useEffect, useMemo, useRef, useState } from 'react'
import { QRCodeCanvas } from 'qrcode.react'
import type { FlyerDesign } from '../../api/types'

// Raster resolution is decoupled from the on-artboard size so a 300dpi export
// (pixelRatio 2) still gets clean module edges. Capped so a huge QR layer
// can't allocate an 8k texture.
function rasterPx(size: number) {
  return Math.min(2048, Math.max(512, Math.round(size * 2)))
}

interface QrSpec {
  key: string
  value: string
  px: number
  fg: string
  bg: string
}

export function useQrCanvases(design: FlyerDesign, claimUrl: string) {
  // One raster per DISTINCT (value, size, colours) tuple — two QR layers with
  // the same settings share a canvas instead of encoding twice.
  const specs = useMemo<QrSpec[]>(() => {
    const seen = new Map<string, QrSpec>()
    for (const layer of design.layers) {
      if (layer.type !== 'qr') continue
      const px = rasterPx(layer.size)
      const key = `${claimUrl}|${px}|${layer.fg}|${layer.bg}`
      if (!seen.has(key)) seen.set(key, { key, value: claimUrl, px, fg: layer.fg, bg: layer.bg })
    }
    return [...seen.values()]
  }, [design.layers, claimUrl])

  const [canvases, setCanvases] = useState<Record<string, HTMLCanvasElement>>({})
  const hosts = useRef(new Map<string, HTMLCanvasElement | null>())

  useEffect(() => {
    let cancelled = false
    // One frame of slack: qrcode.react paints in its own layout effect, and
    // reading the bitmap in the same tick can catch a blank canvas.
    const raf = requestAnimationFrame(() => {
      if (cancelled) return
      const next: Record<string, HTMLCanvasElement> = {}
      for (const spec of specs) {
        const src = hosts.current.get(spec.key)
        if (!src || src.width === 0) continue
        const copy = document.createElement('canvas')
        copy.width = src.width
        copy.height = src.height
        copy.getContext('2d')?.drawImage(src, 0, 0)
        next[spec.key] = copy
      }
      setCanvases((prev) => {
        const same = Object.keys(next).length === Object.keys(prev).length
          && Object.keys(next).every((k) => k in prev)
        return same ? prev : next
      })
    })
    return () => { cancelled = true; cancelAnimationFrame(raf) }
  }, [specs])

  function canvasFor(size: number, fg: string, bg: string): HTMLCanvasElement | undefined {
    return canvases[`${claimUrl}|${rasterPx(size)}|${fg}|${bg}`]
  }

  // Rendered by the caller as a DOM sibling of the Stage. Off-screen rather
  // than display:none — a hidden canvas still rasterises, but keeping it in
  // flow-free absolute position avoids any layout cost.
  const hidden = (
    <div aria-hidden style={{ position: 'absolute', left: -99999, top: 0, width: 1, height: 1, overflow: 'hidden' }}>
      {specs.map((spec) => (
        <QRCodeCanvas
          key={spec.key}
          ref={(el) => { hosts.current.set(spec.key, el) }}
          value={spec.value}
          size={spec.px}
          fgColor={spec.fg}
          bgColor={spec.bg}
          level="M"
          marginSize={2}
        />
      ))}
    </div>
  )

  return { canvasFor, hidden }
}
