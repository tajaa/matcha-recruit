import { describe, expect, it } from 'vitest'
import { composeDoc, type Measure } from '../../compose/compose'
import { addItem, patchItems } from '../../model/ops'
import type { Doc, GraphicItem, Item, LineItem, RectItem, TextItem } from '../../model/types'
import { applyOps, fitOps, type MerlinOp, type Scope } from './merlinOps'

const base = (): Doc => ({
  v: 1, size: { w: 612, h: 792 }, facing: true, margins: { t: 36, b: 36, i: 54, o: 36 }, cols: { n: 3, g: 12 },
  baseline: { start: 36, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'in', paper: '#fbf8f1',
  pages: [{ id: 'p1' }, { id: 'p2' }], guides: [], items: [], threads: [], paywall_page: null,
})

/** Page 1: a headline frame (headline + body), a box, a rule, a one-colour
 *  graphic, a sticker, a locked box; page 2: a box. */
function doc(): Doc {
  let d = base()
  for (const [kind, page, box] of [
    ['text', 'p1', { x: 36, y: 72, w: 540, h: 200 }], ['rect', 'p1', { x: 0, y: 0, w: 72, h: 72 }],
    ['line', 'p1', { x: 36, y: 600, w: 540, h: 0 }], ['graphic', 'p1', { x: 10, y: 10, w: 20, h: 20 }],
    ['graphic', 'p1', { x: 40, y: 10, w: 20, h: 20 }], ['rect', 'p1', { x: 100, y: 100, w: 50, h: 50 }],
    ['rect', 'p2', { x: 0, y: 0, w: 10, h: 10 }],
  ] as const) d = addItem(d, kind, page, box).doc
  const [t1, r1, l1, g1, g2, r2, r3] = d.items.map((i) => i.id)
  expect([t1, r1, l1, g1, g2, r2, r3]).toEqual(['t1', 'r1', 'l1', 'g1', 'g2', 'r2', 'r3'])
  d = patchItems(d, ['g1'], { src: 'sha1', color: '#111111' })
  d = patchItems(d, ['g2'], { src: 'sha2', color: null })
  d = patchItems(d, ['r1'], { fill_swatch: 'sw1' })
  d = patchItems(d, ['r2'], { locked: true })
  return {
    ...d,
    threads: [{ id: 's1', frames: ['t1'], paras: [
      { role: 'h1', runs: [{ t: 'the tide ', font: 'Source Serif 4', size: 48 }, { t: 'comes in', it: true }] },
      { runs: [{ t: 'Body copy starts here.' }] },
    ] }],
  }
}

const scope: Scope = { page: 'p1', selection: [], hasFamily: (f) => ['Bebas Neue', 'Source Serif 4'].includes(f) }
const item = <T extends Item>(d: Doc, id: string) => d.items.find((i) => i.id === id) as T

describe('Merlin’s edits', () => {
  it('sets only the fields a frame of that kind has, and a colour set by hand leaves its swatch', () => {
    const out = applyOps(doc(), [
      { op: 'set', id: 'r1', x: 20, y: 30, w: 200, fill: '#ff0000', stroke: { c: '#000000', w: 2 }, zoom: 300, cols: 3 },
      { op: 'set', id: 'l1', stroke: null, rot: 15 },
      { op: 'set', id: 'g1', color: '#c0392b' },
      { op: 'set', id: 't1', cols: 2, gutter: 18, valign: 'center', hidden: false },
    ], scope)
    const r1 = item<RectItem>(out.doc, 'r1')
    expect([r1.x, r1.y, r1.w, r1.h, r1.fill, r1.stroke]).toEqual([20, 30, 200, 72, '#ff0000', { c: '#000000', w: 2 }])
    expect(r1.fill_swatch).toBeUndefined()
    expect('zoom' in r1 || 'cols' in r1).toBe(false)
    expect(item<LineItem>(out.doc, 'l1')).toMatchObject({ rot: 15, stroke: { c: '#1a1a1a', w: 1 } })
    expect(item<GraphicItem>(out.doc, 'g1').color).toBe('#c0392b')
    expect(item<TextItem>(out.doc, 't1')).toMatchObject({ cols: 2, gutter: 18, valign: 'center' })
    expect(out.did).toHaveLength(4)
    expect(out.did[0]).toMatch(/^Did \{"op":"set","id":"r1"/)
    expect(out.skipped).toEqual([])
  })

  it('skips a frame off the page, a locked one, an unknown one and fields its kind lacks, saying why', () => {
    const before = doc()
    const out = applyOps(before, [
      { op: 'set', id: 'r3', x: 5 },
      { op: 'set', id: 'r2', x: 5 },
      { op: 'arrange', id: 'zz9', to: 'front' },
      { op: 'set', id: 'g2', color: '#c0392b' },
      { op: 'set', id: 'l1', fill: '#ffffff' },
    ], scope)
    expect(out.doc).toBe(before)
    expect(out.did).toEqual([])
    expect(out.skipped).toEqual([
      'Skipped {"op":"set","id":"r3","x":5}: r3 isn\'t on the page Merlin is working on',
      'Skipped {"op":"set","id":"r2","x":5}: r2 is locked',
      'Skipped {"op":"arrange","id":"zz9","to":"front"}: zz9 isn\'t on the page Merlin is working on',
      'Skipped {"op":"set","id":"g2","color":"#c0392b"}: none of those fields apply to a graphic',
      'Skipped {"op":"set","id":"l1","fill":"#ffffff"}: none of those fields apply to a line',
    ])
  })

  it('works on what was selected on another page too', () => {
    const out = applyOps(doc(), [{ op: 'set', id: 'r3', fill: '#00ff00' }], { ...scope, selection: ['r3'] })
    expect(item<RectItem>(out.doc, 'r3').fill).toBe('#00ff00')
  })

  it('restyles the paragraphs named (all of them when none are), leaving out a font the Studio hasn’t', () => {
    const one = applyOps(doc(), [{ op: 'type', id: 't1', paras: [0], font: 'Bebas Neue', size: 72, track: 40, align: 'c', lead: 70 }], scope)
    const [head, body] = one.doc.threads[0].paras
    expect(head).toMatchObject({ role: 'h1', align: 'c', lead: 70 })
    // Bebas Neue has no italic, so the italic words join the rest.
    expect(head.runs).toEqual([{ t: 'the tide comes in', font: 'Bebas Neue', size: 72, track: 40 }])
    expect(body).toEqual(doc().threads[0].paras[1])
    const all = applyOps(doc(), [{ op: 'type', id: 't1', font: 'Comic Sans', color: '#222222' }], scope)
    expect(all.doc.threads[0].paras.every((p) => p.runs.every((r) => r.color === '#222222' && r.font !== 'Comic Sans'))).toBe(true)
    const none = applyOps(doc(), [{ op: 'type', id: 't1', font: 'Comic Sans' }, { op: 'type', id: 'r1', size: 9 }], scope)
    expect(none.skipped.map((s) => s.split(': ').pop())).toEqual(['no type the Studio can set', 'r1 isn\'t a text frame'])
  })

  it('changes the letter case of headings only: body text keeps its letters', () => {
    const upper = applyOps(doc(), [{ op: 'case', id: 't1', to: 'upper' }], scope)
    expect(upper.doc.threads[0].paras[0].runs.map((r) => r.t)).toEqual(['THE TIDE ', 'COMES IN'])
    expect(upper.doc.threads[0].paras[1].runs[0].t).toBe('Body copy starts here.')
    const title = applyOps(doc(), [{ op: 'case', id: 't1', to: 'title' }], scope)
    expect(title.doc.threads[0].paras[0].runs.map((r) => r.t).join('')).toBe('The Tide Comes In')
    const body = applyOps(doc(), [{ op: 'case', id: 't1', paras: [1], to: 'upper' }], scope)
    expect(body.skipped[0]).toMatch(/t1's text is body text, which keeps its letters$/)
    expect(body.doc.threads).toEqual(doc().threads)
  })

  it('adds shapes and short labels on its page, behind everything when asked, as headings or captions', () => {
    const ops: MerlinOp[] = [
      { op: 'add', kind: 'rect', x: 0, y: 0, w: 612, h: 792, fill: '#f4efe6', to: 'back' },
      { op: 'add', kind: 'text', x: 36, y: 40, w: 200, h: 20, text: 'FASHION', role: 'h3', type: { font: 'Bebas Neue', size: 11, track: 200 } },
      { op: 'add', kind: 'line', x: 36, y: 64, w: 540, h: 0, stroke: { c: '#111111', w: 0.5 } },
      { op: 'add', kind: 'text', x: 0, y: 0, w: 10, h: 10, text: '  ' },
    ]
    const out = applyOps(doc(), ops, scope)
    const added = out.doc.items.slice(-2)
    expect(out.doc.items[0]).toMatchObject({ kind: 'rect', page: 'p1', w: 612, h: 792, fill: '#f4efe6' })
    expect(added[0]).toMatchObject({ kind: 'text', page: 'p1', x: 36, y: 40 })
    expect(added[1]).toMatchObject({ kind: 'line', stroke: { c: '#111111', w: 0.5 } })
    const label = out.doc.threads.find((t) => t.frames.includes(added[0].id))!
    expect(label.paras).toEqual([{ role: 'h3', runs: [{ font: 'Bebas Neue', size: 11, track: 200, t: 'FASHION' }] }])
    expect(out.did).toHaveLength(3)
    expect(out.skipped[0]).toMatch(/a label needs words and a heading or caption role$/)
    const gone = applyOps(doc(), [ops[0]], { ...scope, page: 'p9' })
    expect(gone.skipped[0]).toMatch(/the page is gone$/)
  })

  it('changes the stacking order, and keeps each note short', () => {
    const out = applyOps(doc(), [{ op: 'arrange', id: 'r1', to: 'back' }], scope)
    expect(out.doc.items[0].id).toBe('r1')
    const long = applyOps(doc(), [{ op: 'set', id: 'r3', x: 1, y: 2, w: 3, h: 4, rot: 5, opacity: 6, fill: '#123456', stroke: { c: '#654321', w: 7 }, radius: 8 }
      , ...Array.from({ length: 3 }, () => ({ op: 'arrange', id: 'x'.repeat(12), to: 'front' }) as MerlinOp)], scope)
    for (const n of long.skipped) expect(n.length).toBeLessThanOrEqual(300)
  })
})

describe('keeping text that fits fitting', () => {
  const mono: Measure = { width: (c, t) => [...t].length * 0.5 * c.size, metrics: (c) => ({ asc: 0.8 * c.size, desc: 0.2 * c.size }) }
  const fits = (d: Doc) => !composeDoc(d, mono).overset.size

  it('leaves out type that would overflow its frame, saying about how much room it needed', () => {
    expect(fits(doc())).toBe(true)
    const out = fitOps(doc(), [{ op: 'type', id: 't1', paras: [0], size: 200 }, { op: 'set', id: 'r1', fill: '#ff0000' }], scope, mono)
    expect(fits(out.doc)).toBe(true)
    expect(out.doc.threads[0].paras[0].runs[0].size).toBe(48)
    expect(item<RectItem>(out.doc, 'r1').fill).toBe('#ff0000')
    expect(out.did).toEqual(['Did {"op":"set","id":"r1","fill":"#ff0000"}'])
    expect(out.skipped).toHaveLength(1)
    expect(out.skipped[0]).toMatch(/^Skipped \{"op":"type","id":"t1","paras":\[0\],"size":200\}: the text in t1 would no longer fit its frame \(it would need about \d+ pt of height at 540 pt wide\); make the frame bigger or the type smaller$/)
    const room = Number(/about (\d+) pt/.exec(out.skipped[0])![1])
    expect(room).toBeGreaterThan(200)
  })

  it('keeps bigger type when the frame grows with it, and takes back a frame made too small', () => {
    const grown = fitOps(doc(), [{ op: 'type', id: 't1', paras: [0], size: 200 }, { op: 'set', id: 't1', h: 1400 }], scope, mono)
    expect(grown.skipped).toEqual([])
    expect(grown.doc.threads[0].paras[0].runs[0].size).toBe(200)
    const squeezed = fitOps(doc(), [{ op: 'set', id: 't1', h: 20 }], scope, mono)
    expect(item<TextItem>(squeezed.doc, 't1').h).toBe(200)
    expect(squeezed.skipped[0]).toMatch(/the text in t1 would no longer fit its frame/)
  })

  it('leaves out a label too long for the frame it adds', () => {
    const out = fitOps(doc(), [{ op: 'add', kind: 'text', x: 36, y: 40, w: 40, h: 12, text: 'A LONG SECTION NAME', role: 'h3', type: { size: 11 } }], scope, mono)
    expect(out.doc.items).toHaveLength(doc().items.length)
    expect(out.skipped[0]).toMatch(/would no longer fit its frame/)
  })

  it('doesn’t police text that already overflowed', () => {
    const full = patchItems(doc(), ['t1'], { h: 20 })
    expect(fits(full)).toBe(false)
    const out = fitOps(full, [{ op: 'type', id: 't1', size: 60 }], scope, mono)
    expect(out.skipped).toEqual([])
    expect(out.did).toHaveLength(1)
  })
})
