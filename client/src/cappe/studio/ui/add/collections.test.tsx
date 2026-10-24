import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import fonts from '../../../../../../server/app/cappe/services/magazine/studio/fonts_manifest.json'
import { collectionsApi } from '../../collectionsApi'
import { compose, type Measure } from '../../compose/compose'
import { Shaper } from '../../compose/shaper'
import { FaceBook, type Manifest } from '../../fonts/faces'
import { allIds, newItem, pageSide, spreads } from '../../model/doc'
import { LIMITS, docProblem } from '../../model/limits'
import { collectionJsonSize, portableCollection } from '../../model/collections'
import type { Doc, TextItem } from '../../model/types'
import { Store, DEFAULT_VIEW, type State } from '../../store/store'
import { StudioContext, type StudioCtx } from '../context'
import { applyCollection, insertCollection } from './applyCollection'
import { applyTemplate } from './applyTemplate'
import { COLLECTIONS } from './collections'
import { TEMPLATES } from './templates'
import CollectionsTab from './CollectionsTab'
import { collectionLibrary } from './collectionLibrary'
import { collectionPreview } from './collectionPreview'
import TemplatesTab from './TemplatesTab'
import { CappeApiError } from '../../../api'

vi.mock('../../collectionsApi', () => ({ collectionsApi: { list: vi.fn(), open: vi.fn(), save: vi.fn(), remove: vi.fn() } }))
const book = new FaceBook(fonts as Manifest)
const measure: Measure = { width: (c, t) => [...t].length * 0.5 * c.size,
  metrics: (c) => { const f = book.measureFace(c.font, c.wt, c.it); return Shaper.metrics(f!, c.size) } }
const blank = (): Doc => ({ ...structuredClone(COLLECTIONS[0].doc), items: [], threads: [], pages: [{ id: 'p1' }, { id: 'p2' }] })
function studio(doc = blank()) {
  const store = new Store({ doc, page: 0, selection: [], tool: 'select', view: { ...DEFAULT_VIEW }, panels: [],
    assets: {}, editing: null, overset: new Set(), drawer: 'templates', dialog: null, guide: null, threading: null,
    snaps: null, marquee: null, save: { rev: 1, state: 'saved', draft: false, live: false, message: null },
  } as State, measure)
  const ctx = { store, fonts: { book, ensureDoc: vi.fn(async () => {}), ensure: vi.fn(async () => {}) },
    editor: { close: vi.fn() }, fit: vi.fn(), post: { title: 'An issue' },
  } as unknown as StudioCtx
  return { store, ctx }
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(collectionsApi.list).mockResolvedValue([]) })

describe('complete editorial designs', () => {
  it('contains four distinct, valid ten-page directions with available fonts and named frames', () => {
    expect(COLLECTIONS).toHaveLength(4)
    for (const { doc, pages } of COLLECTIONS) {
      expect(doc.pages).toHaveLength(10)
      expect(pages).toHaveLength(doc.pages.length) // each page named, in order
      expect(pages[0]).toBe('Cover')
      expect(docProblem(doc)).toBeNull()
      expect(new Set(allIds(doc)).size).toBe(allIds(doc).length)
      for (const i of doc.items) expect(i.name).toBeTruthy()
      for (const t of doc.threads) for (const p of t.paras) for (const r of p.runs) expect(book.face(r.font!, r.wt ?? 400, !!r.it), r.font).toBeDefined()
      expect(doc.items.some((i) => i.name === 'Masthead')).toBe(true)
      expect(doc.items.some((i) => i.name === 'Contents title')).toBe(true)
      expect(doc.items.some((i) => i.name === 'Opening headline')).toBe(true)
      expect(doc.items.some((i) => i.name === 'Essay photograph 3')).toBe(true)
      expect(doc.items.some((i) => i.name === 'Questions and answers')).toBe(true)
      expect(doc.items.some((i) => i.name === 'Credits title')).toBe(true)
    }
  })

  it('gives every sample line room at the actual face’s height', () => {
    for (const c of COLLECTIONS) for (const t of c.doc.threads) {
      const frames = t.frames.map((id) => c.doc.items.find((i) => i.id === id) as TextItem)
      expect(compose(t.paras, frames, measure).overset, `${c.name}: ${frames[0].name}`).toBe(false)
    }
  })
})

