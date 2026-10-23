// Everything the Studio can do from a menu, a key or a button: one list, so a
// menu shows the key that does the same thing.

import { boardOffset } from '../canvas/geometry'
import { allIds, newId } from '../model/doc'
import { addPages, arrange, deleteItems, deletePage, duplicate, movePage, patchItems, type Arrange } from '../model/ops'
import type { Doc, Item, Thread } from '../model/types'
import type { State, Tool } from '../store/store'
import { conversation } from './ask/conversation'
import type { StudioCtx } from './context'

export type Command = {
  id: string
  label: string
  /** As a menu shows it: ⌘ ⇧ ⌥. */
  keys?: string
  run: (c: StudioCtx) => void
  enabled?: (s: State) => boolean
}

const selected = (s: State) => s.selection.length > 0 && !s.editing
/** One picture frame with a picture in it, selected. */
const pictureSelected = (s: State) => !s.editing && s.selection.length === 1
  && s.doc.items.some((i) => i.id === s.selection[0] && i.kind === 'image' && !!i.asset_id)
/** Zoom to `z`, keeping what is in the middle of the view there. */
export function zoomTo(c: StudioCtx, z: number): void {
  const next = Math.max(0.05, Math.min(64, z))
  const zoom = c.store.get().view.zoom
  const sc = document.querySelector<HTMLElement>('[data-studio-scroller]')
  c.store.set((s) => ({ view: { ...s.view, zoom: next } }))
  if (!sc) return
  const o = boardOffset(sc)
  const mid = { x: (sc.scrollLeft + sc.clientWidth / 2 - o.x) / zoom, y: (sc.scrollTop + sc.clientHeight / 2 - o.y) / zoom }
  requestAnimationFrame(() => {
    sc.scrollLeft = o.x + mid.x * next - sc.clientWidth / 2
    sc.scrollTop = o.y + mid.y * next - sc.clientHeight / 2
  })
}

// Copied items (and the whole threads among them), kept for Paste.
let clip: { items: Item[]; threads: Thread[] } | null = null

function copy(s: State): void {
  const items = s.doc.items.filter((i) => s.selection.includes(i.id))
  const ids = new Set(items.map((i) => i.id))
  clip = { items, threads: s.doc.threads.filter((t) => t.frames.every((f) => ids.has(f))) }
}

/** The copied items, on the page in view (offset when it is where they came from). */
export function paste(doc: Doc, page: string): { doc: Doc; ids: string[] } {
  if (!clip) return { doc, ids: [] }
  const map = new Map<string, string>()
  let taken = allIds(doc)
  const same = clip.items.every((i) => i.page === page && doc.items.some((d) => d.id === i.id))
  const items = clip.items.map((i) => {
    const id = newId(i.kind === 'text' ? 't' : i.kind[0], taken)
    taken = [...taken, id]
    map.set(i.id, id)
    return { ...i, id, page, x: i.x + (same ? 12 : 0), y: i.y + (same ? 12 : 0), locked: false }
  })
  const threads = clip.threads.map((t) => {
    const id = newId('s', taken)
    taken = [...taken, id]
    return { id, frames: t.frames.map((f) => map.get(f)!), paras: t.paras }
  })
  return { doc: { ...doc, items: [...doc.items, ...items], threads: [...doc.threads, ...threads] }, ids: items.map((i) => i.id) }
}

const arrangeCmd = (id: Arrange, label: string, keys: string): Command => ({
  id: `arrange-${id}`, label, keys, enabled: selected,
  run: ({ store }) => store.edit((d) => arrange(d, store.get().selection, id)),
})

const tool = (t: Tool, label: string, keys: string): Command => ({
  id: `tool-${t}`, label, keys, run: ({ store, editor }) => { editor.close(); store.set({ tool: t, threading: null }) },
})

const toggle = (key: keyof State['view'], label: string, keys?: string): Command => ({
  id: `view-${key}`, label, keys,
  run: ({ store }) => store.set((s) => ({ view: { ...s.view, [key]: !s.view[key] } })),
})

