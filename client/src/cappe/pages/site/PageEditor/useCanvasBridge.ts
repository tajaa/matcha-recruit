import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type RefObject } from 'react'
import type { CappeBlock, CappeCanvasElement } from '../../../types'
import { CV_MAX_ELEMENTS, cvEls, cvNextY, cvNewElement, isCanvasBlock } from './canvasHelpers'
import { applyFieldPath } from './merlinOps'
import { decideSelect, decideSelectionUpdate, type PendingSelection } from './selectionContext'

/** `cz-selection` payload from the runtime (canvas.js:postSelection), resolved
 *  to the block's stable `_k` id at RECEIPT time (inside this hook's message
 *  handler, where `blocksRef` is live truth) rather than at send time — a
 *  block delete/insert/undo between the click and a later render can't
 *  silently repoint an old numeric index at a different block. If the
 *  reported index doesn't resolve to a real block, the existing selection is
 *  left untouched rather than cleared — the iframe's rendered DOM can lag
 *  parent `blocks` state (a debounced/suspended preview), so "can't resolve
 *  this index right now" is not the same claim as "the block is gone"; the
 *  staleness effect below is what actually clears a selection once its block
 *  is confirmed gone. */
export type CanvasSelection = {
  block: string
  /** `set_field`-style dot path (see server `BLOCK_FIELDS`) — null for a
   *  whole-block/element selection. Mutually exclusive with `element`. */
  field: string | null
  /** A freeform-canvas element id (`elements[].id`), addressed via
   *  `canvas_update`, not `set_field` — mutually exclusive with `field`. */
  element: string | null
  kind: 'text' | 'image' | 'button' | 'element'
  start: number | null
  end: number | null
  text: string | null
}

/** Canvas mode (Pro & Business): click-on-page editing via the preview iframe.
 *  Owns selection/breakpoint/floating-panel state, the freeform canvas-element
 *  mutators, and the postMessage bridge to the framed runtime. `iframeRef` is
 *  shared with the theme bridge (both modes reuse the one preview iframe). */
