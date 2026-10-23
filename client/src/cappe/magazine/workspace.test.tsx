import { useEffect, useState } from 'react'
import { act, createEvent, fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { CappeAsset, StoryBlock } from '../types'
import type { FrameTarget } from './canvas/bridge'
import type { StoryDoc } from './canvas/storyDoc'
import { newBlock } from './editor/blocks'
import { designOf, findLayer, newShape, newText } from './design/designOps'
import type { Design, Layer, TextLayer } from './design/types'
import {
  addBlock, addImage, addPage, addShape, addText, artOf, artRatio, command, designAssets, designFontHrefs, designMessages, panelKey,
  type Clipboard,
} from './workspace/actions'
import { alphaOf, hexToHsva, hsvaToHex, readColour, withAlpha } from './workspace/color'
import { evalSum } from './workspace/sum'
import ArtInspector, { type ArtHandlers } from './workspace/ArtInspector'
import LayerInspector from './workspace/LayerInspector'
import LayersPanel from './workspace/LayersPanel'

const S = 'preview'
const ASSET = { id: 'a-1', url: 'https://cdn.example.test/a.jpg', alt: 'Boats', title: 'Harbour', width: 1600, height: 1000, variants: {} } as unknown as CappeAsset
const ASSETS = new Map([[ASSET.id, ASSET]])

const words = (id: string, over: Partial<TextLayer> = {}): TextLayer => ({ ...newText(null, 'body'), id, ...over })
const shape = (id: string): Layer => ({ ...newShape(null, 'rect'), id })

const story = (): StoryDoc => ({
  fields: { title: 'Low tide', kicker: '', excerpt: '', byline: '', topic: '', layout: 'standard', status: 'draft', access: 'free' },
  blocks: [
    { ...(newBlock('cover') as Extract<StoryBlock, { type: 'cover' }>), asset_id: 'a-1' },
    newBlock('text'),
    { ...(newBlock('photo') as Extract<StoryBlock, { type: 'photo' }>), asset_id: 'a-1', design: { layers: [words('w1'), shape('s1')] } },
    { type: 'photos', layout: 'pair', items: [{ asset_id: 'a-1', caption: '' }, { asset_id: null, caption: '' }] },
    newBlock('page'),
  ],
})
const at = (block: number, item: number | null = null) => ({ block, item })
const layers = (d: StoryDoc, block: number, item: number | null = null) => designOf(d.blocks[block], item)!.layers

describe('sums typed into a number', () => {
  it('works out + − × ÷ and brackets, and nothing else', () => {
    expect(evalSum('12')).toBe(12)
    expect(evalSum(' 1.2 * 2 ')).toBeCloseTo(2.4)
    expect(evalSum('(10+2)/4')).toBe(3)
    expect(evalSum('10÷4')).toBe(2.5)
    expect(evalSum('3×2-1')).toBe(5)
    expect(evalSum('-5+-2')).toBe(-7)
    expect(evalSum('.5+1.')).toBe(1.5)
    for (const bad of ['', 'abc', '1/0', '2(3', '(1', '1+', 'alert(1)', '2**3']) expect(evalSum(bad)).toBeNull()
  })
})

describe('colours', () => {
  it('reads what a person types, and keeps a colour through the picker', () => {
    expect(readColour('#ABC')).toBe('#aabbcc')
    expect(readColour('ff8800')).toBe('#ff8800')
    expect(readColour('#11223380')).toBe('#11223380')
    expect(readColour('rgb(255, 0, 0)')).toBe('#ff0000')
    expect(readColour('rgba(0,0,0,0.5)')).toBe('#00000080')
    expect(readColour('white')).toBe('#ffffff')
    expect(readColour('Accent')).toBe('accent')
    expect(readColour('blue-ish')).toBeNull()
    for (const c of ['#ff8800', '#10b981', '#000000', '#ffffff', '#3366cc80']) expect(hsvaToHex(hexToHsva(c))).toBe(c)
    expect(withAlpha('#ff8800', 0.5)).toBe('#ff880080')
    expect(withAlpha('accent', 0.5)).toBe('accent')
    expect(alphaOf('#00000040')).toBeCloseTo(0.25, 2)
    expect(alphaOf('#000000')).toBe(1)
  })
})

describe('what the panels add', () => {
  it('finds the picture or page in hand: a layer’s, a picture’s, a page; never a picture not chosen', () => {
    const d = story()
    expect(artOf(d, { kind: 'layer', story: S, block: 2, item: null, ids: ['w1'] })).toEqual(at(2))
    expect(artOf(d, { kind: 'block', story: S, block: 0 })).toEqual(at(0))
    expect(artOf(d, { kind: 'block', story: S, block: 3, item: 0 })).toEqual(at(3, 0))
    expect(artOf(d, { kind: 'block', story: S, block: 3, item: 1 })).toBeNull()  // no picture yet
    expect(artOf(d, { kind: 'block', story: S, block: 3 })).toBeNull()  // the group as a whole
    expect(artOf(d, { kind: 'block', story: S, block: 4 })).toEqual(at(4))
    expect(artOf(d, { kind: 'block', story: S, block: 1 })).toBeNull()
    expect(artOf(d, null)).toBeNull()
    expect(artRatio(d, at(2), ASSETS)).toBe(1.6)
    expect(artRatio(d, at(4), ASSETS)).toBe(0.75)
    const cropped = { ...d, blocks: d.blocks.map((b, i) => (i === 2 ? { ...b, crop: { x: 0, y: 0, w: 50, h: 100 } } : b)) }
    expect(artRatio(cropped, at(2), ASSETS)).toBe(0.8)
  })

  it('lays words light on a picture and dark on a light page, selected', () => {
    const d = story()
    const onPhoto = addText(d, S, at(2), 'heading')!
    const added = layers(onPhoto.doc, 2).at(-1) as TextLayer
    expect(added).toMatchObject({ kind: 'text', font: 'heading', color: '#ffffff' })
    expect(onPhoto.select).toEqual({ kind: 'layer', story: S, block: 2, item: null, ids: [added.id] })
    expect(layers(addText(d, S, at(4), 'body')!.doc, 4)[0]).toMatchObject({ color: '#111111' })
    const dark = { ...d, blocks: d.blocks.map((b, i) => (i === 4 && b.type === 'page' ? { ...b, design: { ...b.design, background: { kind: 'solid' as const, color: '#101010', angle: 180, stops: [] } } } : b)) }
    expect(layers(addText(dark, S, at(4), 'body')!.doc, 4)[0]).toMatchObject({ color: '#ffffff' })
  })

  it('makes a square look square on the artboard’s shape, and lays a picture at its own', () => {
    const d = story()
    const sq = layers(addShape(d, S, at(2), ASSETS, 'rect', true)!.doc, 2).at(-1)!
    expect(sq).toMatchObject({ kind: 'shape', w: 30, h: 48 })  // 30% of a 16:10 picture's width is 48% of its height
    const onPage = layers(addShape(d, S, at(4), ASSETS, 'ellipse', true)!.doc, 4)[0]
    expect(onPage).toMatchObject({ shape: 'ellipse', w: 30, h: 22.5 })
    const pic = layers(addImage(d, S, at(4), ASSETS, ASSET)!.doc, 4)[0]
    expect(pic).toMatchObject({ kind: 'image', asset_id: 'a-1', name: 'Harbour', w: 40, h: 18.8 })
  })

  it('adds a block after the one in hand, never before the cover, and stops at a full story', () => {
    const d = story()
    const quote = addBlock(d, S, { kind: 'block', story: S, block: 1 }, newBlock('quote'))!
    expect(quote.doc.blocks.map((b) => b.type)).toEqual(['cover', 'text', 'quote', 'photo', 'photos', 'page'])
    expect(quote.select).toEqual({ kind: 'block', story: S, block: 2 })
    // A layer's block counts as in hand; nothing in hand adds at the end.
    expect(addBlock(d, S, { kind: 'layer', story: S, block: 2, item: null, ids: ['w1'] }, newBlock('divider'))!.select).toEqual({ kind: 'block', story: S, block: 3 })
    expect(addBlock(d, S, null, newBlock('divider'))!.doc.blocks.at(-1)!.type).toBe('divider')
    const noCover = { ...d, blocks: d.blocks.slice(1) }
    expect(addBlock(noCover, S, null, newBlock('cover'))!.select).toEqual({ kind: 'block', story: S, block: 0 })
    expect(addBlock(d, S, null, newBlock('cover'))).toBeNull()  // one cover a story
    const full = { ...d, blocks: Array.from({ length: 120 }, () => newBlock('divider')) }
    expect(addBlock(full, S, null, newBlock('text'))).toBeNull()
    const page = addPage(d, S, { kind: 'block', story: S, block: 0 }, '2:3')!
    expect(page.doc.blocks[1]).toMatchObject({ type: 'page', aspect: '2:3' })
  })
})

describe('commands on layers', () => {
  const sel = (ids: string[], block = 2): FrameTarget => ({ kind: 'layer', story: S, block, item: null, ids })

  it('copies, pastes (offset on the same picture, in place on another) and cuts', () => {
    const d = story()
    const clip: Clipboard = { layers: [], from: '' }
    expect(command(d, S, sel(['w1']), 'copy', clip)).toBeNull()
    expect(clip.layers.map((l) => l.id)).toEqual(['w1'])
    const pasted = command(d, S, sel(['w1']), 'paste', clip)!
    const copy = layers(pasted.doc, 2).at(-1)!
    expect(copy.id).not.toBe('w1')
    expect(copy.x).toBe((findLayer(designOf(d.blocks[2], null), 'w1')!.x) + 2)
    // On the page (the page itself selected): pasted where it was.
    const elsewhere = command(d, S, { kind: 'block', story: S, block: 4 }, 'paste', clip)!
    expect(layers(elsewhere.doc, 4)[0]).toMatchObject({ x: findLayer(designOf(d.blocks[2], null), 'w1')!.x })
    expect(elsewhere.select).toMatchObject({ kind: 'layer', block: 4 })
    const cut = command(d, S, sel(['s1']), 'cut', clip)!
    expect(layers(cut.doc, 2).map((l) => l.id)).toEqual(['w1'])
    expect(cut.select).toEqual({ kind: 'block', story: S, block: 2 })
    expect(clip.layers.map((l) => l.id)).toEqual(['s1'])
    // A text block can take nothing.
    expect(command(d, S, { kind: 'block', story: S, block: 1 }, 'paste', clip)).toBeNull()
    expect(command(d, S, null, 'delete', clip)).toBeNull()
  })

  it('duplicates, groups and ungroups, stacks and deletes', () => {
    const d = story()
    const clip: Clipboard = { layers: [], from: '' }
    const dup = command(d, S, sel(['w1']), 'duplicate', clip)!
    expect(layers(dup.doc, 2)).toHaveLength(3)
    const grouped = command(d, S, sel(['w1', 's1']), 'group', clip)!
    const g = layers(grouped.doc, 2)
    expect(g).toHaveLength(1)
    expect(g[0].kind).toBe('group')
    expect(grouped.select).toEqual(sel([g[0].id]))
    expect(command(d, S, sel(['w1']), 'group', clip)).toBeNull()  // one layer is no group
    const apart = command(grouped.doc, S, sel([g[0].id]), 'ungroup', clip)!
    expect(layers(apart.doc, 2).map((l) => l.id)).toEqual(['w1', 's1'])
    const front = command(d, S, sel(['w1']), 'front', clip)!
    expect(layers(front.doc, 2).map((l) => l.id)).toEqual(['s1', 'w1'])
    const gone = command(d, S, sel(['w1', 's1']), 'delete', clip)!
    expect(designOf(gone.doc.blocks[2], null)).toBeNull()  // an emptied design is kept as none
  })

  it('reads the keys pressed in the panels as the page does', () => {
    const k = (key: string, mods: Partial<{ metaKey: boolean; ctrlKey: boolean; shiftKey: boolean; altKey: boolean; code: string }> = {}) =>
      panelKey({ key, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, ...mods })
    expect(k('Delete')).toBe('delete')
    expect(k('Backspace')).toBe('delete')
    expect(k('c', { metaKey: true })).toBe('copy')
    expect(k('x', { ctrlKey: true })).toBe('cut')
    expect(k('v', { metaKey: true })).toBe('paste')
    expect(k('d', { metaKey: true })).toBe('duplicate')
    expect(k('g', { metaKey: true })).toBe('group')
    expect(k('G', { metaKey: true, shiftKey: true })).toBe('ungroup')
    expect(k(']', { metaKey: true })).toBe('forward')
    expect(k('‘', { metaKey: true, altKey: true, code: 'BracketRight' })).toBe('front')
    expect(k('[', { metaKey: true })).toBe('backward')
    expect(k('“', { metaKey: true, altKey: true, code: 'BracketLeft' })).toBe('back')
    expect(k('a')).toBeNull()
    expect(k('s', { metaKey: true })).toBeNull()
  })
})

describe('drawing a change on the page at once', () => {
  it('sends each design that changed, with its pictures and faces', () => {
    const d = story()
    const withPic = addImage(d, S, at(2), ASSETS, ASSET)!.doc
    const typed = { ...withPic, blocks: withPic.blocks.map((b, i) => (i === 2 && b.type === 'photo'
      ? { ...b, design: { layers: b.design!.layers.map((l) => (l.kind === 'text' ? { ...l, font: 'Playfair Display', weight: 900 } : l)) } } : b)) }
    const msgs = designMessages(d, typed, S, ASSETS)
    expect(msgs).toHaveLength(1)
    expect(msgs[0]).toMatchObject({ type: 'mz-design', story: S, block: 2, item: null, path: 'design' })
    expect(Object.keys(msgs[0].assets as object)).toEqual(['a-1'])
    expect(msgs[0].fonts).toEqual(['https://fonts.googleapis.com/css2?family=Playfair%20Display:ital,wght@0,400;0,700;0,900&display=swap'])
    // A group's picture by its item; nothing that didn't change; nothing when blocks moved.
    const item = addText(d, S, at(3, 0), 'body')!.doc
    expect(designMessages(d, item, S, ASSETS)).toEqual([expect.objectContaining({ block: 3, item: 0, path: 'items.0.design' })])
    expect(designMessages(d, { ...d, fields: { ...d.fields, title: 'x' } }, S, ASSETS)).toEqual([])
    expect(designMessages(d, { ...d, blocks: d.blocks.slice(1) }, S, ASSETS)).toEqual([])
    expect(designMessages(null, d, S, ASSETS)).toEqual([])
    // The magazine's own faces are on the page already.
    expect(designFontHrefs({ layers: [words('a')] })).toEqual([])
    expect(designAssets({ layers: [{ ...words('a') }] }, ASSETS)).toEqual({})
  })
})

/** The inspector over a design kept in state, as the editor keeps it. */
function Inspect({ start, ids, onCommand = vi.fn(), onReplace = vi.fn(), seen }: {
  start: Design; ids: string[]; onCommand?: (k: string) => void; onReplace?: (id: string) => void; seen: { design: Design }
}) {
  const [d, setD] = useState(start)
  useEffect(() => { Object.assign(seen, { design: d }) }, [d, seen])
  return <LayerInspector design={d} ids={ids} accent="#e11d48" onChange={(fn) => setD((x) => fn(x))} onCommand={onCommand} onReplacePicture={onReplace} />
}

describe('LayerInspector', () => {
  it('places, types and styles one layer of words', () => {
    const seen = { design: { layers: [] } as Design }
    render(<Inspect start={{ layers: [words('w1')] }} ids={['w1']} seen={seen} />)
    const w = () => seen.design.layers[0] as TextLayer
    const set = (label: string, value: string) => {
      const box = screen.getByLabelText(label)
      fireEvent.change(box, { target: { value } })
      fireEvent.blur(box)
    }
    set("X, percent of the picture's width", '10+5')
    set('Width', '500')
    expect(w()).toMatchObject({ x: 15, w: 400 })
    set('Turn', '-90')
    expect(w().rot).toBe(-90)
    // A box that grows with its words has no height to set until it is fixed.
    fireEvent.click(screen.getByRole('button', { name: 'H: grows' }))
    expect(w()).toMatchObject({ autosize: 'none', h: 10 })
    set('Height', '22')
    expect(w().h).toBe(22)
    fireEvent.click(screen.getByRole('button', { name: 'Middle' }))
    expect(w().valign).toBe('middle')

    fireEvent.change(screen.getByLabelText('Weight'), { target: { value: '700' } })
    expect(w().weight).toBe(700)
    set("Size, percent of the picture's width", '6')
    expect(w().size).toBe(6)
    fireEvent.click(screen.getByRole('button', { name: 'AA' }))
    expect(w().case).toBe('upper')
    fireEvent.click(screen.getByRole('button', { name: 'Flip across' }))
    expect(w().flip_x).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Lock' }))
    expect(w().locked).toBe(true)
    fireEvent.change(screen.getByRole('textbox', { name: 'Layer name' }), { target: { value: 'Headline' } })
    expect(w().name).toBe('Headline')

    fireEvent.click(screen.getByRole('button', { name: 'Add a shadow' }))
    expect(w().shadows).toHaveLength(1)
    set('Shadow blur', '4')
    expect(w().shadows[0].blur).toBe(4)
    fireEvent.click(screen.getByRole('button', { name: 'Remove this shadow' }))
    expect(w().shadows).toEqual([])
    set('Corner radius', '3')
    expect(w().radius).toEqual([3, 3, 3, 3])
    fireEvent.change(screen.getByLabelText('Blend'), { target: { value: 'multiply' } })
    expect(w().blend).toBe('multiply')
    fireEvent.change(screen.getByLabelText('Where a reader goes when they tap this'), { target: { value: 'example.com' } })
    expect(screen.getByText('A link starts with https:// or mailto:')).toBeInTheDocument()
  })

  it('lines several layers up and sends the rest to the page’s commands', () => {
    const seen = { design: { layers: [] } as Design }
    const onCommand = vi.fn()
    const three = { layers: [{ ...words('a'), x: 10 }, { ...shape('b'), x: 40 }, { ...shape('c'), x: 70 }] }
    render(<Inspect start={three} ids={['a', 'b', 'c']} onCommand={onCommand} seen={seen} />)
    expect(screen.getByText('3 layers')).toBeInTheDocument()
    expect(screen.queryByLabelText('Width')).toBeNull()  // positions are one layer's
    fireEvent.click(screen.getByRole('button', { name: 'Align left' }))
    expect(seen.design.layers.map((l) => l.x)).toEqual([10, 10, 10])
    fireEvent.click(screen.getByRole('button', { name: 'Space evenly across' }))
    fireEvent.click(screen.getByRole('button', { name: 'Group (⌘G)' }))
    expect(onCommand).toHaveBeenCalledWith('group')
    fireEvent.click(screen.getByRole('button', { name: 'Bring to front (⌥⌘])' }))
    expect(onCommand).toHaveBeenLastCalledWith('front')
  })

  it('changes nothing for a number left as it was', () => {
    const seen = { design: { layers: [] } as Design }
    render(<Inspect start={{ layers: [words('w1')] }} ids={['w1']} seen={seen} />)
    const before = seen.design
    for (const label of ["X, percent of the picture's width", 'Width', 'Turn']) {
      const box = screen.getByLabelText(label)
      fireEvent.focus(box)
      fireEvent.blur(box)
    }
    // The same number typed again is no change either.
    const x = screen.getByLabelText("X, percent of the picture's width")
    fireEvent.change(x, { target: { value: String((before.layers[0] as TextLayer).x) } })
    fireEvent.keyDown(x, { key: 'Enter' })
    expect(seen.design).toBe(before)
  })

  it('keeps a gradient stop where it is dragged or typed, still selected', () => {
    const seen = { design: { layers: [] } as Design }
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 100, 20))
    HTMLElement.prototype.setPointerCapture ??= () => {}
    render(<Inspect start={{ layers: [shape('s1')] }} ids={['s1']} seen={seen} />)
    fireEvent.click(screen.getByRole('button', { name: 'Linear' }))
    const stops = () => (seen.design.layers[0] as Extract<Layer, { kind: 'shape' }>).fill.stops.map((x) => x.at)
    expect(stops()).toEqual([0, 100])
    const drag = (name: string, to: number) => {
      const knob = screen.getByRole('button', { name })
      fireEvent.pointerDown(knob, { pointerId: 1 })
      act(() => { knob.dispatchEvent(new MouseEvent('pointermove', { clientX: to })) })
      act(() => { knob.dispatchEvent(new MouseEvent('pointerup')) })
    }
    drag('Stop at 0%', 40)
    expect(stops()).toEqual([40, 100])  // where it was let go
    drag('Stop at 100%', 20)
    expect(stops()).toEqual([20, 40])
    expect(screen.getByLabelText('Stop position')).toHaveValue('20')  // the one dragged
    const pos = screen.getByLabelText('Stop position')
    fireEvent.change(pos, { target: { value: '60' } })
    fireEvent.blur(pos)
    expect(stops()).toEqual([40, 60])
    expect(screen.getByLabelText('Stop position')).toHaveValue('60')  // still the one moved
  })

  it('replaces, fits and colours a picture laid on another', () => {
    const seen = { design: { layers: [] } as Design }
    const onReplace = vi.fn()
    const pic = layers(addImage(story(), S, at(4), ASSETS, ASSET)!.doc, 4)[0]
    render(<Inspect start={{ layers: [pic] }} ids={[pic.id]} onReplace={onReplace} seen={seen} />)
    fireEvent.click(screen.getByRole('button', { name: 'Replace picture…' }))
    expect(onReplace).toHaveBeenCalledWith(pic.id)
    fireEvent.change(screen.getByLabelText('Fit'), { target: { value: 'contain' } })
    fireEvent.change(within(screen.getByRole('region', { name: 'Picture' })).getByLabelText('Colour'), { target: { value: 'bw' } })
    expect(seen.design.layers[0]).toMatchObject({ fit: 'contain', filter: 'bw' })
    expect(screen.queryByRole('region', { name: 'Fill' })).toBeNull()  // a picture has no fill
  })
})

