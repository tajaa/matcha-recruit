import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import fonts from '../../../../../../server/app/cappe/services/magazine/studio/fonts_manifest.json'
import bank from '../../../../../../server/app/cappe/services/magazine/studio/graphics_manifest.json'
import { compose, type Measure } from '../../compose/compose'
import { Shaper } from '../../compose/shaper'
import { FaceBook, type Manifest } from '../../fonts/faces'
import { LIMITS, docProblem } from '../../model/limits'
import { addItem } from '../../model/ops'
import type { Doc, TextItem } from '../../model/types'
import { DEFAULT_VIEW, Store, type State } from '../../store/store'
import { StudioContext, type StudioCtx } from '../context'
import { applyTemplate, blankPage, templateFaces, templateItems } from './applyTemplate'
import { TEMPLATES } from './templates'
import TemplatesTab from './TemplatesTab'

const mono: Measure = { width: (c, t) => [...t].length * 0.5 * c.size, metrics: (c) => ({ asc: 0.8 * c.size, desc: 0.2 * c.size }) }
const book = new FaceBook(fonts as Manifest)
const shas = new Set((bank as { graphics: { sha: string }[] }).graphics.map((g) => g.sha))

/** A new story, as the server makes one: an empty frame threaded over two pages. */
const starter = (): Doc => ({
  v: 1, size: { w: 612, h: 792 }, facing: true, margins: { t: 54, b: 54, i: 54, o: 54 }, cols: { n: 3, g: 12 },
  baseline: { start: 54, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'in', paper: '#ffffff',
  pages: [{ id: 'p1' }, { id: 'p2' }], guides: [], paywall_page: null,
  items: [
    { id: 't1', kind: 'text', page: 'p1', x: 54, y: 54, w: 504, h: 684, rot: 0, opacity: 100, locked: false, hidden: false, name: '', cols: 3, gutter: 12, inset: 0, valign: 'top', fill: null, stroke: null },
    { id: 't2', kind: 'text', page: 'p2', x: 54, y: 54, w: 504, h: 684, rot: 0, opacity: 100, locked: false, hidden: false, name: '', cols: 3, gutter: 12, inset: 0, valign: 'top', fill: null, stroke: null },
  ],
  threads: [{ id: 's1', frames: ['t1', 't2'], paras: [{ runs: [{ t: '' }] }] }],
})

function studio(d = starter(), page = 0) {
  const store = new Store({
    doc: d, selection: [], editing: null, page, tool: 'select', view: { ...DEFAULT_VIEW }, panels: [], drawer: 'templates',
    overset: new Set(), assets: {}, dialog: null, guide: null, threading: null, snaps: null, marquee: null,
    save: { rev: 1, state: 'saved', message: null, draft: false, live: false },
  } as State, mono)
  const ctx = { store, siteId: 's1', postId: 'post1', editor: { close: vi.fn() }, fit: vi.fn(),
    fonts: { book, ensure: vi.fn(async () => {}) } } as unknown as StudioCtx
  return { store, ctx }
}

describe('the templates', () => {
  it('set type only in faces the Studio has, and use only graphics in the bank', () => {
    for (const t of TEMPLATES) {
      for (const [f, w, i] of templateFaces(t)) expect(book.face(f, w, i), `${t.id}: ${f} ${w}${i ? ' italic' : ''}`).toBeDefined()
      for (const ti of t.items) if (ti.kind === 'graphic') expect(shas.has(ti.src), `${t.id}: ${ti.name}`).toBe(true)
    }
    expect(new Set(TEMPLATES.map((t) => t.id)).size).toBe(TEMPLATES.length)
    // Named, so the Layers and Ask the Studio can say which frame is which.
    for (const t of TEMPLATES) for (const ti of t.items) expect(ti.name, `${t.id}: a ${ti.kind}`).toBeTruthy()
  })

  it('give every line room at its face’s own height', () => {
    // Ascent and descent from the faces themselves (a display face can be far
    // taller than its size), so a frame too short for its type fails here, not
    // as “Some text doesn’t fit” on the page.
    const real: Measure = { width: mono.width, metrics: (c) => {
      const f = book.measureFace(c.font, c.wt, c.it)
      return f ? Shaper.metrics(f, c.size) : mono.metrics(c)
    } }
    for (const t of TEMPLATES) {
      const { items, threads } = templateItems(t, starter(), 'p1')
      for (const th of threads) {
        const frames = th.frames.map((id) => items.find((i) => i.id === id) as TextItem)
        expect(compose(th.paras, frames, real).overset, `${t.id}: ${frames[0].name}`).toBe(false)
      }
    }
  })

  it('make documents the Studio can keep', () => {
    for (const t of TEMPLATES) {
      const { items, threads } = templateItems(t, starter(), 'p2')
      const ids = [...items.map((i) => i.id), ...threads.map((th) => th.id)]
      expect(new Set([...ids, 't1', 't2', 's1', 'p1', 'p2']).size).toBe(ids.length + 5)
      for (const i of items) {
        expect(LIMITS.KINDS).toContain(i.kind)
        expect(i.id).toMatch(/^[a-z0-9]{1,12}$/)
        expect(i.name.length).toBeLessThanOrEqual(LIMITS.MAX_NAME)
      }
      for (const th of threads) {
        expect(th.paras.length).toBeGreaterThan(0)
        for (const f of th.frames) expect(items.find((i) => i.id === f)?.kind).toBe('text')
      }
      expect(items.filter((i) => i.kind === 'text').every((i) => threads.some((th) => th.frames.includes(i.id)))).toBe(true)
    }
  })

  it('fit another page size, out to its bleed, with type scaled to it', () => {
    const a4: Doc = { ...starter(), size: { w: 595.28, h: 841.89 }, bleed: 12 }
    const { items, threads } = templateItems(TEMPLATES.find((t) => t.id === 'opener-photo')!, a4, 'p1')
    expect(items[0]).toMatchObject({ kind: 'image', x: -12, y: -12, w: 619.28 })
    expect(items[0].h).toBeCloseTo(456 * (841.89 / 792) + 12, 1)
    const run = threads[0].paras[1].runs[0]
    expect(run).toMatchObject({ t: 'The Long Way Home', font: 'Playfair Display', wt: 900 })
    expect(run.size).toBeCloseTo(54 * (595.28 / 612), 1)
  })

  it('flow a story through linked columns', () => {
    const { items, threads } = templateItems(TEMPLATES.find((t) => t.id === 'body-two')!, starter(), 'p1')
    const cols = items.filter((i) => i.name.startsWith('Column')).map((i) => i.id)
    const story = threads.find((th) => th.frames.includes(cols[0]))!
    expect(story.frames).toEqual(cols)
    expect(story.paras.length).toBe(4)
  })
})

describe('what a story can hold', () => {
  it('names the first limit a document is past, as the server would', () => {
    const d = starter()
    expect(docProblem(d)).toBeNull()
    expect(docProblem({ ...d, pages: Array.from({ length: LIMITS.MAX_PAGES + 1 }, (_, k) => ({ id: `p${k}` })) })).toMatch(/256 pages/)
    const rect = addItem(d, 'rect', 'p1', { x: 0, y: 0, w: 1, h: 1 }).doc.items[2]
    expect(docProblem({ ...d, items: Array.from({ length: LIMITS.MAX_ITEMS + 1 }, (_, k) => ({ ...rect, id: `r${k}`, page: `p${k % 20}` })) })).toMatch(/6000 frames/)
    expect(docProblem({ ...d, items: Array.from({ length: LIMITS.MAX_ITEMS_PER_PAGE + 1 }, (_, k) => ({ ...rect, id: `r${k}` })) })).toMatch(/A page holds/)
    const text = (t: string, paras = 1) => ({ ...d, threads: [{ ...d.threads[0], paras: Array.from({ length: paras }, () => ({ runs: [{ t }] })) }] })
    expect(docProblem(text('', LIMITS.MAX_PARAS + 1))).toMatch(/too many paragraphs/)
    expect(docProblem(text('x'.repeat(LIMITS.MAX_THREAD_CHARS + 1)))).toMatch(/story is too long/)
    const many = { ...d, threads: Array.from({ length: 4 }, (_, k) => ({ id: `s${k}`, frames: [], paras: [{ runs: [{ t: 'x'.repeat(LIMITS.MAX_THREAD_CHARS) }] }] })) }
    expect(docProblem(many)).toMatch(/too much text/)
    expect(docProblem({ ...d, paper: 'x'.repeat(LIMITS.MAX_DOC_BYTES) })).toMatch(/too big to save/)
  })
})

describe('using a template', () => {
  it('lays out a blank page, leaving the story’s thread on the next page alone', async () => {
    const { store, ctx } = studio()
    expect(blankPage(store.get().doc, 0)).toBe(true)
    await applyTemplate(ctx, TEMPLATES.find((t) => t.id === 'cover-classic')!)
    const d = store.get().doc
    expect(d.pages).toHaveLength(2)
    expect(d.items.filter((i) => i.page === 'p1').every((i) => i.name)).toBe(true) // only the template's, all named
    expect(d.threads.find((th) => th.id === 's1')!.frames).toEqual(['t2'])
    expect(d.items.filter((i) => i.page === 'p1').map((i) => i.name)).toContain('Masthead')
    expect(store.get().page).toBe(0)
    expect(ctx.fit).toHaveBeenCalledWith(0, false)
    store.undo()
    expect(store.get().doc.items.map((i) => i.id)).toEqual(['t1', 't2'])
  })

  it('comes in as a new page after one that has something on it', async () => {
    const d = addItem(starter(), 'rect', 'p1', { x: 0, y: 0, w: 10, h: 10 }).doc
    const { store, ctx } = studio(d)
    expect(blankPage(d, 0)).toBe(false)
    await applyTemplate(ctx, TEMPLATES.find((t) => t.id === 'quote')!)
    const after = store.get().doc
    expect(after.pages).toHaveLength(3)
    expect(after.items.filter((i) => i.page === after.pages[1].id).map((i) => i.name)).toEqual(['Colour', 'Quote mark', 'Quote'])
    expect(after.items.filter((i) => i.page === 'p1')).toHaveLength(2)
    expect(store.get().page).toBe(1)
  })

  it('doesn’t count a page with words, or a locked frame, as blank', () => {
    const words = starter()
    words.threads[0].paras = [{ runs: [{ t: 'Hello' }] }]
    expect(blankPage(words, 0)).toBe(false)
    const locked = starter()
    ;(locked.items[0] as TextItem).locked = true
    expect(blankPage(locked, 0)).toBe(false)
  })

  const quote = () => TEMPLATES.find((t) => t.id === 'quote')!
  /** A story `n` pages long with a shape on page `at` (index). */
  const long = (n: number, at: number): Doc => {
    const d = { ...starter(), pages: Array.from({ length: n }, (_, k) => ({ id: `p${k + 1}` })) }
    return addItem(d, 'rect', `p${at + 1}`, { x: 0, y: 0, w: 10, h: 10 }).doc
  }

  it('refuses, changing nothing, when the story has no room for another page', async () => {
    for (const at of [1, LIMITS.MAX_PAGES - 1]) {
      const d = long(LIMITS.MAX_PAGES, at)
      const { store, ctx } = studio(d, at)
      const before = store.get().doc
      await expect(applyTemplate(ctx, quote())).resolves.toBeNull()
      expect(store.get().doc).toBe(before)
      expect(store.get().notice).toMatch(/at most 256 pages/)
      expect(store.canUndo()).toBe(false)
    }
  })

  it('refuses, changing nothing, a template that would take the story past what it can save', async () => {
    const d = addItem(starter(), 'rect', 'p1', { x: 0, y: 0, w: 10, h: 10 }).doc
    d.threads = Array.from({ length: LIMITS.MAX_THREADS }, (_, k) => ({ id: `s${k + 1}`, frames: [`x${k}`], paras: [{ runs: [{ t: 'Words' }] }] }))
    d.items = [...d.items.filter((i) => i.kind !== 'text'), ...d.threads.map((_, k) => ({ ...starter().items[0], id: `x${k}` }))]
    const { store, ctx } = studio(d)
    await expect(applyTemplate(ctx, quote())).resolves.toBeNull()
    expect(store.get().doc.threads).toHaveLength(LIMITS.MAX_THREADS)
    expect(store.get().doc.pages).toHaveLength(2)
    expect(store.get().notice).toBe('The template wasn’t added: A story holds at most 200 separate texts.')
  })

  it('goes where it was clicked while its faces load, and one at a time', async () => {
    const d = addItem(starter(), 'rect', 'p1', { x: 0, y: 0, w: 10, h: 10 }).doc
    const { store, ctx } = studio(d)
    let loaded!: () => void
    const faces = new Promise<void>((res) => { loaded = res })
    ctx.fonts.ensure = vi.fn(() => faces)
    const first = applyTemplate(ctx, quote())
    store.set({ page: 1 })  // the writer turns the page meanwhile
    await expect(applyTemplate(ctx, TEMPLATES.find((t) => t.id === 'contents')!)).resolves.toBeNull()
    loaded()
    await expect(first).resolves.toBe(1)
    const after = store.get().doc
    expect(after.pages.map((p) => p.id)).toEqual(['p1', after.pages[1].id, 'p2'])
    expect(after.items.filter((i) => i.page === after.pages[1].id).map((i) => i.name)).toEqual(['Colour', 'Quote mark', 'Quote'])
    expect(after.items.some((i) => i.name === 'List')).toBe(false)
  })

  it('says so when the page it was for is deleted while its faces load', async () => {
    const { store, ctx } = studio(starter(), 1)
    let loaded!: () => void
    const faces = new Promise<void>((res) => { loaded = res })
    ctx.fonts.ensure = vi.fn(() => faces)
    const using = applyTemplate(ctx, quote())
    store.edit((d) => ({ ...d, pages: [d.pages[0]], items: d.items.filter((i) => i.page !== 'p2'), threads: [{ ...d.threads[0], frames: ['t1'] }] }))
    const before = store.get().doc
    loaded()
    await expect(using).resolves.toBeNull()
    expect(store.get().doc).toBe(before)
    expect(store.get().notice).toBe('The page that template was for has been deleted.')
  })

  it('shows which template is being set up, and takes no other until it is', async () => {
    const { store, ctx } = studio()
    let loaded!: () => void
    const faces = new Promise<void>((res) => { loaded = res })
    ctx.fonts.ensure = vi.fn(() => faces)
    render(<StudioContext.Provider value={ctx}><TemplatesTab /></StudioContext.Provider>)
    const quoteButton = screen.getByRole('button', { name: 'Use the big quote template' })
    fireEvent.click(quoteButton)
    expect(quoteButton).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText('Setting it up…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Use the contents template' })).toBeDisabled()
    loaded()
    await waitFor(() => expect(quoteButton).not.toBeDisabled())
    expect(store.get().doc.items.some((i) => i.name === 'Quote')).toBe(true)
  })

  it('shows each template drawn small, and uses one with a click', async () => {
    const { store, ctx } = studio()
    render(<StudioContext.Provider value={ctx}><TemplatesTab /></StudioContext.Provider>)
    expect(screen.getByText(/Click one to lay out page 1/)).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Use the contents template' })
    expect(button.querySelector('.lyt-item')).not.toBeNull()
    fireEvent.click(button)
    await waitFor(() => expect(store.get().doc.items.some((i) => i.name === 'List')).toBe(true))
  })
})
