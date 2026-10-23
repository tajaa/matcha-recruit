import { describe, expect, it } from 'vitest'
import type { Measure } from '../../compose/compose'
import { addItem, patchItems } from '../../model/ops'
import type { Doc } from '../../model/types'
import { DEFAULT_VIEW, Store, type State } from '../../store/store'
import { describeStudio, MAX_DESCRIPTION } from './describe'

const mono: Measure = { width: (c, t) => [...t].length * 0.5 * c.size, metrics: (c) => ({ asc: 0.8 * c.size, desc: 0.2 * c.size }) }

const base = (): Doc => ({
  v: 1, size: { w: 612, h: 792 }, facing: true, margins: { t: 36, b: 36, i: 54, o: 36 }, cols: { n: 3, g: 12 },
  baseline: { start: 36, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'in', paper: '#fbf8f1',
  pages: [{ id: 'p1' }, { id: 'p2' }, { id: 'p3' }], guides: [], items: [], threads: [], paywall_page: 3,
})

/** Page 2: a headline frame, a picture, a rule; page 3 has a box. */
function studio(over: Partial<State> = {}, doc = base()) {
  let d = addItem(doc, 'text', 'p2', { x: 36, y: 72, w: 540, h: 200 }).doc
  d = addItem(d, 'image', 'p2', { x: 36, y: 216, w: 540, h: 360 }).doc
  d = addItem(d, 'line', 'p2', { x: 36, y: 600, w: 540, h: 0 }).doc
  d = addItem(d, 'rect', 'p3', { x: 0, y: 0, w: 72, h: 72 }).doc
  const [text, image, , rect] = d.items.map((i) => i.id)
  d = patchItems(d, [image], { asset_id: 'a1', fit: 'fill' })
  d = patchItems(d, [rect], { fill: '#d4502a' })
  d = {
    ...d,
    threads: [{ id: 's1', frames: [text], paras: [
      { role: 'h1', align: 'c', lead: 52, runs: [{ t: 'The tide comes in twice a day', font: 'Playfair Display', wt: 700, size: 48, track: -10, color: '#111111' }] },
      { runs: [{ t: 'Body copy starts ' }, { t: 'here', it: true }] },
    ] }],
  }
  const store = new Store({
    doc: d, selection: [text], editing: null, page: 1, tool: 'select', view: { ...DEFAULT_VIEW }, panels: [],
    overset: new Set(), dialog: null, guide: null, threading: null, snaps: null, marquee: null,
    assets: { a1: { id: 'a1', url: 'https://cdn.example.test/a.jpg', alt: 'Boats at dusk', width: 1600, height: 1000, recipe: { look: 'film' } } },
    save: { rev: 1, state: 'saved', message: null, draft: false, live: false }, ...over,
  } as State, mono)
  return { store, text, image, rect }
}

describe('what Ask the Studio sends about the page', () => {
  it('describes the document in its own units', () => {
    const out = describeStudio(studio().store.get())
    expect(out).toContain('Document: 3 pages, each 8.5 in wide × 11 in high; facing pages (they pair up as spreads); units: inches.')
    expect(out).toContain('Margins: top 0.5 in, bottom 0.5 in, inside 0.75 in, outside 0.5 in. 3 columns, gutter 0.167 in.')
    expect(out).toContain('Paper colour #fbf8f1')
    expect(out).toContain('Pages from page 3 on are for subscribers only.')
    expect(out).toContain('In view: page 2 of 3 (a spread with page 3).')
  })

  it('lists the page in view back to front, marking what is selected, with its type', () => {
    const { store, text } = studio()
    const out = describeStudio(store.get())
    const lines = out.split('\n')
    const at = (s: string) => lines.findIndex((l) => l.includes(s))
    expect(at(`[selected] Text frame "${text}"`)).toBeGreaterThan(0)
    expect(at(`[selected] Text frame "${text}"`)).toBeLessThan(at('Picture frame'))
    expect(at('Picture frame')).toBeLessThan(at('Line '))
    expect(out).toContain('at 0.5 in from the left, 1 in from the top; 7.5 in × 2.778 in')
    expect(out).toContain('· Headline: "The tide comes in twice a day" in Playfair Display 700, 48 pt, leading 52 pt, tracking -10, #111111, centred')
    expect(out).toContain('· Body text: "Body copy starts here" in Source Serif 4 400, 10.5 pt, leading auto, tracking 0, #1a1a1a, left (some words styled differently)')
    expect(out).toContain('shows "Boats at dusk", landscape, edited with the Film look; fit Fill')
    expect(out).toContain('stroke 1 pt')
    expect(out).not.toContain('#d4502a') // page 3's box isn't in view
  })

  it('names the overset frame and what is selected elsewhere', () => {
    const { store, text, rect } = studio()
    store.set({ overset: new Set(['s1']), selection: [text, rect] })
    const out = describeStudio(store.get())
    expect(out).toContain("some of its text doesn't fit")
    expect(out).toContain('Selected on other pages:')
    expect(out).toContain(`[selected] Rectangle "${rect}"`)
    expect(out).toContain('fill #d4502a')
  })

  it('says when nothing is selected or the page is empty, and lists the looks', () => {
    const { store } = studio({ selection: [], page: 0 })
    const out = describeStudio(store.get())
    expect(out).toContain('Nothing is selected.')
    expect(out).toContain('(nothing on this page yet)')
    expect(out).toMatch(/The Picture Editor's looks: Vivid, Warm, .*Noir/)
  })

  it('stays under its size, keeping the document and the first frames', () => {
    let d = base()
    for (let i = 0; i < 400; i++) d = addItem(d, 'rect', 'p2', { x: i, y: i, w: 10, h: 10 }).doc
    const out = describeStudio(studio({}, d).store.get())
    expect(out.length).toBeLessThanOrEqual(MAX_DESCRIPTION)
    expect(out).toContain('Document: 3 pages')
    expect(out).toContain('…and more on the page, left out here.')
    expect(out).toContain("The Picture Editor's looks")
  })
})
