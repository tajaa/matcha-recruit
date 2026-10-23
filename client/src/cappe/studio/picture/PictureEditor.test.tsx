import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Asset } from '../model/types'
import PictureEditor from './PictureEditor'

// The GPU and the model are faked: what's drawn is recorded, and the model
// answers each click with a mask.
const h = vi.hoisted(() => ({
  draws: [] as { recipe: Record<string, unknown>; opts: Record<string, unknown> }[],
  masks: [] as (Uint8Array | null)[],
  pixels: ((): Promise<Blob> => Promise.reject(new Error('unset'))) as (...a: unknown[]) => Promise<Blob>,
  saveEdit: ((): Promise<unknown> => Promise.reject(new Error('unset'))) as (...a: unknown[]) => Promise<unknown>,
  load: ((): Promise<void> => Promise.resolve()) as (...a: unknown[]) => Promise<void>,
  maskFails: false,
  calls: { pixels: [] as unknown[][], saveEdit: [] as unknown[][], mask: [] as unknown[][], load: 0, encode: 0 },
}))

vi.mock('./gl', () => ({
  PictureGL: class {
    maxSize = 8192
    setSource() {}
    setMask(alpha: Uint8Array | null) { h.masks.push(alpha) }
    // The stage passes options; the looks' thumbnails and the full-size bake don't.
    draw(recipe: Record<string, unknown>, _w: number, _h: number, opts?: Record<string, unknown>) { if (opts) h.draws.push({ recipe, opts }) }
    dispose() {}
  },
}))
vi.mock('./segment', () => ({
  WorkerSegmenter: class {
    load(p: unknown) { h.calls.load++; return h.load(p) }
    encode() { h.calls.encode++; return Promise.resolve() }
    // Each mask's size says how many clicks it was made from.
    mask(points: unknown[]) {
      h.calls.mask.push([points])
      if (h.maskFails) return Promise.reject(new Error('The model lost its place.'))
      return Promise.resolve({ alpha: new Uint8Array(4 * points.length), width: 2, height: 2 * points.length, score: 0.97 })
    }
    dispose() {}
  },
}))
vi.mock('../api', () => ({
  studioApi: {
    pixels: (...a: unknown[]) => { h.calls.pixels.push(a); return h.pixels(...a) },
    saveEdit: (...a: unknown[]) => { h.calls.saveEdit.push(a); return h.saveEdit(...a) },
  },
}))

const ASSET: Asset = { id: 'a1', url: 'https://cdn.example.test/a.jpg', credit_line: 'Haley', alt: 'The tower' }
const SAVED = { id: 'e1', kind: 'edit', url: 'https://cdn.example.test/e.jpg' }
const lastDraw = () => h.draws[h.draws.length - 1]
const lastMask = () => h.masks[h.masks.length - 1]

beforeEach(() => {
  h.draws = []
  h.masks = []
  h.calls = { pixels: [], saveEdit: [], mask: [], load: 0, encode: 0 }
  h.pixels = () => Promise.resolve(new Blob(['x'], { type: 'image/jpeg' }))
  h.saveEdit = () => Promise.resolve(SAVED)
  h.load = () => Promise.resolve()
  h.maskFails = false
  vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 400, height: 300, close: () => {} })))
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  HTMLCanvasElement.prototype.toDataURL = () => 'data:image/jpeg;base64,AA'
  HTMLCanvasElement.prototype.toBlob = function (cb: BlobCallback, type?: string) { cb(new Blob(['y'], { type })) }
  Element.prototype.getBoundingClientRect = () => ({ left: 0, top: 0, width: 400, height: 300, right: 400, bottom: 300, x: 0, y: 0, toJSON: () => ({}) })
})

const open = (props: Partial<Parameters<typeof PictureEditor>[0]> = {}) => {
  const onDone = vi.fn(), onClose = vi.fn()
  render(<PictureEditor siteId="s1" asset={ASSET} onDone={onDone} onClose={onClose} {...props} />)
  return { onDone, onClose }
}
const ready = () => waitFor(() => expect(h.draws.length).toBeGreaterThan(0))

