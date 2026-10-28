// Everything the Studio can do from a menu, a key or a button: one list, so a
// menu shows the key that does the same thing.

import { alignItems, canSpace, spaceItems, type Align } from '../canvas/align'
import { boardOffset } from '../canvas/geometry'
import { acrossSpread, facingPage, groupOf, linkFrames, linkProblem, unlinkFrames } from '../model/crops'
import { cutoutFor, subjectProblem } from '../model/subject'
import { placeSubject } from './subject'
import { allIds, newId } from '../model/doc'
import { SPINE_CLEAR } from '../model/gutter'
import { resolveItem, resolveParas } from '../model/identity'
import { addPages, arrange, deleteItems, deletePage, duplicate, ensureThread, movePage, patchItems, type Arrange } from '../model/ops'
import type { Doc, Item, Thread } from '../model/types'
import type { AddTab, State, Store, Tool } from '../store/store'
import { conversation, MATCH_QUESTION } from './ask/conversation'
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
/** Picture frames selected that can show one picture between them. */
const linkable = (s: State) => !s.editing && !linkProblem(s.doc, s.selection)
/** Frames selected with a linked crop among them. */
const linked = (s: State) => !s.editing && s.selection.some((id) => !!groupOf(s.doc, id))
/** One unturned picture frame selected, on a page with a page facing it. */
const spreadable = (s: State) => {
  const item = s.selection.length === 1 && !s.editing ? s.doc.items.find((i) => i.id === s.selection[0]) : undefined
  return !!item && item.kind === 'image' && item.rot === 0 && !item.locked
    && facingPage(s.doc, s.doc.pages.findIndex((p) => p.id === item.page)) !== null
}
/** The picture frame selected made two, one on each page of the spread. */
function across(c: StudioCtx, spine: number): void {
  const { store } = c
  let ids: string[] = []
  store.edit((d) => { const r = acrossSpread(d, store.get().selection[0], store.get().assets, spine); ids = r?.ids ?? []; return r?.doc ?? d })
  if (ids.length) store.set({ selection: ids })
}

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
let clip: { items: Item[]; threads: Thread[]; origin: object; flatItems: Item[]; flatThreads: Thread[] } | null = null
const scopes = new WeakMap<Store, object>()
const scope = (store: Store) => {
  let token = scopes.get(store)
  if (!token) { token = {}; scopes.set(store, token) }
  return token
}

function copy(origin: Store): void {
  const s = origin.get()
  const items = s.doc.items.filter((i) => s.selection.includes(i.id))
  const ids = new Set(items.map((i) => i.id))
  const threads = s.doc.threads.filter((t) => t.frames.every((f) => ids.has(f)))
  clip = { items, threads, origin: scope(origin),
    flatItems: items.map((i) => { const out = { ...resolveItem(i, s.doc.identity) }; delete out.fill_swatch; delete out.stroke_swatch; return out }),
    flatThreads: threads.map((t) => ({ ...t, paras: resolveParas(t.paras, s.doc.identity) })) }
}

