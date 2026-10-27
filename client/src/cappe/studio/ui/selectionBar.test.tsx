import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { createRef } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { macRightClick } from '../canvas/usePointer'
import type { Measure } from '../compose/compose'
import { layout } from '../canvas/geometry'
import { newItem } from '../model/doc'
import type { Asset, Doc, ImageItem, Item, TextItem } from '../model/types'
import { DEFAULT_VIEW, Store, type State } from '../store/store'
import { barPlace, barShown } from './barPlace'
import { command } from './commands'
import ContextMenu from './ContextMenu'
import { StudioContext, type StudioCtx } from './context'
import { menuRows } from './menuRows'
import SelectionBar from './SelectionBar'

const mono: Measure = { width: (c, t) => [...t].length * 0.5 * c.size, metrics: (c) => ({ asc: 0.8 * c.size, desc: 0.2 * c.size }) }
const doc = (over: Partial<Doc> = {}): Doc => ({
  v: 1, size: { w: 600, h: 800 }, facing: false, margins: { t: 50, b: 50, i: 50, o: 50 }, cols: { n: 1, g: 12 },
  baseline: { start: 50, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'pt', paper: '#ffffff',
  pages: [{ id: 'p1' }], guides: [], items: [], threads: [], paywall_page: null, ...over,
})
const text = newItem('text', 'p1', 't1', { x: 50, y: 50, w: 400, h: 300 }) as TextItem
const words = (): Partial<Doc> => ({ items: [text], threads: [{ id: 's1', frames: ['t1'], paras: [{ runs: [{ t: 'Cover lines' }] }] }] })
const rect = (id: string, x: number, over: Partial<Item> = {}): Item => ({ ...newItem('rect', 'p1', id, { x, y: 100, w: 100, h: 100 }), ...over } as Item)
const picture = (over: Partial<ImageItem> = {}): ImageItem => ({ ...(newItem('image', 'p1', 'i1', { x: 50, y: 50, w: 300, h: 200 }) as ImageItem), ...over })
const PIC: Asset = { id: 'a1', url: 'https://cdn.example.test/a.jpg', width: 3000, height: 2000 }

function studio(d: Doc, over: Partial<State> = {}) {
  const store = new Store({
    doc: d, selection: [], editing: null, page: 0, tool: 'select', view: { ...DEFAULT_VIEW }, panels: [], drawer: null,
    overset: new Set(), assets: { a1: PIC }, dialog: null, guide: null, threading: null, snaps: null, marquee: null,
    save: { rev: 1, state: 'saved', message: null, draft: false, live: false }, ...over,
  } as State, mono)
  const editor = { open: vi.fn(), close: vi.fn(), currentChar: () => ({}), currentPara: () => ({}) }
  const ctx = {
    store, editor, siteId: 's1', postId: 'post1',
    fonts: { book: { face: () => undefined }, ensure: () => Promise.resolve(), ensureDoc: () => Promise.resolve() },
  } as unknown as StudioCtx
  return { store, ctx, editor }
}

// jsdom lays nothing out: every box is a 1000 × 800 view at the window's corner.
const VIEW = { left: 0, top: 0, right: 1000, bottom: 800, width: 1000, height: 800, x: 0, y: 0 }
beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ ...VIEW, toJSON: () => VIEW } as DOMRect)
})

function bar(d: Doc, over: Partial<State> = {}) {
  const made = studio(d, over)
  const scroller = createRef<HTMLDivElement>(), board = createRef<HTMLDivElement>()
  render(
    <StudioContext.Provider value={made.ctx}>
      <div>
        <div ref={scroller}><div ref={board} /></div>
        <SelectionBar lay={layout(d)} scroller={scroller} board={board} />
      </div>
      <ContextMenu />
    </StudioContext.Provider>,
  )
  return { ...made, scroller }
}

const item = (store: Store, id: string) => store.get().doc.items.find((i) => i.id === id)!
const runs = (store: Store) => store.get().doc.threads[0].paras[0].runs

afterEach(() => { vi.restoreAllMocks() })

