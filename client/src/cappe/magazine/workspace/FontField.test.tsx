import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CUTS } from '../../studio/fonts/cuts'
import FontField from './FontField'

describe('the font picker', () => {
  it('lists the Studio’s cuts after the catalog, previewed in the family they are cut from', () => {
    const onChange = vi.fn()
    render(<FontField value="Playfair Poster" roles={false} cuts={CUTS} onChange={onChange} />)
    expect(screen.getByRole('button', { name: 'Font: Playfair Poster' }).querySelector('span')).toHaveStyle({ fontFamily: "'Playfair'" })
    fireEvent.click(screen.getByRole('button', { name: 'Font: Playfair Poster' }))
    fireEvent.change(screen.getByLabelText('Search fonts'), { target: { value: 'bodoni' } })
    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options.at(-1)).toBe('Bodoni Moda DisplayGummfit cut') // after the catalog's Bodonis
    expect(options[0]).toBe('Bodoni ModaRegular–Black')
    fireEvent.click(screen.getByText('Bodoni Moda Display'))
    expect(onChange).toHaveBeenCalledWith('Bodoni Moda Display')
    const link = [...document.head.querySelectorAll('link')].find((l) => l.href.includes('text=Bodoni%20Moda%20Display'))
    expect(link?.href).toContain('family=Bodoni%20Moda&')
  })

  it('offers no cuts outside the Studio', () => {
    render(<FontField value="Lora" roles={false} onChange={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Font: Lora' }))
    fireEvent.change(screen.getByLabelText('Search fonts'), { target: { value: 'display' } })
    expect(screen.queryByText('Bodoni Moda Display')).toBeNull()
  })
})
