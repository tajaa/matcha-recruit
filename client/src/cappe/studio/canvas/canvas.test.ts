import { describe, expect, it } from 'vitest'
import { newItem } from '../model/doc'
import type { Doc, Item } from '../model/types'
import { GAP, PASTE, bounds, hitItem, hits, layout, menuTarget, pageAt, snap1, snapTargets, turn } from './geometry'
import { alignItems, canSpace, rehome, spaceItems } from './align'
import { dragBox, resize, rotate } from './transform'

const doc = (over: Partial<Doc> = {}): Doc => ({
  v: 1, size: { w: 600, h: 800 }, facing: true, margins: { t: 50, b: 50, i: 40, o: 60 }, cols: { n: 2, g: 20 },
  baseline: { start: 50, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'pt', paper: '#ffffff',
  pages: [{ id: 'p1' }, { id: 'p2' }, { id: 'p3' }], guides: [], items: [], threads: [], paywall_page: null, ...over,
})
const rect = (over: Partial<Item> = {}): Item => ({ ...newItem('rect', 'p1', 'r1', { x: 100, y: 100, w: 200, h: 100 }), ...over } as Item)
const near = (a: { x: number; y: number }, b: { x: number; y: number }) => {
  expect(a.x).toBeCloseTo(b.x)
  expect(a.y).toBeCloseTo(b.y)
}

describe('the pasteboard', () => {
  it('stacks spreads, a lone first page on the right as it would be in a pair', () => {
    const lay = layout(doc())
    expect(lay.spreads.map((s) => s.pages)).toEqual([[0], [1, 2]])
    expect(lay.origin[0]).toEqual({ x: PASTE + 600, y: PASTE })
    expect(lay.origin[1]).toEqual({ x: PASTE, y: PASTE + 800 + GAP })
    expect(lay.origin[2].x).toBe(PASTE + 600)
    expect(lay.width).toBe(1200 + 2 * PASTE)
    expect(layout(doc({ facing: false })).origin[0].x).toBe(PASTE + 300) // single pages are centred
  })

  it('finds the page under a point, or the nearest one', () => {
    const d = doc()
    const lay = layout(d)
    expect(pageAt(d, lay, { x: lay.origin[2].x + 10, y: lay.origin[2].y + 10 })).toBe(2)
    expect(pageAt(d, lay, { x: 0, y: lay.origin[1].y + 100 })).toBe(1)
  })
})

describe('items on it', () => {
  it('turns points about a centre', () => {
    near(turn({ x: 10, y: 0 }, { x: 0, y: 0 }, 90), { x: 0, y: 10 })
    expect(turn({ x: 3, y: 4 }, { x: 0, y: 0 }, 0)).toEqual({ x: 3, y: 4 })
  })

  it('hits a turned item inside its turned box only', () => {
    const o = { x: 0, y: 0 }
    const r = rect({ rot: 90 }) // 200×100 turned upright: x 150–250, y 50–250
    expect(hits(r, o, { x: 200, y: 60 })).toBe(true)
    expect(hits(r, o, { x: 110, y: 150 })).toBe(false)
    expect(hits(rect(), o, { x: 98, y: 98 }, 3)).toBe(true)
  })

  it('picks the topmost visible item', () => {
    const d = doc({ items: [rect(), rect({ id: 'r2' }), rect({ id: 'r3', hidden: true })] })
    const lay = layout(d)
    const p = { x: lay.origin[0].x + 150, y: lay.origin[0].y + 150 }
    expect(hitItem(d, lay, p)?.id).toBe('r2')
    expect(hitItem(d, lay, { x: 0, y: 0 })).toBeNull()
  })

  it('bounds turned items by their corners', () => {
    const b = bounds([rect({ rot: 90 })], () => ({ x: 0, y: 0 }))!
    expect([b.x, b.y, b.w, b.h].map((v) => Math.round(v))).toEqual([150, 50, 100, 200])
    expect(bounds([], () => ({ x: 0, y: 0 }))).toBeNull()
  })
})

describe('snapping', () => {
  it('offers page edges, margins (inside on the spine), columns, guides and other items', () => {
    const d = doc({ guides: [{ id: 'g1', page: 'p2', axis: 'v', at: 123 }], items: [rect({ page: 'p2' }), rect({ id: 'r2', page: 'p2', rot: 5 })] })
    const lay = layout(d)
    const t = snapTargets(d, lay, 1, new Set())
    const xs = t.x.map((x) => x - lay.origin[1].x)
    // A left page: outside margin on the left (60), inside on the right (40).
    expect(xs.slice(0, 5)).toEqual([0, 300, 600, 60, 560])
    expect(xs).toEqual(expect.arrayContaining([300, 320, 123, 100, 200]))
    expect(xs.filter((x) => x === 100)).toHaveLength(1) // a turned item isn't a target
    expect(snapTargets(d, lay, 1, new Set(['r1'])).x.map((x) => x - lay.origin[1].x)).not.toContain(200)
  })

  it('takes the smallest move within tolerance', () => {
    expect(snap1([10, 50], [12, 49], 3)).toEqual({ d: -1, at: 49 })
    expect(snap1([10], [20], 3)).toEqual({ d: 0, at: null })
  })
})

describe('transforms', () => {
  const geo = { x: 0, y: 0, w: 100, h: 50, rot: 0 }

  it('resizes from a handle, the opposite corner staying put', () => {
    expect(resize(geo, 'se', 20, 10)).toEqual({ x: 0, y: 0, w: 120, h: 60, rot: 0 })
    expect(resize(geo, 'nw', 20, 10)).toEqual({ x: 20, y: 10, w: 80, h: 40, rot: 0 })
    expect(resize(geo, 'e', 20, 99)).toEqual({ x: 0, y: 0, w: 120, h: 50, rot: 0 })
    expect(resize(geo, 'se', 20, 0, { keep: true })).toEqual({ x: 0, y: 0, w: 120, h: 60, rot: 0 })
    expect(resize(geo, 'e', 10, 0, { fromCentre: true })).toEqual({ x: -10, y: 0, w: 120, h: 50, rot: 0 })
    expect(resize(geo, 'w', 500, 0).w).toBe(1)
  })

  it('keeps a turned item’s opposite corner where it is on the page', () => {
    const turned = { ...geo, rot: 90 }
    const corner = (g: typeof geo) => turn({ x: g.x, y: g.y }, { x: g.x + g.w / 2, y: g.y + g.h / 2 }, g.rot)
    const after = resize(turned, 'se', 0, 30) // down the page is along its width
    expect(after.w).toBe(130)
    near(corner(after), corner(turned))
  })

  it('turns by the angle dragged through, in 15° steps with Shift, between −180 and 180', () => {
    const c = { x: 0, y: 0 }
    expect(rotate(0, c, { x: 10, y: 0 }, { x: 0, y: 10 })).toBe(90)
    expect(rotate(0, c, { x: 10, y: 0 }, { x: 10, y: 2 }, true)).toBe(15)
    expect(rotate(170, c, { x: 10, y: 0 }, { x: 0, y: 10 })).toBe(-100)
  })

  it('drags out boxes, squares and 45° lines', () => {
    expect(dragBox({ x: 10, y: 10 }, { x: 0, y: 30 })).toEqual({ x: 0, y: 10, w: 10, h: 20, flip: true })
    expect(dragBox({ x: 0, y: 0 }, { x: 10, y: 30 }, { square: true })).toMatchObject({ w: 30, h: 30 })
    const line = dragBox({ x: 0, y: 0 }, { x: 10, y: 9 }, { square: true, line: true })
    expect(line.w).toBeCloseTo(line.h)
  })
})

describe('lining things up', () => {
  const at = (d: Doc, id: string) => d.items.find((i) => i.id === id)!
  const r = (id: string, x: number, y: number, w: number, h: number, over: Partial<Item> = {}): Item =>
    ({ ...newItem('rect', 'p1', id, { x, y, w, h }), ...over } as Item)

  it('lines one thing up with its page', () => {
    const d = doc({ items: [r('a', 100, 100, 200, 100)] })
    expect(at(alignItems(d, ['a'], 'right'), 'a').x).toBe(400)
    expect(at(alignItems(d, ['a'], 'centre'), 'a').x).toBe(200)
    expect(at(alignItems(d, ['a'], 'bottom'), 'a').y).toBe(700)
    expect(at(alignItems(d, ['a'], 'middle'), 'a').y).toBe(350)
    // Already there: the same document, so no undo step and nothing to save.
    const centred = alignItems(d, ['a'], 'centre')
    expect(alignItems(centred, ['a'], 'centre')).toBe(centred)
  })

  it('lines several up with the box around them; a locked one stays put but counts', () => {
    const d = doc({ items: [r('a', 100, 100, 200, 100), r('b', 50, 300, 100, 50)] })
    const left = alignItems(d, ['a', 'b'], 'left')
    expect([at(left, 'a').x, at(left, 'b').x]).toEqual([50, 50])
    const right = alignItems(d, ['a', 'b'], 'right')
    expect([at(right, 'a').x, at(right, 'b').x]).toEqual([100, 200])
    const top = alignItems(d, ['a', 'b'], 'top')
    expect(at(top, 'b').y).toBe(100)
    const held = doc({ items: [r('a', 100, 100, 200, 100), r('l', 10, 300, 50, 50, { locked: true })] })
    const out = alignItems(held, ['a', 'l'], 'left')
    expect(at(out, 'a').x).toBe(10)
    expect(at(out, 'l')).toBe(at(held, 'l'))
    // Nothing that can move: the same document.
    expect(alignItems(held, ['l'], 'left')).toBe(held)
  })

  it('lines a turned thing up by the corners it shows', () => {
    const d = doc({ items: [r('a', 100, 100, 200, 100, { rot: 90 }), r('b', 50, 400, 100, 50)] })
    // Turned a quarter, it shows 100 wide from x 150: its box moves 100 left.
    expect(at(alignItems(d, ['a', 'b'], 'left'), 'a').x).toBe(0)
  })

  it('puts something that lands on the other page of a spread onto that page', () => {
    const d = doc({ items: [r('a', 500, 100, 50, 50, { page: 'p2' }), r('b', 300, 100, 50, 50, { page: 'p3' })] })
    const out = alignItems(d, ['a', 'b'], 'right')
    expect(at(out, 'a')).toMatchObject({ page: 'p3', x: 300, y: 100 })
    expect(at(out, 'b')).toMatchObject({ page: 'p3', x: 300 })
  })

  it('spaces three or more evenly, the first and last staying put', () => {
    const d = doc({ items: [r('a', 0, 0, 10, 10), r('c', 200, 300, 10, 10), r('b', 50, 100, 20, 30)] })
    const across = spaceItems(d, ['a', 'b', 'c'], 'across')
    expect([at(across, 'a').x, at(across, 'b').x, at(across, 'c').x]).toEqual([0, 95, 200])
    const down = spaceItems(d, ['a', 'b', 'c'], 'down')
    // 310 tall with 50 of boxes: two gaps of 130.
    expect([at(down, 'a').y, at(down, 'b').y, at(down, 'c').y]).toEqual([0, 140, 300])
    expect(canSpace(d, ['a', 'b'])).toBe(false)
    expect(spaceItems(d, ['a', 'b'], 'across')).toBe(d)
    const locked = doc({ items: [...d.items.slice(0, 2), { ...d.items[2], locked: true }] })
    expect(canSpace(locked, ['a', 'b', 'c'])).toBe(false)
  })

  it('spaces their middles when a wide one is over the others, so none leaves the room', () => {
    // 380 of boxes in 300 of room: even gaps would be negative.
    const d = doc({ items: [r('a', 0, 0, 300, 10), r('b', 50, 0, 30, 10), r('c', 100, 0, 50, 10)] })
    const out = spaceItems(d, ['a', 'b', 'c'], 'across')
    // Middles 65 (b), 125 (c), 150 (a): spaced to 65, 107.5, 150.
    expect([at(out, 'b').x, at(out, 'c').x, at(out, 'a').x]).toEqual([50, 82.5, 0])
    for (const id of ['a', 'b', 'c']) {
      const i = at(out, id)
      expect(i.x).toBeGreaterThanOrEqual(0)
      expect(i.x + i.w).toBeLessThanOrEqual(300)
    }
  })

  it('keeps the room from the first start to the furthest end, whichever starts last', () => {
    // c starts last but b ends furthest (at 500): 420 of boxes, two gaps of 40.
    const d = doc({ items: [r('a', 0, 0, 10, 10), r('b', 100, 0, 400, 10), r('c', 150, 0, 10, 10)] })
    const out = spaceItems(d, ['a', 'b', 'c'], 'across')
    expect([at(out, 'a').x, at(out, 'b').x, at(out, 'c').x]).toEqual([0, 50, 490])
  })

  it('rehomes only what has crossed onto another page', () => {
    const d = doc({ items: [r('a', 100, 100, 50, 50, { page: 'p2' }), r('b', 700, 100, 50, 50, { page: 'p2' })] })
    const out = rehome(d, layout(d), ['a', 'b', 'gone'])
    expect(at(out, 'a')).toBe(at(d, 'a'))
    expect(at(out, 'b')).toMatchObject({ page: 'p3', x: 100 })
  })
})

describe('what a right-click is about', () => {
  it('the thing under it (keeping the selection it is part of), else nothing and the page under it', () => {
    const d = doc({ items: [rect({ id: 'a' }), rect({ id: 'b', x: 350 })] })
    const lay = layout(d)
    const on = (x: number, y: number) => ({ x: lay.origin[0].x + x, y: lay.origin[0].y + y })
    expect(menuTarget(d, lay, on(150, 150), [])).toEqual({ selection: ['a'], page: 0 })
    expect(menuTarget(d, lay, on(150, 150), ['a', 'b'])).toEqual({ selection: ['a', 'b'], page: 0 })
    expect(menuTarget(d, lay, on(150, 150), ['b'])).toEqual({ selection: ['a'], page: 0 })
    expect(menuTarget(d, lay, { x: lay.origin[2].x + 10, y: lay.origin[2].y + 700 }, ['a'])).toEqual({ selection: [], page: 2 })
  })
})
