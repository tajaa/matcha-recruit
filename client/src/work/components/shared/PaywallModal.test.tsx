import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import PaywallModal from './PaywallModal'

const checkout = vi.hoisted(() => vi.fn())
vi.mock('../../api/matchaWork/billing', () => ({ startPersonalCheckout: checkout }))

beforeEach(() => { checkout.mockReset() })

describe('PaywallModal', () => {
  it('offers Lite for a free user and requests the Lite checkout', () => {
    checkout.mockImplementation(() => new Promise(() => {}))
    render(<PaywallModal
      detail={{ code: 'plan_required', feature: 'journals_full', required_plan: 'lite', current_plan: 'free' }}
      onClose={() => {}}
    />)
    expect(screen.getByText('This journal type needs Lite')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Get Lite' }))
    expect(checkout).toHaveBeenCalledWith('lite')
  })

  it('offers only Pro when Lite is already active', () => {
    checkout.mockImplementation(() => new Promise(() => {}))
    render(<PaywallModal
      detail={{ code: 'plan_required', feature: 'projects_collab', required_plan: 'pro', current_plan: 'lite' }}
      onClose={() => {}}
    />)
    expect(screen.getByRole('button', { name: 'Current plan' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Upgrade to Pro' }))
    expect(checkout).toHaveBeenCalledWith('pro')
  })

  it('does not sell Lite for a Pro-only action', () => {
    checkout.mockImplementation(() => new Promise(() => {}))
    render(<PaywallModal
      detail={{ code: 'plan_required', feature: 'projects_collab', required_plan: 'pro', current_plan: 'free' }}
      onClose={() => {}}
    />)
    expect(screen.getByRole('button', { name: 'Pro required for this feature' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Get Pro' }))
    expect(checkout).toHaveBeenCalledExactlyOnceWith('pro')
  })

  it('keeps keyboard focus in the dialog and restores the trigger on close', () => {
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()
    const view = render(<PaywallModal
      detail={{ code: 'plan_required', feature: 'journals_full', required_plan: 'lite', current_plan: 'free' }}
      onClose={() => {}}
    />)
    const close = screen.getByRole('button', { name: 'Close upgrade options' })
    expect(close).toHaveFocus()
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
    expect(screen.getByRole('button', { name: 'Get Pro' })).toHaveFocus()
    view.unmount()
    expect(trigger).toHaveFocus()
    trigger.remove()
  })
})