describe('using a collection', () => {
  it('starts a blank document in one undoable edit and recomposes its words', async () => {
    const { store, ctx } = studio()
    const original = store.get().doc
    expect(await applyCollection(ctx, COLLECTIONS[0].doc)).toBe(0)
    expect(store.get().doc.pages).toHaveLength(10)
    expect(store.get().overset.size).toBe(0)
    expect(store.get().doc.threads.every((t) => t.comp)).toBe(true)
    store.undo()
    expect(store.get().doc).toEqual(original)
    expect(store.canUndo()).toBe(false)
    store.redo()
    expect(store.get().doc.pages).toHaveLength(10)
  })

  it('keeps existing content, subscription boundary and linked text when inserted repeatedly', () => {
    const source = structuredClone(COLLECTIONS[0].doc)
    source.threads[0].frames.push(source.threads[1].frames[0])
    source.threads.splice(1, 1)
    const snapshot = structuredClone(source)
    const original = { ...structuredClone(COLLECTIONS[1].doc), paywall_page: 4 }
    const built = insertCollection(original, source, original.pages[1].id)
    expect(built.spacer).toBe(true)
    expect(built.page).toBe(4)
    expect(built.doc.paywall_page).toBe(16)
    for (const i of original.items) expect(built.doc.items).toContain(i)
    for (const t of original.threads) expect(built.doc.threads).toContain(t)
    const again = insertCollection(built.doc, source, original.pages[1].id)
    expect(new Set(allIds(again.doc)).size).toBe(allIds(again.doc).length)
    expect(again.doc.threads.find((t) => !original.threads.includes(t))!.frames).toHaveLength(2)
    expect(source).toEqual(snapshot)
    expect(docProblem(again.doc)).toBeNull()
  })

  it('fits an A4 page, scales type and restores bleed without bringing source photos', () => {
    const d = { ...blank(), size: { w: 595.28, h: 841.89 }, bleed: 12 }
    const src = structuredClone(COLLECTIONS[2].doc)
    const image = src.items.find((i) => i.kind === 'image')!
    if (image.kind === 'image') { image.asset_id = 'private-photo'; image.caption = 'private caption' }
    const built = insertCollection(d, src, 'p1').doc
    expect(built.size).toEqual(d.size)
    expect(built.items[0]).toMatchObject({ x: -12, y: -12, w: 619.28, h: 865.89 })
    expect(built.threads[0].paras[0].runs[0].size).toBeCloseTo(src.threads[0].paras[0].runs[0].size! * 595.28 / 612, 1)
    expect(built.items.filter((i) => i.kind === 'image').every((i) => i.asset_id === null && i.caption === '')).toBe(true)
  })

  it('preserves existing readers’ access rules when inserting after the paywall', () => {
    const doc = { ...COLLECTIONS[0].doc, paywall_page: 2 }
    expect(insertCollection(doc, COLLECTIONS[1].doc, doc.pages[5].id).doc.paywall_page).toBe(2)
  })

  it('preserves guides in an otherwise blank story and refuses excess guides', () => {
    const doc = { ...blank(), guides: [{ id: 'g1', page: 'p1', axis: 'v' as const, at: 100 }] }
    const built = insertCollection(doc, COLLECTIONS[0].doc, 'p1')
    expect(built.doc.guides).toEqual(doc.guides)
    expect(built.doc.pages[0]).toBe(doc.pages[0])
    expect(built.page).toBe(2)
    expect(built.doc.pages).toContain(doc.pages[1])
    const source = { ...COLLECTIONS[0].doc, guides: Array.from({ length: LIMITS.MAX_GUIDES }, (_, k) => ({ id: `g${k + 1}`, page: 'p1', axis: 'v' as const, at: k })) }
    expect(() => insertCollection(doc, source, 'p1')).toThrow(/at most 1000 guides/)
  })

  it('refuses extreme resizes that the server would silently clamp', () => {
    const tiny = { ...structuredClone(COLLECTIONS[0].doc), size: { w: 72, h: 72 } }
    tiny.threads[0].paras[0].runs[0].size = 200
    expect(() => insertCollection(blank(), tiny, 'p1')).toThrow(/measurements exceed/)
  })

  it('refuses a document past its limits atomically', async () => {
    const d = { ...COLLECTIONS[0].doc, pages: Array.from({ length: LIMITS.MAX_PAGES }, (_, k) => ({ id: `p${k + 1}` })) }
    const { store, ctx } = studio(d)
    const before = store.get().doc
    await expect(applyCollection(ctx, COLLECTIONS[0].doc)).rejects.toThrow(/at most 256 pages/)
    expect(store.get().doc).toBe(before)
    expect(store.canUndo()).toBe(false)
  })

  it('targets the clicked page while fonts load and excludes a competing template', async () => {
    const { store, ctx } = studio(COLLECTIONS[0].doc)
    let release!: () => void
    ctx.fonts.ensureDoc = vi.fn(() => new Promise<void>((resolve) => { release = resolve }))
    const applying = applyCollection(ctx, COLLECTIONS[1].doc)
    store.set({ page: 8 })
    await expect(applyCollection(ctx, COLLECTIONS[2].doc)).resolves.toBeNull()
    await expect(applyTemplate(ctx, TEMPLATES[0])).resolves.toBeNull()
    release()
    await expect(applying).resolves.toBe(2)
    expect(store.get().page).toBe(2)
    expect(store.get().doc.pages).toHaveLength(22)
  })

  it('refuses when the target page disappears or fonts cannot load', async () => {
    const { store, ctx } = studio(COLLECTIONS[0].doc)
    ctx.fonts.ensureDoc = vi.fn(async () => { store.edit((d) => ({ ...d, pages: d.pages.slice(1), items: [], threads: [] })) })
    await expect(applyCollection(ctx, COLLECTIONS[1].doc)).rejects.toThrow(/has been deleted/)
    const before = store.get().doc
    ctx.fonts.ensureDoc = vi.fn(async () => { throw new Error('Font unavailable') })
    store.set({ page: 0 })
    await expect(applyCollection(ctx, COLLECTIONS[1].doc)).rejects.toThrow('Font unavailable')
    expect(store.get().doc).toBe(before)
  })
})

