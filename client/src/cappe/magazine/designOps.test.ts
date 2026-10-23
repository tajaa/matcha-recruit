import { describe, expect, it } from 'vitest'
import type { StoryBlock } from '../types'
import {
  addLayers, align, arrange, boxOf, cloneLayers, designOf, distribute, duplicate, findLayer, group, holdsDesign, moveLayer,
  newImage, newShape, newText, normAngle, patchLayers, removeLayers, round, setGeometry, ungroup, withDesign,
} from './design/designOps'
import type { Design, Layer } from './design/types'

const shape = (id: string, x = 10, y = 10, w = 20, h = 20): Layer => ({ ...newShape(null, 'rect'), id, x, y, w, h })
const ids = (d: Design) => d.layers.map((l) => l.id)

describe('design operations', () => {
  it('round half up as the server does, never to -0', () => {
    expect(round(12.25)).toBe(12.3)
    expect(round(-12.25)).toBe(-12.2)
    expect(Object.is(round(-0.04), 0)).toBe(true)
    expect(round(1.005, 2)).toBe(1)  // as Python: 1.005 is 1.00499… in binary
  })

  it('finds a design on a cover, a photo, a picture in a group and a page, and puts it back', () => {
    const d: Design = { layers: [shape('a')] }
    const photo: StoryBlock = { type: 'photo', asset_id: 'x', caption: '', size: 'column', design: d }
    const photos: StoryBlock = { type: 'photos', layout: 'pair', items: [{ asset_id: 'x', caption: '' }, { asset_id: 'y', caption: '', design: d }] }
    const page: StoryBlock = { type: 'page', aspect: '3:4', design: { layers: [], background: { kind: 'solid', color: '#ffffff', angle: 180, stops: [] } } }
    expect(designOf(photo, null)).toBe(d)
    expect(designOf(photos, 1)).toBe(d)
    expect(designOf(photos, 0)).toBeNull()
    expect(holdsDesign({ type: 'quote', text: '', attribution: '', style: 'big' }, null)).toBe(false)
    expect(holdsDesign(photos, 1)).toBe(true)
    expect(holdsDesign(photos, 5)).toBe(false)
    // A picture's design with nothing left on it is none; a page keeps its background.
    expect((withDesign(photo, null, { layers: [] }) as { design: unknown }).design).toBeNull()
    expect((withDesign(photos, 0, d) as Extract<StoryBlock, { type: 'photos' }>).items[0].design).toBe(d)
    const p2 = withDesign(page, null, { layers: [shape('b')] }) as Extract<StoryBlock, { type: 'page' }>
    expect(p2.design.background?.color).toBe('#ffffff')
    expect(ids(p2.design)).toEqual(['b'])
  })

  it('adds words, shapes and pictures with ids of their own', () => {
    const t = newText(null, 'heading')
    const d = addLayers(null, [t])!
    const s = newShape(d, 'ellipse', { square: true, ratio: 1.5 })
    expect(s.h).toBe(45)  // a circle on a 3:2 picture is half as tall again in percent
    const p = newImage(addLayers(d, [s]), 'asset', 2, 1)
    expect(new Set([t.id, s.id, p.id]).size).toBe(3)
    expect(p.h).toBe(20)  // a 2:1 picture 40% wide on a square artboard
    expect(t.rt.content[0]).toEqual({ type: 'paragraph', content: [{ type: 'text', text: 'Add a heading' }] })
    expect(addLayers({ layers: Array.from({ length: 200 }, (_, i) => shape(`x${i}`)) }, [shape('one-more')])).toBeNull()
  })

  it('moves, sizes and turns layers within what the server keeps', () => {
    let d: Design = { layers: [shape('a'), newText(null, 'body')] }
    d = setGeometry(d, [{ id: 'a', x: -500, y: 33.333, w: 0.1, rot: 270 }])
    expect(findLayer(d, 'a')).toMatchObject({ x: -100, y: 33.3, w: 0.5, rot: -90 })
    const t = d.layers[1]
    d = setGeometry(d, [{ id: t.id, size: 99 }])
    expect((findLayer(d, t.id) as Extract<Layer, { kind: 'text' }>).size).toBe(60)
    expect(normAngle(-190)).toBe(170)
    expect(normAngle(180)).toBe(180)
    expect(setGeometry(d, [{ id: 'nobody', x: 1 }])).toBe(d)
  })

  it('moves and scales a group through its children', () => {
    let d: Design = { layers: [shape('a', 10, 10, 10, 10), shape('b', 30, 10, 10, 10)] }
    const g = group(d, ['a', 'b'])
    d = g.design
    expect(boxOf(findLayer(d, g.id!)!)).toEqual({ x: 10, y: 10, w: 30, h: 10 })
    d = setGeometry(d, [{ id: g.id!, x: 20, y: 50, w: 60 }])
    expect(findLayer(d, 'a')).toMatchObject({ x: 20, y: 50, w: 20, h: 10 })
    expect(findLayer(d, 'b')).toMatchObject({ x: 60, y: 50, w: 20 })
  })

  it('restyles only the layers that have the property, and keeps a weight the face has', () => {
    const t = newText(null, 'body')
    let d: Design = { layers: [t, shape('a')] }
    d = patchLayers(d, [t.id, 'a'], { font: 'Anton', weight: 700, opacity: 50 })
    expect(findLayer(d, t.id)).toMatchObject({ font: 'Anton', weight: 400, opacity: 50 })
    expect(findLayer(d, 'a')).toMatchObject({ opacity: 50 })
    expect('font' in findLayer(d, 'a')!).toBe(false)
    // A face with no italic sets the words upright (the server would anyway).
    d = patchLayers(patchLayers(d, [t.id], { font: 'Playfair Display', italic: true }), [t.id], { font: 'Anton' })
    expect(findLayer(d, t.id)).toMatchObject({ font: 'Anton', italic: false })
  })

  it('groups siblings where the topmost was, and ungroups them back with its look', () => {
    const d: Design = { layers: [shape('a'), shape('b'), shape('c'), shape('d')] }
    const { design, id } = group(d, ['d', 'b'])
    expect(ids(design)).toEqual(['a', 'c', id])
    expect((findLayer(design, id!) as Extract<Layer, { kind: 'group' }>).children.map((l) => l.id)).toEqual(['b', 'd'])
    const faded = patchLayers(design, [id!], { opacity: 50 })
    const back = ungroup(faded, id!)
    expect(ids(back.design)).toEqual(['a', 'c', 'b', 'd'])
    expect(findLayer(back.design, 'b')!.opacity).toBe(50)
    expect(group(d, ['a']).id).toBeNull()  // one layer is no group
  })

  it('stacks layers forward, back, to the front and to the back', () => {
    const d: Design = { layers: [shape('a'), shape('b'), shape('c')] }
    expect(ids(arrange(d, ['a'], 'forward'))).toEqual(['b', 'a', 'c'])
    expect(ids(arrange(d, ['c'], 'forward'))).toEqual(['a', 'b', 'c'])
    expect(ids(arrange(d, ['c'], 'backward'))).toEqual(['a', 'c', 'b'])
    expect(ids(arrange(d, ['a', 'b'], 'front'))).toEqual(['c', 'a', 'b'])
    expect(ids(arrange(d, ['c'], 'back'))).toEqual(['c', 'a', 'b'])
    expect(ids(moveLayer(d, 'a', 'c', 'above'))).toEqual(['b', 'c', 'a'])
    expect(ids(moveLayer(d, 'c', 'a', 'below'))).toEqual(['c', 'a', 'b'])
  })

  it('aligns one layer to its artboard and several to each other, and spaces them evenly', () => {
    const d: Design = { layers: [shape('a', 10, 10, 20, 20), shape('b', 50, 40, 10, 10), shape('c', 80, 70, 10, 10)] }
    expect(findLayer(align(d, ['a'], 'right'), 'a')!.x).toBe(80)
    expect(findLayer(align(d, ['a'], 'middle'), 'a')!.y).toBe(40)
    const top = align(d, ['a', 'b', 'c'], 'top')
    expect(['a', 'b', 'c'].map((i) => findLayer(top, i)!.y)).toEqual([10, 10, 10])
    const spaced = distribute({ layers: [shape('a', 0, 0, 10, 10), shape('b', 15, 0, 10, 10), shape('c', 90, 0, 10, 10)] }, ['a', 'b', 'c'], 'x')
    expect(findLayer(spaced, 'b')!.x).toBe(45)
    expect(distribute(d, ['a', 'b'], 'x')).toBe(d)
  })

  it('goes by the height the page measured for words that grow with them', () => {
    const t = { ...newText(null, 'heading'), id: 't', x: 0, y: 0, w: 50, h: 10, autosize: 'height' } as Layer
    const d: Design = { layers: [t, shape('a', 0, 50, 10, 10)] }
    const heights = { t: 25 }
    expect(boxOf(t, heights).h).toBe(25)
    expect(boxOf(t).h).toBe(10)  // nothing measured yet: what it keeps
    expect(boxOf({ ...t, autosize: 'none' } as Layer, heights).h).toBe(10)  // a fixed box is its own
    expect(findLayer(align(d, ['t'], 'bottom', heights), 't')!.y).toBe(75)
    expect(findLayer(align(d, ['t'], 'middle', heights), 't')!.y).toBe(37.5)
    const g = group(d, ['t', 'a'], heights)
    expect(findLayer(g.design, g.id!)).toMatchObject({ y: 0, h: 60 })
  })

  it('copies layers with new ids, nudged, above the originals', () => {
    const d: Design = { layers: [shape('a'), shape('b')] }
    const { design, ids: copies } = duplicate(d, ['a'])
    expect(ids(design)).toEqual(['a', copies[0], 'b'])
    expect(findLayer(design, copies[0])).toMatchObject({ x: 12, y: 12 })
    const g = group(d, ['a', 'b'])
    const [copy] = cloneLayers(g.design, [findLayer(g.design, g.id!)!])
    const all = [copy.id, ...(copy as Extract<Layer, { kind: 'group' }>).children.map((c) => c.id)]
    expect(new Set([...all, 'a', 'b', g.id]).size).toBe(all.length + 3)
  })

  it('takes layers away, and a group left empty with them', () => {
    const g = group({ layers: [shape('a'), shape('b'), shape('c')] }, ['a', 'b'])
    expect(ids(removeLayers(g.design, ['a', 'b']))).toEqual(['c'])
    expect((findLayer(removeLayers(g.design, ['a']), g.id!) as Extract<Layer, { kind: 'group' }>).children.map((l) => l.id)).toEqual(['b'])
  })
})
