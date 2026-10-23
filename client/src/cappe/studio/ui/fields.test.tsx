import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { NumberField } from '../../magazine/workspace/controls'
import { LengthField } from './fields'

describe('panel fields', () => {
  // Applying type hands the keys back to the text; an Enter let through would
  // then replace the words selected with a new paragraph.
  it('take Enter for themselves: it applies what was typed and goes no further', () => {
    const onLength = vi.fn()
    const onSize = vi.fn()
    render(<>
      <LengthField label="Space before" value={0} units="in" onChange={onLength} />
      <NumberField label="Size" value={10.5} onChange={onSize} />
    </>)
    const length = screen.getByLabelText('Space before')
    fireEvent.change(length, { target: { value: '12p' } })
    expect(fireEvent.keyDown(length, { key: 'Enter' })).toBe(false) // default prevented
    expect(onLength).toHaveBeenCalledWith(144)
    const size = screen.getByLabelText('Size')
    fireEvent.change(size, { target: { value: '30' } })
    expect(fireEvent.keyDown(size, { key: 'Enter' })).toBe(false)
    expect(onSize).toHaveBeenCalledWith(30)
  })

  it('step with the arrows (Shift: ten) and let Escape drop what was typed', () => {
    const onChange = vi.fn()
    render(<LengthField label="Width" value={72} units="pt" onChange={onChange} />)
    const input = screen.getByLabelText('Width')
    fireEvent.keyDown(input, { key: 'ArrowUp', shiftKey: true })
    expect(onChange).toHaveBeenLastCalledWith(82)
    fireEvent.change(input, { target: { value: 'nonsense' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect((input as HTMLInputElement).value).toBe('72')
  })
})
