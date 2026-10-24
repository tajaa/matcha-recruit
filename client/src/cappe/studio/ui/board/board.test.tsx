import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Measure } from '../../compose/compose'
import { groupOf } from '../../model/crops'
import { newItem } from '../../model/doc'
import { LIMITS } from '../../model/limits'
import { runs } from '../../model/sections'
import type { Asset, Doc, ImageItem, Item } from '../../model/types'
import { DEFAULT_VIEW, Store, type State } from '../../store/store'
import { command } from '../commands'
import { StudioContext, type StudioCtx } from '../context'
import { ObjectPanel } from '../panels/ObjectPanel'
import Board from './Board'
import { PAIRS, applyPair, pairTarget } from './pairs'
import { boundPages, nudge, sidesChanged, slotAt, type Tile } from './sequence'

const doc = (over: Partial<Doc> = {}): Doc => ({
  v: 1, size: { w: 600, h: 800 }, facing: true, margins: { t: 50, b: 50, i: 50, o: 50 }, cols: { n: 1, g: 12 },
  baseline: { start: 50, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'pt', paper: '#ffffff',
  pages: Array.from({ length: 5 }, (_, k) => ({ id: `p${k + 1}` })), guides: [], items: [], threads: [], paywall_page: null,
  ...over,
})
const ids = (d: Doc) => d.pages.map((p) => p.id)
const rect = (id: string, page: string, x = 50, w = 100): Item => newItem('rect', page, id, { x, y: 50, w, h: 100 })
const frame = (id: string, page: string, box: { x: number; y: number; w: number; h: number }, over: Partial<ImageItem> = {}): ImageItem =>
  ({ ...(newItem('image', page, id, box) as ImageItem), ...over })
const PIC: Asset = { id: 'a1', url: 'https://cdn.example.test/a.jpg', width: 3000, height: 2000 }

describe('what moves together, and where a drop lands', () => {
  it('a page with a picture across the spine brings the page facing it', () => {
    const d = doc({ items: [frame('i1', 'p2', { x: 400, y: 0, w: 400, h: 300 })] })
    expect(boundPages(d, ['p2'])).toEqual(['p2', 'p3'])
    expect(boundPages(d, ['p3'])).toEqual(['p2', 'p3'])
    expect(boundPages(d, ['p4'])).toEqual(['p4'])
    // Linked frames, one on each page, bind them too.
    const linked = doc({ items: [frame('i1', 'p4', { x: 0, y: 0, w: 600, h: 800 }, { link: 'lk1' }),
      frame('i2', 'p5', { x: 0, y: 0, w: 600, h: 800 }, { link: 'lk1' })] })
    expect(boundPages(linked, ['p5'])).toEqual(['p4', 'p5'])
    // A full-bleed background (out to the bleed, not past it) stays on its own page.
    const backgrounds = doc({ items: [{ ...rect('b1', 'p2', -9, 618), y: -9, h: 818 }, { ...rect('b2', 'p3', -9, 618), y: -9, h: 818 }] })
    expect(boundPages(backgrounds, ['p2'])).toEqual(['p2'])
    expect(boundPages(backgrounds, ['p3'])).toEqual(['p3'])
    // Without facing pages nothing is bound.
    expect(boundPages({ ...d, facing: false }, ['p2'])).toEqual(['p2'])
  })

  it('drops before the page under the pointer’s left half, after its right half, else beside the nearest', () => {
    const tiles: Tile[] = [
      { index: 0, left: 0, top: 0, right: 100, bottom: 140 },
      { index: 1, left: 120, top: 0, right: 220, bottom: 140 },
      { index: 2, left: 0, top: 200, right: 100, bottom: 340 },
    ]
    expect(slotAt([], 0, 0)).toBeNull()
    expect(slotAt(tiles, 130, 50)).toEqual({ slot: 1, before: true, x: 120, top: 0, bottom: 140 })
    expect(slotAt(tiles, 210, 50)).toEqual({ slot: 2, before: false, x: 220, top: 0, bottom: 140 })
    // Past the end of a row: after its last page; between rows: the nearest.
    expect(slotAt(tiles, 400, 60)?.slot).toBe(2)
    expect(slotAt(tiles, 40, 180)?.slot).toBe(2)
  })

  it('moves a spread at a time with facing pages, so the pages around keep their sides', () => {
    const d = doc()
    expect(ids(nudge(d, ['p2', 'p3'], 1))).toEqual(['p1', 'p4', 'p5', 'p2', 'p3'])
    expect(ids(nudge(d, ['p4', 'p5'], -1))).toEqual(['p1', 'p4', 'p5', 'p2', 'p3'])
    expect(nudge(d, ['p1'], -1)).toBe(d)
    expect(ids(nudge({ ...d, facing: false }, ['p2'], 1))).toEqual(['p1', 'p3', 'p2', 'p4', 'p5'])
  })

  it('says from which page an odd move turned pages over', () => {
    const d = doc()
    expect(sidesChanged(d, nudge(d, ['p2', 'p3'], 1))).toBeNull()
    expect(sidesChanged(d, nudge(d, ['p2'], 1))).toBe(1)
    expect(sidesChanged({ ...d, facing: false }, { ...nudge(d, ['p2'], 1), facing: false })).toBeNull()
  })
})

describe('paired layouts', () => {
  it('lays out a blank spread, or a new one after a spread that has things on it', () => {
    const d = doc()
    expect(pairTarget(d, [0, 1])).toBeNull() // the cover faces nothing
    expect(pairTarget(d, [2, 3])).toBeNull() // two pages, but not one spread
    expect(pairTarget(d, [1, 2])).toEqual({ left: 1, fresh: false })
    expect(pairTarget({ ...d, items: [rect('r1', 'p3')] }, [1, 2])).toEqual({ left: 1, fresh: true })

    const across = PAIRS.find((p) => p.id === 'across')!
    const made = applyPair(d, [1, 2], across)
    if ('problem' in made) throw new Error(made.problem)
    expect(made.left).toBe(1)
    const pics = made.doc.items as ImageItem[]
    expect(pics.map((i) => i.page)).toEqual(['p2', 'p3'])
    expect(pics[0].link).toBeTruthy()
    expect(pics[1].link).toBe(pics[0].link)
    expect(pics[0]).toMatchObject({ x: -9, y: -9, w: 609, h: 818 })

    const busy = { ...d, items: [rect('r1', 'p2')] }
    const after = applyPair(busy, [1, 2], PAIRS.find((p) => p.id === 'diptych')!)
    if ('problem' in after) throw new Error(after.problem)
    expect(after.doc.pages).toHaveLength(7)
    expect(after.left).toBe(3)
    expect(after.doc.items.find((i) => i.id === 'r1')?.page).toBe('p2') // nothing covered
    expect(after.doc.items.filter((i) => i.kind === 'image').map((i) => i.page)).toEqual(ids(after.doc).slice(3, 5))
    expect((after.doc.items as ImageItem[]).some((i) => i.link)).toBe(false)
  })

  it('every layout keeps its frames on their pages and the spine-clear one off the fold', () => {
    for (const pair of PAIRS) {
      const made = applyPair(doc(), [1, 2], pair)
      if ('problem' in made) throw new Error(`${pair.id}: ${made.problem}`)
      expect(made.doc.items.length, pair.id).toBeGreaterThanOrEqual(2)
    }
    const spine = applyPair(doc(), [1, 2], PAIRS.find((p) => p.id === 'spine')!)
    if ('problem' in spine) throw new Error(spine.problem)
    const [l, r] = spine.doc.items
    expect(l.x + l.w).toBe(600 - 36)
    expect(r.x).toBe(36)
  })

  it('says why when there is no room for another spread', () => {
    const full = doc({ pages: Array.from({ length: LIMITS.MAX_PAGES }, (_, k) => ({ id: `p${k + 1}` })), items: [rect('r1', 'p2')] })
    expect(applyPair(full, [1, 2], PAIRS[0])).toEqual({ problem: expect.stringContaining(`${LIMITS.MAX_PAGES} pages`) })
  })
})

// ── the board on screen ──────────────────────────────────────────────────

const mono: Measure = { width: (c, t) => [...t].length * 0.5 * c.size, metrics: (c) => ({ asc: 0.8 * c.size, desc: 0.2 * c.size }) }

function mount(d: Doc, node: 'board' | 'object' = 'board', extra: Partial<State> = {}) {
  const store = new Store({
    doc: d, selection: [], editing: null, page: 0, tool: 'select', view: { ...DEFAULT_VIEW }, panels: [], drawer: null,
    overset: new Set(), assets: { a1: PIC }, dialog: node === 'board' ? 'board' : null, guide: null, threading: null, snaps: null,
    marquee: null, save: { rev: 1, state: 'saved', message: null, draft: false, live: false }, ...extra,
  } as State, mono)
  const fit = vi.fn()
  const ctx = { store, fit, fonts: { book: { face: () => undefined } }, editor: { close: () => {} }, siteId: 's1', postId: 'post1' } as unknown as StudioCtx
  render(<StudioContext.Provider value={ctx}>{node === 'board' ? <Board /> : <ObjectPanel />}</StudioContext.Provider>)
  return { store, fit }
}

// A page's tile (the rhythm strip's buttons are named "Page n: its beat").
const tile = (n: number) => screen.getByRole('button', { name: `Page ${n}` })

afterEach(() => { vi.restoreAllMocks(); try { localStorage.clear() } catch { /* storage off */ } })

describe('the issue board', () => {
  it('shows every page, drawn, with the issue’s rhythm along the top', () => {
    mount(doc({ items: [rect('r1', 'p2', 0, 600)] }))
    const board = screen.getByRole('dialog', { name: 'Issue board' })
    expect(within(board).getByText('5 pages')).toBeInTheDocument()
    for (let n = 1; n <= 5; n++) expect(tile(n)).toBeInTheDocument()
    expect(within(screen.getByLabelText('The rhythm of the issue')).getAllByRole('button')).toHaveLength(5)
    // The renderer drew page 2's rectangle into its tile.
    expect(board.querySelectorAll('.lyt-item').length).toBe(1)
  })

  it('starts, renames and removes a story', () => {
    const { store } = mount(doc())
    fireEvent.click(tile(3))
    fireEvent.click(screen.getByRole('button', { name: 'Start a story here' }))
    expect(runs(store.get().doc).map((r) => [r.section?.name ?? null, r.start, r.end])).toEqual([[null, 0, 2], ['Story 1', 2, 5]])
    const name = screen.getByRole('textbox', { name: 'Story name' })
    fireEvent.change(name, { target: { value: 'Night market' } })
    fireEvent.blur(name)
    expect(store.get().doc.sections?.[0].name).toBe('Night market')
    // A name of nothing but spaces keeps the one it had.
    fireEvent.change(name, { target: { value: '   ' } })
    fireEvent.blur(name)
    expect(store.get().doc.sections?.[0].name).toBe('Night market')
    fireEvent.click(screen.getByRole('button', { name: /Remove the story break/ }))
    expect(store.get().doc.sections).toBeUndefined()
  })

  it('moves the pages selected with ⌥ arrows, says when pages turned over, and undoes', () => {
    const { store } = mount(doc())
    fireEvent.click(tile(2))
    fireEvent.click(tile(3), { shiftKey: true })
    fireEvent.keyDown(tile(3), { key: 'ArrowRight', altKey: true })
    expect(ids(store.get().doc)).toEqual(['p1', 'p4', 'p5', 'p2', 'p3'])
    expect(screen.queryByRole('status')).toBeNull()
    fireEvent.keyDown(tile(4), { key: 'z', metaKey: true })
    expect(ids(store.get().doc)).toEqual(['p1', 'p2', 'p3', 'p4', 'p5'])
    // One page alone: the pages after it change sides, and the board says so.
    fireEvent.click(tile(2))
    fireEvent.click(screen.getByRole('button', { name: 'Move later' }))
    expect(ids(store.get().doc)).toEqual(['p1', 'p3', 'p4', 'p2', 'p5'])
    expect(screen.getByRole('status')).toHaveTextContent('Pages from page 2 on now face the other way')
  })

  it('drags pages into place', () => {
    const { store } = mount(doc())
    // Lay the tiles out in a row, 100 px each.
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      const n = Number(this.dataset.boardPage ?? -1)
      return { left: n * 100, right: n * 100 + 90, top: 0, bottom: 120, width: 90, height: 120, x: n * 100, y: 0, toJSON: () => ({}) } as DOMRect
    })
    fireEvent.pointerDown(tile(1), { button: 0, clientX: 40, clientY: 50 })
    act(() => { window.dispatchEvent(new PointerEvent('pointermove', { clientX: 380, clientY: 50, buttons: 1 })) })
    expect(screen.getByText('Moving 1 page')).toBeInTheDocument()
    act(() => { window.dispatchEvent(new PointerEvent('pointerup', { clientX: 380, clientY: 50 })) })
    // Dropped on page 4's right half: after it.
    expect(ids(store.get().doc)).toEqual(['p2', 'p3', 'p4', 'p1', 'p5'])
    expect(screen.queryByText('Moving 1 page')).toBeNull()
  })

  it('lets go of a drag whose release it never heard, or that the browser cancelled', () => {
    const { store } = mount(doc())
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      const n = Number(this.dataset.boardPage ?? -1)
      return { left: n * 100, right: n * 100 + 90, top: 0, bottom: 120, width: 90, height: 120, x: n * 100, y: 0, toJSON: () => ({}) } as DOMRect
    })
    // Pressed, then the release happened outside the window: the next move has no button held.
    fireEvent.pointerDown(tile(1), { button: 0, clientX: 40, clientY: 50 })
    act(() => { window.dispatchEvent(new PointerEvent('pointermove', { clientX: 380, clientY: 50, buttons: 0 })) })
    expect(screen.queryByText('Moving 1 page')).toBeNull()
    // Dragging, then the browser cancels the pointer: nothing moves, and the next move isn't a drag.
    fireEvent.pointerDown(tile(1), { button: 0, clientX: 40, clientY: 50 })
    act(() => { window.dispatchEvent(new PointerEvent('pointermove', { clientX: 380, clientY: 50, buttons: 1 })) })
    expect(screen.getByText('Moving 1 page')).toBeInTheDocument()
    act(() => { window.dispatchEvent(new PointerEvent('pointercancel')) })
    act(() => { window.dispatchEvent(new PointerEvent('pointermove', { clientX: 300, clientY: 50, buttons: 1 })) })
    act(() => { window.dispatchEvent(new PointerEvent('pointerup', { clientX: 300, clientY: 50 })) })
    expect(screen.queryByText('Moving 1 page')).toBeNull()
    expect(ids(store.get().doc)).toEqual(['p1', 'p2', 'p3', 'p4', 'p5'])
  })

  it('offers to move a story earlier only past another story', () => {
    const { store } = mount(doc({ sections: [{ id: 'st1', page: 'p2', name: 'One' }, { id: 'st2', page: 'p4', name: 'Two' }] }))
    const earlier = screen.getAllByRole('button', { name: 'Move the story earlier' })
    expect(earlier[0]).toBeDisabled() // only the pages before the first story are ahead of it
    fireEvent.click(earlier[1])
    expect(runs(store.get().doc).map((r) => r.section?.name ?? null)).toEqual([null, 'Two', 'One'])
  })

  it('moves a story with the facing page a picture runs onto, so the picture stays whole', () => {
    // Story One ends on p2 (a left page); Two starts on p3, its facing page. A picture runs across them.
    const d = doc({ sections: [{ id: 'st1', page: 'p2', name: 'One' }, { id: 'st2', page: 'p3', name: 'Two' }],
      items: [frame('i1', 'p2', { x: 300, y: 0, w: 600, h: 400 })] })
    const { store } = mount(d)
    fireEvent.click(screen.getAllByRole('button', { name: 'Move the story later' })[0])
    const now = ids(store.get().doc)
    expect(now.indexOf('p3') - now.indexOf('p2')).toBe(1) // still side by side
  })

  it('lays out a spread with a paired layout', () => {
    const { store } = mount(doc())
    fireEvent.click(tile(2))
    expect(screen.getByRole('button', { name: 'Lay out the spread…' })).toBeDisabled()
    fireEvent.click(tile(3), { shiftKey: true })
    fireEvent.click(screen.getByRole('button', { name: 'Lay out the spread…' }))
    fireEvent.click(within(screen.getByRole('menu', { name: 'Spread layouts' })).getByRole('menuitem', { name: /Diptych/ }))
    expect(store.get().doc.items.map((i) => [i.kind, i.page])).toEqual([['image', 'p2'], ['image', 'p3']])
    expect(screen.getByRole('status')).toHaveTextContent('Diptych laid out on pages 2–3')
  })

  it('opens a page in the editor on a double-click, and closes on Esc', async () => {
    const { store, fit } = mount(doc())
    fireEvent.doubleClick(tile(4))
    expect(store.get()).toMatchObject({ dialog: null, page: 3 })
    await vi.waitFor(() => expect(fit).toHaveBeenCalledWith(3, true))

    store.set({ dialog: 'board' })
    fireEvent.keyDown(screen.getByRole('dialog', { name: 'Issue board' }), { key: 'Escape' })
    expect(store.get().dialog).toBeNull()
  })

  it('flags words in the gutter on their spread', () => {
    const d = doc({
      items: [newItem('text', 'p2', 't1', { x: 400, y: 50, w: 190, h: 100 })],
      threads: [{ id: 's1', frames: ['t1'], paras: [{ runs: [{ t: 'Words by the spine' }] }] }],
    })
    mount(d)
    expect(screen.getByRole('img', { name: /run into the gutter/ })).toBeInTheDocument()
  })
})

