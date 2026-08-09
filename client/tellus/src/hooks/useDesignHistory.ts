// Undo/redo + dirty tracking for the flyer designer document.
//
// The split that matters: `set(next)` updates the live document every frame
// (a drag emits dozens), `set(next, { commit: true })` additionally snapshots
// the PREVIOUS document into the undo stack. Callers commit on drag-end,
// transform-end, text blur, add/delete/reorder and style changes — never per
// pointermove or per keystroke, or one drag would cost 40 undo steps.
//
// All five transitions run through ONE reducer rather than a cluster of
// setState calls. The earlier shape called setFuture/setDesign/setDirty and
// mutated a baseline ref from inside a setPast updater; React StrictMode
// double-invokes updaters to surface exactly that impurity, so a single undo
// pushed two entries onto the redo stack. A reducer makes each transition a
// single pure function of the previous state.
import { useCallback, useMemo, useReducer } from 'react'
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
  /**
   * Clear the dirty flag — but ONLY if `saved` is still the live document.
   * An edit made while the PUT was in flight must stay dirty, or its pending
   * autosave is cancelled, the toolbar claims "All changes saved", and the
   * beforeunload guard unregisters while the newer edit was never sent.
   */
  markSaved: (saved: FlyerDesign) => void
}

interface HistoryState {
  design: FlyerDesign
  past: FlyerDesign[]
  future: FlyerDesign[]
  // The committed baseline is part of the state, not a ref: an uncommitted drag
  // mutates `design` on every frame, and undo has to rewind to the document as
  // it stood at the last commit, not to the middle of the gesture.
  baseline: FlyerDesign
  dirty: boolean
}

type HistoryAction =
  | { type: 'set'; next: FlyerDesign; commit: boolean }
  | { type: 'reset'; next: FlyerDesign }
  | { type: 'undo' }
  | { type: 'redo' }
  | { type: 'saved'; saved: FlyerDesign }

function reduce(s: HistoryState, a: HistoryAction): HistoryState {
  switch (a.type) {
    case 'set': {
      if (!a.commit) return { ...s, design: a.next, dirty: true }
      const past = s.baseline === a.next ? s.past : [...s.past, s.baseline].slice(-MAX_HISTORY)
      return { design: a.next, past, future: [], baseline: a.next, dirty: true }
    }
    case 'reset':
      return { design: a.next, past: [], future: [], baseline: a.next, dirty: false }
    case 'undo': {
      if (s.past.length === 0) return s
      const prev = s.past[s.past.length - 1]
      return {
        design: prev,
        past: s.past.slice(0, -1),
        future: [s.baseline, ...s.future].slice(0, MAX_HISTORY),
        baseline: prev,
        dirty: true,
      }
    }
    case 'redo': {
      if (s.future.length === 0) return s
      const next = s.future[0]
      return {
        design: next,
        past: [...s.past, s.baseline].slice(-MAX_HISTORY),
        future: s.future.slice(1),
        baseline: next,
        dirty: true,
      }
    }
    case 'saved':
      return s.dirty && s.design === a.saved ? { ...s, dirty: false } : s
  }
}

export function useDesignHistory(initial: FlyerDesign): DesignHistory {
  const [state, dispatch] = useReducer(reduce, initial, (d) => ({
    design: d, past: [], future: [], baseline: d, dirty: false,
  }))

  const set = useCallback(
    (next: FlyerDesign, opts?: { commit?: boolean }) => dispatch({ type: 'set', next, commit: !!opts?.commit }),
    [],
  )
  const reset = useCallback((next: FlyerDesign) => dispatch({ type: 'reset', next }), [])
  const undo = useCallback(() => dispatch({ type: 'undo' }), [])
  const redo = useCallback(() => dispatch({ type: 'redo' }), [])
  const markSaved = useCallback((saved: FlyerDesign) => dispatch({ type: 'saved', saved }), [])

  return useMemo(() => ({
    design: state.design,
    set,
    reset,
    undo,
    redo,
    canUndo: state.past.length > 0,
    canRedo: state.future.length > 0,
    dirty: state.dirty,
    markSaved,
  }), [state, set, reset, undo, redo, markSaved])
}
