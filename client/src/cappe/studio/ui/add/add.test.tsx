import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import manifest from '../../../../../../server/app/cappe/services/magazine/studio/fonts_manifest.json'
import { cappeApi } from '../../../api'
import type { CappeAsset, CappeStockResult } from '../../../types'
import type { Measure } from '../../compose/compose'
import { FaceBook, type Manifest } from '../../fonts/faces'
import { layout } from '../../canvas/geometry'
import { addItem, deletePage, movePage } from '../../model/ops'
import type { Doc, ImageItem } from '../../model/types'
import { DEFAULT_VIEW, Store, type State } from '../../store/store'
import { StudioContext, type StudioCtx } from '../context'
import AddPanel from './AddPanel'
import { ELEMENTS, TEXT_COMBOS, TEXT_STYLES, facesOf } from './catalog'
import { graphicsApi, matchPicks, type GraphicBrowse, type GraphicCard } from '../../model/graphics'
import type { BankPhoto } from './bank'
import { ObjectPanel } from '../panels/ObjectPanel'
import { describeStudio } from '../ask/describe'
import { dropInto, dropOn, importStock } from './drag'
import { addElement, addGraphic, addPicture, addText, landing } from './place'

const mono: Measure = { width: (c, t) => [...t].length * 0.5 * c.size, metrics: (c) => ({ asc: 0.8 * c.size, desc: 0.2 * c.size }) }
const book = new FaceBook(manifest as Manifest)
const doc = (): Doc => ({
  v: 1, size: { w: 600, h: 800 }, facing: false, margins: { t: 50, b: 50, i: 60, o: 40 }, cols: { n: 1, g: 12 },
  baseline: { start: 50, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'pt', paper: '#ffffff',
  pages: [{ id: 'p1' }, { id: 'p2' }], guides: [], items: [], threads: [], paywall_page: null,
})
const asset = (over: Partial<CappeAsset> = {}): CappeAsset => ({ id: 'a1', url: 'https://cdn.example.test/a.jpg', width: 1500, height: 1000,
  alt: 'Boats at dusk', credit_line: 'Ana', kind: 'upload', variants: null, ...over } as CappeAsset)

function studio(d = doc(), over: Partial<State> = {}) {
  const store = new Store({
    doc: d, selection: [], editing: null, page: 1, tool: 'text', view: { ...DEFAULT_VIEW, zoom: 1 }, panels: [], drawer: 'elements',
    overset: new Set(), assets: {}, dialog: null, guide: null, threading: null, snaps: null, marquee: null,
    save: { rev: 1, state: 'saved', message: null, draft: false, live: false }, ...over,
  } as State, mono)
  const board = document.createElement('div')
  board.getBoundingClientRect = () => ({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) })
  const ctx = { store, siteId: 's1', postId: 'post1', board: () => board, editor: { close: vi.fn() },
    fonts: { book, ensure: vi.fn(async () => {}) } } as unknown as StudioCtx
  return { store, ctx }
}

const el = (id: string) => ELEMENTS.find((e) => e.id === id)!
const only = (s: Store) => s.get().doc.items[s.get().doc.items.length - 1]

beforeEach(() => vi.restoreAllMocks())

describe('the side panel’s catalogue', () => {
  it('sets type only in faces the Studio has', () => {
    for (const s of [...TEXT_STYLES, ...TEXT_COMBOS]) {
      for (const [f, w, i] of facesOf(s, { font: 'Source Serif 4', wt: 400 })) {
        expect(book.face(f, w, i), `${s.id}: ${f} ${w}${i ? ' italic' : ''}`).toBeDefined()
      }
    }
  })

  it('has unique ids', () => {
    expect(new Set(ELEMENTS.map((e) => e.id)).size).toBe(ELEMENTS.length)
    const text = [...TEXT_STYLES, ...TEXT_COMBOS].map((s) => s.id)
    expect(new Set(text).size).toBe(text.length)
  })
})