export const COMMANDS: Command[] = [
  // File
  { id: 'save', label: 'Save a version', keys: '⌘S', run: (c) => void c.save({ keep: true }) },
  { id: 'story', label: 'Story settings…', run: ({ store }) => store.set({ dialog: 'story' }) },
  { id: 'revisions', label: 'Versions…', run: ({ store }) => store.set({ dialog: 'revisions' }) },
  { id: 'close', label: 'Close the Studio', run: (c) => c.close() },
  // Edit
  { id: 'undo', label: 'Undo', keys: '⌘Z', run: ({ store }) => store.undo(), enabled: () => true },
  { id: 'redo', label: 'Redo', keys: '⇧⌘Z', run: ({ store }) => store.redo(), enabled: () => true },
  { id: 'cut', label: 'Cut', keys: '⌘X', enabled: selected,
    run: ({ store }) => { copy(store.get()); store.edit((d) => deleteItems(d, store.get().selection), { extra: { selection: [] } }) } },
  { id: 'copy', label: 'Copy', keys: '⌘C', enabled: selected, run: ({ store }) => copy(store.get()) },
  { id: 'paste', label: 'Paste', keys: '⌘V', enabled: () => !!clip,
    run: ({ store }) => {
      const s = store.get()
      let ids: string[] = []
      store.edit((d) => { const r = paste(d, d.pages[s.page].id); ids = r.ids; return r.doc })
      store.set({ selection: ids })
    } },
  { id: 'duplicate', label: 'Duplicate', keys: '⌘D', enabled: selected,
    run: ({ store }) => {
      let ids: string[] = []
      store.edit((d) => { const r = duplicate(d, store.get().selection); ids = r.ids; return r.doc })
      store.set({ selection: ids })
    } },
  { id: 'delete', label: 'Delete', keys: '⌫', enabled: selected,
    run: ({ store }) => store.edit((d) => deleteItems(d, store.get().selection), { extra: { selection: [] } }) },
  { id: 'select-all', label: 'Select all on the page', keys: '⌘A',
    run: ({ store }) => {
      const s = store.get()
      const page = s.doc.pages[s.page].id
      store.set({ selection: s.doc.items.filter((i) => i.page === page && !i.locked && !i.hidden).map((i) => i.id) })
    } },
  { id: 'deselect', label: 'Deselect', keys: '⇧⌘A', run: ({ store }) => store.set({ selection: [], threading: null }) },
  // Layout
  { id: 'page-add', label: 'Add a page', keys: '⇧⌘P',
    run: ({ store }) => store.edit((d) => addPages(d, store.get().page), { extra: { page: store.get().page + 1 } }) },
  { id: 'spread-add', label: 'Add a spread', run: ({ store }) => store.edit((d) => addPages(d, store.get().page, 2)) },
  { id: 'page-delete', label: 'Delete this page', enabled: (s) => s.doc.pages.length > 1,
    run: ({ store }) => store.edit((d) => deletePage(d, store.get().page), { extra: { selection: [] } }) },
  { id: 'page-up', label: 'Move page earlier', enabled: (s) => s.page > 0,
    run: ({ store }) => { const p = store.get().page; store.edit((d) => movePage(d, p, p - 1), { extra: { page: p - 1 } }) } },
  { id: 'page-down', label: 'Move page later', enabled: (s) => s.page < s.doc.pages.length - 1,
    run: ({ store }) => { const p = store.get().page; store.edit((d) => movePage(d, p, p + 1), { extra: { page: p + 1 } }) } },
  { id: 'margins', label: 'Margins and columns…',
    run: ({ store }) => store.set((s) => ({ panels: s.panels.includes('pages') ? s.panels : ['pages', ...s.panels] })) },
  // Type
  { id: 'story-editor', label: 'Story Editor', keys: '⌘Y',
    run: ({ store }) => store.set((s) => ({ panels: s.panels.includes('story') ? s.panels.filter((p) => p !== 'story') : [...s.panels, 'story'] })) },
  // Object
  arrangeCmd('front', 'Bring to front', '⇧⌘]'),
  arrangeCmd('forward', 'Bring forward', '⌘]'),
  arrangeCmd('backward', 'Send backward', '⌘['),
  arrangeCmd('back', 'Send to back', '⇧⌘['),
  { id: 'lock', label: 'Lock / unlock', keys: '⌘L', enabled: selected,
    run: ({ store }) => {
      const s = store.get()
      const items = s.doc.items.filter((i) => s.selection.includes(i.id))
      store.edit((d) => patchItems(d, s.selection, { locked: !items.every((i) => i.locked) }))
    } },
  { id: 'hide', label: 'Hide', keys: '⌘3', enabled: selected,
    run: ({ store }) => store.edit((d) => patchItems(d, store.get().selection, { hidden: true }), { extra: { selection: [] } }) },
  { id: 'show-all', label: 'Show all on the page', keys: '⌥⌘3',
    run: ({ store }) => {
      const s = store.get()
      const page = s.doc.pages[s.page].id
      store.edit((d) => patchItems(d, d.items.filter((i) => i.page === page && i.hidden).map((i) => i.id), { hidden: false }))
    } },
  { id: 'place', label: 'Place a picture…', keys: '⌘P', run: ({ store }) => store.set({ dialog: 'library' }) },
  { id: 'edit-picture', label: 'Edit picture…', keys: '⇧⌘E', enabled: pictureSelected, run: ({ store }) => store.set({ dialog: 'picture' }) },
  { id: 'cut-out', label: 'Cut out the subject…', enabled: pictureSelected, run: ({ store }) => store.set({ dialog: 'cutout' }) },
  // View
  // Help
  { id: 'ask', label: 'Ask the Studio…',
    run: ({ store }) => {
      store.set((s) => ({ panels: s.panels.includes('ask') ? s.panels : [...s.panels, 'ask'] }))
      conversation(store).focus()
    } },
  { id: 'guide', label: 'How the Studio works', run: ({ store }) => store.set({ guide: 'start' }) },
  { id: 'shortcuts', label: 'Keyboard shortcuts', run: ({ store }) => store.set({ guide: 'keys' }) },
  { id: 'zoom-in', label: 'Zoom in', keys: '⌘=', run: (c) => zoomTo(c, c.store.get().view.zoom * 1.25) },
  { id: 'zoom-out', label: 'Zoom out', keys: '⌘-', run: (c) => zoomTo(c, c.store.get().view.zoom / 1.25) },
  { id: 'fit-page', label: 'Fit page in window', keys: '⌘0', run: (c) => c.fit(c.store.get().page, false) },
  { id: 'fit-spread', label: 'Fit spread in window', keys: '⌥⌘0', run: (c) => c.fit(c.store.get().page, true) },
  { id: 'actual', label: 'Actual size', keys: '⌘1', run: (c) => zoomTo(c, 96 / 72) },
  toggle('rulers', 'Rulers', '⌘R'),
  toggle('guides', 'Guides', '⌘;'),
  toggle('margins', 'Margins and columns'),
  toggle('baseline', 'Baseline grid', '⌥⌘\''),
  toggle('grid', 'Document grid', '⌘\''),
  toggle('snap', 'Snap', '⇧⌘;'),
  // Tools
  tool('select', 'Selection', 'V'),
  tool('text', 'Type', 'T'),
  tool('frame', 'Picture frame', 'F'),
  tool('rect', 'Rectangle', 'M'),
  tool('ellipse', 'Ellipse', 'L'),
  tool('line', 'Line', '\\'),
  tool('hand', 'Hand', 'H'),
  tool('zoom', 'Zoom', 'Z'),
]