describe('where the bar goes', () => {
  const view = { left: 0, top: 0, right: 1000, bottom: 800 }
  const size = { w: 300, h: 36 }

  it('sits centred above the selection, clear of the turn handle', () => {
    expect(barPlace(view, { left: 100, top: 50 }, { x: 200, y: 200, w: 200, h: 100 }, 1, size, 30))
      .toEqual({ left: 250, top: 250 - 10 - 30 - 36 })
  })

  it('goes below when there is no room above, and to the top of the view when neither fits', () => {
    expect(barPlace(view, { left: 0, top: 0 }, { x: 100, y: 20, w: 100, h: 100 }, 1, size)?.top).toBe(130)
    expect(barPlace(view, { left: 0, top: 0 }, { x: 100, y: 20, w: 100, h: 780 }, 1, size)?.top).toBe(8)
  })

  it('has no place when the selection is scrolled out of the view, any side', () => {
    for (const sel of [{ x: 100, y: 2000 }, { x: 100, y: -300 }, { x: 1200, y: 100 }, { x: -300, y: 100 }]) {
      expect(barPlace(view, { left: 0, top: 0 }, { ...sel, w: 100, h: 100 }, 1, size)).toBeNull()
    }
    // A sliver still in view keeps it.
    expect(barPlace(view, { left: 0, top: 0 }, { x: 100, y: 750, w: 100, h: 100 }, 1, size)).not.toBeNull()
  })

  it('never runs past the sides of the view, and scales with the zoom', () => {
    expect(barPlace(view, { left: 0, top: 0 }, { x: 0, y: 400, w: 20, h: 20 }, 1, size)?.left).toBe(8)
    expect(barPlace(view, { left: 0, top: 0 }, { x: 990, y: 400, w: 20, h: 20 }, 1, size)?.left).toBe(1000 - 300 - 8)
    expect(barPlace(view, { left: 0, top: 0 }, { x: 200, y: 200, w: 100, h: 100 }, 2, size)).toEqual({ left: 500 - 150, top: 400 - 10 - 36 })
  })

  it('shows only for a selection, with nothing in front and no drag or drawing tool in hand', () => {
    const { store } = studio(doc({ items: [rect('r1', 50)] }), { selection: ['r1'] })
    const s = store.get()
    expect(barShown(s)).toBe(true)
    expect(barShown({ ...s, selection: [] })).toBe(false)
    expect(barShown({ ...s, selection: ['gone'] })).toBe(false)
    expect(barShown({ ...s, gesture: true })).toBe(false)
    expect(barShown({ ...s, dialog: 'library' })).toBe(false)
    expect(barShown({ ...s, guide: 'start' })).toBe(false)
    expect(barShown({ ...s, tool: 'rect' })).toBe(false)
    expect(barShown({ ...s, tool: 'text' })).toBe(true)
    expect(barShown({ ...s, threading: { thread: null, frame: 'r1' } })).toBe(false)
  })
})

