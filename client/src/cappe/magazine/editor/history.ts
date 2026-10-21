import { useCallback, useReducer } from 'react'

/** Edits closer together than this are one step of undo: typing a sentence
 *  undoes as a sentence, not a letter at a time. */
export const MERGE_MS = 1000
/** How many steps back undo can go. */
export const HISTORY_LIMIT = 200

export type History<T> = { past: T[]; present: T; future: T[]; at: number }

type Action<T> =
  | { kind: 'set'; next: (t: T) => T; step: boolean; now: number }
  | { kind: 'undo' }
  | { kind: 'redo' }
  | { kind: 'reset'; value: T }
  | { kind: 'replace'; value: T }

/** Pure: the history after one action. A `set` that changes nothing is
 *  ignored; one that lands within MERGE_MS of the last (and isn't a `step`,
 *  like adding or deleting a block) folds into the same undo step. */
export function historyReducer<T>(h: History<T>, a: Action<T>): History<T> {
  switch (a.kind) {
    case 'set': {
      const next = a.next(h.present)
      if (next === h.present) return h
      const merge = !a.step && h.past.length > 0 && a.now - h.at < MERGE_MS && h.future.length === 0
      const past = merge ? h.past : [...h.past, h.present].slice(-HISTORY_LIMIT)
      return { past, present: next, future: [], at: a.step ? 0 : a.now }
    }
    case 'undo': {
      if (!h.past.length) return h
      return { past: h.past.slice(0, -1), present: h.past[h.past.length - 1], future: [h.present, ...h.future], at: 0 }
    }
    case 'redo': {
      if (!h.future.length) return h
      return { past: [...h.past, h.present], present: h.future[0], future: h.future.slice(1), at: 0 }
    }
    case 'reset':
      return { past: [], present: a.value, future: [], at: 0 }
    case 'replace':
      // The same document, as the server saved it: no undo step of its own.
      return { ...h, present: a.value, at: 0 }
  }
}

/** A value with undo and redo. `set(fn)` records an edit (`{ step: true }`
 *  for one that should never merge with typing); `reset` starts a fresh
 *  history (a load); `replace` swaps the value without a step (a save). */
export function useHistory<T>(initial: T) {
  const [h, dispatch] = useReducer(historyReducer<T>, { past: [], present: initial, future: [], at: 0 })
  const set = useCallback((next: (t: T) => T, opts?: { step?: boolean }) =>
    dispatch({ kind: 'set', next, step: !!opts?.step, now: Date.now() }), [])
  const undo = useCallback(() => dispatch({ kind: 'undo' }), [])
  const redo = useCallback(() => dispatch({ kind: 'redo' }), [])
  const reset = useCallback((value: T) => dispatch({ kind: 'reset', value }), [])
  const replace = useCallback((value: T) => dispatch({ kind: 'replace', value }), [])
  return { value: h.present, canUndo: h.past.length > 0, canRedo: h.future.length > 0, set, undo, redo, reset, replace }
}