describe('putting things on the page', () => {
  it('adds a shape in the middle of the page in view, selected, as one undo step', () => {
    const { store, ctx } = studio()
    addElement(ctx, el('rounded'))
    const s = store.get()
    expect(only(store)).toMatchObject({ kind: 'rect', page: 'p2', x: 228, y: 328, w: 144, h: 144, radius: 24, fill: '#d9d4cc' })
    expect(s.selection).toEqual([only(store).id])
    expect(s.tool).toBe('select')
    store.undo()
    expect(store.get().doc.items).toHaveLength(0)
  })

  it('puts a colour block behind everything, out to the bleed', () => {
    const d = addItem(doc(), 'rect', 'p2', { x: 0, y: 0, w: 10, h: 10 }).doc
    const { store, ctx } = studio(d)
    addElement(ctx, el('block-top'))
    const first = store.get().doc.items[0]
    expect(first).toMatchObject({ kind: 'rect', page: 'p2', x: -9, y: -9, w: 618, h: 169 })
    expect(store.get().doc.items).toHaveLength(2)
  })

  it('keeps what is dropped near an edge on the page', () => {
    const { store, ctx } = studio()
    const lay = layout(store.get().doc)
    const o = lay.origin[0]
    const at = landing(ctx, { clientX: o.x + 590, clientY: o.y + 10 })
    expect(at).toMatchObject({ page: 0, pageId: 'p1', x: 590, y: 10, hit: null, dropped: true })
    addElement(ctx, el('square'), at)
    expect(only(store)).toMatchObject({ page: 'p1', x: 609 - 144, y: -9 })
    expect(store.get().page).toBe(0)
  })

  it('sets text in its faces, in a frame cut to its lines', async () => {
    const { store, ctx } = studio()
    const editorial = TEXT_COMBOS.find((s) => s.id === 'editorial')!
    await addText(ctx, editorial)
    expect(ctx.fonts.ensure).toHaveBeenCalledTimes(3)
    const frame = only(store)
    const thread = store.get().doc.threads.find((t) => t.frames.includes(frame.id))!
    expect(thread.paras.map((p) => p.runs[0].t)).toEqual(editorial.parts.map((p) => p.text))
    expect(thread.paras[1]).toMatchObject({ role: 'h1', lead: 50, runs: [{ font: 'Playfair Display', wt: 900, size: 46 }] })
    expect(frame).toMatchObject({ kind: 'text', x: 60, w: 500 })
    expect(frame.h).toBeLessThan(400)
    expect(store.get().overset.size).toBe(0)
    expect(frame.y + frame.h / 2).toBeCloseTo(400, -1)
    store.undo()
    expect(store.get().doc.items).toHaveLength(0)
  })

  it('fills the empty frame selected, and otherwise makes a frame the picture’s shape', () => {
    const { store, ctx } = studio()
    addElement(ctx, el('frame-square'))
    const frame = only(store)
    addPicture(ctx, asset())
    expect(store.get().doc.items).toHaveLength(1)
    expect((only(store) as ImageItem).asset_id).toBe('a1')
    expect(store.get().assets.a1).toMatchObject({ id: 'a1', credit_line: 'Ana' })
    addPicture(ctx, asset({ id: 'a2' }))
    const made = only(store) as ImageItem
    expect(made.id).not.toBe(frame.id)
    expect(made).toMatchObject({ asset_id: 'a2', w: 360, h: 240 })
  })

  it('fills the frame a picture is dropped on, and drops anywhere else make a new one', async () => {
    const { store, ctx } = studio()
    const lay = layout(store.get().doc)
    const o = lay.origin[1]
    addElement(ctx, el('frame-landscape'), landing(ctx, { clientX: o.x + 300, clientY: o.y + 200 }))
    const frame = only(store)
    store.set({ selection: [] })
    await dropInto(ctx, { kind: 'asset', asset: asset() }, landing(ctx, { clientX: o.x + 300, clientY: o.y + 200 }))
    expect(store.get().doc.items).toHaveLength(1)
    expect((only(store) as ImageItem).asset_id).toBe('a1')
    await dropInto(ctx, { kind: 'asset', asset: asset({ id: 'a2' }) }, landing(ctx, { clientX: o.x + 300, clientY: o.y + 650 }))
    expect(store.get().doc.items).toHaveLength(2)
    expect(store.get().selection).toEqual([only(store).id])
    expect(only(store).id).not.toBe(frame.id)
  })
})

