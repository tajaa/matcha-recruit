import { useEffect, useReducer, useRef } from 'react'
import type { CappeBlock } from '../../../../types/cappe'

export type EditorSnapshot = {
  blocks: CappeBlock[]
  title: string
  meta: Record<string, unknown>
  theme: Record<string, unknown>
}

/** Undo/redo for the page editor. Snapshots blocks + title + meta + theme.
 *
 *  Recording is coalesced (500 ms) so a burst of keystrokes collapses to one
 *  entry, and suppressed while a restore is being applied. Equality is by
 *  reference on each field — React state keeps the same reference until its
 *  setter runs, so an untouched field never triggers a spurious record. */
export function useEditorHistory(snap: EditorSnapshot, apply: (s: EditorSnapshot) => void) {
  const present = useRef<EditorSnapshot>(snap)
  const latest = useRef<EditorSnapshot>(snap)
  const past = useRef<EditorSnapshot[]>([])
  const future = useRef<EditorSnapshot[]>([])
  const restoring = useRef(false)
  const [, bump] = useReducer((n: number) => n + 1, 0)

  const same = (a: EditorSnapshot, b: EditorSnapshot) =>
    a.blocks === b.blocks && a.title === b.title && a.meta === b.meta && a.theme === b.theme

  // Track the live snapshot every render so undo/redo can flush an edit that is
  // still inside the 500 ms record debounce (otherwise that edit is skipped and
  // lost — undo would jump two steps).
  latest.current = snap

  /** Commit an un-recorded live edit as a history checkpoint. Returns true if it
   *  recorded one. Mirrors the debounced recorder so the two never double-log. */
  const commitPending = (): boolean => {
    if (same(present.current, latest.current)) return false
    past.current.push(present.current)
    if (past.current.length > 50) past.current.shift()
    future.current = []
    present.current = latest.current
    return true
  }

  useEffect(() => {
    // A restore just applied this exact state — adopt it without recording.
    if (restoring.current) { restoring.current = false; present.current = snap; return }
    if (same(present.current, snap)) return
    const id = setTimeout(() => {
      if (same(present.current, snap)) return
      past.current.push(present.current)
      if (past.current.length > 50) past.current.shift()
      future.current = []
      present.current = snap
      bump()
    }, 500)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snap.blocks, snap.title, snap.meta, snap.theme])

  const undo = () => {
    commitPending() // fold any un-recorded live edit into history first
    if (!past.current.length) return
    const prev = past.current.pop() as EditorSnapshot
    future.current.push(present.current)
    present.current = prev
    restoring.current = true
    apply(prev)
    bump()
  }
  const redo = () => {
    // A live edit invalidates the redo stack (standard editor behavior).
    if (commitPending()) { bump(); return }
    if (!future.current.length) return
    const next = future.current.pop() as EditorSnapshot
    past.current.push(present.current)
    present.current = next
    restoring.current = true
    apply(next)
    bump()
  }
  /** Drop history and adopt `s` as the baseline — call once after initial load
   *  so the first undo doesn't rewind to the empty pre-load state. */
  const reset = (s: EditorSnapshot) => {
    past.current = []
    future.current = []
    present.current = s
    latest.current = s
    restoring.current = false
    bump()
  }

  const hasPendingEdit = !same(present.current, latest.current)
  return {
    undo, redo, reset,
    canUndo: past.current.length > 0 || hasPendingEdit,
    canRedo: future.current.length > 0 && !hasPendingEdit,
  }
}
