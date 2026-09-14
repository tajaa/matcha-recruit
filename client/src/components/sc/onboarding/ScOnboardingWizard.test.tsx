import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../../api/client'

const { statusMock, completeMock, refreshMock, navigateMock } = vi.hoisted(() => ({
  statusMock: vi.fn(),
  completeMock: vi.fn(),
  refreshMock: vi.fn(),
  navigateMock: vi.fn(),
}))

vi.mock('../../../api/sc/scOnboarding', () => ({
  scOnboardingApi: { status: statusMock, complete: completeMock },
}))
vi.mock('../../../hooks/useMe', () => ({ useMe: () => ({ refresh: refreshMock }) }))
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => navigateMock,
}))

import ScOnboardingWizard from './ScOnboardingWizard'

function renderWizard() {
  return render(<MemoryRouter initialEntries={['/sc/onboarding']}><ScOnboardingWizard /></MemoryRouter>)
}

describe('ScOnboardingWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    refreshMock.mockResolvedValue(undefined)
  })

  afterEach(() => vi.useRealTimers())

  it('waits out the Stripe activation window instead of dead-ending on 403', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    statusMock
      .mockRejectedValueOnce(new ApiError('Activate this product before completing setup', 403, null))
      .mockResolvedValueOnce({ company_name: 'Safety Co', completed: false, completed_at: null })

    renderWizard()

    await waitFor(() => expect(screen.getByText('Finishing activation…')).toBeInTheDocument())
    await vi.advanceTimersByTimeAsync(1500)
    await waitFor(() => expect(screen.getByText('Set up Safety Co')).toBeInTheDocument())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('gives up with the server message once the activation budget is spent', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    statusMock.mockRejectedValue(new ApiError('Matcha S&C onboarding is not enabled for this company', 403, null))

    renderWizard()

    await vi.advanceTimersByTimeAsync(1500 * 9)
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('not enabled for this company'),
    )
  })

  it('refreshes the cached profile before redirecting an already-complete tenant', async () => {
    statusMock.mockResolvedValue({
      company_name: 'Safety Co', completed: true, completed_at: '2026-09-14T00:00:00Z',
    })

    renderWizard()

    // The route guard reads the same cached /auth/me; navigating on a stale
    // profile bounces the user straight back into the wizard.
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/app', { replace: true }))
    expect(refreshMock).toHaveBeenCalled()
    expect(refreshMock.mock.invocationCallOrder[0])
      .toBeLessThan(navigateMock.mock.invocationCallOrder[0])
  })
})