describe('collection library', () => {
  it('previews all pages, applies a direction and reports completion', async () => {
    const { store, ctx } = studio()
    render(<StudioContext.Provider value={ctx}><CollectionsTab /></StudioContext.Provider>)
    expect(screen.getByRole('button', { name: 'Explore Maison' })).toHaveTextContent('10 editable pages')
    fireEvent.click(screen.getByRole('button', { name: 'Explore Maison' }))
    expect(screen.getByLabelText('Pages in this collection').querySelectorAll('.lyt-item').length).toBeGreaterThan(30)
    expect(screen.getByText('02 · Contents')).toBeInTheDocument()
    expect(screen.getByText('10 · Credits')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Use all 10 pages' }))
    await waitFor(() => expect(store.get().doc.pages).toHaveLength(10))
    expect(screen.getByText(/Added 10 pages/)).toBeInTheDocument()
  })

  it('saves a portable snapshot and allows removing it without changing story pages', async () => {
    const { store, ctx } = studio(COLLECTIONS[0].doc)
    const row = { id: 'saved', name: 'My issue', page_count: 10, created_at: '2026-10-23' }
    vi.mocked(collectionsApi.save).mockResolvedValue(row)
    vi.mocked(collectionsApi.open).mockResolvedValue({ ...row, doc: portableCollection(store.get().doc) })
    vi.mocked(collectionsApi.remove).mockResolvedValue(undefined)
    render(<StudioContext.Provider value={ctx}><CollectionsTab /></StudioContext.Provider>)
    const saveButton = screen.getByRole('button', { name: 'Save these pages' })
    await waitFor(() => expect(saveButton).not.toBeDisabled())
    fireEvent.click(saveButton)
    fireEvent.change(screen.getByLabelText('Collection name'), { target: { value: ' My issue ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save collection' }))
    await waitFor(() => expect(collectionsApi.save).toHaveBeenCalledWith('My issue', portableCollection(store.get().doc), expect.any(String)))
    fireEvent.click(await screen.findByRole('button', { name: /My issue/ }))
    const remove = await screen.findByRole('button', { name: 'Remove saved collection' })
    const original = store.get().doc
    fireEvent.click(remove)
    await waitFor(() => expect(collectionsApi.remove).toHaveBeenCalledWith('saved'))
    expect(store.get().doc).toBe(original)
  })

  it('leaves a failed save open for retry', async () => {
    const { ctx } = studio()
    vi.mocked(collectionsApi.save).mockRejectedValue(new Error('Connection lost'))
    render(<StudioContext.Provider value={ctx}><CollectionsTab /></StudioContext.Provider>)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save these pages' })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: 'Save these pages' }))
    fireEvent.change(screen.getByLabelText('Collection name'), { target: { value: 'Keep this name' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save collection' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Connection lost')
    expect(screen.getByLabelText('Collection name')).toHaveValue('Keep this name')
    expect(screen.getByRole('button', { name: 'Save collection' })).not.toBeDisabled()
  })
})

describe('collection robustness regressions', () => {
  it('preserves every original facing pair and page side before a nonempty tail', () => {
    const original = COLLECTIONS[0].doc
    for (const count of [1, 2, 3, 10]) for (const facing of [true, false]) for (const at of [0, 1, 2, 5, 8, 9]) {
      const source = { ...blank(), facing, pages: Array.from({ length: count }, (_, k) => ({ id: `p${k + 1}` })) }
      const built = insertCollection(original, source, original.pages[at].id)
      for (const [k, p] of original.pages.entries()) {
        const index = built.doc.pages.findIndex((next) => next.id === p.id)
        expect(pageSide(built.doc, index), `${count}/${facing}/${at}/${p.id}`).toBe(pageSide(original, k))
      }
      const pairs = spreads(built.doc).map((s) => s.map((k) => built.doc.pages[k].id).join('|'))
      for (const pair of spreads(original).filter((s) => s.length === 2)) expect(pairs).toContain(pair.map((k) => original.pages[k].id).join('|'))
    }
  })

  it('preserves zero-width/height line endpoints when fitting bleed', () => {
    for (const box of [{ x: 20, y: 0, w: 100, h: 0 }, { x: 0, y: 20, w: 0, h: 100 }]) {
      const source = { ...blank(), items: [newItem('line', 'p1', 'l1', box)] }
      const built = insertCollection({ ...blank(), bleed: 12 }, source, 'p1')
      expect(built.doc.items[0]).toMatchObject(box)
    }
  })

  it('preserves shapes entirely outside trim when reducing bleed', () => {
    for (const box of [{ x: -72, y: 20, w: 20, h: 100 }, { x: 20, y: -72, w: 100, h: 20 },
      { x: 664, y: 20, w: 20, h: 100 }, { x: 20, y: 844, w: 100, h: 20 }]) {
      const source = { ...blank(), bleed: 72, items: [newItem('rect', 'p1', 'r1', box)] }
      const built = insertCollection({ ...blank(), bleed: 0 }, source, 'p1')
      expect(built.doc.items[0]).toMatchObject(box)
    }
  })

  it('refuses page gutters and tiny strokes that the save schema would change', () => {
    const source = { ...blank(), size: { w: 306, h: 396 }, cols: { n: 2, g: 200 } }
    expect(() => insertCollection(blank(), source, 'p1')).toThrow(/measurements exceed/)
    const stroke = { ...newItem('line', 'p1', 'l1', { x: 20, y: 20, w: 100, h: 0 }), stroke: { c: '#000000', w: 0.01 } }
    expect(() => insertCollection({ ...blank(), size: { w: 72, h: 72 } }, { ...blank(), items: [stroke] }, 'p1')).toThrow(/measurements exceed/)
  })

  it('counts Unicode and emoji with the server’s ASCII JSON encoding', () => {
    expect(collectionJsonSize({ t: '界📷\u007f' })).toBe(32)
    const target: Doc = { ...blank(), pages: Array.from({ length: 15 }, (_, k) => ({ id: `p${k + 1}` })),
      items: Array.from({ length: 5000 }, (_, k) => ({ ...newItem('rect', `p${Math.floor(k / 350) + 1}`, `r${k + 1}`, { x: 0, y: 0, w: 10, h: 10 }), name: '界'.repeat(60) })),
      threads: ['t0', 't00'].map((id, k) => ({ id: `s${k}`, frames: [id], paras: [{ runs: [{ t: '界'.repeat(100_000) }] }] })),
    }
    target.items.push(...['t0', 't00'].map((id) => newItem('text', 'p15', id, { x: 0, y: 0, w: 500, h: 500 })))
    const source: Doc = { ...blank(), items: [newItem('text', 'p1', 't1', { x: 0, y: 0, w: 500, h: 500 })],
      threads: [{ id: 's1', frames: ['t1'], paras: [{ runs: [{ t: '界'.repeat(100_000) }] }] }],
    }
    expect(collectionJsonSize(target)).toBeLessThan(LIMITS.MAX_DOC_BYTES)
    expect(collectionJsonSize(portableCollection(source))).toBeLessThan(1_000_000)
    expect(() => insertCollection(target, source, 'p1')).toThrow(/too big to save/)
  })

  it('validates the composed size before mutating the document, undo, or autosave', async () => {
    const para = { runs: [{ t: '', font: 'Bodoni Moda', wt: 500, size: 12, track: 1, color: '#111111', u: true }], lead: 2 }
    const count = Math.floor((3_900_000 - 2000) / (JSON.stringify(para).length + 1))
    const target: Doc = { ...blank(), pages: [{ id: 'p1' }], items: [newItem('rect', 'p1', 'r1', { x: 0, y: 0, w: 50, h: 50 })], threads: [] }
    for (let k = 0, remaining = count; remaining > 0; k++) {
      const n = Math.min(10_000, remaining); remaining -= n
      target.items.push(newItem('text', 'p1', `t${k + 1}`, { x: 0, y: 0, w: 500, h: 0 }))
      target.threads.push({ id: `s${k + 1}`, frames: [`t${k + 1}`], paras: Array.from({ length: n }, () => structuredClone(para)), comp: { lines: [] } })
    }
    const source: Doc = { ...blank(), pages: [{ id: 'p1' }], items: [newItem('text', 'p1', 'tsrc', { x: 0, y: 0, w: 100, h: 20_000 })],
      threads: [{ id: 'ssrc', frames: ['tsrc'], paras: [{ runs: [{ t: 'x\n'.repeat(10_000), size: 1 }] }] }],
    }
    const { store, ctx } = studio(target)
    const before = store.get().doc
    const changed = vi.fn(); store.onDocChange = changed
    expect(collectionJsonSize(insertCollection(before, source, 'p1').doc)).toBeLessThan(LIMITS.MAX_DOC_BYTES)
    await expect(applyCollection(ctx, source)).rejects.toThrow(/too big to save/)
    expect(store.get().doc).toBe(before)
    expect(store.canUndo()).toBe(false)
    expect(changed).not.toHaveBeenCalled()
  })

  it('shares preview preparation across all pages and retries a failed font load', async () => {
    const { ctx } = studio()
    const source = structuredClone(COLLECTIONS[0].doc)
    const first = collectionPreview(ctx, source)
    await Promise.all(Array.from({ length: 32 }, () => {
      expect(collectionPreview(ctx, source)).toBe(first)
      return collectionPreview(ctx, source)
    }))
    expect(ctx.fonts.ensureDoc).toHaveBeenCalledTimes(1)
    const next = structuredClone(source)
    vi.mocked(ctx.fonts.ensureDoc).mockRejectedValueOnce(new Error('Offline'))
    await expect(collectionPreview(ctx, next)).rejects.toThrow('Offline')
    await expect(collectionPreview(ctx, next)).resolves.toMatchObject({ pages: source.pages })
  })

  it('keeps a pending save and its completion when switching template views', async () => {
    const { ctx } = studio()
    const row = { id: 'new', name: 'In flight', page_count: 2, created_at: '2026-10-23' }
    let finish!: (card: typeof row) => void
    vi.mocked(collectionsApi.save).mockImplementation(() => new Promise((resolve) => { finish = resolve }))
    render(<StudioContext.Provider value={ctx}><TemplatesTab /></StudioContext.Provider>)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save these pages' })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: 'Save these pages' }))
    fireEvent.change(screen.getByLabelText('Collection name'), { target: { value: row.name } })
    fireEvent.click(screen.getByRole('button', { name: 'Save collection' }))
    fireEvent.click(screen.getByRole('button', { name: 'Single pages' }))
    fireEvent.click(screen.getByRole('button', { name: 'Collections' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled())
    await act(async () => { finish(row) })
    await waitFor(() => expect(screen.getByRole('button', { name: /In flight/ })).toBeInTheDocument())
    expect(screen.getByRole('status')).toHaveTextContent('saved to your collections')
    expect(collectionsApi.list).toHaveBeenCalledTimes(1)
  })

  it('invalidates stale reads and reuses a request key for an unchanged retry', async () => {
    const { store } = studio()
    const library = collectionLibrary(store)
    await library.load()
    library.form(true); library.rename('Retry')
    vi.mocked(collectionsApi.save).mockRejectedValueOnce(new Error('Response lost'))
    await library.save(store.get().doc)
    const first = vi.mocked(collectionsApi.save).mock.calls[0]
    let finishRead!: (rows: []) => void
    vi.mocked(collectionsApi.list).mockImplementationOnce(() => new Promise((resolve) => { finishRead = resolve }))
    const read = library.load(true)
    const row = { id: 'saved', name: 'Retry', page_count: 2, created_at: '2026-10-23' }
    vi.mocked(collectionsApi.save).mockResolvedValue(row)
    await library.save(store.get().doc)
    finishRead([]); await read
    expect(vi.mocked(collectionsApi.save).mock.calls[1]).toEqual(first)
    expect(library.get().rows).toEqual([row])
    library.rename('Changed intent')
    await library.save(store.get().doc)
    expect(vi.mocked(collectionsApi.save).mock.calls[2][2]).not.toEqual(first[2])
  })

  it('refreshes collections from another session when reopening the panel', async () => {
    const { ctx } = studio()
    render(<StudioContext.Provider value={ctx}><TemplatesTab /></StudioContext.Provider>)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save these pages' })).not.toBeDisabled())
    const row = { id: 'another-session', name: 'From another Studio', page_count: 2, created_at: '2026-10-23' }
    vi.mocked(collectionsApi.list).mockResolvedValue([row])
    fireEvent.click(screen.getByRole('button', { name: 'Single pages' }))
    fireEvent.click(screen.getByRole('button', { name: 'Collections' }))
    expect(await screen.findByRole('button', { name: /From another Studio/ })).toBeInTheDocument()
    expect(collectionsApi.list).toHaveBeenCalledTimes(2)
  })

  it.each(['save', 'remove'] as const)('preserves a %s failure settled while the panel was hidden', async (operation) => {
    const { store, ctx } = studio()
    const library = collectionLibrary(store)
    let fail!: (error: Error) => void
    const response = new Promise<never>((_resolve, reject) => { fail = reject })
    if (operation === 'save') vi.mocked(collectionsApi.save).mockReturnValueOnce(response)
    else vi.mocked(collectionsApi.remove).mockReturnValueOnce(response)
    render(<StudioContext.Provider value={ctx}><TemplatesTab /></StudioContext.Provider>)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save these pages' })).not.toBeDisabled())
    library.rename('Keep my name')
    let pending!: Promise<unknown>
    act(() => { pending = operation === 'save' ? library.save(store.get().doc) : library.remove('missing') })
    fireEvent.click(screen.getByRole('button', { name: 'Single pages' }))
    await act(async () => { fail(new Error('Write lost while hidden')); await pending })
    fireEvent.click(screen.getByRole('button', { name: 'Collections' }))
    await waitFor(() => expect(collectionsApi.list).toHaveBeenCalledTimes(2))
    expect(await screen.findByRole('alert')).toHaveTextContent('Write lost while hidden')
    expect(library.get().name).toBe('Keep my name')
  })

  it('recovers an initial list failure after saving and keeps all pre-existing rows', async () => {
    const { store } = studio()
    const library = collectionLibrary(store)
    vi.mocked(collectionsApi.list).mockRejectedValueOnce(new Error('Offline'))
    await library.load()
    const older = { id: 'older', name: 'Older', page_count: 2, created_at: '2026-10-22' }
    const row = { id: 'new', name: 'New', page_count: 2, created_at: '2026-10-23' }
    vi.mocked(collectionsApi.save).mockResolvedValue(row)
    vi.mocked(collectionsApi.list).mockResolvedValue([row, older])
    library.form(true); library.rename(row.name)
    await library.save(store.get().doc)
    await waitFor(() => expect(library.get().rows).toEqual([row, older]))
    expect(library.get().error).toBeNull()
  })

  it('keeps failed deletions retryable and accepts a missing row after a lost response', async () => {
    const { store } = studio()
    const library = collectionLibrary(store)
    const row = { id: 'remove', name: 'Remove', page_count: 2, created_at: '2026-10-23' }
    vi.mocked(collectionsApi.list).mockResolvedValue([row])
    await library.load()
    vi.mocked(collectionsApi.remove).mockRejectedValueOnce(new Error('Network lost'))
    expect(await library.remove(row.id)).toBe(false)
    expect(library.get().rows).toEqual([row])
    expect(library.get().pending).toBeNull()
    vi.mocked(collectionsApi.remove).mockRejectedValueOnce(new CappeApiError('Missing', undefined, 404))
    expect(await library.remove(row.id)).toBe(true)
    expect(library.get().rows).toEqual([])
  })

  it('refuses excessive page and Unicode sizes before sending a save', async () => {
    const { store } = studio()
    const library = collectionLibrary(store)
    await library.load(); library.form(true); library.rename('Keep this name')
    await library.save({ ...blank(), pages: Array.from({ length: 33 }, (_, k) => ({ id: `p${k + 1}` })) })
    expect(library.get().error).toMatch(/up to 32 pages/)
    const large = structuredClone(COLLECTIONS[0].doc)
    large.threads[0].paras[0].runs[0].t = '界'.repeat(200_000)
    await library.save(large)
    expect(library.get().error).toMatch(/too big to save/)
    expect(library.get().name).toBe('Keep this name')
    expect(library.get().pending).toBeNull()
    expect(collectionsApi.save).not.toHaveBeenCalled()
  })

  it('serializes repeated save clicks and gives an edited design a fresh request key', async () => {
    const { store } = studio()
    const library = collectionLibrary(store)
    await library.load(); library.rename('Same name')
    let reject!: (error: Error) => void
    vi.mocked(collectionsApi.save).mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail }))
    const first = library.save(store.get().doc)
    await library.save(store.get().doc)
    expect(collectionsApi.save).toHaveBeenCalledTimes(1)
    reject(new Error('Lost response')); await first
    const key = vi.mocked(collectionsApi.save).mock.calls[0][2]
    const changed = { ...blank(), paper: '#ff0000' }
    vi.mocked(collectionsApi.save).mockResolvedValue({ id: 'new', name: 'Same name', page_count: 2, created_at: '2026-10-23' })
    await library.save(changed)
    expect(vi.mocked(collectionsApi.save).mock.calls[1][2]).not.toBe(key)
  })

  it('keeps deletion pending across view changes and removes the row on completion', async () => {
    const { ctx } = studio()
    const row = { id: 'deleted', name: 'Remove me', page_count: 2, created_at: '2026-10-23' }
    vi.mocked(collectionsApi.list).mockResolvedValue([row])
    vi.mocked(collectionsApi.open).mockResolvedValue({ ...row, doc: blank() })
    let finish!: () => void
    vi.mocked(collectionsApi.remove).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    render(<StudioContext.Provider value={ctx}><TemplatesTab /></StudioContext.Provider>)
    fireEvent.click(await screen.findByRole('button', { name: /Remove me/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Remove saved collection' }))
    fireEvent.click(screen.getByRole('button', { name: 'Single pages' }))
    fireEvent.click(screen.getByRole('button', { name: 'Collections' }))
    expect(screen.getByRole('button', { name: /Remove me/ })).toBeDisabled()
    await act(async () => { finish() })
    await waitFor(() => expect(screen.queryByRole('button', { name: /Remove me/ })).not.toBeInTheDocument())
    expect(screen.getByRole('status')).toHaveTextContent('removed from your library')
  })

  it('refuses compositions that the server would discard for excessive line count', async () => {
    const source: Doc = { ...blank(),
      items: ['p1', 'p2'].map((page, k) => newItem('text', page, `t${k + 1}`, { x: 0, y: 0, w: 100, h: 20_000 })),
      threads: [{ id: 's1', frames: ['t1', 't2'], paras: [{ runs: [{ t: 'x\n'.repeat(35_000), size: 1 }] }] }],
    }
    const { store, ctx } = studio()
    const original = store.get().doc
    await expect(applyCollection(ctx, source)).rejects.toThrow(/too many composed lines/)
    expect(store.get().doc).toBe(original)
    expect(store.canUndo()).toBe(false)
  })
})

describe('collections from identity-styled pages', () => {
  it('keep how the pages look and name nothing of the source identity, parent frames included', async () => {
    const { captureParent, starterIdentity } = await import('../../model/identity')
    let doc: Doc = { ...blank(), identity: starterIdentity() }
    doc = { ...doc, items: [
      { ...newItem('text', 'p1', 't1', { x: 50, y: 50, w: 300, h: 100 }) } as TextItem,
      { ...newItem('rect', 'p1', 'r1', { x: 0, y: 0, w: 20, h: 20 }), fill: '#000000', fill_swatch: 'sw3' } as Doc['items'][number],
    ], threads: [{ id: 's1', frames: ['t1'], paras: [{ style: 'ps3', runs: [{ t: 'Caption', style: 'cs1' }] }] }] }
    doc = captureParent(doc, 0, 'pl1', 'Feature')
    doc = { ...doc, pages: doc.pages.map((p) => ({ ...p, parent: 'pl1' })) }
    const flat = portableCollection(doc)
    expect(flat.identity).toBeUndefined()
    expect(JSON.stringify(flat)).not.toMatch(/"(style|swatch|fill_swatch|parent)"/)
    // The parent's frames became each page's own, looking as they did.
    expect(flat.items.filter((i) => i.kind === 'rect').map((i) => (i as { fill: string }).fill)).toEqual(['#b44d35', '#b44d35'])
    const run = flat.threads[0].paras[0].runs[0]
    expect(run).toMatchObject({ font: 'Inter', size: 8, color: '#72726b', it: true })
    // Inserted into a story with no identity, the story still saves.
    const into = insertCollection(blank(), doc, 'p1')
    expect(docProblem(into.doc)).toBeNull()
    expect(JSON.stringify(into.doc)).not.toMatch(/"(style|swatch|fill_swatch)"/)
  })
})
