import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import fonts from '../../../../../../server/app/cappe/services/magazine/studio/fonts_manifest.json'
import { collectionsApi } from '../../collectionsApi'
import { compose, type Measure } from '../../compose/compose'
import { Shaper } from '../../compose/shaper'
import { FaceBook, type Manifest } from '../../fonts/faces'
import { allIds } from '../../model/doc'
import { LIMITS, docProblem } from '../../model/limits'
import { portableCollection } from '../../model/collections'
import type { Doc, TextItem } from '../../model/types'
import { Store, DEFAULT_VIEW, type State } from '../../store/store'
import { StudioContext, type StudioCtx } from '../context'
import { applyCollection, insertCollection } from './applyCollection'
import { applyTemplate } from './applyTemplate'
import { COLLECTIONS } from './collections'
import { TEMPLATES } from './templates'
import CollectionsTab from './CollectionsTab'

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
    for (const { doc } of COLLECTIONS) {
      expect(doc.pages).toHaveLength(10)
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
    expect(built.doc.paywall_page).toBe(15)
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
    expect(store.get().doc.pages).toHaveLength(21)
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
    fireEvent.click(screen.getByRole('button', { name: 'Explore Maison' }))
    expect(screen.getByLabelText('Pages in this collection').querySelectorAll('.lyt-item').length).toBeGreaterThan(30)
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
    await waitFor(() => expect(collectionsApi.save).toHaveBeenCalledWith('My issue', portableCollection(store.get().doc)))
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