describe('LayersPanel', () => {
  it('lists blocks and their layers topmost first, and selects, hides, renames and stacks them', () => {
    const d = story()
    const onSelect = vi.fn(), onToggle = vi.fn(), onRename = vi.fn(), onMoveLayer = vi.fn(), onMoveBlock = vi.fn()
    render(<LayersPanel blocks={d.blocks} target={{ kind: 'layer', story: S, block: 2, item: null, ids: ['w1'] }} story={S} assets={ASSETS}
      onSelect={onSelect} onToggle={onToggle} onRename={onRename} onMoveLayer={onMoveLayer} onMoveBlock={onMoveBlock} />)
    const tree = screen.getByRole('tree', { name: 'The story’s layers' })
    const items = within(tree).getAllByRole('treeitem').map((li) => li.firstElementChild!.textContent)
    expect(items).toEqual(['Cover', 'Text', 'Photo', 'Rectangle', 'Add a little bit of body text', 'Photo group', 'Designed page'])
    expect(within(tree).getAllByRole('treeitem', { selected: true }).map((li) => li.firstElementChild!.textContent)).toEqual(['Add a little bit of body text'])

    fireEvent.click(screen.getByText('Rectangle'), { shiftKey: true })
    expect(onSelect).toHaveBeenLastCalledWith({ kind: 'layer', story: S, block: 2, item: null, ids: ['w1', 's1'] })
    fireEvent.click(screen.getByText('Photo group'))
    expect(onSelect).toHaveBeenLastCalledWith({ kind: 'block', story: S, block: 3 })
    fireEvent.click(screen.getByText('Picture 1'))
    expect(onSelect).toHaveBeenLastCalledWith({ kind: 'block', story: S, block: 3, item: 0 })

    fireEvent.click(screen.getAllByRole('button', { name: 'Hide' })[0])
    expect(onToggle).toHaveBeenLastCalledWith(at(2), 's1', 'hidden')
    fireEvent.click(screen.getAllByRole('button', { name: 'Lock' })[1])
    expect(onToggle).toHaveBeenLastCalledWith(at(2), 'w1', 'locked')
    fireEvent.doubleClick(screen.getByText('Rectangle'))
    const name = screen.getByRole('textbox', { name: 'Layer name' })
    fireEvent.change(name, { target: { value: '  Sky band  ' } })
    fireEvent.keyDown(name, { key: 'Enter' })
    expect(onRename).toHaveBeenLastCalledWith(at(2), 's1', 'Sky band')

    // Dragging the words above the rectangle (in front of it).
    const row = (text: string) => screen.getByText(text).parentElement!
    const dataTransfer = { effectAllowed: '' }
    fireEvent.dragStart(row('Add a little bit of body text'), { dataTransfer })
    const rect = row('Rectangle')
    rect.getBoundingClientRect = () => ({ top: 0, height: 28, bottom: 28, left: 0, right: 200, width: 200, x: 0, y: 0, toJSON: () => ({}) })
    // (jsdom's drag events carry no pointer position: set it.)
    const over = createEvent.dragOver(rect, { dataTransfer })
    Object.defineProperty(over, 'clientY', { value: 3 })
    fireEvent(rect, over)
    fireEvent.drop(rect, { dataTransfer })
    expect(onMoveLayer).toHaveBeenLastCalledWith(at(2), 'w1', 's1', 'above')
    // A layer can't be dropped among the blocks, nor a block on the cover.
    fireEvent.dragStart(row('Designed page'), { dataTransfer })
    fireEvent.drop(row('Cover'), { dataTransfer })
    expect(onMoveBlock).not.toHaveBeenCalled()
    fireEvent.dragOver(row('Text'), { dataTransfer })
    fireEvent.drop(row('Text'), { dataTransfer })
    expect(onMoveBlock).toHaveBeenLastCalledWith(4, 1)
  })
})