describe('what lands after a wait', () => {
  it('lands text on its page though the pages moved while its faces loaded, and says when the page went', async () => {
    const { store, ctx } = studio()  // page 2 (p2) in view
    const held: (() => void)[] = []
    vi.mocked(ctx.fonts.ensure).mockImplementation(() => new Promise<void>((resolve) => { held.push(resolve) }))
    const landed = addText(ctx, TEXT_STYLES[0])
    store.edit((d) => movePage(d, 1, 0))  // p2 is the first page now
    held.splice(0).forEach((go) => go())
    const id = await landed
    expect(store.get().doc.items.find((i) => i.id === id)?.page).toBe('p2')

    const lost = addText(ctx, TEXT_STYLES[0])
    store.edit((d) => deletePage(d, d.pages.findIndex((p) => p.id === 'p2')))
    const before = store.get().doc.items.length
    held.splice(0).forEach((go) => go())
    await expect(lost).rejects.toThrow('isn’t there any more')
    expect(store.get().doc.items).toHaveLength(before)
  })

  it('says in the Studio’s bar why a dropped archive picture couldn’t be added', async () => {
    vi.spyOn(cappeApi, 'post').mockResolvedValue({ imports: [{ id: 'j1', status: 'refused', error: 'Not licensed for reuse.', asset: null }] })
    const { store, ctx } = studio()
    const result = { source: 'nasa', source_id: 'moon-1', title: 'The Moon', credit_line: 'NASA', license: 'pdm', license_version: '',
      thumb: '/thumb', imported: false } as unknown as CappeStockResult
    await dropOn(ctx, { kind: 'stock', result }, landing(ctx))
    expect(store.get().notice).toBe('Not licensed for reuse.')
    expect(store.get().doc.items).toEqual([])
  })
})

describe('archive pictures', () => {
  const result = { source: 'nasa', source_id: 'moon-1', title: 'The Moon', credit_line: 'NASA', license: 'pdm', license_version: '',
    thumb: '/thumb', imported: false } as unknown as CappeStockResult

  it('are imported, waited for, and handed back once in the library', async () => {
    const post = vi.spyOn(cappeApi, 'post').mockResolvedValue({ imports: [{ id: 'j1', status: 'pending', asset: null }] })
    const get = vi.spyOn(cappeApi, 'get')
      .mockResolvedValueOnce({ imports: [{ id: 'j1', status: 'working', asset: null }] })
      .mockResolvedValueOnce({ imports: [{ id: 'j1', status: 'ready', asset: asset({ id: 'moon' }) }] })
    const got = await importStock('s1', 'post1', result, async () => {})
    expect(got.id).toBe('moon')
    expect(post).toHaveBeenCalledWith('/sites/s1/library/import', { items: [{ source: 'nasa', source_id: 'moon-1' }], post_id: 'post1' })
    expect(get).toHaveBeenLastCalledWith('/sites/s1/library/imports?ids=j1')
  })

  it('say why when one can’t be imported', async () => {
    vi.spyOn(cappeApi, 'post').mockResolvedValue({ imports: [{ id: 'j1', status: 'refused', error: 'Not licensed for reuse.', asset: null }] })
    await expect(importStock('s1', 'post1', result, async () => {})).rejects.toThrow('Not licensed for reuse.')
  })
})

