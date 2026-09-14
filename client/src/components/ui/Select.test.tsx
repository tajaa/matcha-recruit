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

describe('Select portal', () => {
  it('renders the open list outside its scroll container so the container cannot clip it', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <div data-testid="scroller" style={{ overflowY: 'auto', maxHeight: 40 }}>
        <Select portal options={[{ value: 'a', label: 'Alpha' }, { value: 'b', label: 'Beta' }]} onChange={onChange} />
      </div>,
    )

    await user.click(screen.getByRole('button', { name: /alpha/i }))
    const option = screen.getByRole('button', { name: /beta/i })
    expect(screen.getByTestId('scroller').contains(option)).toBe(false)
    expect(document.body.contains(option)).toBe(true)

    await user.click(option)
    expect(onChange).toHaveBeenCalledWith({ target: { value: 'b' } })
  })

  it('moves keyboard focus into the portaled list and back to the trigger on Escape', async () => {
    // The list is appended to <body>, after everything else, so Tab from the
    // trigger would never reach it. Opening must move focus in.
    const user = userEvent.setup()
    const onBlur = vi.fn()
    render(
      <>
        <Select portal value="b" options={[{ value: 'a', label: 'Alpha' }, { value: 'b', label: 'Beta' }]} onBlur={onBlur} autoFocus />
        <button type="button">Outside</button>
      </>,
    )
    const trigger = screen.getByRole('button', { name: /beta/i })

    await user.keyboard('{Enter}')
    const selected = screen.getAllByRole('button', { name: /beta/i }).find((b) => b !== trigger)
    expect(document.activeElement).toBe(selected)
    expect(onBlur).not.toHaveBeenCalled()

    await user.keyboard('{Escape}')
    expect(document.activeElement).toBe(trigger)
    expect(screen.getAllByRole('button', { name: /beta/i })).toHaveLength(1)
    expect(onBlur).not.toHaveBeenCalled()

    await user.tab()
    expect(onBlur).toHaveBeenCalledTimes(1)
  })

  it('returns focus to the trigger after a keyboard pick', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Select portal options={[{ value: 'a', label: 'Alpha' }, { value: 'b', label: 'Beta' }]} onChange={onChange} autoFocus />)
    const trigger = screen.getByRole('button', { name: /alpha/i })

    await user.keyboard('{Enter}')
    await user.tab()           // Alpha (focused on open) -> Beta
    await user.keyboard('{Enter}')
    expect(onChange).toHaveBeenCalledWith({ target: { value: 'b' } })
    expect(document.activeElement).toBe(trigger)
  })
})

describe('Select label association', () => {
  it('generates an id when handed an empty one', () => {
    render(<Select label="Kind" id="" options={[{ value: 'a', label: 'Alpha' }]} />)
    expect(screen.getByLabelText('Kind')).toBeTruthy()
  })
})

