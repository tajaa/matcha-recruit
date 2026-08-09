// Undo/redo + dirty tracking for the flyer designer document.
//
// The split that matters: `set(next)` updates the live document every frame
// (a drag emits dozens), `set(next, { commit: true })` additionally snapshots
// the PREVIOUS document into the undo stack. Callers commit on drag-end,
// transform-end, text blur, add/delete/reorder and style changes — never per
// pointermove or per keystroke, or one drag would cost 40 undo steps.
import { useCallback, useRef, useState } from 'react'
import type { FlyerDesign } from '../api/types'

const MAX_HISTORY = 50

export interface DesignHistory {
  design: FlyerDesign
  set: (next: FlyerDesign, opts?: { commit?: boolean }) => void
  /** Replace the document wholesale (load from server) and drop all history. */
  reset: (next: FlyerDesign) => void
  undo: () => void
  redo: () => void
  canUndo: boolean
  canRedo: boolean
  dirty: boolean
  markSaved: () => void
}

export function useDesignHistory(initial: FlyerDesign): DesignHistory {
  const [design, setDesign] = useState<FlyerDesign>(initial)
  const [past, setPast] = useState<FlyerDesign[]>([])
  const [future, setFuture] = useState<FlyerDesign[]>([])
  const [dirty, setDirty] = useState(false)

  // The committed baseline is held in a ref, not state: an uncommitted drag
  // mutates `design` on every frame, and undo has to rewind to the document as
  // it stood at the last commit, not to the middle of the gesture.
  const baseline = useRef<FlyerDesign>(initial)

  const set = useCallback((next: FlyerDesign, opts?: { commit?: boolean }) => {
    if (opts?.commit) {
      const prev = baseline.current
      setPast((p) => (prev === next ? p : [...p, prev].slice(-MAX_HISTORY)))
      setFuture([])
      baseline.current = next
    }
    setDesign(next)
    setDirty(true)
  }, [])

  const reset = useCallback((next: FlyerDesign) => {
    baseline.current = next
    setDesign(next)
    setPast([])
    setFuture([])
    setDirty(false)
  }, [])

  const undo = useCallback(() => {
    setPast((p) => {
      if (p.length === 0) return p
      const prev = p[p.length - 1]
      setFuture((f) => [baseline.current, ...f].slice(0, MAX_HISTORY))
      baseline.current = prev
      setDesign(prev)
      setDirty(true)
      return p.slice(0, -1)
    })
  }, [])

  const redo = useCallback(() => {
    setFuture((f) => {
      if (f.length === 0) return f
      const next = f[0]
      setPast((p) => [...p, baseline.current].slice(-MAX_HISTORY))
      baseline.current = next
      setDesign(next)
      setDirty(true)
      return f.slice(1)
    })
  }, [])

  const markSaved = useCallback(() => setDirty(false), [])

  return { design, set, reset, undo, redo, canUndo: past.length > 0, canRedo: future.length > 0, dirty, markSaved }
}
