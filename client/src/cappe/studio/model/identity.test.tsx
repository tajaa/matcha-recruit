import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DOMParser, DOMSerializer } from '@tiptap/pm/model'
import manifest from '../../../../../server/app/cappe/services/magazine/studio/fonts_manifest.json'
import { identityApi } from '../identityApi'
import { composeDoc, type Measure } from '../compose/compose'
import { FaceBook, type Manifest } from '../fonts/faces'
import { newItem } from './doc'
import { captureParent, detachParent, importIdentity, linkRole, parentDoc, removeStyle, removeSwatch, resolveParas, resolveItem, starterIdentity } from './identity'
import { addPages, applyChar, applyPara, movePage, patchItems } from './ops'
import { docProblem, identityName } from './limits'
import type { Doc, ImageItem, Para } from './types'
import { fromPM, portableSlice, schema, toPM } from '../text/pm'
import { Store, DEFAULT_VIEW, type State } from '../store/store'
import { frameThreads, pageItemsHtml, pagesHtml } from '../render/layoutRender'
import { StudioContext, type StudioCtx } from '../ui/context'
import { IdentityPanel } from '../ui/panels/IdentityPanel'
import { ObjectPanel } from '../ui/panels/ObjectPanel'
import { identityLibrary } from '../ui/identityLibrary'
import { command, paste } from '../ui/commands'

vi.mock('../identityApi', () => ({ identityApi: { open: vi.fn(), save: vi.fn() } }))
const measure: Measure = { width: (c, text) => [...text].length * c.size * 0.5, metrics: (c) => ({ asc: c.size * 0.8, desc: c.size * 0.2 }) }
const book = new FaceBook(manifest as Manifest)
function doc(): Doc {
  return { v: 1, size: { w: 612, h: 792 }, facing: true, margins: { t: 54, b: 54, i: 54, o: 54 }, cols: { n: 3, g: 12 }, baseline: { start: 54, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'in', paper: '#ffffff',
    pages: [{ id: 'p1' }, { id: 'p2' }], guides: [], paywall_page: null, identity: starterIdentity(),
    items: ['p1', 'p2'].map((page, k) => newItem('text', page, `t${k + 1}`, { x: 54, y: 54, w: 120, h: 600 })),
    threads: ['t1', 't2'].map((frame, k) => ({ id: `s${k + 1}`, frames: [frame], paras: [{ style: 'ps3', runs: [{ t: 'A caption with enough words to wrap across several lines.' }] }] })),
  }
}
function studio(d = doc()) {
  const store = new Store({ doc: d, page: 0, selection: ['t1'], tool: 'select', view: DEFAULT_VIEW, panels: ['identity'], drawer: null, editing: null, overset: new Set(), assets: {}, dialog: null, guide: null, threading: null, snaps: null, marquee: null, save: { state: 'saved', rev: 1, draft: false, live: false, message: null } } as State, measure)
  const ctx = { store, siteId: 'site', fonts: { book, ensureDoc: vi.fn(async () => {}) }, editor: { currentChar: () => ({}), currentPara: () => ({}), close: vi.fn() } } as unknown as StudioCtx
  return { store, ctx }
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(identityApi.open).mockResolvedValue({ rev: 0, identity: null }) })