export function useCanvasBridge(
  blocks: CappeBlock[],
  setBlocks: (fn: (bs: CappeBlock[]) => CappeBlock[]) => void,
  iframeRef: RefObject<HTMLIFrameElement | null>,
  /** Right-edge space already claimed by a docked panel (the theme drawer), so
   *  the floating inspector — which is viewport-`fixed` — never slides under it. */
  reservedRight = 0,
  /** Form mode keeps the runtime's hover+click-select (for the form<->preview
   *  sync) but must suppress canvas-only affordances (inline edit, drag-reorder,
   *  element drag/resize) — told to the iframe via `cz-mode`. */
  editMode: 'form' | 'canvas' = 'canvas',
  /** An asset (AssetLibrary thumbnail, a Merlin-generated image) was dropped
   *  onto a section in the preview — set as that section's background. Lives
   *  outside this hook (it needs `merlin.applyImageTo`, a sibling hook in
   *  index.tsx), so it's a callback rather than local state here. */
  onDropImage?: (blockIdx: number, url: string) => void,
  /** Merlin is open: selection context is STICKY — a click on a different
   *  section stages a pending switch (confirmPendingSelection /
   *  dismissPendingSelection below) instead of repointing immediately, and an
   *  empty cz-selection shape can't silently downgrade a finer one to
   *  nothing. See selectionContext.ts for the decision logic. Form/Canvas
   *  editing without Merlin keeps today's immediate click-to-select — the
   *  floating inspector must follow clicks there. */
  stickySelection = false,
) {
  const [selBlock, setSelBlock] = useState<number | null>(null)
  const [selElement, setSelElement] = useState<string | null>(null)  // freeform canvas: selected element id
  // Merlin's highlight-driven selection (Phase 1 of the precision-design plan)
  // — a field, character range, or element kind within selBlock. Independent
  // of selElement (freeform canvas resize/drag state): a text-range highlight
  // inside a canvas heading sets both, a plain section click sets neither.
  const [selection, setSelection] = useState<CanvasSelection | null>(null)
  // A different section clicked while stickySelection is on and a context is
  // already active — parked here until the panel's "Switch" confirms it (or
  // its ✕ dismisses it, leaving the current context untouched).
  const [pendingSel, setPendingSel] = useState<PendingSelection | null>(null)
  const [canvasBp, setCanvasBp] = useState<'d' | 'm'>('d')            // freeform canvas: editing desktop vs mobile
  const [popPos, setPopPos] = useState<{ top: number; left: number }>({ top: 96, left: 96 })
  // Once the user drags the floating inspector, keep it where they put it (don't
  // re-anchor to the next clicked element); reset when the panel closes.
  const panelDragged = useRef(false)
  const reservedRightRef = useRef(0)
  reservedRightRef.current = reservedRight
  const maxLeft = () => window.innerWidth - 372 - reservedRightRef.current
  function startPanelDrag(e: ReactPointerEvent) {
    e.preventDefault()
    const sx = e.clientX, sy = e.clientY
    const orig = { ...popPos }
    const onMove = (ev: PointerEvent) => {
      panelDragged.current = true
      setPopPos({
        left: Math.min(Math.max(orig.left + (ev.clientX - sx), 8), maxLeft()),
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
  const suspendPreview = useRef(false)
  const [refreshTick, setRefreshTick] = useState(0)
  // Bumped on EVERY cz-select message (unlike selBlock, which is stable when
  // the same block is clicked twice) — consumers that must re-trigger on a
  // repeat click (form-mode card sync) key off this.
  const [selectSeq, setSelectSeq] = useState(0)
  // Refs mirror state for the (mount-once) postMessage handler — avoid stale closures.
  const selBlockRef = useRef<number | null>(null)
  const blocksRef = useRef<CappeBlock[]>([])
  const selElementRef = useRef<string | null>(null)
  const canvasBpRef = useRef<'d' | 'm'>('d')
  const stickyRef = useRef(stickySelection)
  const pendingSelRef = useRef<PendingSelection | null>(null)
  selBlockRef.current = selBlock
  blocksRef.current = blocks
  selElementRef.current = selElement
  canvasBpRef.current = canvasBp
  stickyRef.current = stickySelection
  pendingSelRef.current = pendingSel
  const postToCanvas = (msg: unknown) => iframeRef.current?.contentWindow?.postMessage(msg, '*')
  const editModeRef = useRef(editMode)
  editModeRef.current = editMode
  const onDropImageRef = useRef(onDropImage)
  onDropImageRef.current = onDropImage
  // Re-assert the interaction mode whenever it changes, and once more when a
  // fresh runtime signals ready (the iframe fully reloads on most edits, which
  // would otherwise silently reset restrictMode to its 'canvas' default).
  useEffect(() => { postToCanvas({ type: 'cz-mode', mode: editMode }) }, [editMode])
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

  // `selection` is keyed on a block's `_k`, so it survives reorders/undo for
  // free — but the block it names can still be deleted (or undone away)
  // entirely. Drop it the moment that happens, rather than letting a later
  // Merlin turn address a block that no longer exists.
  useEffect(() => {
    setSelection((s) => (s && !blocks.some((b) => b._k === s.block) ? null : s))
    setPendingSel((p) => (p && !blocks.some((b) => b._k === p.blockKey) ? null : p))
  }, [blocks])

  // Sticky mode just turned off (Merlin closed) — a staged switch has no UI
  // left to confirm/dismiss it, so drop it rather than leave it dangling.
  useEffect(() => {
    if (!stickySelection) setPendingSel(null)
  }, [stickySelection])

  // Canvas bridge: the framed runtime posts selection/edit/reorder events; we
  // validate by source identity (the iframe is opaque-origin, so `e.origin` is
  // "null" — never check it). Mounted once; reads live state via refs.
  useEffect(() => {
    function onMsg(e: MessageEvent) {
      if (e.source !== iframeRef.current?.contentWindow) return
      const d = e.data || {}
      switch (d.type) {
        case 'cz-ready': {
          postToCanvas({ type: 'cz-mode', mode: editModeRef.current })
          const sb = selBlockRef.current
          if (sb != null) {
            if (isCanvasBlock(blocksRef.current[sb]) && selElementRef.current) postToCanvas({ type: 'cz-elem-highlight', id: selElementRef.current })
            else postToCanvas({ type: 'cz-highlight', block: sb })
          }
          // Only canvas mode ever narrows the iframe for the mobile breakpoint
          // (CanvasModeView); replaying it while a fresh runtime loads under
          // Form's restrict-mode (Form itself, or Merlin riding 'form' — see
          // index.tsx) would activate the mobile @media layout inside a
          // full-width iframe with no way to toggle back.
          if (editModeRef.current === 'canvas' && canvasBpRef.current === 'm') postToCanvas({ type: 'cz-bp', bp: 'm' })
          break
        }
        case 'cz-select': {
          const decision = decideSelect({
            sticky: stickyRef.current,
            currentBlock: selBlockRef.current,
            incomingBlock: d.block,
            incomingKey: blocksRef.current[d.block]?._k as string | undefined,
          })
          if (decision.action === 'stage') {
            // Park the switch — don't touch selBlock/selection/highlight yet.
            // The panel's "Switch" button calls confirmPendingSelection below;
            // its ✕ calls dismissPendingSelection, leaving the current
            // context exactly as it was.
            setPendingSel(decision.pending)
            break
          }
          setPendingSel(null)  // an applied select supersedes any staged switch
          setSelBlock(d.block)
          setSelectSeq((n) => n + 1)
          const onEl = isCanvasBlock(blocksRef.current[d.block]) && d.field != null
          setSelElement(onEl ? d.field : null)
          // Anchor the floating editor near the clicked element (iframe rect +
          // element rect → parent viewport), clamped on-screen — unless the user
          // has dragged the panel somewhere, in which case leave it.
          const fr = iframeRef.current?.getBoundingClientRect()
          if (!panelDragged.current && fr && d.rect) {
            const left = Math.min(Math.max(fr.left + d.rect.left + 8, 8), maxLeft())
            const top = Math.min(Math.max(fr.top + d.rect.top + 8, 64), window.innerHeight - 160)
            setPopPos({ top, left })
          }
          // A canvas element already shows resize handles in the iframe; re-highlighting
          // the section would clear them, so only highlight non-element selections.
          if (!onEl) postToCanvas({ type: 'cz-highlight', block: d.block })
          break
        }
        case 'cz-selection': {
          const blockKey = blocksRef.current[d.block]?._k as string | undefined
          // An index that doesn't resolve (the iframe's rendered DOM lagging
          // parent `blocks` state — e.g. a debounced/suspended preview after
          // a delete) means "can't tell what this points at now", not "the
          // user's existing selection is gone" — leave it alone rather than
          // wiping a still-valid highlight.
          if (!blockKey) break
          const next: CanvasSelection = {
            block: blockKey, field: d.field ?? null, element: d.element ?? null, kind: d.kind || 'text',
            start: d.start ?? null, end: d.end ?? null, text: d.text ?? null,
          }
          const verdict = decideSelectionUpdate({ sticky: stickyRef.current, pending: pendingSelRef.current, next })
          if (verdict === 'stage') {
            // Detail for the block already staged as pending — ride it there
            // so Switch applies the full context, not just the bare section.
            setPendingSel((p) => (p ? { ...p, selection: next } : p))
            break
          }
          if (verdict === 'ignore') {
            // Sticky + an empty shape (dead-space click inside the CURRENT
            // section): this used to silently downgrade a fine "Editing: …"
            // chip to nothing. Ignore it — the existing selection stands.
            break
          }
          setSelection(next)
          break
        }
        case 'cz-edit': {
          // Defense in depth against an image field ever reaching contenteditable
          // (canvas.js's dblclick handler is the primary guard, and blur now
          // tells us the kind it saw) — never let typed text overwrite an image
          // URL even if that guard is ever bypassed or the attribute is dropped.
          if (d.kind === 'image') break
          const b = blocksRef.current[d.block]
          if (isCanvasBlock(b)) {
            setBlocks((bs) => bs.map((x, j) => (j === d.block ? { ...x, elements: cvEls(x).map((el) => (el.id === d.field ? { ...el, text: d.value } : el)) } : x)))
            // Same re-anchor as the non-canvas branch below, for a freeform
            // canvas element: the selection's range is offsets into the OLD
            // element text, which this edit just moved or deleted.
            setSelection((s) => {
              if (!s || s.block !== b?._k || s.element !== d.field) return s
              if (s.start == null || s.end == null || !s.text) return s
              const idx = typeof d.value === 'string' ? d.value.indexOf(s.text) : -1
              return idx === -1 ? { ...s, start: null, end: null, text: null } : { ...s, start: idx, end: idx + s.text.length }
            })
          } else if (b) {
            // `d.field` is a set_field-style dot path (a list-item field like
            // "items.2.title" is addressable since P0's full-coverage tagging) —
            // route through the same applyFieldPath the Merlin op applier uses,
            // not a literal top-level `{[d.field]: d.value}` assign, which would
            // write a bogus key named "items.2.title" instead of descending
            // into the array.
            const updated = applyFieldPath(b, d.field, d.value)
            if (!updated) {
              // The render side is expected to only ever emit a path
              // BLOCK_FIELDS actually supports (server/app/cappe/services/
              // merlin/catalog.py) — reaching here means that invariant broke
              // somewhere upstream. The user's typed edit is dropped either
              // way (writing a bogus top-level key was the worse alternative,
              // see applyFieldPath's own doc), but this should never be
              // silent — there's no toast plumbed into this hook.
              console.warn(`cz-edit: "${d.field}" doesn't match block ${b.type}'s shape — edit dropped`)
              break
            }
            setBlocks((bs) => bs.map((x, j) => (j === d.block ? updated : x)))
            // The current selection's range is offsets into the OLD field
            // value — an edit to that same field just moved or deleted the
            // text it names. Re-anchor by searching the new value for the
            // same substring (same idea as the server's own re-anchor in
            // turn.py); drop the range (fall back to whole-field) if the
            // text is gone, rather than keep pointing at stale offsets.
            setSelection((s) => {
              if (!s || s.block !== updated._k || s.field !== d.field) return s
              if (s.start == null || s.end == null || !s.text) return s
              const idx = typeof d.value === 'string' ? d.value.indexOf(s.text) : -1
              return idx === -1 ? { ...s, start: null, end: null, text: null } : { ...s, start: idx, end: idx + s.text.length }
            })
          }
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
          // `selection` is NOT cleared here — it's keyed on the block's stable
          // `_k` (resolved at cz-selection receipt), not the numeric index a
          // reorder shifts, so the highlighted field is still valid at its
          // new position. The staleness effect below only drops it once the
          // block itself is actually gone.
          break
        case 'cz-drop-image': {
          // Only accept https URLs — the dropped value comes from the
          // sandboxed iframe's dataTransfer, sourced from our own draggable
          // thumbnails, but it's still untrusted input crossing a frame
          // boundary. Block index is validated by the eventual `_k` lookup
          // in index.tsx (an out-of-range index there is just a no-op).
          const url = typeof d.url === 'string' ? d.url : ''
          if (url.startsWith('https://') && typeof d.block === 'number') {
            onDropImageRef.current?.(d.block, url)
          }
          break
        }
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

  // The panel's "Switch" button — apply the staged section as the real
  // context. Re-resolves the pending `_k` at confirm time (not the click
  // time it was staged): a Merlin edit landing in between is fine, and a
  // block that got deleted in between just makes this a no-op (the
  // staleness effect above will have already cleared pendingSel).
  const confirmPendingSelection = () => {
    const p = pendingSel
    setPendingSel(null)
    if (!p) return
    const idx = blocks.findIndex((b) => b._k === p.blockKey)
    if (idx === -1) return
    setSelBlock(idx)
    setSelElement(null)
    setSelection(p.selection)
    setSelectSeq((n) => n + 1)
    postToCanvas({ type: 'cz-highlight', block: idx })
  }
  // The panel's ✕ on the pending row — keep the current context, discard
  // what was staged.
  const dismissPendingSelection = () => setPendingSel(null)
  // The coarse chip's ✕ — full context dismissal. Previously unreachable in
  // Merlin mode (only CanvasModeView's floating-inspector close button sent
  // cz-clear, and that view isn't rendered under Merlin).
  const clearSelectedContext = () => {
    setSelBlock(null)
    setSelElement(null)
    setSelection(null)
    setPendingSel(null)
    postToCanvas({ type: 'cz-clear' })
  }

  return {
    selBlock, setSelBlock,
    selElement, setSelElement,
    selection, setSelection,
    pendingSelection: pendingSel,
    confirmPendingSelection,
    dismissPendingSelection,
    clearSelectedContext,
    canvasBp, setCanvasBreakpoint,
    popPos,
    panelDragged,
    startPanelDrag,
    iframeRef,
    suspendPreview,
    refreshTick,
    selectSeq,
    postToCanvas,
    patchCanvasElement,
    addCanvasElement,
    removeCanvasElement,
  }
}
