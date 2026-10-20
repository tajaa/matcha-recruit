import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ProductImagesEditor, { MAX_IMAGES } from './ProductImagesEditor'

vi.mock('./ImageUpload', () => ({
  default: ({ value, onChange, onUploaded }: { value: string; onChange: (u: string) => void; onUploaded?: (u: string) => void }) => (
    <>
      <input aria-label="Picture link" value={value} onChange={(e) => onChange(e.target.value)} />
      <button type="button" onClick={() => onUploaded?.('/uploads/new.png')}>Finish upload</button>
    </>
  ),
}))

const two = [{ url: 'https://c.example.com/1.jpg', alt: 'Front' }, { url: 'https://c.example.com/2.jpg', alt: '' }]

describe('ProductImagesEditor', () => {
  it('adds a picture only when asked, at the end', () => {
    const onChange = vi.fn()
    render(<ProductImagesEditor siteId="s" images={two} onChange={onChange} />)
    fireEvent.change(screen.getByRole('textbox', { name: 'Picture link' }), { target: { value: ' https://c.example.com/3.jpg ' } })
    expect(onChange).not.toHaveBeenCalled()                  // typing a link is not adding it
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(onChange).toHaveBeenCalledWith([...two, { url: 'https://c.example.com/3.jpg', alt: '' }])
  })

  it('adds an uploaded picture at once, so a save never drops it', () => {
    const onChange = vi.fn()
    render(<ProductImagesEditor siteId="s" images={two} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'Finish upload' }))
    expect(onChange).toHaveBeenCalledWith([...two, { url: '/uploads/new.png', alt: '' }])
  })

  it('reorders and removes, so any picture can become the cover', () => {
    const onChange = vi.fn()
    render(<ProductImagesEditor siteId="s" images={two} onChange={onChange} />)
    expect(screen.getByRole('button', { name: 'Move picture 1 up' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Move picture 2 up' }))
    expect(onChange).toHaveBeenLastCalledWith([two[1], two[0]])
    fireEvent.click(screen.getByRole('button', { name: 'Remove picture 1' }))
    expect(onChange).toHaveBeenLastCalledWith([two[1]])
  })

  it('stops offering to add at the limit', () => {
    const full = Array.from({ length: MAX_IMAGES }, (_, i) => ({ url: `/u/${i}.png`, alt: '' }))
    render(<ProductImagesEditor siteId="s" images={full} onChange={() => {}} />)
    expect(screen.queryByRole('button', { name: 'Add' })).not.toBeInTheDocument()
    expect(screen.getByText(/20 pictures is the most/)).toBeInTheDocument()
  })
})