describe('a picture across the spread, from the Object panel', () => {
  it('runs one picture over both pages, linked, and unlinks it', () => {
    const d = doc({ items: [frame('i1', 'p2', { x: 50, y: 50, w: 300, h: 300 }, { asset_id: 'a1' })] })
    const { store } = mount(d, 'object', { selection: ['i1'] })
    fireEvent.click(screen.getByRole('button', { name: /Across/ }))
    const s = store.get()
    expect(s.selection).toHaveLength(2)
    const g = groupOf(s.doc, 'i1')!
    expect(g.members.map((m) => m.page)).toEqual(['p2', 'p3'])
    expect(g.members.every((m) => m.asset_id === 'a1')).toBe(true)
    expect(screen.getByRole('button', { name: /Unlink crops/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Unlink crops/ }))
    expect(groupOf(store.get().doc, 'i1')).toBeNull()
  })

  it('offers Link crops for frames on one spread, and says why not otherwise', () => {
    const d = doc({ items: [frame('i1', 'p2', { x: 50, y: 50, w: 200, h: 300 }, { asset_id: 'a1' }),
      frame('i2', 'p3', { x: 50, y: 50, w: 200, h: 300 }), frame('i3', 'p4', { x: 50, y: 50, w: 200, h: 300 })] })
    const { store } = mount(d, 'object', { selection: ['i1', 'i3'] })
    expect(screen.getByRole('button', { name: /Link crops/ })).toBeDisabled()
    expect(screen.getByText('Linked frames have to be on one spread.')).toBeInTheDocument()
    act(() => store.set({ selection: ['i1', 'i2'] }))
    fireEvent.click(screen.getByRole('button', { name: /Link crops/ }))
    expect(groupOf(store.get().doc, 'i2')?.members.map((m) => m.id)).toEqual(['i1', 'i2'])
    expect((store.get().doc.items.find((i) => i.id === 'i2') as ImageItem).asset_id).toBe('a1')
  })

  it('the board opens from its command, with ⌥⌘P', () => {
    const { store } = mount(doc(), 'object')
    expect(command('board').keys).toBe('⌥⌘P')
    command('board').run({ store, editor: { close: () => {} } } as unknown as StudioCtx)
    expect(store.get().dialog).toBe('board')
  })
})
