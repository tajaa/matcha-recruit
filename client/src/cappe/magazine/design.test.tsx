import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PhotoDesigner from './editor/PhotoDesigner'
import BlockEditor from './editor/BlockEditor'
import { cropBetween, newBlock } from './editor/blocks'
import type { CappeAsset, StoryBlock } from '../types'

type Photo = Extract<StoryBlock, { type: 'photo' }>

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

describe('PhotoDesigner', () => {
  it('puts words where the picture is clicked, and moves them', () => {
    const onChange = vi.fn()
    const { rerender } = render(<PhotoDesigner block={photo()} asset={ASSET} onChange={onChange} />)
    const frame = screen.getByTestId('photo-frame')
    box(frame)
    expect(frame.querySelector('img')).toHaveAttribute('src', 'https://cdn.example.test/a-960.webp')
    fireEvent.click(frame, { clientX: 100, clientY: 150 })
    const placed = onChange.mock.calls[0][0] as Photo
    expect(placed.overlays).toEqual([{ x: 25, y: 75, text: '', size: 'm', tone: 'light', box: false, align: 'center' }])

    rerender(<PhotoDesigner block={placed} asset={ASSET} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Words 1'), { target: { value: 'Dawn' } })
    expect((onChange.mock.lastCall![0] as Photo).overlays![0].text).toBe('Dawn')
    fireEvent.change(screen.getByLabelText('Size of words 1'), { target: { value: 'xl' } })
    expect((onChange.mock.lastCall![0] as Photo).overlays![0].size).toBe('xl')
    fireEvent.click(screen.getByRole('button', { name: /Move/ }))
    expect(screen.getByText('Click where the words should go.')).toBeInTheDocument()
    const again = screen.getByTestId('photo-frame')
    box(again)
    fireEvent.click(again, { clientX: 300, clientY: 20 })
    expect((onChange.mock.lastCall![0] as Photo).overlays).toEqual([{ ...placed.overlays![0], x: 75, y: 10 }])
    fireEvent.click(screen.getByRole('button', { name: 'Remove words 1' }))
    expect((onChange.mock.lastCall![0] as Photo).overlays).toEqual([])
  })

  it('stops at eight pieces of words', () => {
    const onChange = vi.fn()
    const full = photo({ overlays: Array.from({ length: 8 }, () => ({ x: 50, y: 50, text: 'x', size: 'm' as const, tone: 'light' as const, box: false, align: 'center' as const })) })
    render(<PhotoDesigner block={full} asset={ASSET} onChange={onChange} />)
    const frame = screen.getByTestId('photo-frame')
    box(frame)
    fireEvent.click(frame, { clientX: 10, clientY: 10 })
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByText('A photo holds 8 pieces of text.')).toBeInTheDocument()
  })

  it('crops by dragging, shows the crop, and can go back to the whole picture', () => {
    const onChange = vi.fn()
    const { rerender } = render(<PhotoDesigner block={photo()} asset={ASSET} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /Crop/ }))
    const area = screen.getByTestId('crop-area')
    box(area)
    fireEvent.pointerDown(area, { clientX: 100, clientY: 20 })
    fireEvent.pointerMove(area, { clientX: 300, clientY: 180 })
    fireEvent.pointerUp(area)
    const cropped = onChange.mock.lastCall![0] as Photo
    expect(cropped.crop).toEqual({ x: 25, y: 10, w: 50, h: 80 })

    rerender(<PhotoDesigner block={cropped} asset={ASSET} onChange={onChange} />)
    const frame = screen.getByTestId('photo-frame')
    expect(frame.style.aspectRatio).toBe('100000 / 80000')
    expect(frame.querySelector('img')!.style.left).toBe('-50%')
    fireEvent.click(screen.getByRole('button', { name: /Whole picture/ }))
    expect((onChange.mock.lastCall![0] as Photo).crop).toBeNull()
  })

  it('sets the border, shape and colour; a circle can’t be cropped', () => {
    const onChange = vi.fn()
    const { rerender } = render(<PhotoDesigner block={photo()} asset={ASSET} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Border'), { target: { value: 'mat' } })
    expect((onChange.mock.lastCall![0] as Photo).border).toBe('mat')
    fireEvent.change(screen.getByLabelText('Colour'), { target: { value: 'bw' } })
    expect((onChange.mock.lastCall![0] as Photo).filter).toBe('bw')
    rerender(<PhotoDesigner block={photo({ shape: 'circle', crop: { x: 0, y: 0, w: 50, h: 50 } })} asset={ASSET} onChange={onChange} />)
    expect(screen.getByRole('button', { name: /Crop/ })).toBeDisabled()
    expect(screen.getByTestId('photo-frame').style.aspectRatio).toBe('')
  })
})

describe('BlockEditor — text design', () => {
  it('chooses the style and alignment (a book page is already a column)', () => {
    const onChange = vi.fn()
    render(<BlockEditor block={newBlock('text')} index={1} count={2} assets={new Map()} onChange={onChange}
      onMove={vi.fn()} onRemove={vi.fn()} onPickAsset={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Style'), { target: { value: 'statement' } })
    expect(onChange.mock.lastCall![0]).toMatchObject({ variant: 'statement' })
    expect(screen.queryByLabelText('Columns')).toBeNull()
    fireEvent.change(screen.getByLabelText('Align'), { target: { value: 'justify' } })
    expect(onChange.mock.lastCall![0]).toMatchObject({ align: 'justify' })
  })

  it('opens the photo designer once a photo has a picture', () => {
    render(<BlockEditor block={photo()} index={1} count={2} assets={new Map([['a-1', ASSET]])} onChange={vi.fn()}
      onMove={vi.fn()} onRemove={vi.fn()} onPickAsset={vi.fn()} />)
    expect(screen.getByTestId('photo-frame')).toBeInTheDocument()
  })
})
