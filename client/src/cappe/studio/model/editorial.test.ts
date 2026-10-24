import { describe, expect, it } from 'vitest'
import { hitItem, layout } from '../canvas/geometry'
import { portableCollection } from './collections'
import { keepLinks, linkProblem } from './crops'
import { charOf, newItem, paraOf, registerFaces } from './doc'
import { applyChar, applyPara, kernAt, patchItems } from './ops'
import { cutoutFor, putSubjectInFront, subjectProblem } from './subject'
import type { Asset, Doc, Face, ImageItem, Shape, TextItem } from './types'

const doc = (over: Partial<Doc> = {}): Doc => ({
  v: 1, size: { w: 600, h: 800 }, facing: false, margins: { t: 50, b: 50, i: 50, o: 50 }, cols: { n: 1, g: 12 },
  baseline: { start: 50, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'pt', paper: '#ffffff',
  pages: [{ id: 'p1' }], guides: [], items: [], threads: [], paywall_page: null, ...over,
})

const OWN = 'u-0123456789abcdef'
const face = (weight: number, italic: boolean, sha: string): Face => ({ family: OWN, name: 'Canela', weight, italic, sha, bytes: 1,
  upm: 1000, asc: 900, desc: -250, cap: 700, x: 480, features: ['smcp'] })

describe('type the server keeps', () => {
  it('kerning, alternates, drop caps and keep options, clamped as the server clamps them', () => {
    const c = charOf({ kern: 900, ot: 'swsh,smcp,bogus,smcp' })
    expect([c.kern, c.ot]).toEqual([500, 'smcp,swsh'])
    expect(charOf({ kern: Number.NaN }).kern).toBe(0)
    const p = paraOf({ dc: 1, dcn: 9, kw: 0, ko: 7, runt: 2 })
    expect([p.dc, p.dcn, p.kw, p.ko, p.runt]).toEqual([0, 3, 1, 3, 2])
  })

  it('a magazine’s own font by its key: its nearest face once known, any weight to the hundred before', () => {
    const other = 'u-ffffffffffffffff'
    expect(charOf({ font: other, wt: 649, it: true })).toMatchObject({ font: other, wt: 600, it: true })
    registerFaces([face(300, false, '5'.repeat(64)), face(700, true, '4'.repeat(64))])
    expect(charOf({ font: OWN, wt: 400, it: true })).toMatchObject({ font: OWN, wt: 300, it: false })
    expect(charOf({ font: OWN, wt: 600, it: true })).toMatchObject({ font: OWN, wt: 700, it: true })
    expect(charOf({ font: 'Nope' }).font).toBe('Source Serif 4')
  })

  it('a style applied over letters keeps their kerning and alternates', () => {
    const paras = [{ runs: [{ t: 'A', kern: -40, ot: 'swsh', size: 30 }, { t: 'V' }] }]
    expect(applyChar(paras, [0, 0], [0, 2], { style: 'cs1' })[0].runs).toEqual([{ t: 'A', kern: -40, ot: 'swsh', style: 'cs1' }, { t: 'V', style: 'cs1' }])
    expect(applyPara(paras, 0, 0, { style: 'ps1' })[0].runs).toEqual([{ t: 'A', kern: -40, ot: 'swsh' }, { t: 'V' }])
  })
})

const SHAPE: Shape = { ar: 1, rows: [[0.4, 0.6], [0.3, 0.7]] }
const photo = (over: Partial<ImageItem> = {}): ImageItem => ({ ...(newItem('image', 'p1', 'i1', { x: 100, y: 100, w: 300, h: 300 }) as ImageItem),
  asset_id: 'a1', ...over })
const text = (id: string, over: Partial<TextItem> = {}) => ({ ...(newItem('text', 'p1', id, { x: 50, y: 150, w: 500, h: 100 }) as TextItem), ...over })
const assets: Record<string, Asset> = {
  a1: { id: 'a1', url: '/a1.jpg', width: 1000, height: 1000 },
  c1: { id: 'c1', url: '/c1.png', width: 1000, height: 1000, kind: 'edit', parent: 'a1', recipe: { cutout: { points: [], feather: 0, invert: false } } as never },
  b1: { id: 'b1', url: '/b1.jpg', width: 1000, height: 1000 },
}

describe('kerning by hand', () => {
  // A face that kerns "AV" and "TA" by -80 thousandths of an em.
  const pairs: Record<string, number> = { AV: -80, TA: -80 }
  const width = (c: { size: number }, t: string) => {
    let w = [...t].length * 0.6
    for (let k = 0; k < t.length - 1; k++) w += (pairs[t.slice(k, k + 2)] ?? 0) / 1000
    return w * c.size
  }
  const word = (t: string) => [{ runs: [{ t, size: 50 }] }]

  it('starts from the font’s own kerning of every pair in the word, so the first step tightens', () => {
    const out = kernAt(word('TAVERN go'), 0, 2, -10, width)
    expect(out[0].runs).toEqual([{ t: 'T', size: 50, kern: -80 }, { t: 'A', size: 50, kern: -90 }, { t: 'VERN go', size: 50 }])
    // Kerned already: only the step.
    expect(kernAt(out, 0, 2, -10, width)[0].runs[1]).toEqual({ t: 'A', size: 50, kern: -100 })
    expect(kernAt(out, 0, 6, 20, width)[0].runs.at(-1)).toEqual({ t: ' go', size: 50 })
  })

  it('does nothing after a space or at the start', () => {
    const p = word('A V')
    expect(kernAt(p, 0, 2, -10, width)).toBe(p)
    expect(kernAt(p, 0, 0, -10, width)).toBe(p)
  })
})

describe('the subject in front of the lettering', () => {
  it('finds the cut-out to use: the picture itself, else the newest made of it', () => {
    expect(cutoutFor(assets, 'a1')?.id).toBe('c1')
    expect(cutoutFor(assets, 'c1')?.id).toBe('c1')
    expect(cutoutFor(assets, 'b1')).toBeNull()
    expect(cutoutFor(assets, null)).toBeNull()
  })

  it('keeps the photo behind the text it covers and sets its cut-out over it, linked', () => {
    const d = doc({ items: [text('t1'), photo(), text('t2', { y: 600 })] })
    const out = putSubjectInFront(d, 'i1', assets.c1, SHAPE)!
    expect(out.doc.items.map((i) => i.id)).toEqual(['i1', 't1', out.id, 't2']) // under the masthead, then the cut-out over it
    const [base, , partner] = out.doc.items as ImageItem[]
    expect(base).toMatchObject({ asset_id: 'a1', link: partner.link, shape: SHAPE })
    expect(partner).toMatchObject({ asset_id: 'c1', cutout: true, x: 100, y: 100, w: 300, h: 300, fx: 50, zoom: 100 })
    expect(linkProblem(out.doc, ['i1', out.id])).toBeNull() // a cut-out partner shows its own picture
    // A frame showing the cut-out goes back to its photo.
    const shown = putSubjectInFront(doc({ items: [photo({ asset_id: 'c1' }), text('t1')] }), 'i1', assets.c1, SHAPE)!
    expect((shown.doc.items[0] as ImageItem).asset_id).toBe('a1')
  })

  it('says why it can’t', () => {
    expect(subjectProblem(doc({ items: [photo({ asset_id: null })] }), 'i1')).toMatch(/photo/)
    expect(subjectProblem(doc({ items: [photo({ rot: 4 })] }), 'i1')).toMatch(/turned/)
    expect(subjectProblem(doc({ items: [photo({ fit: 'fit' })] }), 'i1')).toMatch(/Fill/)
    expect(subjectProblem(doc({ items: [photo({ cutout: true })] }), 'i1')).toMatch(/already/)
  })

  it('stays lined up with its photo: a narrower window shows the same picture, a new photo lets it go', () => {
    const made = putSubjectInFront(doc({ items: [photo(), text('t1')] }), 'i1', assets.c1, SHAPE)!
    const before = made.doc
    const fresh = keepLinks(doc({ items: [photo(), text('t1')] }), before, assets)
    expect(fresh.items.find((i) => i.id === 'i1')).toMatchObject({ fx: 50, fy: 50, zoom: 100 }) // the photo didn't move
    const narrowed = keepLinks(fresh, patchItems(fresh, [made.id], { w: 100 }), assets)
    const partner = narrowed.items.find((i) => i.id === made.id) as ImageItem
    expect(partner.asset_id).toBe('c1') // never given the photo
    expect([partner.fx, partner.zoom]).toEqual([0, 100]) // the photo's left third, at the photo's scale
    expect(narrowed.items.find((i) => i.id === 'i1')).toMatchObject({ fx: 50, zoom: 100 }) // which stays where it was
    const swapped = keepLinks(fresh, patchItems(fresh, ['i1'], { asset_id: 'b1' }), assets)
    expect(swapped.items.find((i) => i.id === made.id)).not.toHaveProperty('link')
  })

  it('is clicked only on the subject, unless it is selected', () => {
    const made = putSubjectInFront(doc({ items: [text('t1', { x: 100, y: 100, w: 300, h: 300 }), photo()] }), 'i1', assets.c1, SHAPE)!
    const lay = layout(made.doc)
    const o = lay.origin[0]
    const at = (x: number, y: number) => hitItem(made.doc, lay, { x: o.x + x, y: o.y + y })?.id
    expect(at(250, 150)).toBe(made.id) // on the subject (the middle fifth of the top half)
    expect(at(120, 150)).toBe('t1') // beside it: the lettering
    expect(hitItem(made.doc, lay, { x: o.x + 120, y: o.y + 150 }, 0, new Set([made.id]))?.id).toBe(made.id)
  })
})

describe('a collection', () => {
  it('leaves the magazine’s own fonts and cut-out subjects behind', () => {
    const d = doc({ items: [photo({ shape: SHAPE, wrap: { m: 'subject', o: 4 }, link: 'lk1' }), photo({ id: 'i2', asset_id: 'c1', cutout: true, link: 'lk1' }), text('t1')],
      threads: [{ id: 's1', frames: ['t1'], paras: [{ runs: [{ t: 'Mast', font: OWN, wt: 700 }, { t: 'head', kern: 20 }] }] }],
      faces: [face(700, false, '4'.repeat(64))] })
    const out = portableCollection(d)
    expect(out.faces).toBeUndefined()
    expect(out.items[0]).toMatchObject({ asset_id: null, wrap: { m: 'box', o: 4 } })
    expect(out.items[0]).not.toHaveProperty('shape')
    expect(out.items[1]).not.toHaveProperty('cutout')
    expect(out.threads[0].paras[0].runs).toEqual([{ t: 'Mast', wt: 700 }, { t: 'head', kern: 20 }])
  })
})
