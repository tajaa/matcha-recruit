// The editing surface: a Konva Stage scaled to fit its container, with
// selection, drag-with-snapping, and a Transformer for resize/rotate.
//
// Coordinate model: the document is authored in ARTBOARD pixels (print units)
// and the Stage is scaled down to fit on screen. Nothing in the document ever
// stores a screen coordinate, so a 300dpi export is the same scene at a
// different pixelRatio.
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Layer, Line, Rect, Stage, Transformer } from 'react-konva'
import type Konva from 'konva'
import type { DesignLayer, FlyerDesign } from '../../api/types'
import { applyScaleToSize, layerBox } from '../../utils/designer'
import { BackgroundNode, LayerNode } from './LayerRenderer'

const SNAP_THRESHOLD = 8 // artboard px

export interface DesignerCanvasProps {
  design: FlyerDesign
  selectedId: string | null
  onSelect: (id: string | null) => void
  /** commit=false while a gesture is in flight, true on its end (one undo step). */
  onLayerChange: (id: string, patch: Partial<DesignLayer>, commit: boolean) => void
  onBeginTextEdit: (layer: Extract<DesignLayer, { type: 'text' }>, node: Konva.Text) => void
  /** QR rasters come from the page (useQrCanvases), which also owns the export gate. */
  qrCanvasFor: (size: number, fg: string, bg: string) => HTMLCanvasElement | undefined
  /** Hidden QRCodeCanvas hosts — must mount as a DOM sibling of the Stage. */
  qrHidden: ReactNode
  stickerSrc: (assetId: string) => string
  stageRef: React.RefObject<Konva.Stage | null>
  editingLayerId: string | null
  /** Text-edit textarea, positioned against the stage container. */
  overlay?: ReactNode
}

