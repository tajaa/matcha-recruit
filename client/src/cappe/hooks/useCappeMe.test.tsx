import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { invalidateCappeMeCache, useCappeMe } from './useCappeMe'

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api, getCappeToken: () => 'token' }))

function Sidebar() {
  const { account } = useCappeMe()
  return <p data-testid="sidebar">{account?.plan ?? 'none'}</p>
}

function Billing() {
  const { account, refresh } = useCappeMe()
  return <button type="button" data-testid="billing" onClick={() => void refresh()}>{account?.plan ?? 'none'}</button>
}

beforeEach(() => {
  invalidateCappeMeCache()
  api.get.mockReset()
})

describe('useCappeMe', () => {
  it('pushes a refreshed account to every mounted instance', async () => {
    api.get.mockResolvedValueOnce({ plan: 'free' }).mockResolvedValueOnce({ plan: 'business' })
    render(<><Sidebar /><Billing /></>)
    await waitFor(() => expect(screen.getByTestId('sidebar')).toHaveTextContent('free'))

    // The billing page refreshes after a plan change; the sidebar must follow.
    fireEvent.click(screen.getByTestId('billing'))

    await waitFor(() => expect(screen.getByTestId('sidebar')).toHaveTextContent('business'))
    expect(screen.getByTestId('billing')).toHaveTextContent('business')
    // One shared fetch on mount, one on refresh.
    expect(api.get).toHaveBeenCalledTimes(2)
  })
})
