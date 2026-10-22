import { describe, expect, it } from 'vitest'
import { newItem } from '../model/doc'
import type { Doc, Item } from '../model/types'
import { GAP, PASTE, bounds, hitItem, hits, layout, pageAt, snap1, snapTargets, turn } from './geometry'
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
