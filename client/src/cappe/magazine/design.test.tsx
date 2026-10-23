import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import CropTool from './editor/CropTool'
import BlockOptions from './editor/BlockOptions'
import { cropBetween, newBlock } from './editor/blocks'
import type { CappeAsset, StoryBlock } from '../types'

type Photo = Extract<StoryBlock, { type: 'photo' }>
type Text = Extract<StoryBlock, { type: 'text' }>

const ASSET = {
  id: 'a-1', kind: 'upload', url: 'https://cdn.example.test/a.jpg', alt: 'Tower', width: 2000, height: 1000,
  credit_line: 'Photo: Ana', variants: { webp: [{ w: 480, url: 'https://cdn.example.test/a-480.webp' }, { w: 960, url: 'https://cdn.example.test/a-960.webp' }] },
} as unknown as CappeAsset

const photo = (over: Partial<Photo> = {}): Photo => ({ ...(newBlock('photo') as Photo), asset_id: 'a-1', ...over })

// jsdom lays nothing out: give the picture a 400×200 box at the origin.
function box(el: Element) {
  el.getBoundingClientRect = () => ({ left: 0, top: 0, width: 400, height: 200, right: 400, bottom: 200, x: 0, y: 0, toJSON: () => ({}) })
}

describe('cropBetween', () => {
  it('is the rectangle between two points, if it is big enough', () => {
    expect(cropBetween({ x: 60, y: 80 }, { x: 10, y: 20 })).toEqual({ x: 10, y: 20, w: 50, h: 60 })
    expect(cropBetween({ x: 10, y: 10 }, { x: 13, y: 60 })).toBeNull()
  })
})

describe('CropTool', () => {
  it('crops by dragging across the picture, and goes back to the whole picture', () => {
    const onChange = vi.fn()
    const { rerender } = render(<CropTool block={photo()} asset={ASSET} onChange={onChange} />)
    expect(screen.queryByTestId('crop-area')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Crop' }))
    const area = screen.getByTestId('crop-area')
    expect(area.querySelector('img')).toHaveAttribute('src', 'https://cdn.example.test/a-960.webp')
    box(area)
    fireEvent.pointerDown(area, { clientX: 100, clientY: 20 })
    fireEvent.pointerMove(area, { clientX: 300, clientY: 180 })
    fireEvent.pointerUp(area)
    const cropped = onChange.mock.lastCall![0] as Photo
    expect(cropped.crop).toEqual({ x: 25, y: 10, w: 50, h: 80 })
    // Done: the tool closes once a crop is made.
    expect(screen.queryByTestId('crop-area')).toBeNull()

    rerender(<CropTool block={cropped} asset={ASSET} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'The whole picture' }))
    expect((onChange.mock.lastCall![0] as Photo).crop).toBeNull()
  })

  it('ignores a drag too small to be a crop', () => {
    const onChange = vi.fn()
    render(<CropTool block={photo()} asset={ASSET} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'Crop' }))
    const area = screen.getByTestId('crop-area')
    box(area)
    fireEvent.pointerDown(area, { clientX: 10, clientY: 10 })
    fireEvent.pointerUp(area)
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByTestId('crop-area')).toBeInTheDocument()
  })

  it('sets the border, shape and colour; a circle can’t be cropped', () => {
    const onChange = vi.fn()
    const { rerender } = render(<CropTool block={photo()} asset={ASSET} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Border'), { target: { value: 'mat' } })
    expect((onChange.mock.lastCall![0] as Photo).border).toBe('mat')
    fireEvent.change(screen.getByLabelText('Colour'), { target: { value: 'bw' } })
    expect((onChange.mock.lastCall![0] as Photo).filter).toBe('bw')
    fireEvent.change(screen.getByLabelText('Shape'), { target: { value: 'arch' } })
    expect((onChange.mock.lastCall![0] as Photo).shape).toBe('arch')
    rerender(<CropTool block={photo({ shape: 'circle' })} asset={ASSET} onChange={onChange} />)
    expect(screen.getByRole('button', { name: 'Crop' })).toBeDisabled()
  })
})

