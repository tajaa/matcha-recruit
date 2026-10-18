import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AdminActionMenu } from './AdminActionMenu'

describe('AdminActionMenu', () => {
  it('supports keyboard selection, disabled actions, and Escape focus restoration', async () => {
    const action = vi.fn()
    const user = userEvent.setup()
    render(<MemoryRouter><AdminActionMenu label="Account actions" items={[
      { label: 'Unavailable', disabled: true }, { label: 'Grant tokens', onSelect: action },
      { label: 'Manage', to: '/admin/companies/company-1' },
    ]} /></MemoryRouter>)
    const trigger = screen.getByRole('button', { name: 'Account actions' })
    trigger.focus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitem', { name: 'Grant tokens' })).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitem', { name: 'Manage' })).toHaveFocus()
    expect(screen.getByRole('menuitem', { name: 'Manage' })).toHaveAttribute('href', '/admin/companies/company-1')
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    await user.click(trigger)
    await user.keyboard('{Enter}')
    expect(action).toHaveBeenCalledOnce()
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('dismisses on outside input and page scrolling', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><input aria-label="Search" /><AdminActionMenu label="Actions" items={[{ label: 'Reset' }]} /></MemoryRouter>)
    await user.click(screen.getByRole('button', { name: 'Actions' }))
    await user.click(screen.getByRole('textbox', { name: 'Search' }))
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Search' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Actions' }))
    fireEvent.scroll(window)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})
