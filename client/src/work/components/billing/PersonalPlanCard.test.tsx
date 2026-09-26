import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import PersonalPlanCard from './PersonalPlanCard'
import { cancelPersonalSubscription, getMWSubscription } from '../../api/matchaWork/billing'

vi.mock('../../api/matchaWork/billing', () => ({
  getMWSubscription: vi.fn(),
  cancelPersonalSubscription: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('confirm', vi.fn(() => true))
})
afterEach(() => vi.unstubAllGlobals())

const paidThrough = new Date('2026-10-25T00:00:00Z').toLocaleDateString('en-US', {
  month: 'short', day: 'numeric', year: 'numeric',
})

describe('PersonalPlanCard', () => {
  it('shows the paid period and lets a subscriber stop renewal', async () => {
    vi.mocked(getMWSubscription).mockResolvedValueOnce({
      active: true,
      pack_id: 'matcha_work_lite',
      status: 'active',
      current_period_end: null,
    }).mockResolvedValueOnce({
      active: false,
      pack_id: 'matcha_work_lite',
      status: 'canceled',
      current_period_end: '2026-10-25T00:00:00Z',
    })
    vi.mocked(cancelPersonalSubscription).mockResolvedValue({
      canceled: true, message: 'Subscription will not renew at the end of the current period.',
    })
    render(<PersonalPlanCard />)
    expect(await screen.findByText('Lite plan')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel plan' }))
    await waitFor(() => expect(screen.getByText('Renewal canceled', { exact: false })).toBeInTheDocument())
    expect(screen.getByText(new RegExp(`Access until ${paidThrough}`))).toBeInTheDocument()
    expect(cancelPersonalSubscription).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('button', { name: 'Cancel plan' })).not.toBeInTheDocument()
  })

  it('shows a canceled subscription without another cancel action', async () => {
    vi.mocked(getMWSubscription).mockResolvedValue({
      active: false,
      pack_id: 'matcha_work_personal',
      status: 'canceled',
      current_period_end: '2026-10-25T00:00:00Z',
    })
    render(<PersonalPlanCard />)
    expect(await screen.findByText('Pro plan')).toBeInTheDocument()
    expect(screen.getByText(new RegExp(`Access until ${paidThrough}`))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel plan' })).not.toBeInTheDocument()
  })
})