/** The copied items, on the page in view (offset when it is where they came from). */
export function paste(doc: Doc, page: string, origin?: Store): { doc: Doc; ids: string[] } {
  if (!clip) return { doc, ids: [] }
  const map = new Map<string, string>()
  let taken = allIds(doc)
  const same = clip.items.every((i) => i.page === page && doc.items.some((d) => d.id === i.id))
  // Edits replace identity objects. Ownership remains the same, but a
  // definition deleted since Copy must fall back to its copied appearance.
  const has = (kind: 'paragraphs' | 'characters' | 'swatches', id?: string) => !id || !!doc.identity?.[kind].some((r) => r.id === id)
  const linked = !!origin && scope(origin) === clip.origin && clip.items.every((i) => has('swatches', i.fill_swatch) && has('swatches', i.stroke_swatch))
    && clip.threads.every((t) => t.paras.every((p) => has('paragraphs', p.style) && p.runs.every((r) => has('characters', r.style) && has('swatches', r.swatch))))
  const items = (linked ? clip.items : clip.flatItems).map((i) => {
    const id = newId(i.kind === 'text' ? 't' : i.kind[0], taken)
    taken = [...taken, id]
    map.set(i.id, id)
    return { ...i, id, page, x: i.x + (same ? 12 : 0), y: i.y + (same ? 12 : 0), locked: false }
  })
  const threads = (linked ? clip.threads : clip.flatThreads).map((t) => {
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

/** Something selected that can move: what lining up acts on. */
const alignable = (s: State) => selected(s) && s.doc.items.some((i) => s.selection.includes(i.id) && !i.locked)

const alignCmd = (how: Align, label: string): Command => ({
  id: `align-${how}`, label, enabled: alignable,
  run: ({ store }) => store.edit((d) => alignItems(d, store.get().selection, how)),
})

/** One unlocked text frame selected, to type in. */
const oneText = (s: State) => !s.editing && s.selection.length === 1
  && s.doc.items.some((i) => i.id === s.selection[0] && i.kind === 'text' && !i.locked)

const tool = (t: Tool, label: string, keys: string): Command => ({
  id: `tool-${t}`, label, keys, run: ({ store, editor }) => { editor.close(); store.set({ tool: t, threading: null }) },
})

const drawer = (tab: AddTab, label: string): Command => ({
  id: `add-${tab}`, label, run: ({ store }) => store.set({ drawer: tab }),
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
    run: ({ store }) => { copy(store); store.edit((d) => deleteItems(d, store.get().selection), { extra: { selection: [] } }) } },
  { id: 'copy', label: 'Copy', keys: '⌘C', enabled: selected, run: ({ store }) => copy(store) },
  { id: 'paste', label: 'Paste', keys: '⌘V', enabled: () => !!clip,
    run: ({ store }) => {
      const s = store.get()
      let ids: string[] = []
      store.edit((d) => { const r = paste(d, d.pages[s.page].id, store); ids = r.ids; return r.doc })
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
  // Insert
  drawer('templates', 'Page templates…'),
  drawer('elements', 'Shapes, lines and frames…'),
  drawer('text', 'Text styles and pairings…'),
  drawer('photos', 'Free photos and AI pictures…'),
  drawer('uploads', 'Your pictures…'),
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
  { id: 'board', label: 'Issue board', keys: '⌥⌘P', run: ({ store, editor }) => { editor.close(); store.set({ dialog: 'board' }) } },
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
  // One thing lines up with its page; several with each other.
  alignCmd('left', 'Align left'),
  alignCmd('centre', 'Align centre'),
  alignCmd('right', 'Align right'),
  alignCmd('top', 'Align top'),
  alignCmd('middle', 'Align middle'),
  alignCmd('bottom', 'Align bottom'),
  { id: 'space-across', label: 'Space evenly across', enabled: (s) => selected(s) && canSpace(s.doc, s.selection),
    run: ({ store }) => store.edit((d) => spaceItems(d, store.get().selection, 'across')) },
  { id: 'space-down', label: 'Space evenly down', enabled: (s) => selected(s) && canSpace(s.doc, s.selection),
    run: ({ store }) => store.edit((d) => spaceItems(d, store.get().selection, 'down')) },
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
  { id: 'subject-front', label: 'Put the subject in front…', enabled: (s) => pictureSelected(s) && !subjectProblem(s.doc, s.selection[0]),
    run: (c) => {
      const s = c.store.get()
      const frame = s.doc.items.find((i) => i.id === s.selection[0])
      const cut = frame?.kind === 'image' ? cutoutFor(s.assets, frame.asset_id) : null
      if (cut) void placeSubject(c, frame!.id, cut)
      else c.store.set({ dialog: 'subject' })
    } },
  { id: 'fonts', label: 'Your fonts…', run: ({ store }) => store.set({ dialog: 'fonts' }) },
  { id: 'edit-text', label: 'Type in this frame', enabled: oneText,
    run: ({ store, editor }) => {
      const frame = store.get().selection[0]
      let thread = ''
      store.edit((d) => { const r = ensureThread(d, frame); thread = r.thread; return r.doc })
      store.set({ selection: [frame], tool: 'select' })
      editor.open(thread)
    } },
  { id: 'across-spread', label: 'Run the picture across the spread', enabled: spreadable, run: (c) => across(c, 0) },
  { id: 'spine-clear', label: 'Split the picture clear of the spine', enabled: spreadable, run: (c) => across(c, SPINE_CLEAR) },
  { id: 'link-crops', label: 'Link crops (one picture through the frames)', enabled: linkable,
    run: ({ store }) => store.edit((d) => linkFrames(d, store.get().selection, store.get().assets)) },
  { id: 'unlink-crops', label: 'Unlink crops', enabled: linked,
    run: ({ store }) => store.edit((d) => unlinkFrames(d, store.get().selection)) },
  // View
  // Help
  // Ask and Ask about this answer, even when the panel was last left on Merlin
  // (which would design from the same words, and change the page).
  { id: 'ask', label: 'Ask the Studio…',
    run: ({ store }) => {
      store.set((s) => ({ panels: s.panels.includes('ask') ? s.panels : [...s.panels, 'ask'] }))
      conversation(store).setMode('ask')
      conversation(store).focus()
    } },
  { id: 'ask-about', label: 'Ask about this…', enabled: (s) => s.selection.length > 0,
    run: ({ store }) => {
      store.set((s) => ({ panels: s.panels.includes('ask') ? s.panels : [...s.panels, 'ask'] }))
      conversation(store).setMode('ask')
      conversation(store).prompt(MATCH_QUESTION)
    } },
  { id: 'merlin', label: 'Design with Merlin…',
    run: ({ store }) => {
      store.set((s) => ({ panels: s.panels.includes('ask') ? s.panels : [...s.panels, 'ask'] }))
      conversation(store).setMode('merlin')
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
  toggle('gutter', 'Gutter safety'),
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
