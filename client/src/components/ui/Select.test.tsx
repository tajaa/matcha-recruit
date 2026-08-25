import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Select } from './Select'

describe('Select focus boundary', () => {
  it('keeps the owner active while focus moves from the trigger to an option', async () => {
    const user = userEvent.setup()
    const onBlur = vi.fn()
    const onChange = vi.fn()
    render(
      <>
        <Select options={[{ value: 'a', label: 'Alpha' }]} onBlur={onBlur} onChange={onChange} autoFocus />
        <button type="button">Outside</button>
      </>,
    )

    await user.click(screen.getByRole('button', { name: /alpha/i }))
    await user.click(screen.getAllByRole('button', { name: /alpha/i })[1])

    expect(onChange).toHaveBeenCalledWith({ target: { value: 'a' } })
    expect(onBlur).not.toHaveBeenCalled()
  })

  it('notifies once when keyboard focus leaves the full select', async () => {
    const user = userEvent.setup()
    const onBlur = vi.fn()
    render(
      <>
        <Select options={[{ value: 'a', label: 'Alpha' }]} onBlur={onBlur} autoFocus />
        <button type="button">Outside</button>
      </>,
    )

    await user.keyboard('{Enter}')
    await user.tab()
    expect(onBlur).not.toHaveBeenCalled()
    await user.tab()
    expect(onBlur).toHaveBeenCalledTimes(1)
  })
})
