import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import type { CappeBlock, CappeCanvasElement } from '../../../../types/cappe'
import { CV_MAX_ELEMENTS, cvEls, cvNextY, cvNewElement, isCanvasBlock } from './canvasHelpers'

/** Canvas mode (Pro & Business): click-on-page editing via the preview iframe.
 *  Owns selection/breakpoint/floating-panel state, the freeform canvas-element
 *  mutators, and the postMessage bridge to the framed runtime. */
export function useCanvasBridge(blocks: CappeBlock[], setBlocks: (fn: (bs: CappeBlock[]) => CappeBlock[]) => void) {
  const [selBlock, setSelBlock] = useState<number | null>(null)
  const [selElement, setSelElement] = useState<string | null>(null)  // freeform canvas: selected element id
  const [canvasBp, setCanvasBp] = useState<'d' | 'm'>('d')            // freeform canvas: editing desktop vs mobile
  const [popPos, setPopPos] = useState<{ top: number; left: number }>({ top: 96, left: 96 })
  // Once the user drags the floating inspector, keep it where they put it (don't
  // re-anchor to the next clicked element); reset when the panel closes.
  const panelDragged = useRef(false)
  function startPanelDrag(e: ReactPointerEvent) {
    e.preventDefault()
    const sx = e.clientX, sy = e.clientY
    const orig = { ...popPos }
    const onMove = (ev: PointerEvent) => {
      panelDragged.current = true
      setPopPos({
        left: Math.min(Math.max(orig.left + (ev.clientX - sx), 8), window.innerWidth - 372),
        top: Math.min(Math.max(orig.top + (ev.clientY - sy), 8), window.innerHeight - 80),
      })
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const suspendPreview = useRef(false)
  const [refreshTick, setRefreshTick] = useState(0)
  // Refs mirror state for the (mount-once) postMessage handler — avoid stale closures.
  const selBlockRef = useRef<number | null>(null)
  const blocksRef = useRef<CappeBlock[]>([])
  const selElementRef = useRef<string | null>(null)
  const canvasBpRef = useRef<'d' | 'm'>('d')
  selBlockRef.current = selBlock
  blocksRef.current = blocks
  selElementRef.current = selElement
  canvasBpRef.current = canvasBp
  const postToCanvas = (msg: unknown) => iframeRef.current?.contentWindow?.postMessage(msg, '*')
  // Flip desktop/mobile editing: tell the canvas runtime (so drags write the right
  // coords) and narrow the preview iframe so the mobile @media layout activates.
  const setCanvasBreakpoint = (bp: 'd' | 'm') => { setCanvasBp(bp); postToCanvas({ type: 'cz-bp', bp }) }
  const patchCanvasElement = (blockIdx: number, id: string, fn: (e: CappeCanvasElement) => CappeCanvasElement) =>
    setBlocks((bs) => bs.map((b, i) => (i !== blockIdx ? b : { ...b, elements: cvEls(b).map((e) => (e.id === id ? fn(e) : e)) })))
  const addCanvasElement = (blockIdx: number, kind: CappeCanvasElement['kind']) => {
    const b = blocks[blockIdx]
    if (!b || cvEls(b).length >= CV_MAX_ELEMENTS) return
    const ne = cvNewElement(kind, cvNextY(cvEls(b)))
    setBlocks((bs) => bs.map((x, i) => (i !== blockIdx ? x : { ...x, elements: [...cvEls(x), ne] })))
    setSelElement(ne.id)
  }
  const removeCanvasElement = (blockIdx: number, id: string) => {
    setBlocks((bs) => bs.map((b, i) => (i !== blockIdx ? b : { ...b, elements: cvEls(b).filter((e) => e.id !== id) })))
    setSelElement((cur) => (cur === id ? null : cur))
  }

  // Canvas bridge: the framed runtime posts selection/edit/reorder events; we
  // validate by source identity (the iframe is opaque-origin, so `e.origin` is
  // "null" — never check it). Mounted once; reads live state via refs.
  useEffect(() => {
    function onMsg(e: MessageEvent) {
      if (e.source !== iframeRef.current?.contentWindow) return
      const d = e.data || {}
      switch (d.type) {
        case 'cz-ready': {
          const sb = selBlockRef.current
          if (sb != null) {
            if (isCanvasBlock(blocksRef.current[sb]) && selElementRef.current) postToCanvas({ type: 'cz-elem-highlight', id: selElementRef.current })
            else postToCanvas({ type: 'cz-highlight', block: sb })
          }
          if (canvasBpRef.current === 'm') postToCanvas({ type: 'cz-bp', bp: 'm' })
          break
        }
        case 'cz-select': {
          setSelBlock(d.block)
          const onEl = isCanvasBlock(blocksRef.current[d.block]) && d.field != null
          setSelElement(onEl ? d.field : null)
          // Anchor the floating editor near the clicked element (iframe rect +
          // element rect → parent viewport), clamped on-screen — unless the user
          // has dragged the panel somewhere, in which case leave it.
          const fr = iframeRef.current?.getBoundingClientRect()
          if (!panelDragged.current && fr && d.rect) {
            const left = Math.min(Math.max(fr.left + d.rect.left + 8, 8), window.innerWidth - 372)
            const top = Math.min(Math.max(fr.top + d.rect.top + 8, 64), window.innerHeight - 160)
            setPopPos({ top, left })
          }
          // A canvas element already shows resize handles in the iframe; re-highlighting
          // the section would clear them, so only highlight non-element selections.
          if (!onEl) postToCanvas({ type: 'cz-highlight', block: d.block })
          break
        }
        case 'cz-edit': {
          const b = blocksRef.current[d.block]
          if (isCanvasBlock(b)) setBlocks((bs) => bs.map((x, j) => (j === d.block ? { ...x, elements: cvEls(x).map((el) => (el.id === d.field ? { ...el, text: d.value } : el)) } : x)))
          else if (b) setBlocks((bs) => bs.map((x, j) => (j === d.block ? { ...x, [d.field]: d.value } : x)))
          break
        }
        case 'cz-elem-move':
        case 'cz-elem-resize': {
          const bp = d.bp === 'm' ? 'm' : 'd'
          const p = d.pos || {}
          const pos = { x: Math.max(0, p.x | 0), y: Math.max(0, p.y | 0), w: Math.max(1, p.w | 0), h: Math.max(1, p.h | 0) }
          setBlocks((bs) => bs.map((x, j) => (j === d.block ? { ...x, elements: cvEls(x).map((el) => (el.id === d.id ? { ...el, [bp]: pos } : el)) } : x)))
          break
        }
        case 'cz-reorder':
          setBlocks((bs) => {
            const next = [...bs]
            const [moved] = next.splice(d.from, 1)
            next.splice(d.to, 0, moved)
            return next
          })
          setSelBlock(d.to)
          setSelElement(null)  // a freeform element selection doesn't survive a section move
          break
        case 'cz-editing-start':
          suspendPreview.current = true
          break
        case 'cz-editing-end':
          suspendPreview.current = false
          setRefreshTick((n) => n + 1)
          break
      }
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [])

  return {
    selBlock, setSelBlock,
    selElement, setSelElement,
    canvasBp, setCanvasBreakpoint,
    popPos,
    panelDragged,
    startPanelDrag,
    iframeRef,
    suspendPreview,
    refreshTick,
    postToCanvas,
    patchCanvasElement,
    addCanvasElement,
    removeCanvasElement,
  }
}
