// Maps one document layer onto its Konva node.
//
// Every raster source is loaded with crossOrigin='anonymous'. Without it a
// brand logo served from the public CloudFront bucket taints the canvas and
// stage.toDataURL() throws a SecurityError at export time — the failure shows
// up only when someone tries to download their flyer, so it is set here once
// for every image path rather than per-callsite.
import { useEffect, useState } from 'react'
import { Circle, Image as KonvaImage, Line, Rect, Text } from 'react-konva'
import type Konva from 'konva'
import type { DesignLayer } from '../../api/types'

function useHtmlImage(src: string | null): HTMLImageElement | undefined {
  const [img, setImg] = useState<HTMLImageElement>()
  useEffect(() => {
    if (!src) { setImg(undefined); return }
    let alive = true
    const el = new window.Image()
    el.crossOrigin = 'anonymous'
    el.onload = () => { if (alive) setImg(el) }
    el.onerror = () => { if (alive) setImg(undefined) }
    el.src = src
    return () => { alive = false }
  }, [src])
  return img
}

export interface LayerNodeProps {
  layer: DesignLayer
  stickerSrc: (assetId: string) => string
  qrCanvas: (size: number, fg: string, bg: string) => HTMLCanvasElement | undefined
  draggable: boolean
  listening: boolean
  onSelect?: () => void
  onDragMove?: (x: number, y: number) => void
  onDragEnd?: (x: number, y: number) => void
  onDblClick?: (node: Konva.Node) => void
  visible?: boolean
}

export function LayerNode({
  layer, stickerSrc, qrCanvas, draggable, listening, onSelect, onDragMove, onDragEnd, onDblClick, visible = true,
}: LayerNodeProps) {
  const imageSrc = layer.type === 'image' ? layer.src : layer.type === 'sticker' ? stickerSrc(layer.assetId) : null
  const img = useHtmlImage(imageSrc)

  const common = {
    id: layer.id,
    name: 'layer',
    x: layer.x,
    y: layer.y,
    rotation: layer.rotation,
    opacity: layer.opacity,
    visible,
    draggable: draggable && !layer.locked,
    listening,
    onMouseDown: onSelect,
    onTouchStart: onSelect,
    onDragMove: (e: Konva.KonvaEventObject<DragEvent>) => onDragMove?.(Math.round(e.target.x()), Math.round(e.target.y())),
    onDragEnd: (e: Konva.KonvaEventObject<DragEvent>) => onDragEnd?.(Math.round(e.target.x()), Math.round(e.target.y())),
    onDblClick: (e: Konva.KonvaEventObject<MouseEvent>) => onDblClick?.(e.target),
    onDblTap: (e: Konva.KonvaEventObject<TouchEvent>) => onDblClick?.(e.target),
  }

  switch (layer.type) {
    case 'text':
      return (
        <Text
          {...common}
          text={layer.text}
          fontFamily={layer.fontFamily}
          fontSize={layer.fontSize}
          fontStyle={layer.fontStyle}
          fill={layer.fill}
          align={layer.align}
          width={layer.width}
          lineHeight={layer.lineHeight}
          letterSpacing={layer.letterSpacing}
          wrap="word"
        />
      )
    case 'image':
    case 'sticker':
      if (!img) return null
      return <KonvaImage {...common} image={img} width={layer.width} height={layer.height} />
    case 'qr': {
      const canvas = qrCanvas(layer.size, layer.fg, layer.bg)
      // Placeholder rather than nothing while the raster is a frame behind —
      // and it is what template thumbnails render, since those have no
      // campaign (and therefore no claim URL) to encode. Deliberately drawn as
      // a dashed outline, NOT a solid fg-coloured block: a solid block is
      // indistinguishable from a dark QR, so an export that caught this frame
      // looked like a finished flyer. (ExportMenu also awaits the raster now —
      // this is the visual backstop.)
      if (!canvas) {
        return (
          <Rect
            {...common}
            width={layer.size}
            height={layer.size}
            fill={layer.bg}
            stroke={layer.fg}
            strokeWidth={Math.max(2, layer.size * 0.02)}
            dash={[layer.size * 0.08, layer.size * 0.06]}
          />
        )
      }
      return <KonvaImage {...common} image={canvas} width={layer.size} height={layer.size} />
    }
    case 'shape':
      if (layer.shape === 'circle') {
        // Konva circles are centre-anchored; the document stores every layer
        // top-left, so offset by the radius to keep one coordinate convention.
        const r = layer.width / 2
        return (
          <Circle
            {...common}
            x={layer.x + r}
            y={layer.y + r}
            radius={r}
            fill={layer.fill}
            stroke={layer.stroke}
            strokeWidth={layer.strokeWidth}
          />
        )
      }
      if (layer.shape === 'line') {
        return (
          <Line
            {...common}
            points={[0, 0, layer.width, 0]}
            stroke={layer.stroke || layer.fill}
            strokeWidth={layer.height}
            lineCap="round"
          />
        )
      }
      return (
        <Rect
          {...common}
          width={layer.width}
          height={layer.height}
          fill={layer.fill}
          stroke={layer.stroke}
          strokeWidth={layer.strokeWidth}
          cornerRadius={layer.cornerRadius}
        />
      )
  }
}

export function BackgroundNode({ design }: { design: { artboard: { w: number; h: number }; background: DesignBackground } }) {
  const src = design.background.kind === 'image' ? design.background.src : null
  const img = useHtmlImage(src)
  const { w, h } = design.artboard
  if (design.background.kind === 'color') {
    return <Rect x={0} y={0} width={w} height={h} fill={design.background.color} listening={false} />
  }
  if (!img) return <Rect x={0} y={0} width={w} height={h} fill="#ffffff" listening={false} />
  // 'cover': scale up to fill, centre the overflow.
  const scale = Math.max(w / img.width, h / img.height)
  const dw = img.width * scale
  const dh = img.height * scale
  return <KonvaImage image={img} x={(w - dw) / 2} y={(h - dh) / 2} width={dw} height={dh} listening={false} />
}

type DesignBackground = { kind: 'color'; color: string } | { kind: 'image'; src: string; fit: 'cover' }