describe('the Picture Editor', () => {
  it('opens the picture from our origin, and saves nothing when nothing changed', async () => {
    const { onClose } = open()
    await ready()
    expect(h.calls.pixels).toEqual([['s1', 'a1']])
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(onClose).toHaveBeenCalled()
    expect(h.calls.saveEdit).toEqual([])
  })

  it('draws a look and the sliders, and Done saves them as a new picture', async () => {
    const { onDone } = open()
    await ready()
    fireEvent.click(screen.getByRole('button', { name: /Noir/ }))
    expect(lastDraw().recipe).toMatchObject({ look: 'noir', bw: true, contrast: 45 })
    fireEvent.change(screen.getByRole('slider', { name: 'Exposure' }), { target: { value: '0.5' } })
    expect(lastDraw().recipe).toMatchObject({ look: 'noir', exposure: 0.5 })
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(onDone).toHaveBeenCalledWith(SAVED))
    const [site, id, blob, recipe] = h.calls.saveEdit[0] as [string, string, Blob, unknown]
    expect([site, id, blob.type]).toEqual(['s1', 'a1', 'image/jpeg'])
    expect(recipe).toEqual({ look: 'noir', exposure: 0.5, contrast: 45, blacks: -30, vignette: -35, grain: 25, bw: true })
  })

  it('holds Before to show the picture as it was, and undoes and redoes', async () => {
    open()
    await ready()
    fireEvent.change(screen.getByRole('slider', { name: 'Contrast' }), { target: { value: '30' } })
    const before = screen.getByRole('button', { name: 'Before' })
    fireEvent.pointerDown(before)
    expect(lastDraw().opts.before).toBe(true)
    fireEvent.pointerUp(before)
    fireEvent.keyDown(window, { key: 'z', metaKey: true })
    expect(lastDraw().recipe).toEqual({})
    fireEvent.keyDown(window, { key: 'z', metaKey: true, shiftKey: true })
    expect(lastDraw().recipe).toEqual({ contrast: 30 })
  })

  it('edits an edited picture again from its source, with its recipe', async () => {
    open({ asset: { ...ASSET, id: 'e0', kind: 'edit', parent: 'a1', recipe: { exposure: 1, look: 'warm' } } })
    await ready()
    expect(h.calls.pixels).toEqual([['s1', 'a1']])
    expect((screen.getByRole('slider', { name: 'Exposure' }) as HTMLInputElement).value).toBe('1')
    fireEvent.change(screen.getByRole('slider', { name: 'Tint' }), { target: { value: '10' } })
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(h.calls.saveEdit).toHaveLength(1))
    expect(h.calls.saveEdit[0].slice(0, 2)).toEqual(['s1', 'a1'])
  })

  it('edits the picture as it is when its source has left the library', async () => {
    h.pixels = (_s: unknown, id: unknown) => (id === 'a1' ? Promise.reject(new Error('gone')) : Promise.resolve(new Blob(['x'], { type: 'image/png' })))
    open({ asset: { ...ASSET, id: 'e0', kind: 'edit', parent: 'a1', recipe: { exposure: 1 } } })
    await ready()
    expect(h.calls.pixels.map((c) => c[1])).toEqual(['a1', 'e0'])
    expect(lastDraw().recipe).toEqual({})
  })

  it('crops to a shape, turns and flips', async () => {
    open()
    await ready()
    fireEvent.click(screen.getByRole('tab', { name: 'Crop' }))
    expect(lastDraw().opts.uncropped).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: '1:1' }))
    // 400 × 300: the largest square is 300 wide, centred.
    expect(lastDraw().recipe).toMatchObject({ crop: { x: 0.125, y: 0, w: 0.75, h: 1 } })
    fireEvent.click(screen.getByRole('button', { name: 'Turn right' }))
    expect(lastDraw().recipe).toMatchObject({ crop: { turn: 90, w: 1, h: 1 } })
    fireEvent.click(screen.getByRole('button', { name: 'Flip across' }))
    expect(lastDraw().recipe).toMatchObject({ crop: { turn: 90, flip_h: true } })
  })

  it('cuts out what is clicked, and saves it with its transparency', async () => {
    const { onDone } = open()
    await ready()
    fireEvent.click(screen.getByRole('tab', { name: 'Cut out' }))
    expect(await screen.findByText('Click what to keep.')).toBeInTheDocument()
    expect([h.calls.load, h.calls.encode]).toEqual([1, 1])
    const target = document.querySelector('[data-cutout-target]')!
    await act(async () => { fireEvent.pointerDown(target, { clientX: 200, clientY: 150 }) })
    expect(h.calls.mask).toEqual([[[{ x: 0.5, y: 0.5, keep: true }]]])
    await waitFor(() => expect(h.masks.some((m) => m && m.length === 4)).toBe(true))
    await act(async () => { fireEvent.pointerDown(target, { clientX: 40, clientY: 30, altKey: true }) })
    expect(h.calls.mask[1]).toEqual([[{ x: 0.5, y: 0.5, keep: true }, { x: 0.1, y: 0.1, keep: false }]])
    await waitFor(() => expect(lastMask()?.length).toBe(8))
    // Undo brings back the first click's mask without asking the model again;
    // Reset all clears it, and undoing that brings it back too.
    fireEvent.keyDown(window, { key: 'z', metaKey: true })
    await waitFor(() => expect(lastMask()?.length).toBe(4))
    fireEvent.keyDown(window, { key: 'z', metaKey: true, shiftKey: true })
    await waitFor(() => expect(lastMask()?.length).toBe(8))
    fireEvent.click(screen.getByRole('button', { name: 'Reset all' }))
    await waitFor(() => expect(lastMask()).toBeNull())
    fireEvent.keyDown(window, { key: 'z', metaKey: true })
    await waitFor(() => expect(lastMask()?.length).toBe(8))
    expect(h.calls.mask).toHaveLength(2)
    fireEvent.change(screen.getByRole('slider', { name: 'Feather' }), { target: { value: '20' } })
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    const [, , blob, recipe] = h.calls.saveEdit[0] as [string, string, Blob, { cutout: unknown }]
    expect(blob.type).toBe('image/png')
    expect(recipe.cutout).toEqual({ points: [{ x: 0.5, y: 0.5, keep: true }, { x: 0.1, y: 0.1, keep: false }], feather: 20, invert: false })
  })

  it('says when a click couldn’t be cut out, and won’t save without its mask', async () => {
    h.maskFails = true
    open({ startIn: 'cutout' })
    await screen.findByText('Click what to keep.')
    const target = document.querySelector('[data-cutout-target]')!
    await act(async () => { fireEvent.pointerDown(target, { clientX: 200, clientY: 150 }) })
    expect(await screen.findByRole('alert')).toHaveTextContent('lost its place')
    expect(screen.queryByText('Cutting out…')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(await screen.findByText(/didn’t work on those clicks/)).toBeInTheDocument()
    expect(h.calls.saveEdit).toEqual([])
    // Another click is another try.
    h.maskFails = false
    await act(async () => { fireEvent.pointerDown(target, { clientX: 100, clientY: 150 }) })
    await waitFor(() => expect(lastMask()?.length).toBe(8))
    expect(screen.queryByText('lost its place')).toBeNull()
  })

  it('says when the cut-out model can’t be had, and tries again', async () => {
    h.load = () => Promise.reject(new Error('The cut-out model isn’t on this server yet.'))
    open({ startIn: 'cutout' })
    expect(await screen.findByRole('alert')).toHaveTextContent('isn’t on this server yet')
    h.load = () => Promise.resolve()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Click what to keep.')).toBeInTheDocument()
  })

  it('says when the edit couldn’t be saved, and stays open', async () => {
    h.saveEdit = () => Promise.reject(new Error('This isn’t that picture edited.'))
    const { onDone } = open()
    await ready()
    fireEvent.change(screen.getByRole('slider', { name: 'Vibrance' }), { target: { value: '25' } })
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('isn’t that picture edited')
    expect(onDone).not.toHaveBeenCalled()
  })

  it('closes with Esc', async () => {
    const { onClose } = open()
    await ready()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})