describe('BlockOptions — text', () => {
  it('chooses the style, alignment and drop cap (a book page is already a column)', () => {
    const onChange = vi.fn()
    render(<BlockOptions block={newBlock('text')} assets={new Map()} onChange={onChange} onPickAsset={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Style'), { target: { value: 'statement' } })
    expect(onChange.mock.lastCall![0]).toMatchObject({ variant: 'statement' })
    expect(screen.queryByLabelText('Columns')).toBeNull()
    fireEvent.click(within(screen.getByRole('group', { name: 'Align' })).getByRole('button', { name: 'Justified' }))
    expect(onChange.mock.lastCall![0]).toMatchObject({ align: 'justify' })
    fireEvent.click(screen.getByLabelText('Drop cap'))
    expect(onChange.mock.lastCall![0]).toMatchObject({ dropcap: true })
  })

  it('sets its own type, each following the magazine until set', () => {
    const onChange = vi.fn()
    const { rerender } = render(<BlockOptions block={newBlock('text')} assets={new Map()} onChange={onChange} onPickAsset={vi.fn()} />)
    // The magazine's body face, the story's size, the page's ink and spacing.
    expect(screen.getByRole('button', { name: 'Font: Magazine body' })).toBeInTheDocument()
    expect(screen.getByLabelText('Line spacing')).toHaveValue('')
    expect(screen.getByLabelText('Line spacing')).toHaveAttribute('placeholder', 'Auto')
    expect(screen.getByRole('button', { name: 'Colour: Page ink' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Font: Magazine body' }))
    fireEvent.change(screen.getByLabelText('Search fonts'), { target: { value: 'Playfair' } })
    fireEvent.click(screen.getByRole('button', { name: /^Playfair Display/ }))
    expect(onChange.mock.lastCall![0]).toMatchObject({ font: 'Playfair Display' })

    const size = screen.getByLabelText('Size, times the story\'s')
    fireEvent.change(size, { target: { value: '1.2*2' } })
    fireEvent.blur(size)
    expect(onChange.mock.lastCall![0]).toMatchObject({ size: 2.4 })
    const lines = screen.getByLabelText('Line spacing')
    fireEvent.change(lines, { target: { value: '9' } })
    fireEvent.blur(lines)
    expect(onChange.mock.lastCall![0]).toMatchObject({ leading: 3 })  // held to what the server keeps

    rerender(<BlockOptions block={{ ...(newBlock('text') as Text), leading: 1.3, color: '#aa0000' }} assets={new Map()} onChange={onChange} onPickAsset={vi.fn()} />)
    expect(screen.getByLabelText('Line spacing')).toHaveValue('1.3')
    fireEvent.click(screen.getByRole('button', { name: 'Line spacing back to automatic' }))
    expect(onChange.mock.lastCall![0]).toMatchObject({ leading: 0 })
    fireEvent.click(screen.getByRole('button', { name: 'Colour: #aa0000' }))
    fireEvent.click(screen.getByRole('button', { name: 'Page ink' }))
    expect(onChange.mock.lastCall![0]).toMatchObject({ color: '' })
  })
})

describe('BlockOptions — pictures', () => {
  it('crops a photo once it has a picture', () => {
    const { rerender } = render(<BlockOptions block={photo({ asset_id: null })} assets={new Map([['a-1', ASSET]])} onChange={vi.fn()} onPickAsset={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Crop' })).toBeNull()
    rerender(<BlockOptions block={photo()} assets={new Map([['a-1', ASSET]])} onChange={vi.fn()} onPickAsset={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Crop' })).toBeInTheDocument()
  })

  it('chooses, takes out and adds a photo group’s pictures', () => {
    const onChange = vi.fn()
    const onPick = vi.fn()
    const group = newBlock('photos') as Extract<StoryBlock, { type: 'photos' }>
    render(<BlockOptions block={group} assets={new Map([['a-1', ASSET]])} onChange={onChange} onPickAsset={onPick} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose picture 2' }))
    onPick.mock.lastCall![0](ASSET)
    expect(onChange.mock.lastCall![0]).toMatchObject({ items: [{ asset_id: null }, { asset_id: 'a-1' }] })
    fireEvent.click(screen.getByRole('button', { name: 'Remove picture 1' }))
    expect(onChange.mock.lastCall![0].items).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: /Add a picture/ }))
    expect(onChange.mock.lastCall![0].items).toHaveLength(3)
    fireEvent.change(screen.getByLabelText('Arrangement'), { target: { value: 'mosaic' } })
    expect(onChange.mock.lastCall![0]).toMatchObject({ layout: 'mosaic' })
  })

  it('moves a cover picture’s focus, and has nothing of its own for a designed page', () => {
    const onChange = vi.fn()
    const cover = { ...(newBlock('cover') as Extract<StoryBlock, { type: 'cover' }>), style: 'overlay' as const }
    const { container, rerender } = render(<BlockOptions block={cover} assets={new Map()} onChange={onChange} onPickAsset={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Headline colour'), { target: { value: 'dark' } })
    expect(onChange.mock.lastCall![0]).toMatchObject({ tone: 'dark' })
    fireEvent.change(screen.getAllByRole('slider')[0], { target: { value: '20' } })
    expect(onChange.mock.lastCall![0]).toMatchObject({ focal: { x: 20, y: 50 } })
    rerender(<BlockOptions block={newBlock('page')} assets={new Map()} onChange={onChange} onPickAsset={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })
})
