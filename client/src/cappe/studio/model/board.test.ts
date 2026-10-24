import { describe, expect, it } from 'vitest'
import type { Measure } from '../compose/compose'
import { DEFAULT_VIEW, Store, type State } from '../store/store'
import { acrossSpread, cropsFor, fitPlacement, groupOf, keepLinks, linkFrames, linkGroups, linkProblem, shown, unlinkFrames,
  type Rect } from './crops'
import { newItem } from './doc'
import { GUTTER_SAFE, gutterIssues } from './gutter'
import { addPages, deletePage, movePage, patchItems } from './ops'
import { beats } from './rhythm'
import { cleanName, keepSections, moveBlock, removeSection, renameSection, runs, startSection } from './sections'
import type { Asset, Doc, ImageItem, Item, Para } from './types'

const doc = (over: Partial<Doc> = {}): Doc => ({
  v: 1, size: { w: 600, h: 800 }, facing: true, margins: { t: 50, b: 50, i: 50, o: 50 }, cols: { n: 1, g: 12 },
  baseline: { start: 50, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'pt', paper: '#ffffff',
  pages: Array.from({ length: 9 }, (_, k) => ({ id: `p${k + 1}` })), guides: [], items: [], threads: [], paywall_page: null,
  ...over,
})
const ids = (d: Doc) => d.pages.map((p) => p.id)
const story = (d: Doc) => runs(d).map((r) => `${r.section?.name ?? '-'}:${ids(d).slice(r.start, r.end).join(',')}`)

describe('stories in the issue', () => {
  it('are runs of pages, from each story’s first page to the next', () => {
    expect(story(doc({ pages: [{ id: 'p1' }, { id: 'p2' }] }))).toEqual(['-:p1,p2'])
    let d = startSection(doc(), 3, 'Essay')
    d = startSection(d, 1)
    d = startSection(d, 6, ' Interview\u0007 ')
    expect(story(d)).toEqual(['-:p1', 'Story 2:p2,p3', 'Essay:p4,p5,p6', 'Interview:p7,p8,p9'])
    expect(startSection(d, 3)).toBe(d) // one story starts there already
  })

  it('keep a name as the server does: no controls, trimmed, 80 characters counted whole', () => {
    expect(cleanName('  Fall\u0000 issue ')).toBe('Fall issue')
    expect(Array.from(cleanName('😀'.repeat(100)))).toHaveLength(80)
    const d = startSection(doc(), 0, 'Front')
    const id = d.sections![0].id
    expect(renameSection(d, id, 'Lookbook').sections![0].name).toBe('Lookbook')
    expect(renameSection(d, id, 'Front')).toBe(d)
    expect(removeSection(d, id).sections).toBeUndefined() // none left: the key goes, as the server stores it
  })

  const three = () => startSection(startSection(startSection(doc(), 0, 'A'), 3, 'B'), 6, 'C') // A p1-3, B p4-6, C p7-9

  it('move a page into the story it lands in', () => {
    const d = moveBlock(three(), ['p2'], 5) // between p5 and p6, inside B
    expect(story(d)).toEqual(['A:p1,p3', 'B:p4,p5,p2,p6', 'C:p7,p8,p9'])
    expect(d.paywall_page).toBeNull()
  })

  it('dropped in front of a story’s first page, pages open that story, or close the one before', () => {
    // p8 dropped at the B/C boundary: on C's first page it opens C, after B's last it ends B.
    expect(story(moveBlock(three(), ['p8'], 6, 'after'))).toEqual(['A:p1,p2,p3', 'B:p4,p5,p6', 'C:p8,p7,p9'])
    expect(story(moveBlock(three(), ['p8'], 6, 'before'))).toEqual(['A:p1,p2,p3', 'B:p4,p5,p6,p8', 'C:p7,p9'])
    // Two pages, after every page: with nothing after them they join the story before.
    expect(story(moveBlock(three(), ['p1', 'p2'], 9, 'after'))).toEqual(['A:p3', 'B:p4,p5,p6', 'C:p7,p8,p9,p1,p2'])
  })

  it('move a story’s first page alone without moving the story', () => {
    const d = moveBlock(three(), ['p4'], 9)
    expect(story(d)).toEqual(['A:p1,p2,p3', 'B:p5,p6', 'C:p7,p8,p9,p4'])
  })

  it('move a whole story between stories, never into the middle of one', () => {
    expect(story(moveBlock(three(), ['p7', 'p8', 'p9'], 0))).toEqual(['C:p7,p8,p9', 'A:p1,p2,p3', 'B:p4,p5,p6'])
    // Dropped inside A, it lands after A.
    expect(story(moveBlock(three(), ['p7', 'p8', 'p9'], 1))).toEqual(['A:p1,p2,p3', 'C:p7,p8,p9', 'B:p4,p5,p6'])
    // Pages before the first story stay first.
    const front = startSection(startSection(doc(), 2, 'A'), 5, 'B') // - p1-2, A p3-5, B p6-9
    expect(story(moveBlock(front, ['p6', 'p7', 'p8', 'p9'], 0))).toEqual(['-:p1,p2', 'B:p6,p7,p8,p9', 'A:p3,p4,p5'])
  })

  it('leave the document alone when nothing moves', () => {
    const d = three()
    expect(moveBlock(d, ['p2'], 1)).toBe(d)
    expect(moveBlock(d, [], 3)).toBe(d)
  })

  it('follow their pages through any edit: a deleted first page hands the story on', () => {
    const d = three()
    expect(story(keepSections(d, deletePage(d, 3)))).toEqual(['A:p1,p2,p3', 'B:p5,p6', 'C:p7,p8,p9'])
    let gone = deletePage(deletePage(deletePage(d, 5), 4), 3)
    gone = keepSections(d, gone)
    expect(story(gone)).toEqual(['A:p1,p2,p3', 'C:p7,p8,p9'])
    const added = addPages(d, 4)
    expect(keepSections(d, added)).toBe(added) // a new page joins the story it lands in, by itself
    expect(story(keepSections(d, movePage(d, 3, 1)))).toEqual(['A:p1', 'B:p4,p2,p3,p5,p6', 'C:p7,p8,p9'])
  })
})

// ── linked crops ────────────────────────────────────────────────────────────

const PIC: Asset = { id: 'a1', url: 'https://cdn.example.test/a.jpg', width: 3000, height: 2000 }
const PORTRAIT: Asset = { id: 'a2', url: 'https://cdn.example.test/b.jpg', width: 2000, height: 3000 }
const assets = { a1: PIC, a2: PORTRAIT }
const frame = (id: string, page: string, box: Rect, over: Partial<ImageItem> = {}): ImageItem =>
  ({ ...(newItem('image', page, id, box) as ImageItem), ...over })

/** Where a frame's picture lands, as a browser draws it (independently of
 *  crops.ts): object-fit cover, object-position fx% fy%, then scale() by the
 *  zoom as the renderer prints it (2 places) about the same point. */
function browser(r: Rect, c: { fx: number; fy: number; zoom: number }, a: Asset) {
  const iw = a.width!, ih = a.height!
  const cover = Math.max(r.w / iw, r.h / ih)
  const z = Number((c.zoom / 100).toFixed(2))
  const place = (start: number, size: number, img: number, f: number) => {
    const left = (size - img * cover) * f
    const origin = size * f
    return start + origin + (left - origin) * z
  }
  return { x: place(r.x, r.w, iw, c.fx / 100), y: place(r.y, r.h, ih, c.fy / 100), s: cover * z }
}
/** Which picture pixel a frame shows at a spread point. */
const pixel = (r: Rect, c: ImageItem, a: Asset, x: number, y: number) => {
  const p = browser(r, c, a)
  return { u: (x - p.x) / p.s, v: (y - p.y) / p.s }
}
const rectOf = (d: Doc, id: string) => {
  const g = linkGroups(d).flatMap((x) => x.members.map((m, k) => [m.id, x.rects[k]] as const))
  return new Map(g).get(id)!
}
const item = (d: Doc, id: string) => d.items.find((i) => i.id === id) as ImageItem

describe('linked crops', () => {
  it('know where a frame shows its picture, as the browser draws it', () => {
    const r = { x: 30, y: 40, w: 500, h: 300 }
    for (const c of [{ fx: 50, fy: 50, zoom: 100 }, { fx: 12.5, fy: 80, zoom: 137 }, { fx: 100, fy: 0, zoom: 400 }]) {
      const want = browser(r, c, PIC), got = shown(r, c, { iw: 3000, ih: 2000 })
      expect(got.x).toBeCloseTo(want.x, 9)
      expect(got.y).toBeCloseTo(want.y, 9)
      expect(got.s).toBeCloseTo(want.s, 12)
    }
  })

  it('run one picture across a spread, lined up at the spine', () => {
    let d = doc({ items: [frame('i1', 'p2', { x: 100, y: 100, w: 300, h: 200 }, { asset_id: 'a1' })] })
    const made = acrossSpread(d, 'i1', assets)!
    d = made.doc
    const [left, right] = made.ids.map((id) => item(d, id))
    expect(left.page).toBe('p2')
    expect(right.page).toBe('p3')
    expect([left.x, left.y, left.w, left.h]).toEqual([-9, -9, 609, 818])
    expect([right.x, right.y, right.w, right.h]).toEqual([0, -9, 609, 818])
    expect(right.asset_id).toBe('a1')
    expect(left.link).toBe(right.link)
    for (const y of [-9, 100, 400, 809]) {
      const a = pixel(rectOf(d, left.id), left, PIC, 600, y), b = pixel(rectOf(d, right.id), right, PIC, 600, y)
      expect(Math.abs(a.u - b.u) * browser(rectOf(d, left.id), left, PIC).s).toBeLessThan(0.15) // pt, at the spine
      expect(Math.abs(a.v - b.v) * browser(rectOf(d, left.id), left, PIC).s).toBeLessThan(0.15)
    }
  })

  it('show one picture through windows that leave the spine clear', () => {
    const made = acrossSpread(doc({ items: [frame('i1', 'p3', { x: 0, y: 0, w: 10, h: 10 }, { asset_id: 'a2' })] }), 'i1', assets, 30)!
    const d = made.doc
    const [a, b] = made.ids.map((id) => item(d, id)) // left, right: the frame clicked was the right one
    expect([a.x + a.w, b.x]).toEqual([570, 30])
    // The gap is the picture's, hidden: the pixel at the spine is the same seen from either window.
    const pa = browser(rectOf(d, a.id), a, PORTRAIT), pb = browser(rectOf(d, b.id), b, PORTRAIT)
    expect(Math.abs(pa.x - pb.x)).toBeLessThan(0.2)
    expect(Math.abs(pa.s - pb.s) / pa.s).toBeLessThan(0.001)
  })

  it('fit a fresh picture so frames of different sizes need nearly whole zooms', () => {
    const rects = [{ x: 0, y: 0, w: 200, h: 700 }, { x: 640, y: 120, w: 420, h: 260 }]
    const p = fitPlacement(rects, { iw: 3000, ih: 2000 }, null)!
    const crops = cropsFor(rects, p, { iw: 3000, ih: 2000 })!
    crops.forEach((c, k) => {
      const got = browser(rects[k], c, PIC)
      expect(Math.abs(got.s - p.s) / p.s).toBeLessThan(0.002)
    })
  })

  it('refuse frames that can’t share a picture', () => {
    const d = doc({ items: [frame('i1', 'p2', { x: 0, y: 0, w: 10, h: 10 }), frame('i2', 'p4', { x: 0, y: 0, w: 10, h: 10 }),
      frame('i3', 'p3', { x: 0, y: 0, w: 10, h: 10 }, { rot: 5 }), { ...newItem('rect', 'p2', 'r1', { x: 0, y: 0, w: 1, h: 1 }) },
      frame('i4', 'p3', { x: 0, y: 0, w: 10, h: 10 }, { asset_id: 'a1' }), frame('i5', 'p2', { x: 0, y: 0, w: 10, h: 10 }, { asset_id: 'a2' })] })
    expect(linkProblem(d, ['i1'])).toMatch(/two picture frames/)
    expect(linkProblem(d, ['i1', 'r1'])).toMatch(/two picture frames/)
    expect(linkProblem(d, ['i1', 'i3'])).toMatch(/Turned/)
    expect(linkProblem(d, ['i1', 'i2'])).toMatch(/one spread/)
    expect(linkProblem(d, ['i4', 'i5'])).toMatch(/different pictures/)
    expect(linkProblem(d, ['i1', 'i4'])).toBeNull()
    expect(acrossSpread(d, 'i1', assets)?.ids).toHaveLength(2)
    expect(acrossSpread(doc({ items: [frame('i9', 'p1', { x: 0, y: 0, w: 1, h: 1 })] }), 'i9', assets)).toBeNull() // page 1 is alone
    expect(acrossSpread(doc({ facing: false, items: [frame('i9', 'p2', { x: 0, y: 0, w: 1, h: 1 })] }), 'i9', assets)).toBeNull()
  })

  const pair = () => linkFrames(doc({ items: [
    frame('i1', 'p2', { x: 100, y: 200, w: 400, h: 300 }), frame('i2', 'p3', { x: 60, y: 200, w: 300, h: 300 }),
  ] }), ['i1', 'i2'], assets)

  it('fill every linked frame when a picture goes in one', () => {
    const before = pair()
    expect(groupOf(before, 'i1')?.members.map((m) => m.id)).toEqual(['i1', 'i2'])
    const after = keepLinks(before, patchItems(before, ['i2'], { asset_id: 'a1' }), assets)
    expect(item(after, 'i1').asset_id).toBe('a1')
    const a = browser(rectOf(after, 'i1'), item(after, 'i1'), PIC), b = browser(rectOf(after, 'i2'), item(after, 'i2'), PIC)
    expect(Math.abs(a.x - b.x)).toBeLessThan(0.5)
    expect(Math.abs(a.y - b.y)).toBeLessThan(0.5)
  })

  const filled = () => { const d = pair(); return keepLinks(d, patchItems(d, ['i1'], { asset_id: 'a1' }), assets) }

  it('keep the picture still when one window moves, and move it when they all do', () => {
    const d = filled()
    const still = browser(rectOf(d, 'i2'), item(d, 'i2'), PIC)
    const one = keepLinks(d, patchItems(d, ['i1'], { x: 140, w: 360 }), assets)
    expect(item(one, 'i2')).toEqual(item(d, 'i2'))
    const moved = browser(rectOf(one, 'i1'), item(one, 'i1'), PIC)
    expect(Math.abs(moved.x - still.x)).toBeLessThan(0.5)
    expect(Math.abs(moved.y - still.y)).toBeLessThan(0.5)
    const both = keepLinks(d, patchItems(d, ['i1', 'i2'], { y: 230 }), assets)
    expect([item(both, 'i1').fy, item(both, 'i2').fy]).toEqual([item(d, 'i1').fy, item(d, 'i2').fy])
  })

  it('move the picture for every window when one window’s crop changes', () => {
    const d = filled()
    const after = keepLinks(d, patchItems(d, ['i2'], { zoom: 180 }), assets)
    const a = browser(rectOf(after, 'i1'), item(after, 'i1'), PIC), b = browser(rectOf(after, 'i2'), item(after, 'i2'), PIC)
    expect(item(after, 'i1').zoom).not.toBe(item(d, 'i1').zoom)
    expect(Math.abs(a.s - b.s) / a.s).toBeLessThan(0.005)
  })

  it('let a frame go when it is turned, set to fit, copied in, or unlinked', () => {
    const d = filled()
    expect(item(keepLinks(d, patchItems(d, ['i1'], { rot: 10 }), assets), 'i1').link).toBeUndefined()
    expect(item(keepLinks(d, patchItems(d, ['i2'], { fit: 'fit' }), assets), 'i2').link).toBeUndefined()
    const copy = { ...item(d, 'i1'), id: 'i9', x: 20 } as Item
    const pasted = keepLinks(d, { ...d, items: [...d.items, copy] }, assets)
    expect(item(pasted, 'i9').link).toBeUndefined()
    const apart = unlinkFrames(d, ['i1'])
    expect([item(apart, 'i1').link, item(apart, 'i2').link]).toEqual([undefined, undefined]) // one left alone is no group
  })

  it('run in the store on every edit', () => {
    const mono: Measure = { width: (c, t) => [...t].length * 0.5 * c.size, metrics: (c) => ({ asc: 0.8 * c.size, desc: 0.2 * c.size }) }
    const store = new Store({
      doc: pair(), selection: [], editing: null, page: 1, tool: 'select', view: { ...DEFAULT_VIEW }, panels: [], drawer: null,
      overset: new Set(), assets, dialog: null, guide: null, threading: null, snaps: null, marquee: null,
      save: { rev: 1, state: 'saved', message: null, draft: false, live: false },
    } as State, mono)
    store.edit((x) => patchItems(x, ['i1'], { asset_id: 'a1' }))
    expect(item(store.get().doc, 'i2').asset_id).toBe('a1')
    store.edit((x) => startSection(x, 1, 'Essay'))
    store.edit((x) => deletePage(x, 1))
    expect(store.get().doc.sections?.[0]).toMatchObject({ name: 'Essay', page: 'p3' })
    store.undo()
    expect(store.get().doc.sections?.[0]).toMatchObject({ page: 'p2' })
  })
})

// ── the rhythm ──────────────────────────────────────────────────────────────

const words = (n: number): Para[] => [{ runs: [{ t: 'word '.repeat(n) }] }]

describe('each page’s beat', () => {
  it('reads a page by what covers it', () => {
    const d = doc({
      items: [
        frame('i1', 'p2', { x: -9, y: -9, w: 618, h: 818 }), // full bleed
        frame('i2', 'p3', { x: 120, y: 80, w: 360, h: 600 }), // tall: a portrait
        frame('i3', 'p4', { x: 50, y: 100, w: 500, h: 400 }), // a picture
        frame('i4', 'p5', { x: 50, y: 50, w: 240, h: 320 }), frame('i5', 'p5', { x: 310, y: 400, w: 240, h: 320 }),
        frame('i6', 'p6', { x: 250, y: 500, w: 100, h: 100 }), // a small detail and white around it
        { ...newItem('text', 'p7', 't1', { x: 50, y: 50, w: 500, h: 700 }) },
        { ...newItem('rect', 'p8', 'r1', { x: -9, y: -9, w: 618, h: 818 }), fill: '#2b2b2b' } as Item,
      ],
      threads: [{ id: 's1', frames: ['t1'], paras: words(400) }],
    })
    expect(beats(d).map((b) => b.beat)).toEqual(['white', 'bleed', 'portrait', 'picture', 'pictures', 'detail', 'words', 'colour', 'white'])
    const b = beats(d)
    expect(b[1].weight).toBeGreaterThan(b[3].weight)
    expect(b[8].ink).toBe(0)
  })

  it('counts a picture across the spread on both pages, and nothing hidden', () => {
    const d = doc({ items: [frame('i1', 'p2', { x: -9, y: -9, w: 1218, h: 818 }), frame('i2', 'p4', { x: 0, y: 0, w: 600, h: 800 }, { hidden: true })] })
    expect(beats(d).slice(1, 4).map((x) => x.beat)).toEqual(['bleed', 'bleed', 'white'])
  })
})

describe('the gutter', () => {
  const page = (x: number, w: number, pg = 'p2') => doc({
    items: [{ ...newItem('text', pg, 't1', { x, y: 50, w, h: 300 }) }],
    threads: [{ id: 's1', frames: ['t1'], paras: words(5) }],
  })

  it('says when words reach into the strip by the spine, or cross it', () => {
    expect(gutterIssues(page(50, 500))).toEqual([]) // inside the margins
    expect(gutterIssues(page(50, 600 - GUTTER_SAFE + 1))[0]).toMatchObject({ page: 1, item: 't1' })
    expect(gutterIssues(page(50, 700))[0].message).toMatch(/cross the spine/)
    expect(gutterIssues(page(10, 300, 'p3'))[0].message).toMatch(/page 3 run into the gutter/)
  })

  it('has no spine on a lone page, or without facing pages', () => {
    expect(gutterIssues(page(10, 300, 'p1'))).toEqual([])
    expect(gutterIssues({ ...page(50, 700), facing: false })).toEqual([])
    const empty = page(50, 700)
    expect(gutterIssues({ ...empty, threads: [{ id: 's1', frames: ['t1'], paras: [{ runs: [{ t: ' ' }] }] }] })).toEqual([])
  })
})