describe('the side panel', () => {
  const show = (ctx: StudioCtx) => render(<StudioContext.Provider value={ctx}><AddPanel /></StudioContext.Provider>)

  it('opens and folds its tabs, and searches the elements', () => {
    const { store, ctx } = studio()
    show(ctx)
    expect(screen.getByRole('complementary', { name: 'Elements' })).toBeInTheDocument()
    fireEvent.change(screen.getByPlaceholderText(/Search shapes/), { target: { value: 'circle' } })
    expect(screen.getAllByRole('button', { name: /^Add / }).map((b) => b.getAttribute('aria-label')))
      .toEqual(['Add circle', 'Add circle outline', 'Add circle'])
    fireEvent.click(screen.getByRole('button', { name: 'Add circle outline' }))
    expect(only(store)).toMatchObject({ kind: 'ellipse', fill: null, stroke: { c: '#1a1a1a', w: 2 } })
    fireEvent.click(screen.getByRole('button', { name: 'Text' }))
    expect(store.get().drawer).toBe('text')
    fireEvent.click(screen.getByRole('button', { name: 'Text' }))
    expect(store.get().drawer).toBeNull()
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })

  it('adds a heading from the Text tab', async () => {
    const { store, ctx } = studio(doc(), { drawer: 'text' })
    show(ctx)
    fireEvent.click(screen.getByRole('button', { name: 'Add a heading' }))
    await waitFor(() => expect(store.get().doc.items).toHaveLength(1))
    expect(store.get().doc.threads[0].paras[0].runs[0]).toMatchObject({ t: 'Add a heading', font: 'Playfair Display', wt: 800 })
    expect(screen.getByRole('button', { name: 'Add fashion text' })).toBeInTheDocument()
  })

  it('puts nothing on the page from an AI picture cancelled while it was drawing', async () => {
    const { store, ctx } = studio(doc(), { drawer: 'photos' })
    let finish: (a: CappeAsset) => void = () => {}
    vi.spyOn(cappeApi, 'post').mockImplementation(() => new Promise((resolve) => { finish = resolve as (a: CappeAsset) => void }))
    show(ctx)
    fireEvent.click(screen.getByRole('button', { name: /Make an AI picture/ }))
    fireEvent.change(screen.getByPlaceholderText(/lighthouse keeper/), { target: { value: 'A red kite over the sea' } })
    fireEvent.submit(screen.getByRole('form', { name: 'Illustrate' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await act(async () => { finish(asset({ id: 'kite' })) })
    expect(store.get().doc.items).toEqual([])
  })

  it('finds free photos and adds one with a click', async () => {
    const { store, ctx } = studio(doc(), { drawer: 'photos' })
    const moon = { source: 'nasa', source_id: 'm1', title: 'The Moon', credit_line: 'NASA', license: 'pdm', license_version: '', thumb: '/t', imported: false }
    vi.spyOn(cappeApi, 'get').mockImplementation(async (path: string) => (path.includes('/library/bank')
      ? { total: 0, items: [], collections: [] }
      : { source: 'nasa', query: 'the moon', page: 0, results: [moon], has_more: false }) as never)
    vi.spyOn(cappeApi, 'post').mockResolvedValue({ imports: [{ id: 'j1', status: 'ready', asset: asset({ id: 'moon' }) }] })
    show(ctx)
    expect(await screen.findByText('No Gummfit photos yet. Try the archives.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'NASA' }))
    fireEvent.click(screen.getByRole('button', { name: 'the moon' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Add The Moon' }))
    await waitFor(() => expect((only(store) as ImageItem | undefined)?.asset_id).toBe('moon'))
  })

  it('lists your pictures and adds one with a click', async () => {
    const { store, ctx } = studio(doc(), { drawer: 'uploads' })
    const get = vi.spyOn(cappeApi, 'get').mockResolvedValue({ assets: [asset()] })
    show(ctx)
    const list = await screen.findByRole('list', { name: 'Your pictures' })
    fireEvent.click(within(list).getByRole('button', { name: 'Add Boats at dusk' }))
    expect((only(store) as ImageItem).asset_id).toBe('a1')
    fireEvent.click(screen.getByRole('tab', { name: 'AI' }))
    await waitFor(() => expect(get).toHaveBeenLastCalledWith('/sites/s1/assets?kind=generated'))
  })
})

const card = (over: Partial<GraphicCard>): GraphicCard => ({ sha: 'a'.repeat(64), name: 'Heart', group: 'icons', mono: true, fit: 'contain', w: 24, h: 24, ...over })

describe('graphics from the bank', () => {
  it('starts an icon its own shape in ink, named, and a sticker in its own colours', () => {
    const { store, ctx } = studio()
    addGraphic(ctx, card({ w: 48, h: 24 }))
    expect(only(store)).toMatchObject({ kind: 'graphic', src: 'a'.repeat(64), color: '#1a1a1a', fit: 'contain', name: 'Heart', w: 72, h: 36 })
    addGraphic(ctx, card({ sha: 'b'.repeat(64), name: 'Red heart', group: 'stickers', mono: false }))
    expect(only(store)).toMatchObject({ color: null, w: 120, h: 120 })
    const out = describeStudio(store.get())
    expect(out).toMatch(/Graphic "Heart".*colour #1a1a1a/)
    expect(out).toMatch(/Graphic "Red heart".*in its own colours/)
  })

  it('lays a pattern over the whole page, behind everything', () => {
    const d = addItem(doc(), 'rect', 'p2', { x: 0, y: 0, w: 10, h: 10 }).doc
    const { store, ctx } = studio(d)
    addGraphic(ctx, card({ name: 'Dots', group: 'patterns', fit: 'tile', w: 20, h: 20 }))
    expect(store.get().doc.items[0]).toMatchObject({ kind: 'graphic', fit: 'tile', x: -9, y: -9, w: 618, h: 818, color: '#d9d4cc' })
  })

  it('lets the Object panel recolour a one-colour graphic, repeat it, and says a colourful one keeps its colours', () => {
    const { store, ctx } = studio()
    addGraphic(ctx, card({}))
    const { unmount } = render(<StudioContext.Provider value={ctx}><ObjectPanel /></StudioContext.Provider>)
    expect(screen.getByText('Look', { selector: 'h3' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Repeat' }))
    expect(only(store)).toMatchObject({ fit: 'tile' })
    expect(screen.getByLabelText('Pattern size')).toBeInTheDocument()
    unmount()
    addGraphic(ctx, card({ sha: 'b'.repeat(64), name: 'Red heart', group: 'stickers', mono: false }))
    render(<StudioContext.Provider value={ctx}><ObjectPanel /></StudioContext.Provider>)
    expect(screen.getByText('A colourful graphic keeps its own colours.')).toBeInTheDocument()
  })

  it('browses the bank in the Elements tab, opens a group and searches it all', async () => {
    const icons = Array.from({ length: 24 }, (_, k) => card({ sha: k.toString(16).padStart(64, '0'), name: `Icon ${k}` }))
    const browse: GraphicBrowse = { version: 'v', sets: [], groups: [
      { group: 'shapes', count: 2, items: [card({ sha: 'c'.repeat(64), name: 'Star', group: 'shapes', fit: 'stretch' })] },
      { group: 'icons', count: 1890, items: icons },
    ] }
    vi.spyOn(graphicsApi, 'browse').mockResolvedValue(browse)
    vi.spyOn(graphicsApi, 'picks').mockResolvedValue([])
    const search = vi.spyOn(graphicsApi, 'search').mockResolvedValue({ total: 1, items: [card({ sha: 'd'.repeat(64), name: 'Coffee' })] })
    const { store, ctx } = studio()
    render(<StudioContext.Provider value={ctx}><AddPanel /></StudioContext.Provider>)
    fireEvent.click(await screen.findByRole('button', { name: 'Add Star' }))
    expect(screen.queryByText('From Gummfit')).not.toBeInTheDocument()
    expect(only(store)).toMatchObject({ kind: 'graphic', name: 'Star', fit: 'stretch' })
    expect(screen.getAllByRole('button', { name: /^Add Icon / })).toHaveLength(15)
    fireEvent.click(screen.getByRole('button', { name: 'See all 1,890' }))
    await waitFor(() => expect(search).toHaveBeenCalledWith('', 'icons', undefined, 0, 60))
    fireEvent.click(screen.getByRole('button', { name: /Icons/ }))
    fireEvent.change(screen.getByPlaceholderText(/Search shapes, icons/), { target: { value: 'coffee' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Add Coffee' }))
    expect(search).toHaveBeenLastCalledWith('coffee', undefined, undefined, 0, 60)
    expect(only(store)).toMatchObject({ name: 'Coffee' })
  })
})

const photo = (over: Partial<BankPhoto> = {}): BankPhoto => ({ id: 'b1', name: 'Harbour at dawn', url: 'https://cdn.example.test/b.jpg',
  variants: null as never, width: 1600, height: 1000, credit_line: 'Ana Ruiz / Gummfit', collection: 'Coast', ...over })

describe('Gummfit’s picks and photos', () => {
  const show = (ctx: StudioCtx) => render(<StudioContext.Provider value={ctx}><AddPanel /></StudioContext.Provider>)

  it('finds a pick by every word, in its name, tags or collection', () => {
    const picks = [card({ name: 'Wave', tags: ['sea', 'water'], collection: 'Coast' }), card({ sha: 'b'.repeat(64), name: 'Sun' })]
    expect(matchPicks(picks, 'sea coast').map((g) => g.name)).toEqual(['Wave'])
    expect(matchPicks(picks, 'WAVE')).toHaveLength(1)
    expect(matchPicks(picks, 'sea sun')).toHaveLength(0)
  })

  it('shows Gummfit’s graphics first in Elements, finds them, and adds one', async () => {
    vi.spyOn(graphicsApi, 'browse').mockResolvedValue({ version: 'v', sets: [], groups: [] })
    vi.spyOn(graphicsApi, 'search').mockResolvedValue({ total: 0, items: [] })
    const wave = card({ sha: 'e'.repeat(64), name: 'Wave', group: 'lines', fit: 'stretch', w: 200, h: 20, tags: ['sea'] })
    vi.spyOn(graphicsApi, 'picks').mockResolvedValue([wave])
    const { store, ctx } = studio()
    render(<StudioContext.Provider value={ctx}><AddPanel /></StudioContext.Provider>)
    fireEvent.click(await screen.findByRole('button', { name: 'Add Wave' }))
    expect(screen.getByText('From Gummfit')).toBeInTheDocument()
    expect(only(store)).toMatchObject({ kind: 'graphic', src: 'e'.repeat(64), fit: 'stretch', name: 'Wave' })
    const box = screen.getByPlaceholderText(/Search shapes, icons/)
    fireEvent.change(box, { target: { value: 'sea' } })
    expect(screen.getByRole('button', { name: 'Add Wave' })).toBeInTheDocument()
    fireEvent.change(box, { target: { value: 'mountain' } })
    expect(screen.queryByRole('button', { name: 'Add Wave' })).not.toBeInTheDocument()
  })

  it('opens Photos on Gummfit’s photos, by collection, and places one with a click', async () => {
    const { store, ctx } = studio(doc(), { drawer: 'photos' })
    const get = vi.spyOn(cappeApi, 'get').mockResolvedValue({ total: 1, items: [photo()], collections: ['Coast'] })
    const post = vi.spyOn(cappeApi, 'post').mockResolvedValue(asset({ id: 'bank1', kind: 'stock' }))
    show(ctx)
    const list = await screen.findByRole('list', { name: 'Gummfit photos' })
    fireEvent.click(within(list).getByRole('button', { name: 'Add Harbour at dawn' }))
    await waitFor(() => expect((only(store) as ImageItem | undefined)?.asset_id).toBe('bank1'))
    expect(post).toHaveBeenCalledWith('/sites/s1/library/bank/b1')
    fireEvent.click(screen.getByRole('tab', { name: 'Coast' }))
    await waitFor(() => expect(get).toHaveBeenLastCalledWith('/sites/s1/library/bank?q=&offset=0&collection=Coast'))
    fireEvent.change(screen.getByLabelText('Search free photos'), { target: { value: 'boats' } })
    fireEvent.submit(screen.getByRole('search'))
    await waitFor(() => expect(get).toHaveBeenLastCalledWith('/sites/s1/library/bank?q=boats&offset=0&collection=Coast'))
  })

  it('places a Gummfit photo dropped on the page', async () => {
    const { store, ctx } = studio()
    vi.spyOn(cappeApi, 'post').mockResolvedValue(asset({ id: 'bank1', kind: 'stock' }))
    await dropInto(ctx, { kind: 'bank', photo: photo() }, landing(ctx))
    expect(only(store)).toMatchObject({ kind: 'image', asset_id: 'bank1' })
  })
})