describe('live magazine identities', () => {
  it('updates every linked caption, composes again and undoes in one step without freezing references', () => {
    const { store } = studio(), before = store.get().doc
    store.edit((d) => ({ ...d, identity: { ...d.identity!, paragraphs: d.identity!.paragraphs.map((p) => p.id === 'ps3' ? { ...p, char: { ...p.char, size: 24 } } : p) } }))
    const next = store.get().doc
    for (const t of next.threads) expect(resolveParas(t.paras, next.identity)[0].runs[0].size).toBe(24)
    expect(next.threads[0].comp!.lines.length).toBeGreaterThan(before.threads[0].comp!.lines.length)
    expect(next.threads[0].paras[0]).toEqual(before.threads[0].paras[0])
    store.undo(); expect(store.get().doc).toBe(before)
  })

  it('keeps explicit default/false overrides and style boundaries through typing serialization', () => {
    const paras: Para[] = [{ style: 'ps3', align: 'l', runs: [{ t: 'plain', wt: 400, it: false, size: 10.5 }, { t: 'styled', style: 'cs1', it: false }] }]
    expect(fromPM(toPM(paras))).toEqual(paras)
    const changed = applyChar(paras, [0, 0], [0, 5], { color: '#1a1a1a' })
    expect(fromPM(toPM(changed))[0].runs[0].color).toBe('#1a1a1a')
    const p = resolveParas(changed, starterIdentity())[0]
    expect(p.runs[0]).toMatchObject({ it: false, wt: 400, size: 10.5, color: '#1a1a1a' })
    expect(p.runs[1].it).toBe(false)
  })

  it('applying a named style clears old local type but preserves character style spans', () => {
    const paragraphs: Para[] = [{ sa: 40, runs: [{ t: 'a', size: 50 }, { t: 'b', style: 'cs1', size: 60 }] }]
    const applied = applyPara(paragraphs, 0, 0, { style: 'ps3' })
    expect(applied).toEqual([{ style: 'ps3', runs: [{ t: 'a' }, { t: 'b', style: 'cs1' }] }])
    expect(applyChar(applied, [0, 0], [0, 1], { style: 'cs1' })[0].runs).toEqual([{ t: 'ab', style: 'cs1' }])
  })

  it('palette edits update bound type/shapes; local colour edits detach only that binding', () => {
    const d = doc(), shape = { ...newItem('rect', 'p1', 'r1', { x: 0, y: 0, w: 20, h: 20 }), fill_swatch: 'sw2' }
    d.items.push(shape)
    d.identity!.swatches[1].color = '#ff0000'
    expect(resolveParas(d.threads[0].paras, d.identity)[0].runs[0].color).toBe('#ff0000')
    expect(resolveItem(shape, d.identity)).toMatchObject({ fill: '#ff0000' })
    const local = patchItems(d, ['r1'], { fill: '#000000' })
    expect(resolveItem(local.items.at(-1)!, local.identity)).toMatchObject({ fill: '#000000' })
    const removed = removeSwatch(d, 'sw2')
    expect(resolveParas(removed.threads[0].paras, removed.identity)[0].runs[0].color).toBe('#ff0000')
    expect(removed.identity!.paragraphs[2].char.swatch).toBeUndefined()
  })

  it('deleting styles keeps text and appearance in both local and parent threads', () => {
    const d = doc(), shown = resolveParas(d.threads[0].paras, d.identity)
    const removed = removeStyle(d, 'paragraphs', 'ps3')
    expect(resolveParas(removed.threads[0].paras, removed.identity)).toEqual(shown)
    expect(removed.threads[0].paras[0].style).toBeUndefined()
  })

  it('captures photo-free parents, updates linked pages and detaches just one page with fresh IDs', () => {
    let d = doc(); d.items = d.items.slice(0, 1); d.threads = d.threads.slice(0, 1)
    d.items.push({ ...newItem('image', 'p1', 'i1', { x: 0, y: 0, w: 20, h: 20 }), asset_id: 'private', caption: 'private' } as ImageItem)
    d = captureParent(d, 0, 'pl1', 'Feature')
    expect(d.items).toHaveLength(0)
    expect(d.identity!.parents[0].items[1]).toMatchObject({ asset_id: null, caption: '' })
    d.pages[1].parent = 'pl1'
    const prepared = composeDoc(d, measure).doc
    expect(pageItemsHtml(prepared, 1, { assets: {}, faces: book.face, used: new Map(), threads: frameThreads(prepared) })).toContain('A caption')
    const detached = detachParent(prepared, 1)
    expect(detached.pages[0].parent).toBe('pl1'); expect(detached.pages[1].parent).toBeUndefined()
    expect(detached.items).toHaveLength(2)
    expect(new Set(detached.items.map((i) => i.id)).size).toBe(2)
    expect(detached.threads[0].paras[0].style).toBe('ps3')
    expect(() => captureParent(prepared, 0, 'pl2', 'Another')).toThrow(/Detach/)
  })

  it('refuses capturing a fragment of linked story text', () => {
    const d = doc(); d.threads = [{ ...d.threads[0], frames: ['t1', 't2'] }]
    expect(() => captureParent(d, 0, 'pl1', 'Fragment')).toThrow(/Unlink/)
  })

  it('reuses native parent preparation and safely scales a detached copy', () => {
    let d = doc(); d.items = d.items.slice(0, 1); d.threads = d.threads.slice(0, 1); d = captureParent(d, 0, 'pl1', 'Parent')
    const p = d.identity!.parents[0]
    expect(parentDoc({ ...d }, p)).toBe(parentDoc(d, p))
    const detached = detachParent({ ...d, size: { w: 306, h: 396 } }, 0)
    expect(detached.items[0]).toMatchObject({ x: 27, y: 27, w: 60, h: 300 })
    expect(detached.threads[0].paras[0].runs[0].size).toBe(4)
    expect(detached.threads[0].paras[0].style).toBeUndefined()
  })

  it('copies appearances across documents without leaking local style or palette IDs', () => {
    const { store, ctx } = studio(), original = store.get().doc
    command('copy').run(ctx)
    const target = doc(); delete target.identity; target.items = []; target.threads = []
    const copied = paste(target, 'p1').doc
    expect(copied.threads[0].paras[0].style).toBeUndefined()
    expect(copied.threads[0].paras[0].runs[0]).toMatchObject({ size: 8, color: '#72726b' })
    const same = paste(original, 'p2', store).doc
    expect(same.threads.at(-1)!.paras[0].style).toBe('ps3')
    const pm = toPM(original.threads[0].paras)
    const slice = portableSlice(pm.slice(0, pm.content.size), original.identity)
    const external = fromPM(pm.type.create(null, slice.content))
    expect(external[0].style).toBeUndefined()
    expect(external[0].runs[0]).toMatchObject({ size: 8, color: '#72726b' })
  })

  it('merges saved definitions by name and remaps colliding IDs in parent/type/palette references', () => {
    const d = doc(), source = starterIdentity()
    source.swatches = [{ id: 'alien', name: 'Muted', color: '#ff0000' }]
    source.paragraphs = [{ ...source.paragraphs[2], id: 'different', char: { size: 20, swatch: 'alien' } }]
    source.characters = []
    source.parents = [{ id: 'pl1', name: 'New parent', size: d.size, items: [newItem('text', 'p1', 't1', { x: 0, y: 0, w: 100, h: 100 })], threads: [{ id: 's1', frames: ['t1'], paras: [{ style: 'different', runs: [{ t: 'shared' }] }] }] }]
    const imported = importIdentity(d, source)
    expect(imported.identity!.paragraphs).toHaveLength(3)
    expect(imported.identity!.parents[0].threads[0].paras[0].style).toBe('ps3')
    expect(resolveParas(imported.threads[0].paras, imported.identity)[0].runs[0]).toMatchObject({ size: 20, color: '#ff0000' })
    expect(d.identity!.swatches[1].color).not.toBe('#ff0000')
  })

  it('copies a partial caption with inherited type and full paragraphs with their spacing and semantic role', () => {
    const d = doc(), pm = toPM(d.threads[0].paras)
    const inline = portableSlice(pm.slice(1, 6), d.identity, { style: 'ps3' })
    const pasted = fromPM(schema.node('doc', null, [schema.node('paragraph', null, inline.content)]))
    expect(pasted[0].runs[0]).toMatchObject({ size: 8, font: 'Inter', color: '#72726b' })
    const full = portableSlice(pm.slice(0, pm.content.size), d.identity)
    const host = document.createElement('div'); host.append(DOMSerializer.fromSchema(schema).serializeFragment(full.content))
    const roundtrip = fromPM(DOMParser.fromSchema(schema).parse(host))
    expect(roundtrip[0]).toMatchObject({ role: 'caption', sa: 4 })
    expect(roundtrip[0].style).toBeUndefined()
    host.innerHTML = '<p data-pa="{&quot;style&quot;:&quot;ps1&quot;}"><span data-ch="{&quot;style&quot;:&quot;cs1&quot;}">outside</span></p>'
    const untrusted = fromPM(DOMParser.fromSchema(schema).parse(host))
    expect(untrusted[0].style).toBeUndefined(); expect(untrusted[0].runs[0].style).toBeUndefined()
  })

  it('links effective paragraph roles across local and parent text without reclassifying headings', () => {
    const d = doc()
    d.threads[0].paras.push({ style: 'ps2', runs: [{ t: 'Heading' }] }, { runs: [{ t: 'Body' }] })
    d.identity!.parents = [{ id: 'pl1', name: 'Footer', size: d.size, items: [], threads: [d.threads[1]] }]
    d.identity!.paragraphs.push({ ...d.identity!.paragraphs[2], id: 'ps4', name: 'New caption' })
    const body = linkRole(d, 'ps1')
    expect(body.threads[0].paras.map((p) => p.style)).toEqual(['ps3', 'ps2', 'ps1'])
    const caption = linkRole(body, 'ps4')
    expect(caption.threads[0].paras.map((p) => p.style)).toEqual(['ps4', 'ps2', 'ps1'])
    expect(caption.identity!.parents[0].threads[0].paras[0].style).toBe('ps4')
  })

  it('keeps surviving character styles live when deleting their paragraph style', () => {
    const d = doc(); d.threads[0].paras[0].runs.push({ t: 'Emphasis', style: 'cs1', size: 9 })
    const before = resolveParas(d.threads[0].paras, d.identity)
    const removed = removeStyle(d, 'paragraphs', 'ps3')
    expect(resolveParas(removed.threads[0].paras, removed.identity)).toEqual(before)
    expect(removed.threads[0].paras[0].runs[1].style).toBe('cs1')
    removed.identity = { ...removed.identity!, characters: [{ ...removed.identity!.characters[0], char: { it: false } }] }
    expect(resolveParas(removed.threads[0].paras, removed.identity)[0].runs[1].it).toBe(false)
  })

  it('keeps same-issue clipboard links after identity edits and flattens deleted definitions', () => {
    const { store, ctx } = studio()
    command('copy').run(ctx)
    store.edit((d) => ({ ...d, identity: { ...d.identity!, paragraphs: d.identity!.paragraphs.map((p) => ({ ...p, char: { ...p.char, size: 24 } })) } }))
    command('paste').run(ctx)
    let d = store.get().doc
    expect(d.threads.at(-1)!.paras[0].style).toBe('ps3')
    expect(resolveParas(d.threads.at(-1)!.paras, d.identity)[0].runs[0].size).toBe(24)
    store.edit((d) => removeStyle(d, 'paragraphs', 'ps3'))
    command('paste').run(ctx); d = store.get().doc
    expect(d.threads.at(-1)!.paras[0].style).toBeUndefined()
    expect(resolveParas(d.threads.at(-1)!.paras, d.identity)[0].runs[0].size).toBe(8)
  })

  it('refuses canonical duplicate names and merges trimmed names consistently with the server', () => {
    const d = doc(); d.identity!.characters.push({ id: 'cs2', name: 'Emphasis ', char: {} })
    expect(docProblem(d)).toMatch(/distinct names/)
    const target = doc(), source = starterIdentity(); source.characters[0].name = ' Emphasis '
    expect(importIdentity(target, source).identity!.characters).toHaveLength(1)
    expect(identityName(' \u0000Tide 📷\ud800 ')).toBe('Tide 📷')
  })

  it('bounds repeated parent composition, including empty lines with no character cost', () => {
    const d = doc(); d.items = []; d.threads = []
    d.identity!.parents = [{ id: 'pl1', name: 'Footer', size: d.size, items: [], threads: [{ id: 's1', frames: [], paras: [], comp: { lines: Array.from({ length: 8000 }, () => [0, 0, 0, 0, 0, 0, 0, 0]) } }] }]
    d.pages = Array.from({ length: 4 }, (_, k) => ({ id: `p${k}`, parent: 'pl1' }))
    expect(docProblem(d)).toMatch(/too many composed lines/)
  })

  it('keeps an accepted document safe when loaded fonts grow its parent composition beyond the byte limit', () => {
    const d = doc(); d.items = []; d.threads = []; d.pages = [{ id: 'p1', parent: 'pl1' }]
    d.identity!.parents = [{ id: 'pl1', name: 'Footer', size: d.size, items: [newItem('text', 'p1', 't1', { x: 0, y: 0, w: 2.1, h: 20000 })], threads: [{ id: 's1', frames: ['t1'], paras: [{ runs: [{ t: 'a '.repeat(25000), size: 1 }] }] }] }]
    const { store } = studio(d), before = store.get().doc, save = vi.fn()
    expect(docProblem(before)).toBeNull(); store.onDocChange = save
    store.measure = { ...measure, width: (c, text) => text.length * c.size }
    store.recompose()
    expect(store.get().doc).toBe(before); expect(save).not.toHaveBeenCalled()
    expect(store.get().notice).toMatch(/identity is too big/)
  })

  it('page numbers follow page order and overrides, and furniture never prints behind the paywall', () => {
    let d = doc(); d.identity!.furniture = { ...d.identity!.furniture, numbers: true, header: '<Tide>', start: 4, skip_first: false }
    d.pages[0].header = 'Cover'; d = movePage(d, 0, 1)
    const draw = { assets: {}, faces: book.face, used: new Map(), threads: frameThreads(d) }
    expect(pageItemsHtml(d, 0, draw)).toContain('&lt;Tide&gt;')
    expect(pageItemsHtml(d, 1, draw)).toContain('>5</div>')
    const locked = pagesHtml(d, {}, book.face, { lockedFrom: 2 }).html.split('data-lyt-lock="2"')[1]
    expect(locked).not.toContain('Cover'); expect(locked).not.toContain('lyt-furniture')
    d.pages[0].hide_furniture = true; expect(pageItemsHtml(d, 0, draw)).not.toContain('lyt-furniture')
  })

  it('bounds repeated parent content and refuses an edit before history or autosave changes', () => {
    let d = doc(); d.items = d.items.slice(0, 1); d.threads = d.threads.slice(0, 1); d = captureParent(d, 0, 'pl1', 'Parent')
    const { store } = studio(d), before = store.get().doc, changed = vi.fn(); store.onDocChange = changed
    const tooMany = { ...d, pages: Array.from({ length: 201 }, (_, k) => ({ id: `p${k + 1}`, parent: 'pl1' })) }
    expect(docProblem(tooMany)).toMatch(/parents hold too many/)
    store.edit(() => tooMany)
    expect(store.get().doc).toBe(before); expect(store.canUndo()).toBe(false); expect(changed).not.toHaveBeenCalled()
    expect(addPages(d, 0).identity).toBe(d.identity)
  })
})

