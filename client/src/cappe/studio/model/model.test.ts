import { describe, expect, it } from 'vitest'
import { charOf, mergeRuns, newItem, pageSide, paraText, sparseChar, spreads } from './doc'
import {
  addGuide, addItem, addPages, applyChar, applyPara, arrange, charAt, deleteGuide, deleteItems, deletePage, duplicate,
  ensureThread, link, moveGuide, moveItems, movePage, patchItems, unlinkAfter,
} from './ops'
import type { Doc, Para } from './types'
import { parse, show } from './units'

const doc = (over: Partial<Doc> = {}): Doc => ({
  v: 1, size: { w: 612, h: 792 }, facing: true, margins: { t: 54, b: 54, i: 54, o: 54 }, cols: { n: 3, g: 12 },
  baseline: { start: 54, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'in', paper: '#ffffff',
  pages: [{ id: 'p1' }, { id: 'p2' }], guides: [], items: [], threads: [], paywall_page: null, ...over,
})
const box = { x: 10, y: 10, w: 100, h: 50 }
const text = (paras: Para[]) => paras.map(paraText)

describe('lengths', () => {
  it('show points in the document’s units', () => {
    expect(show(72, 'in')).toBe('1')
    expect(show(150, 'pc')).toBe('12p6')
    expect(show(-6, 'pc')).toBe('-0p6')
    expect(show(72, 'mm')).toBe('25.4')
    expect(show(10, 'px')).toBe('13.3')
  })

  it('read a typed length in any unit, or a sum', () => {
    expect(parse('3in', 'pt')).toBe(216)
    expect(parse('1"', 'pt')).toBe(72)
    expect(parse('12p6', 'in')).toBe(150)
    expect(parse('2', 'in')).toBe(144)
    expect(parse('1in + 6pt', 'pt')).toBe(78)
    expect(parse('1in − 6pt', 'pt')).toBe(66)
    expect(parse('25.4mm', 'pt')).toBeCloseTo(72)
    expect(parse('', 'pt')).toBeNull()
    expect(parse('wide', 'pt')).toBeNull()
  })
})

describe('pages and spreads', () => {
  it('pairs facing pages after a lone first page', () => {
    const d = doc({ pages: [{ id: 'p1' }, { id: 'p2' }, { id: 'p3' }, { id: 'p4' }] })
    expect(spreads(d)).toEqual([[0], [1, 2], [3]])
    expect([0, 1, 2].map((i) => pageSide(d, i))).toEqual(['right', 'left', 'right'])
    expect(spreads({ ...d, facing: false })).toEqual([[0], [1], [2], [3]])
  })

  it('adds, moves and deletes pages; a deleted page takes its items and guides', () => {
    let d = addPages(doc(), 0, 2)
    expect(d.pages.map((p) => p.id)).toEqual(['p1', 'p3', 'p4', 'p2'])
    d = movePage(d, 3, 0)
    expect(d.pages[0].id).toBe('p2')
    expect(movePage(d, 0, 9)).toBe(d)
    d = addItem(d, 'rect', 'p2', box).doc
    d = addGuide(d, 'p2', 'v', 100).doc
    d = deletePage({ ...d, paywall_page: 4 }, 0)
    expect(d.pages.map((p) => p.id)).toEqual(['p1', 'p3', 'p4'])
    expect(d.items).toEqual([])
    expect(d.guides).toEqual([])
    expect(d.paywall_page).toBe(3) // kept on a page that still exists
    expect(deletePage(doc({ pages: [{ id: 'p1' }] }), 0).pages).toHaveLength(1)
  })
})

describe('items', () => {
  it('adds items with fresh ids and the server’s defaults', () => {
    const a = addItem(doc(), 'text', 'p1', box)
    const b = addItem(a.doc, 'text', 'p1', box)
    expect([a.id, b.id]).toEqual(['t1', 't2'])
    expect(b.doc.items[0]).toMatchObject({ kind: 'text', cols: 1, valign: 'top', rot: 0, opacity: 100 })
    expect(addItem(doc(), 'image', 'p1', box).id).toBe('i1')
  })

  it('moves and patches items (rounded), but never a locked one, and changes nothing when nothing changes', () => {
    let d = addItem(doc(), 'rect', 'p1', box).doc
    d = addItem(d, 'rect', 'p1', box).doc
    d = patchItems(d, ['r2'], { locked: true })
    const moved = moveItems(d, ['r1', 'r2'], 5.555, -3)
    expect(moved.items.map((i) => [i.x, i.y])).toEqual([[15.56, 7], [10, 10]])
    expect(moveItems(d, ['r1'], 0, 0)).toBe(d)
    expect(patchItems(d, ['r1'], { x: 10 })).toBe(d)
  })

  it('arranges the stacking order', () => {
    let d = doc()
    for (let k = 0; k < 3; k++) d = addItem(d, 'rect', 'p1', box).doc
    const ids = (x: Doc) => x.items.map((i) => i.id)
    expect(ids(arrange(d, ['r1'], 'front'))).toEqual(['r2', 'r3', 'r1'])
    expect(ids(arrange(d, ['r3'], 'back'))).toEqual(['r3', 'r1', 'r2'])
    expect(ids(arrange(d, ['r1'], 'forward'))).toEqual(['r2', 'r1', 'r3'])
    expect(ids(arrange(d, ['r3'], 'backward'))).toEqual(['r1', 'r3', 'r2'])
  })

  it('duplicates items, a lone text frame with its words', () => {
    let d = addItem(doc(), 'text', 'p1', box).doc
    d = ensureThread(d, 't1').doc
    d = { ...d, threads: [{ ...d.threads[0], paras: [{ runs: [{ t: 'Hello' }] }] }] }
    const r = duplicate(d, ['t1'])
    expect(r.ids).toEqual(['t2'])
    expect(r.doc.items[1]).toMatchObject({ x: 22, y: 22, locked: false })
    expect(r.doc.threads.map((t) => [t.frames, text(t.paras)])).toEqual([[['t1'], ['Hello']], [['t2'], ['Hello']]])
  })

  it('duplicates linked frames together as a thread of their own, and one of them alone without its words', () => {
    let d = addItem(doc(), 'text', 'p1', box).doc
    d = addItem(d, 'text', 'p2', box).doc
    d = link(d, 't1', 't2')
    d = { ...d, threads: [{ ...d.threads[0], paras: [{ runs: [{ t: 'A long story' }] }] }] }
    const both = duplicate(d, ['t2', 't1'])
    expect(both.ids).toEqual(['t3', 't4'])
    // In the thread's own order (t1's copy first), not the selection's.
    expect(both.doc.threads.map((t) => [t.frames, text(t.paras)])).toEqual([[['t1', 't2'], ['A long story']], [['t4', 't3'], ['A long story']]])
    const one = duplicate(d, ['t2'])
    expect(one.doc.threads).toHaveLength(1)
  })

  it('deleting a frame takes it out of its thread; the last frame takes the thread', () => {
    let d = addItem(doc(), 'text', 'p1', box).doc
    d = addItem(d, 'text', 'p2', box).doc
    d = link(d, 't1', 't2')
    expect(d.threads[0].frames).toEqual(['t1', 't2'])
    const one = deleteItems(d, ['t2'])
    expect(one.threads[0].frames).toEqual(['t1'])
    expect(deleteItems(one, ['t1']).threads).toEqual([])
    expect(deleteItems(patchItems(d, ['t1'], { locked: true }), ['t1'])).toEqual(patchItems(d, ['t1'], { locked: true }))
  })
})

describe('threads', () => {
  it('links frames into one thread, bringing the second frame’s words after the first’s', () => {
    let d = doc()
    for (let k = 0; k < 3; k++) d = addItem(d, 'text', 'p1', box).doc
    d = ensureThread(d, 't1').doc
    d = ensureThread(d, 't3').doc
    d = { ...d, threads: d.threads.map((t, k) => ({ ...t, paras: [{ runs: [{ t: k ? 'Two' : 'One' }] }] })) }
    d = link(d, 't1', 't3')
    d = link(d, 't1', 't2') // in between
    expect(d.threads).toHaveLength(1)
    expect(d.threads[0].frames).toEqual(['t1', 't2', 't3'])
    expect(text(d.threads[0].paras)).toEqual(['One', 'Two'])
    expect(link(d, 't1', 't3')).toBe(d)
    const cut = unlinkAfter(d, 't2')
    expect(cut.threads[0].frames).toEqual(['t1', 't2'])
    expect('comp' in cut.threads[0]).toBe(false)
  })

  it('links only text frames', () => {
    let d = addItem(doc(), 'text', 'p1', box).doc
    d = addItem(d, 'rect', 'p1', box).doc
    expect(link(d, 't1', 'r1')).toBe(d)
  })
})

describe('type', () => {
  const paras: Para[] = [{ runs: [{ t: 'Gem of the Bay' }] }, { runs: [{ t: 'Low ' }, { t: 'tide', it: true }] }]

  it('styles a range, splitting runs and merging equal neighbours', () => {
    const bold = applyChar(paras, [0, 4], [1, 2], { wt: 700 })
    expect(bold[0].runs).toEqual([{ t: 'Gem ' }, { t: 'of the Bay', wt: 700 }])
    expect(bold[1].runs).toEqual([{ t: 'Lo', wt: 700 }, { t: 'w ' }, { t: 'tide', it: true }])
    const back = applyChar(bold, [0, 0], [0, 14], { wt: 400 })
    expect(back[0].runs).toEqual([{ t: 'Gem of the Bay' }]) // the default isn't stored
    expect(applyChar(paras, [0, 3], [0, 3], { wt: 700 })).toEqual(paras) // nothing selected
  })

  it('gives an empty paragraph the type to come', () => {
    expect(applyChar([{ runs: [{ t: '' }] }], [0, 0], [0, 0], { size: 30 })[0].runs).toEqual([{ t: '', size: 30 }])
  })

  it('reads the type at a place from the character before it', () => {
    expect(charAt(paras[1], 0)).toEqual({ t: 'Low ' })
    expect(charAt(paras[1], 4)).toEqual({ t: 'Low ' })
    expect(charAt(paras[1], 5)).toMatchObject({ it: true })
  })

  it('sets paragraph attributes on a range, either way round', () => {
    const r = applyPara(paras, 1, 0, { align: 'c', sb: 6 })
    expect(r.map((p) => [p.align, p.sb])).toEqual([['c', 6], ['c', 6]])
    expect(applyPara(r, 0, 0, { align: 'l' })[0].align).toBeUndefined() // the default isn't stored
  })

  it('keeps only what differs from the default', () => {
    expect(sparseChar({ wt: 400, it: false, size: 30 })).toEqual({ size: 30 })
    expect(charOf({}).wt).toBe(400)
    expect(mergeRuns([{ t: 'a' }, { t: 'b' }, { t: '' }, { t: 'c', it: true }])).toEqual([{ t: 'ab' }, { t: 'c', it: true }])
  })
})

describe('guides', () => {
  it('adds, moves and removes guides', () => {
    const { doc: d, id } = addGuide(doc(), 'p1', 'h', 100.123)
    expect(d.guides).toEqual([{ id, page: 'p1', axis: 'h', at: 100.12 }])
    expect(moveGuide(d, id, 50).guides[0].at).toBe(50)
    expect(deleteGuide(d, id).guides).toEqual([])
  })
})

it('a new item sits where it was drawn', () => {
  expect(newItem('line', 'p1', 'l1', { x: 1.234, y: 2, w: 3, h: 4 })).toMatchObject({ x: 1.23, stroke: { w: 1 } })
})
