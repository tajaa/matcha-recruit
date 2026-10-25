import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Measure } from '../compose/compose'
import { newItem } from '../model/doc'
import type { Asset, Doc, ImageItem, TextItem } from '../model/types'
import { DEFAULT_VIEW, Store, type State } from '../store/store'
import { TextEditor } from '../text/editor'
import { StudioContext, type StudioCtx } from './context'

const api = vi.hoisted(() => ({
  fonts: vi.fn(),
  uploadFont: vi.fn(),
  renameFontFamily: vi.fn(),
  hideFont: vi.fn(),
  pixels: vi.fn(),
}))
vi.mock('../api', async (orig) => ({ ...(await orig<typeof import('../api')>()), studioApi: api }))

import FontsDialog from './FontsDialog'
import { CharacterPanel, ParagraphPanel } from './panels/TypePanels'
import { placeSubject } from './subject'

const mono: Measure = { width: (c, t) => [...t].length * 0.5 * c.size, metrics: (c) => ({ asc: 0.8 * c.size, desc: 0.2 * c.size }) }
const doc = (over: Partial<Doc> = {}): Doc => ({
  v: 1, size: { w: 600, h: 800 }, facing: false, margins: { t: 50, b: 50, i: 50, o: 50 }, cols: { n: 1, g: 12 },
  baseline: { start: 50, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'pt', paper: '#ffffff',
  pages: [{ id: 'p1' }], guides: [], items: [], threads: [], paywall_page: null, ...over,
})
const frame = newItem('text', 'p1', 't1', { x: 50, y: 50, w: 400, h: 300 }) as TextItem

function studio(d: Doc, over: Partial<State> = {}) {
  const store = new Store({
    doc: d, selection: ['t1'], editing: null, page: 0, tool: 'select', view: { ...DEFAULT_VIEW }, panels: [], drawer: null,
    overset: new Set(), assets: {}, dialog: null, guide: null, threading: null, snaps: null, marquee: null,
    save: { rev: 1, state: 'saved', message: null, draft: false, live: false }, ...over,
  } as State, mono)
  const book = { add: vi.fn(), face: () => ({ features: ['smcp', 'onum', 'ss01'] }) }
  const ctx = { store, siteId: 's1', fonts: { book, ensure: () => Promise.resolve(), ensureDoc: () => Promise.resolve() } } as unknown as StudioCtx
  return { store, ctx }
}
const shown = (ctx: StudioCtx, el: React.ReactNode) => render(<StudioContext.Provider value={ctx}>{el}</StudioContext.Provider>)
const runs = (store: Store) => store.get().doc.threads[0].paras[0].runs

afterEach(() => { vi.clearAllMocks(); vi.unstubAllGlobals() })

describe('the type panels', () => {
  const words = () => doc({ items: [frame], threads: [{ id: 's1', frames: ['t1'], paras: [{ runs: [{ t: 'Cover lines' }] }] }] })

  it('turn on what the face offers, and kern', () => {
    const { store, ctx } = studio(words())
    shown(ctx, <CharacterPanel />)
    expect(screen.queryByRole('button', { name: 'Swashes' })).toBeNull() // this face has none
    fireEvent.click(screen.getByRole('button', { name: 'Small caps' }))
    expect(runs(store)[0].ot).toBe('smcp')
    fireEvent.click(screen.getByRole('button', { name: 'Set 1' }))
    expect(runs(store)[0].ot).toBe('smcp,ss01')
    fireEvent.click(screen.getByRole('button', { name: 'Small caps' }))
    expect(runs(store)[0].ot).toBe('ss01')
    expect(screen.getByRole('button', { name: 'Add your own font' })).toBeInTheDocument()
  })

  it('set a drop cap and keep lines together', () => {
    const { store, ctx } = studio(words())
    shown(ctx, <ParagraphPanel />)
    fireEvent.change(screen.getByTitle('Drop cap'), { target: { value: '3' } })
    fireEvent.change(screen.getByTitle('Widows: lines kept together at the top of a column'), { target: { value: '2' } })
    fireEvent.change(screen.getByTitle('Runts: the fewest words on the last line'), { target: { value: '2' } })
    expect(store.get().doc.threads[0].paras[0]).toMatchObject({ dc: 3, kw: 2, runt: 2 })
  })

  it('offer the magazine’s own fonts', () => {
    const own = { id: 'f1', family: 'u-0123456789abcdef', name: 'Canela', weight: 700, italic: false, sha: '4'.repeat(64), bytes: 1,
      upm: 1000, asc: 900, desc: -250, cap: 700, x: 480, features: [], filename: 'c.otf', hidden: false, created_at: '' }
    const { store, ctx } = studio(words(), { fonts: [own] })
    shown(ctx, <CharacterPanel />)
    fireEvent.change(screen.getByTitle('Your fonts'), { target: { value: own.family } })
    expect(runs(store)[0].font).toBe(own.family)
  })
})

describe('your own fonts', () => {
  it('upload only with the licence ticked, then list them', async () => {
    const font = { id: 'f1', family: 'u-0123456789abcdef', name: 'Canela', weight: 400, italic: false, sha: '4'.repeat(64), bytes: 1,
      upm: 1000, asc: 900, desc: -250, cap: 700, x: 480, features: [], filename: 'Canela-Regular.otf', hidden: false, created_at: '' }
    api.fonts.mockResolvedValueOnce({ fonts: [] }).mockResolvedValue({ fonts: [font] })
    api.uploadFont.mockResolvedValue(font)
    const { store, ctx } = studio(doc())
    shown(ctx, <FontsDialog />)
    await screen.findByText('No fonts of your own yet.')
    const file = new File(['x'], 'Canela-Regular.otf', { type: 'font/otf' })
    fireEvent.change(screen.getByLabelText('Font file'), { target: { files: [file] } })
    expect(screen.getByLabelText('Font name')).toHaveValue('Canela')
    const add = screen.getByRole('button', { name: 'Add font' })
    expect(add).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /I hold a licence/ }))
    fireEvent.click(add)
    await screen.findByText('Canela')
    expect(api.uploadFont).toHaveBeenCalledWith('s1', file, { name: 'Canela', licence: true })
    expect(store.get().fonts).toEqual([font])
  })

  it('say a plan without a magazine can’t have them', async () => {
    const { CappeApiError } = await import('../../api')
    api.fonts.mockRejectedValue(new CappeApiError('nope', 'plan_required', 402))
    const { ctx } = studio(doc())
    shown(ctx, <FontsDialog />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Your own fonts come with a magazine plan.')
  })
})