describe('ArtInspector', () => {
  const handlers = (): ArtHandlers => ({
    onText: vi.fn(), onShape: vi.fn(), onImage: vi.fn(), onSelectLayers: vi.fn(), onToggle: vi.fn(), onRename: vi.fn(), onMoveLayer: vi.fn(),
  })
  const props = (h: ArtHandlers, onBlock = vi.fn()) => ({
    assets: ASSETS, accent: '#e11d48', handlers: h, onBlock, onMove: vi.fn(), onDuplicate: vi.fn(), onRemove: vi.fn(),
    onPickAsset: vi.fn(), onClose: vi.fn(), onWhole: vi.fn(),
  })

  it('adds to a page, lists what is on it, and sets its shape and background', () => {
    const h = handlers(), onBlock = vi.fn()
    const d = addText(story(), S, at(4), 'heading')!.doc
    render(<ArtInspector blocks={d.blocks} art={at(4)} {...props(h, onBlock)} />)
    expect(screen.getByRole('heading', { name: 'Designed page' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add subheading' }))
    expect(h.onText).toHaveBeenCalledWith('subheading')
    fireEvent.click(screen.getByRole('button', { name: 'Add a circle' }))
    expect(h.onShape).toHaveBeenCalledWith('ellipse', true)
    fireEvent.click(screen.getByRole('button', { name: /Lay a picture on this page/ }))
    expect(h.onImage).toHaveBeenCalled()
    fireEvent.click(screen.getByText('Add a heading'))
    expect(h.onSelectLayers).toHaveBeenCalledWith([layers(d, 4)[0].id], false)
    fireEvent.click(screen.getByRole('button', { name: '1:1' }))
    expect(onBlock.mock.lastCall![0]).toMatchObject({ type: 'page', aspect: '1:1' })
    fireEvent.click(screen.getByRole('button', { name: 'Linear' }))
    expect(onBlock.mock.lastCall![0].design.background).toMatchObject({ kind: 'linear' })
    expect(onBlock.mock.lastCall![0].design.layers).toHaveLength(1)  // its layers kept
  })

  it('waits for a picture before laying anything on it; a group’s picture leads back to the group', () => {
    const h = handlers()
    const p = props(h)
    const { rerender } = render(<ArtInspector blocks={story().blocks} art={at(3, 1)} {...p} />)
    expect(screen.getByRole('heading', { name: 'Picture 2 of the group' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add heading' })).toBeDisabled()
    expect(screen.getByText(/Choose the picture first/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'The whole photo group' }))
    expect(p.onWhole).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Remove this picture' }))
    expect(p.onBlock.mock.lastCall![0].items).toHaveLength(1)
    rerender(<ArtInspector blocks={story().blocks} art={at(0)} {...p} />)
    expect(screen.getByRole('button', { name: 'Add heading' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Move up' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Duplicate block' })).toBeNull()  // one cover a story
  })
})