describe('identity library and controls', () => {
  it('retains palette linkage when changing stroke weight and detaches only an explicit colour edit', () => {
    const d = doc(); d.items.push({ ...newItem('line', 'p1', 'l1', { x: 0, y: 0, w: 100, h: 0 }), stroke_swatch: 'sw3' })
    const { store, ctx } = studio(d); store.set({ selection: ['l1'] })
    render(<StudioContext.Provider value={ctx}><ObjectPanel /></StudioContext.Provider>)
    fireEvent.change(screen.getByLabelText('Stroke weight'), { target: { value: '2pt' } }); fireEvent.blur(screen.getByLabelText('Stroke weight'))
    expect(store.get().doc.items.at(-1)!.stroke_swatch).toBe('sw3')
    act(() => store.edit((d) => ({ ...d, identity: { ...d.identity!, swatches: d.identity!.swatches.map((s) => s.id === 'sw3' ? { ...s, color: '#ff0000' } : s) } })))
    expect(resolveItem(store.get().doc.items.at(-1)!, store.get().doc.identity)).toMatchObject({ stroke: { w: 2, c: '#ff0000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Stroke colour: #ff0000' }))
    fireEvent.change(screen.getByLabelText('Colour, as hex'), { target: { value: '#112233' } }); fireEvent.blur(screen.getByLabelText('Colour, as hex'))
    expect(store.get().doc.items.at(-1)!.stroke_swatch).toBeUndefined()
  })

  it('edits a caption style across an issue from the panel', async () => {
    const { store, ctx } = studio()
    render(<StudioContext.Provider value={ctx}><IdentityPanel /></StudioContext.Provider>)
    fireEvent.click(screen.getByRole('button', { name: 'Caption' }))
    fireEvent.change(screen.getAllByLabelText('Style size')[0], { target: { value: '16' } })
    fireEvent.blur(screen.getAllByLabelText('Style size')[0])
    await waitFor(() => expect(resolveParas(store.get().doc.threads[1].paras, store.get().doc.identity)[0].runs[0].size).toBe(16))
  })

  it('preserves a save failure settled while hidden and the local design during reloads', async () => {
    const { store, ctx } = studio(), library = identityLibrary(store, 'site')
    await library.load()
    let reject!: (error: Error) => void
    vi.mocked(identityApi.save).mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail }))
    const saving = library.save(store.get().doc.identity!)
    reject(new Error('Connection lost')); await saving
    const before = store.get().doc
    render(<StudioContext.Provider value={ctx}><IdentityPanel /></StudioContext.Provider>)
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Connection lost'))
    expect(store.get().doc).toBe(before)
    expect(library.get().pending).toBe(false)
    await act(async () => { await library.load(true) })
    expect(library.get().error).toBeNull()
  })

  it('serializes pending saves and ignores an older GET response', async () => {
    const { store } = studio(), library = identityLibrary(store, 'site')
    await library.load()
    let finish!: (saved: { rev: number; identity: null }) => void
    vi.mocked(identityApi.open).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const read = library.load(), identity = starterIdentity()
    let complete!: (saved: { rev: number; identity: typeof identity }) => void
    vi.mocked(identityApi.save).mockImplementationOnce(() => new Promise((resolve) => { complete = resolve }))
    const saving = library.save(identity); await library.save(identity)
    expect(identityApi.save).toHaveBeenCalledTimes(1)
    complete({ rev: 1, identity }); await saving
    finish({ rev: 0, identity: null }); await read
    expect(library.get().rev).toBe(1); expect(library.get().identity).toEqual(identity)
  })
})