describe('the subject in front', () => {
  it('reads the cut-out’s silhouette and sets it over the text in one step', async () => {
    const pixels = new Uint8ClampedArray(4 * 4 * 4)
    for (const x of [1, 2]) pixels[(0 * 4 + x) * 4 + 3] = 255
    vi.stubGlobal('createImageBitmap', async () => ({ width: 4, height: 4, close: () => {} }))
    const getContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      drawImage: () => {}, getImageData: () => ({ data: pixels }),
    } as unknown as CanvasRenderingContext2D)
    api.pixels.mockResolvedValue(new Blob(['x']))
    const photo: ImageItem = { ...(newItem('image', 'p1', 'i1', { x: 0, y: 0, w: 400, h: 400 }) as ImageItem), asset_id: 'a1' }
    const cut: Asset = { id: 'c1', url: '/c.png', kind: 'edit', parent: 'a1', recipe: { cutout: { points: [], feather: 0, invert: false } } as never }
    const { store, ctx } = studio(doc({ items: [photo, frame] }))
    await placeSubject(ctx, 'i1', cut)
    const items = store.get().doc.items
    expect(items.map((i) => i.id)).toEqual(['i1', 't1', 'i2'])
    expect(items[2]).toMatchObject({ cutout: true, asset_id: 'c1', shape: { ar: 1, rows: [[0.25, 0.75], [1, 0], [1, 0], [1, 0]] } })
    expect(store.get().selection).toEqual(['i2'])
    store.undo()
    expect(store.get().doc.items).toHaveLength(2)
    getContext.mockRestore()
  })

  it('says why when the frame can’t have one', async () => {
    const { store, ctx } = studio(doc({ items: [frame] }))
    await placeSubject(ctx, 't1', { id: 'c1', url: '/c.png' })
    expect(store.get().notice).toMatch(/picture frame/)
  })
})

describe('kerning at the caret', () => {
  it('opens and closes the space after the letter before the caret, and typing on doesn’t take it', () => {
    const d = doc({ items: [frame], threads: [{ id: 's1', frames: ['t1'], paras: [{ runs: [{ t: 'AVA' }] }] }] })
    const { store } = studio(d)
    const editor = new TextEditor(store, () => null)
    editor.open('s1', [0, 1])
    const key = (k: string, mod = false) => act(() => {
      editor.view!.someProp('handleKeyDown', (f) => f(editor.view!, new KeyboardEvent('keydown', { key: k, altKey: true, ctrlKey: mod })))
    })
    key('ArrowLeft')
    key('ArrowLeft')
    expect(runs(store)).toEqual([{ t: 'A', kern: -20 }, { t: 'VA' }])
    key('ArrowRight', true)
    expect(runs(store)[0]).toEqual({ t: 'A', kern: 30 })
    act(() => { editor.view!.dispatch(editor.view!.state.tr.insertText('x')) })
    expect(runs(store)).toEqual([{ t: 'A', kern: 30 }, { t: 'xVA' }])
    editor.destroy()
  })

  it('takes the Kerning field at the caret, for the pair there', () => {
    const d = doc({ items: [frame], threads: [{ id: 's1', frames: ['t1'], paras: [{ runs: [{ t: 'AVA' }] }] }] })
    const { store, ctx } = studio(d)
    const editor = new TextEditor(store, () => null)
    ctx.editor = editor
    editor.open('s1', [0, 1])
    shown(ctx, <CharacterPanel />)
    const field = screen.getByLabelText('Kerning (⌥← ⌥→ at the caret)')
    fireEvent.change(field, { target: { value: '40' } })
    fireEvent.blur(field)
    expect(runs(store)).toEqual([{ t: 'A', kern: 40 }, { t: 'VA' }])
    act(() => { editor.view!.dispatch(editor.view!.state.tr.insertText('x')) })
    expect(runs(store)).toEqual([{ t: 'A', kern: 40 }, { t: 'xVA' }])
    editor.destroy()
  })

  it('changes tracking when letters are selected', () => {
    const d = doc({ items: [frame], threads: [{ id: 's1', frames: ['t1'], paras: [{ runs: [{ t: 'AVA' }] }] }] })
    const { store } = studio(d)
    const editor = new TextEditor(store, () => null)
    editor.open('s1', [0, 0], [0, 3])
    act(() => { editor.view!.someProp('handleKeyDown', (f) => f(editor.view!, new KeyboardEvent('keydown', { key: 'ArrowRight', altKey: true }))) })
    expect(runs(store)).toEqual([{ t: 'AVA', track: 10 }])
    editor.destroy()
  })
})
