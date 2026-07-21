import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { Modal } from './Modal'

describe('Modal dismissal', () => {
  it('closes on Escape and on a backdrop click by default', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<Modal open onClose={onClose} title="T">body</Modal>)

    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)

    await user.click(document.querySelector('.fixed.inset-0') as Element)
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('ignores Escape and backdrop clicks when not dismissible', async () => {
    // The regression the flag exists for: dialogs migrated onto <Modal> had an
    // X button ONLY, so adopting the shared component handed them accidental
    // dismissal — wrong for a newsletter mid-send.
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<Modal open onClose={onClose} title="T" dismissible={false}>body</Modal>)

    await user.keyboard('{Escape}')
    await user.click(document.querySelector('.fixed.inset-0') as Element)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('does not render or listen when closed', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<Modal open={false} onClose={onClose} title="T">body</Modal>)

    expect(screen.queryByText('body')).not.toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('Modal stacking', () => {
  it('Escape closes only the topmost modal', async () => {
    // Each Modal used to add its own document listener, so one Escape collapsed
    // the whole stack — a confirm dialog over an editor took the editor with it.
    const user = userEvent.setup()
    const outer = vi.fn()
    const inner = vi.fn()
    render(
      <>
        <Modal open onClose={outer} title="outer">outer body</Modal>
        <Modal open onClose={inner} title="inner">inner body</Modal>
      </>,
    )

    await user.keyboard('{Escape}')
    expect(inner).toHaveBeenCalledTimes(1)
    expect(outer).not.toHaveBeenCalled()
  })

  it('falls back to the next modal once the top one unmounts', async () => {
    const user = userEvent.setup()
    const outer = vi.fn()
    const inner = vi.fn()
    const { rerender } = render(
      <>
        <Modal open onClose={outer} title="outer">outer body</Modal>
        <Modal open onClose={inner} title="inner">inner body</Modal>
      </>,
    )

    rerender(
      <>
        <Modal open onClose={outer} title="outer">outer body</Modal>
        <Modal open={false} onClose={inner} title="inner">inner body</Modal>
      </>,
    )

    await user.keyboard('{Escape}')
    expect(outer).toHaveBeenCalledTimes(1)
    expect(inner).not.toHaveBeenCalled()
  })

  it('a non-dismissible modal on top does not block the one beneath it', async () => {
    // It registers no stack entry at all, which is the intended reading: it
    // opts out of Escape entirely rather than swallowing the key.
    const user = userEvent.setup()
    const outer = vi.fn()
    render(
      <>
        <Modal open onClose={outer} title="outer">outer body</Modal>
        <Modal open onClose={vi.fn()} title="inner" dismissible={false}>inner body</Modal>
      </>,
    )

    await user.keyboard('{Escape}')
    expect(outer).toHaveBeenCalledTimes(1)
  })
})
