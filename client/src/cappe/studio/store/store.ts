// The Studio's state, outside React: the document, what is selected, the
// tool, the view, the undo history and the save state. Panels read it with
// `useStudio(select)` (useSyncExternalStore); pointer work on the canvas
// reads and writes it directly, so a drag never renders React.
//
// Every change to the document goes through `edit`, which composes the text
// again (compose.composeDoc) before the new document is kept, so a document
// in the store is always set exactly as the pages show it. Edits that belong
// together (one drag, a burst of typing) share a `key` and are one undo step.

import { useSyncExternalStore } from 'react'
import { composeDoc, type Measure } from '../compose/compose'
import type { Asset, Doc } from '../model/types'

export type Tool = 'select' | 'text' | 'frame' | 'rect' | 'ellipse' | 'line' | 'hand' | 'zoom'
export type SaveState = 'saved' | 'dirty' | 'saving' | 'error' | 'conflict'
export type Panel = 'pages' | 'props' | 'character' | 'paragraph' | 'story'

export type View = {
  zoom: number // screen px per pt
  rulers: boolean
  guides: boolean
  margins: boolean
  baseline: boolean
  grid: boolean
  snap: boolean
}

export type State = {
  doc: Doc
  selection: string[]
  /** The text being typed in: its thread, and the text selection in it. */
  editing: { thread: string; anchor: [number, number]; head: [number, number] } | null
  page: number
  tool: Tool
  view: View
  panels: Panel[]
  overset: Set<string>
  assets: Record<string, Asset>
  save: { rev: number; state: SaveState; message: string | null; draft: boolean; live: boolean }
  /** A thread port clicked: the next text frame clicked joins this thread. */
  threading: { thread: string | null; frame: string } | null
  /** `picture`: the Picture Editor on the picture frame selected; `cutout`: it, open at the cut-out. */
  dialog: null | 'library' | 'story' | 'revisions' | 'preview' | 'picture' | 'cutout'
  /** The guide, open at this section (`ui/guideContent.ts`); it can open over a dialog. */
  guide: string | null
  /** While dragging: the lines an edge snapped to, and the marquee (pasteboard pt). */
  snaps: { x: number[]; y: number[] } | null
  marquee: { x: number; y: number; w: number; h: number } | null
}

type Listener = () => void
const HISTORY = 200
const COALESCE_MS = 1200

export class Store {
  private state: State
  private listeners = new Set<Listener>()
  private past: Doc[] = []
  private future: Doc[] = []
  private lastKey: string | null = null
  private lastAt = 0
  /** Called after each change to the document (autosave). */
  onDocChange: ((doc: Doc) => void) | null = null

  measure: Measure

  constructor(initial: State, measure: Measure) {
    this.measure = measure
    const { doc, overset } = composeDoc(initial.doc, measure)
    this.state = { ...initial, doc, overset }
  }

  get = (): State => this.state

  subscribe = (fn: Listener): (() => void) => {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  /** Change what isn't the document (selection, tool, view...). */
  set(patch: Partial<State> | ((s: State) => Partial<State>)): void {
    const next = typeof patch === 'function' ? patch(this.state) : patch
    this.state = { ...this.state, ...next }
    this.emit()
  }

  /** Change the document. `key`: edits with the same key within a moment are
   *  one undo step. */
  edit(fn: (doc: Doc) => Doc, { key = null, extra }: { key?: string | null; extra?: Partial<State> } = {}): void {
    const before = this.state.doc
    const changed = fn(before)
    if (changed === before) {
      if (extra) this.set(extra)
      return
    }
    const { doc, overset } = composeDoc(changed, this.measure)
    const now = Date.now()
    if (!(key && key === this.lastKey && now - this.lastAt < COALESCE_MS)) {
      this.past.push(before)
      if (this.past.length > HISTORY) this.past.shift()
    }
    this.lastKey = key
    this.lastAt = now
    this.future = []
    this.state = { ...this.state, ...extra, doc, overset, save: { ...this.state.save, state: 'dirty' } }
    this.emit()
    this.onDocChange?.(doc)
  }

  /** Close the current undo step (a drag ended, typing paused). */
  seal(): void {
    this.lastKey = null
  }

  /** Compose again (a face finished loading). */
  recompose(): void {
    const { doc, overset } = composeDoc(this.state.doc, this.measure, true)
    if (doc === this.state.doc && overset.size === this.state.overset.size) return
    this.state = { ...this.state, doc, overset }
    this.emit()
  }

  canUndo = () => this.past.length > 0
  canRedo = () => this.future.length > 0

  undo(): void {
    const prev = this.past.pop()
    if (!prev) return
    this.future.push(this.state.doc)
    this.restore(prev)
  }

  redo(): void {
    const next = this.future.pop()
    if (!next) return
    this.past.push(this.state.doc)
    this.restore(next)
  }

  private restore(doc: Doc): void {
    this.lastKey = null
    const ids = new Set(doc.items.map((i) => i.id))
    const threads = new Set(doc.threads.map((t) => t.id))
    const composed = composeDoc(doc, this.measure)
    this.state = {
      ...this.state, doc: composed.doc, overset: composed.overset,
      selection: this.state.selection.filter((id) => ids.has(id)),
      editing: this.state.editing && threads.has(this.state.editing.thread) ? this.state.editing : null,
      page: Math.min(this.state.page, doc.pages.length - 1),
      save: { ...this.state.save, state: 'dirty' },
    }
    this.emit()
    this.onDocChange?.(composed.doc)
  }

  /** Replace the document without history (a reload, a restored version). */
  replace(doc: Doc, extra: Partial<State> = {}): void {
    this.past = []
    this.future = []
    this.lastKey = null
    const composed = composeDoc(doc, this.measure)
    this.state = { ...this.state, ...extra, doc: composed.doc, overset: composed.overset, selection: [], editing: null,
      page: Math.min(this.state.page, doc.pages.length - 1) }
    this.emit()
  }

  private emit(): void {
    for (const fn of this.listeners) fn()
  }
}

/** A slice of the Studio's state, re-rendering when it changes. */
export function useStudio<T>(store: Store, select: (s: State) => T): T {
  return useSyncExternalStore(store.subscribe, () => select(store.get()))
}

export const DEFAULT_VIEW: View = { zoom: 1, rulers: true, guides: true, margins: true, baseline: false, grid: false,
  snap: true }