export const command = (id: string): Command => COMMANDS.find((c) => c.id === id)!

const CODES: Record<string, string> = { BracketRight: ']', BracketLeft: '[', Semicolon: ';', Quote: "'", Equal: '=',
  Minus: '-', Backslash: '\\', Backspace: '⌫', Delete: '⌫' }

/** The key a press is (by where it is on the keyboard, so Shift and Option
 *  don't change it): "A", "0", "]", "⌫"… */
export function keyName(e: Pick<KeyboardEvent, 'code' | 'key'>): string {
  if (CODES[e.code]) return CODES[e.code]
  if (/^Key[A-Z]$/.test(e.code)) return e.code.slice(3)
  if (/^(Digit|Numpad)\d$/.test(e.code)) return e.code.slice(-1)
  return e.key.length === 1 ? e.key.toUpperCase() : e.key
}

/** The command a key press asks for (outside text being typed). */
export function commandForKey(e: Pick<KeyboardEvent, 'code' | 'key' | 'metaKey' | 'ctrlKey' | 'shiftKey' | 'altKey'>): Command | null {
  const mod = e.metaKey || e.ctrlKey
  const name = keyName(e)
  return COMMANDS.find((c) => {
    if (!c.keys) return false
    const wantMod = c.keys.includes('⌘'), wantShift = c.keys.includes('⇧'), wantAlt = c.keys.includes('⌥')
    const key = c.keys.replace(/[⌘⇧⌥]/g, '').toUpperCase()
    return key === name && wantMod === mod && wantShift === e.shiftKey && wantAlt === e.altKey
  }) ?? null
}