export function DesignerCanvas({
  design, selectedId, onSelect, onLayerChange, onBeginTextEdit,
  qrCanvasFor, qrHidden, stickerSrc, stageRef, editingLayerId, overlay,
}: DesignerCanvasProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const trRef = useRef<Konva.Transformer>(null)
  const contentRef = useRef<Konva.Layer>(null)
  const [scale, setScale] = useState(0.2)
  const [guides, setGuides] = useState<{ x: number[]; y: number[] }>({ x: [], y: [] })

  // Fit-to-container. ResizeObserver rather than a window listener so the
  // stage also reacts to the inspector panel collapsing beside it.
  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    function fit() {
      if (!el) return
      const pad = 32
      const cw = el.clientWidth - pad
      const ch = el.clientHeight - pad
      if (cw <= 0 || ch <= 0) return
      setScale(Math.min(cw / design.artboard.w, ch / design.artboard.h))
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [design.artboard.w, design.artboard.h])

  const selected = design.layers.find((l) => l.id === selectedId) ?? null

  // Attach the transformer to whatever is selected. Konva finds the node by
  // id inside the content layer; a selection that no longer exists (deleted
  // layer) detaches instead of throwing. A LOCKED layer attaches nothing:
  // LayerNode already refuses to drag it, and leaving resize/rotate handles
  // live made the lock a half-promise on the one layer (the QR) it exists to
  // protect.
  useEffect(() => {
    const tr = trRef.current
    const layer = contentRef.current
    if (!tr || !layer) return
    const node = selectedId && selectedId !== editingLayerId && !selected?.locked
      ? layer.findOne<Konva.Node>(`#${selectedId}`)
      : null
    tr.nodes(node ? [node] : [])
    tr.getLayer()?.batchDraw()
  }, [selectedId, editingLayerId, selected?.locked, design.layers])

  // Snap targets: artboard edges + centre, plus the edges/centres of every
  // other layer. Returns the adjusted position and the guide lines to draw.
  function snap(layer: DesignLayer, x: number, y: number) {
    const { w, h } = layerBox(layer)
    const vx: number[] = [0, design.artboard.w / 2, design.artboard.w]
    const hy: number[] = [0, design.artboard.h / 2, design.artboard.h]
    for (const other of design.layers) {
      if (other.id === layer.id) continue
      const { w: ow, h: oh } = layerBox(other)
      vx.push(other.x, other.x + ow / 2, other.x + ow)
      hy.push(other.y, other.y + oh / 2, other.y + oh)
    }
    let sx = x
    let sy = y
    const hitX: number[] = []
    const hitY: number[] = []
    for (const guide of vx) {
      for (const [edge, offset] of [[x, 0], [x + w / 2, w / 2], [x + w, w]] as const) {
        if (Math.abs(edge - guide) <= SNAP_THRESHOLD) { sx = guide - offset; hitX.push(guide) }
      }
    }
    for (const guide of hy) {
      for (const [edge, offset] of [[y, 0], [y + h / 2, h / 2], [y + h, h]] as const) {
        if (Math.abs(edge - guide) <= SNAP_THRESHOLD) { sy = guide - offset; hitY.push(guide) }
      }
    }
    return { x: Math.round(sx), y: Math.round(sy), guides: { x: [...new Set(hitX)], y: [...new Set(hitY)] } }
  }

  function handleDragMove(layer: DesignLayer, x: number, y: number) {
    const s = snap(layer, x, y)
    setGuides(s.guides)
    onLayerChange(layer.id, { x: s.x, y: s.y }, false)
  }

  function handleDragEnd(layer: DesignLayer, x: number, y: number) {
    const s = snap(layer, x, y)
    setGuides({ x: [], y: [] })
    onLayerChange(layer.id, { x: s.x, y: s.y }, true)
  }

  // Konva reports a resize as a scale factor on the node. The document has no
  // scale field, so the factor is folded into width/height/fontSize and the
  // node's scale is reset to 1 — otherwise the next transform would compound.
  function handleTransformEnd(layer: DesignLayer, node: Konva.Node) {
    const scaleX = node.scaleX()
    const scaleY = node.scaleY()
    node.scaleX(1)
    node.scaleY(1)
    onLayerChange(layer.id, {
      x: Math.round(node.x()),
      y: Math.round(node.y()),
      rotation: Math.round(node.rotation()),
      ...applyScaleToSize(layer, scaleX, scaleY),
    }, true)
  }

  return (
    <div ref={wrapRef} className="relative flex h-full w-full items-center justify-center overflow-hidden bg-tu-bg">
      {qrHidden}
      <div className="relative shadow-2xl" style={{ width: design.artboard.w * scale, height: design.artboard.h * scale }}>
        <Stage
          ref={stageRef}
          width={design.artboard.w * scale}
          height={design.artboard.h * scale}
          scaleX={scale}
          scaleY={scale}
          onMouseDown={(e) => { if (e.target === e.target.getStage()) onSelect(null) }}
          onTouchStart={(e) => { if (e.target === e.target.getStage()) onSelect(null) }}
        >
          <Layer ref={contentRef}>
            <BackgroundNode design={design} />
            {design.layers.map((layer) => (
              <LayerNode
                key={layer.id}
                layer={layer}
                stickerSrc={stickerSrc}
                qrCanvas={qrCanvasFor}
                draggable
                listening
                visible={layer.id !== editingLayerId}
                onSelect={() => onSelect(layer.id)}
                onDragMove={(x, y) => handleDragMove(layer, x, y)}
                onDragEnd={(x, y) => handleDragEnd(layer, x, y)}
                onDblClick={(node) => {
                  if (layer.type === 'text') onBeginTextEdit(layer, node as Konva.Text)
                }}
              />
            ))}
          </Layer>

          {/* Overlay layer: chrome only, never exported (ExportMenu hides it). */}
          <Layer name="designer-overlay" listening={!!selected}>
            <Rect
              x={0} y={0} width={design.artboard.w} height={design.artboard.h}
              stroke="#3f3f46" strokeWidth={1 / scale} listening={false}
            />
            {guides.x.map((gx) => (
              <Line key={`gx${gx}`} points={[gx, 0, gx, design.artboard.h]} stroke="#f97316" strokeWidth={1 / scale} dash={[6 / scale, 6 / scale]} listening={false} />
            ))}
            {guides.y.map((gy) => (
              <Line key={`gy${gy}`} points={[0, gy, design.artboard.w, gy]} stroke="#f97316" strokeWidth={1 / scale} dash={[6 / scale, 6 / scale]} listening={false} />
            ))}
            <Transformer
              ref={trRef}
              rotateEnabled={selected?.type !== 'qr'}
              keepRatio={selected?.type === 'qr' || selected?.type === 'sticker' || selected?.type === 'image'}
              enabledAnchors={
                selected?.type === 'qr'
                  ? ['top-left', 'top-right', 'bottom-left', 'bottom-right']
                  : undefined
              }
              borderStroke="#f97316"
              anchorStroke="#f97316"
              anchorFill="#18181b"
              anchorSize={10 / scale}
              borderStrokeWidth={1.5 / scale}
              onTransformEnd={(e) => { if (selected) handleTransformEnd(selected, e.target) }}
              boundBoxFunc={(oldBox, newBox) => (newBox.width < 16 || newBox.height < 16 ? oldBox : newBox)}
            />
          </Layer>
        </Stage>
        {overlay}
      </div>
    </div>
  )
}
