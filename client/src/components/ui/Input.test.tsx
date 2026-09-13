import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Input } from './Input'
import { Textarea } from './Textarea'

// A label with no htmlFor target is a caption: clicking it focuses nothing and
// a screen reader reads the field as unlabeled. `id=""` is the easy way back
// into that state (a not-yet-persisted row's id), so it must fall through to a
// generated id exactly like a missing one.
describe('label association', () => {
  it('Input associates its label with no id, and with an empty one', () => {
    render(
      <>
        <Input label="Title" />
        <Input label="Code" id="" />
      </>,
    )
    expect(screen.getByLabelText('Title').tagName).toBe('INPUT')
    expect(screen.getByLabelText('Code').tagName).toBe('INPUT')
  })

  it('Textarea associates its label with an empty id', () => {
    render(<Textarea label="Notes" id="" />)
    expect(screen.getByLabelText('Notes').tagName).toBe('TEXTAREA')
  })
})