describe('the bar over the selection', () => {
  it('sets a text frame’s words: bold, italic, underline, size and alignment', () => {
    const { store } = bar(doc(words()), { selection: ['t1'] })
    expect(screen.getByRole('toolbar', { name: 'Selection' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Bold (⌘B)' }))
    expect(runs(store)[0].wt).toBe(700)
    fireEvent.click(screen.getByRole('button', { name: 'Bold (⌘B)' }))
    expect(runs(store)[0].wt ?? 400).toBe(400) // the regular weight is the default, so it isn't stored
    fireEvent.click(screen.getByRole('button', { name: 'Italic (⌘I)' }))
    fireEvent.click(screen.getByRole('button', { name: 'Underline (⌘U)' }))
    expect(runs(store)[0]).toMatchObject({ it: true, u: true })
    const size = screen.getByRole('textbox', { name: 'Font size' })
    fireEvent.change(size, { target: { value: '12.5' } })
    fireEvent.keyDown(size, { key: 'Enter' })
    expect(runs(store)[0].size).toBe(12.5)
    // The steppers go to the next whole size.
    fireEvent.click(screen.getByRole('button', { name: 'Bigger' }))
    expect(runs(store)[0].size).toBe(13)
    fireEvent.click(screen.getByRole('button', { name: 'Smaller' }))
    fireEvent.click(screen.getByRole('button', { name: 'Smaller' }))
    expect(runs(store)[0].size).toBe(11)
    fireEvent.click(screen.getByRole('button', { name: /^Aligned left/ }))
    expect(store.get().doc.threads[0].paras[0].align).toBe('c')
    fireEvent.click(screen.getByRole('button', { name: /^Centred/ }))
    expect(store.get().doc.threads[0].paras[0].align).toBe('r')
  })

  it('sets letter and line spacing from its Spacing panel', () => {
    const { store } = bar(doc(words()), { selection: ['t1'] })
    fireEvent.click(screen.getByRole('button', { name: 'Spacing' }))
    const panel = screen.getByRole('dialog', { name: 'Spacing' })
    const track = within(panel).getByRole('textbox', { name: 'Letter spacing' })
    fireEvent.change(track, { target: { value: '50' } })
    fireEvent.keyDown(track, { key: 'Enter' })
    expect(runs(store)[0].track).toBe(50)
    expect(within(panel).getByRole('textbox', { name: 'Line spacing' })).toHaveAttribute('placeholder', 'Auto')
  })

  it('keeps the focus where it was when its buttons are pressed, but lets boxes take it', () => {
    bar(doc(words()), { selection: ['t1'] })
    expect(fireEvent.mouseDown(screen.getByRole('button', { name: 'Bold (⌘B)' }))).toBe(false)
    expect(fireEvent.mouseDown(screen.getByRole('textbox', { name: 'Font size' }))).toBe(true)
  })

  it('offers an empty picture frame its picture, and a full one its picture tools', () => {
    const empty = bar(doc({ items: [picture()] }), { selection: ['i1'] })
    fireEvent.click(screen.getByRole('button', { name: 'Choose a picture' }))
    expect(empty.store.get().dialog).toBe('library')
  })

  it('edits, cuts out and crops a picture', () => {
    const { store } = bar(doc({ items: [picture({ asset_id: 'a1' })] }), { selection: ['i1'] })
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    expect(store.get().dialog).toBe('picture')
    act(() => store.set({ dialog: null }))
    fireEvent.click(screen.getByRole('button', { name: 'Cut out' }))
    expect(store.get().dialog).toBe('cutout')
    act(() => store.set({ dialog: null }))
    fireEvent.click(screen.getByRole('button', { name: 'Crop' }))
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Crop' })).getByRole('button', { name: 'Fit' }))
    expect((item(store, 'i1') as ImageItem).fit).toBe('fit')
    fireEvent.click(screen.getByRole('button', { name: 'Replace' }))
    expect(store.get().dialog).toBe('library')
  })

  it('fills a shape, takes its fill away, and gives it a border', () => {
    const { store } = bar(doc({ items: [rect('r1', 50, { fill: '#ff0000' } as Partial<Item>)] }), { selection: ['r1'] })
    fireEvent.click(screen.getByRole('button', { name: 'Fill: #ff0000' }))
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Fill' })).getByRole('button', { name: 'No fill' }))
    expect(item(store, 'r1')).toMatchObject({ fill: null })
    fireEvent.click(screen.getByRole('button', { name: 'Border' }))
    const weight = within(screen.getByRole('dialog', { name: 'Border' })).getByRole('textbox', { name: 'Border weight' })
    fireEvent.change(weight, { target: { value: '3' } })
    fireEvent.keyDown(weight, { key: 'Enter' })
    expect(item(store, 'r1')).toMatchObject({ stroke: { w: 3 } })
    expect(screen.getByRole('textbox', { name: 'Corner radius' })).toBeInTheDocument()
  })

  it('weights a line', () => {
    const line = { ...newItem('line', 'p1', 'l1', { x: 50, y: 50, w: 200, h: 0 }) } as Item
    const { store } = bar(doc({ items: [line] }), { selection: ['l1'] })
    const weight = screen.getByRole('textbox', { name: 'Line weight' })
    fireEvent.change(weight, { target: { value: '0' } })
    fireEvent.keyDown(weight, { key: 'Enter' })
    // A line never goes thinner than a quarter point.
    expect(item(store, 'l1')).toMatchObject({ stroke: { w: 0.25 } })
  })

  it('lines several things up with each other, and spaces three evenly', () => {
    const { store } = bar(doc({ items: [rect('a', 50), rect('b', 300), rect('c', 400)] }), { selection: ['a', 'b', 'c'] })
    fireEvent.click(screen.getByRole('button', { name: 'Position' }))
    const panel = screen.getByRole('dialog', { name: 'Position' })
    expect(panel).toHaveTextContent('Line them up with each other')
    fireEvent.click(within(panel).getByRole('button', { name: /Space across/ }))
    expect(item(store, 'b').x).toBe(225)
    fireEvent.click(within(panel).getByRole('button', { name: 'Align left' }))
    expect(['a', 'b', 'c'].map((id) => item(store, id).x)).toEqual([50, 50, 50])
  })

  it('sees through, duplicates, locks and deletes', () => {
    const { store } = bar(doc({ items: [rect('r1', 50)] }), { selection: ['r1'] })
    fireEvent.click(screen.getByRole('button', { name: 'Transparency' }))
    fireEvent.change(screen.getByRole('slider', { name: 'Opacity' }), { target: { value: '40' } })
    expect(item(store, 'r1').opacity).toBe(40)
    fireEvent.click(screen.getByRole('button', { name: 'Duplicate (⌘D)' }))
    expect(store.get().doc.items).toHaveLength(2)
    const copy = store.get().selection[0]
    fireEvent.click(screen.getByRole('button', { name: 'Delete (⌫)' }))
    expect(store.get().doc.items.map((i) => i.id)).toEqual(['r1'])
    expect(copy).not.toBe('r1')
    act(() => store.set({ selection: ['r1'] }))
    fireEvent.click(screen.getByRole('button', { name: 'Lock (⌘L)' }))
    expect(item(store, 'r1').locked).toBe(true)
    // Locked: only the way out, and the menu.
    expect(screen.getByText('Locked')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete (⌫)' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Unlock (⌘L)' }))
    expect(item(store, 'r1').locked).toBe(false)
  })

  it('opens the right-click menu from More, and steps aside during a drag', () => {
    const { store } = bar(doc({ items: [rect('r1', 50)] }), { selection: ['r1'] })
    fireEvent.click(screen.getByRole('button', { name: 'More' }))
    expect(store.get().menu).toEqual({ x: expect.any(Number), y: expect.any(Number) })
    expect(screen.getByRole('menu', { name: 'Actions' })).toBeInTheDocument()
    act(() => store.set({ menu: null, gesture: true }))
    expect(screen.queryByRole('toolbar', { name: 'Selection' })).toBeNull()
  })

  it('leaves a locked thing as it is when it is selected with others', () => {
    const { store } = bar(doc({ items: [rect('r1', 50, { fill: '#ff0000' } as Partial<Item>), rect('r2', 300, { locked: true, fill: '#00ff00' } as Partial<Item>)] }),
      { selection: ['r1', 'r2'] })
    fireEvent.click(screen.getByRole('button', { name: 'Fill: #ff0000' }))
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Fill' })).getByRole('button', { name: 'No fill' }))
    expect(item(store, 'r1')).toMatchObject({ fill: null })
    expect(item(store, 'r2')).toMatchObject({ fill: '#00ff00' })
    fireEvent.click(screen.getByRole('button', { name: 'Transparency' }))
    fireEvent.change(within(screen.getByRole('dialog', { name: 'Transparency' })).getByRole('slider', { name: 'Opacity' }), { target: { value: '40' } })
    expect([item(store, 'r1').opacity, item(store, 'r2').opacity]).toEqual([40, 100])
    // Lining up still counts the locked one.
    fireEvent.click(screen.getByRole('button', { name: 'Position' }))
    expect(screen.getByRole('dialog', { name: 'Position' })).toHaveTextContent('Line them up with each other')
  })

  it('hides while the selection is scrolled out of sight', () => {
    const { scroller } = bar(doc({ items: [rect('r1', 50)] }), { selection: ['r1'] })
    const toolbar = screen.getByRole('toolbar', { name: 'Selection' })
    expect(toolbar.style.visibility).toBe('')
    // The view now starts far below the page.
    const below = { ...VIEW, top: 5000, bottom: 5800 }
    vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockImplementation(function (this: HTMLElement) {
      const r = this === scroller.current ? below : VIEW
      return { ...r, toJSON: () => r } as DOMRect
    })
    fireEvent.scroll(scroller.current!)
    expect(toolbar.style.visibility).toBe('hidden')
  })

  it('shows only the words’ controls while they are typed in', () => {
    bar(doc(words()), { selection: ['t1'], editing: { thread: 's1', anchor: [0, 0], head: [0, 5] } })
    expect(screen.getByRole('button', { name: 'Bold (⌘B)' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Position' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Delete (⌫)' })).toBeNull()
  })
})

describe('the right-click menu', () => {
  it('offers the page’s things on an empty part of a page', () => {
    const { store } = studio(doc())
    const rows = menuRows(store.get())
    const ids = rows.flatMap((r) => (r !== '-' && 'id' in r ? [r.id] : []))
    expect(ids).toEqual(['paste', 'select-all', 'show-all', 'page-add', 'add-templates', 'board'])
    // With more than one page, this one can go.
    expect(JSON.stringify(menuRows(studio(doc({ pages: [{ id: 'p1' }, { id: 'p2' }] })).store.get()))).toContain('page-delete')
  })

  it('names a picture frame’s picture, and leaves lining up out when everything is locked', () => {
    const full = menuRows(studio(doc({ items: [picture({ asset_id: 'a1' })] }), { selection: ['i1'] }).store.get())
    expect(full).toContainEqual({ id: 'place', label: 'Replace picture…' })
    expect(full).toContainEqual({ id: 'edit-picture' })
    expect(full.some((r) => r !== '-' && 'rows' in r && r.label === 'Align to page')).toBe(true)
    const empty = menuRows(studio(doc({ items: [picture()] }), { selection: ['i1'] }).store.get())
    expect(empty).toContainEqual({ id: 'place', label: 'Choose a picture…' })
    expect(empty).not.toContainEqual({ id: 'edit-picture' })
    const locked = menuRows(studio(doc({ items: [rect('r1', 50, { locked: true })] }), { selection: ['r1'] }).store.get())
    expect(locked).toContainEqual({ id: 'lock', label: 'Unlock' })
    expect(locked.some((r) => r !== '-' && 'rows' in r)).toBe(false)
  })

  it('runs a row and closes; Esc closes; the arrows move through what can be done', () => {
    const { store, ctx } = studio(doc({ items: [rect('r1', 50)] }), { selection: ['r1'], menu: { x: 10, y: 10 } })
    render(<StudioContext.Provider value={ctx}><ContextMenu /></StudioContext.Provider>)
    const menu = screen.getByRole('menu', { name: 'Actions' })
    // The first row that can be done has the keyboard (Paste can't: nothing copied).
    expect(document.activeElement).toBe(within(menu).getByRole('menuitem', { name: /Cut/ }))
    fireEvent.keyDown(menu, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(within(menu).getByRole('menuitem', { name: /Copy/ }))
    fireEvent.keyDown(menu, { key: 'ArrowUp' })
    fireEvent.keyDown(menu, { key: 'ArrowUp' })
    expect(document.activeElement).toBe(within(menu).getByRole('menuitem', { name: /Ask about this/ }))
    fireEvent.click(within(menu).getByRole('menuitem', { name: /Duplicate/ }))
    expect(store.get().doc.items).toHaveLength(2)
    expect(store.get().menu).toBeNull()
    act(() => store.set({ menu: { x: 10, y: 10 } }))
    fireEvent.keyDown(screen.getByRole('menu', { name: 'Actions' }), { key: 'Escape' })
    expect(store.get().menu).toBeNull()
  })

  it('opens a side menu by key and lines the thing up with its page', () => {
    const { store, ctx } = studio(doc({ items: [rect('r1', 50)] }), { selection: ['r1'], menu: { x: 10, y: 10 } })
    render(<StudioContext.Provider value={ctx}><ContextMenu /></StudioContext.Provider>)
    const align = screen.getByRole('menuitem', { name: 'Align to page' })
    align.focus()
    fireEvent.keyDown(align, { key: 'ArrowRight' })
    const side = screen.getAllByRole('menu').find((m) => m !== screen.getByRole('menu', { name: 'Actions' }))!
    expect(document.activeElement).toBe(within(side).getByRole('menuitem', { name: 'Align left' }))
    // ← goes back to the row it came from.
    fireEvent.keyDown(side, { key: 'ArrowLeft' })
    expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: 'Align to page' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Align to page' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Align right' }))
    expect(item(store, 'r1').x).toBe(500)
    expect(store.get().menu).toBeNull()
  })

  it('closes when the pointer goes down anywhere else', () => {
    const { store, ctx } = studio(doc(), { menu: { x: 10, y: 10 } })
    render(<StudioContext.Provider value={ctx}><ContextMenu /></StudioContext.Provider>)
    fireEvent.pointerDown(document.body)
    expect(store.get().menu).toBeNull()
  })

  it('closes when the page moves under it: a scroll, or the wheel or a pinch', () => {
    const { store, ctx } = studio(doc(), { menu: { x: 10, y: 10 } })
    render(<StudioContext.Provider value={ctx}><ContextMenu /></StudioContext.Provider>)
    // The wheel over the menu itself leaves it open.
    fireEvent.wheel(screen.getByRole('menu', { name: 'Actions' }))
    expect(store.get().menu).not.toBeNull()
    fireEvent.wheel(document.body, { ctrlKey: true })
    expect(store.get().menu).toBeNull()
    act(() => store.set({ menu: { x: 10, y: 10 } }))
    fireEvent.scroll(document.body)
    expect(store.get().menu).toBeNull()
  })

  it('keeps the keyboard on its row when its gaps are pressed', () => {
    const { ctx } = studio(doc({ items: [rect('r1', 50)] }), { selection: ['r1'], menu: { x: 10, y: 10 } })
    render(<StudioContext.Provider value={ctx}><ContextMenu /></StudioContext.Provider>)
    const menu = screen.getByRole('menu', { name: 'Actions' })
    const separator = within(menu).getAllByRole('separator')[0]
    // A press whose default is stopped doesn't take the focus away.
    expect(fireEvent.mouseDown(separator)).toBe(false)
    expect(fireEvent.mouseDown(within(menu).getByRole('menuitem', { name: /Paste/ }))).toBe(false)
  })

  it('takes a Mac’s Ctrl-click as a right-click, and only on a Mac', () => {
    const platform = vi.spyOn(navigator, 'platform', 'get')
    platform.mockReturnValue('MacIntel')
    expect(macRightClick({ ctrlKey: true })).toBe(true)
    expect(macRightClick({ ctrlKey: false })).toBe(false)
    platform.mockReturnValue('Win32')
    expect(macRightClick({ ctrlKey: true })).toBe(false)
  })
})

describe('the commands behind them', () => {
  it('types in a text frame, making its text first if it has none', () => {
    const { store, ctx, editor } = studio(doc({ items: [text] }), { selection: ['t1'] })
    expect(command('edit-text').enabled!(store.get())).toBe(true)
    command('edit-text').run(ctx)
    const thread = store.get().doc.threads.find((t) => t.frames.includes('t1'))!
    expect(editor.open).toHaveBeenCalledWith(thread.id)
    expect(command('edit-text').enabled!({ ...store.get(), selection: [] })).toBe(false)
  })
})
