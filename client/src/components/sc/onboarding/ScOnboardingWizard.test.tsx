import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../../api/client'

const { statusMock, completeMock, refreshMock, navigateMock, parseLocationsMock, parseEmployeesMock } = vi.hoisted(() => ({
  statusMock: vi.fn(),
  completeMock: vi.fn(),
  refreshMock: vi.fn(),
  navigateMock: vi.fn(),
  parseLocationsMock: vi.fn(),
  parseEmployeesMock: vi.fn(),
}))

vi.mock('../../../api/sc/scOnboarding', () => ({
  scOnboardingApi: {
    status: statusMock,
    complete: completeMock,
    parseLocationsCsv: parseLocationsMock,
    parseEmployeesCsv: parseEmployeesMock,
  },
}))
vi.mock('../../../hooks/useMe', () => ({ useMe: () => ({ refresh: refreshMock }) }))
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => navigateMock,
}))

import userEvent from '@testing-library/user-event'

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

  async function reachLocationsStep(user: ReturnType<typeof userEvent.setup>) {
    renderWizard()
    await waitFor(() => expect(screen.getByText('Set up Safety Co')).toBeInTheDocument())
    // Select is a button-based dropdown, not a native <select>.
    await user.click(screen.getByRole('button', { name: /Choose a range/ }))
    await user.click(screen.getByRole('button', { name: /11.50 employees/ }))
    await user.type(screen.getByRole('textbox'), '722511')
    await user.click(screen.getByRole('button', { name: 'Continue' }))
  }

  function fileInput(): HTMLInputElement {
    const input = document.querySelector('input[type="file"]')
    if (!input) throw new Error('no file input rendered')
    return input as HTMLInputElement
  }

  it('renders the server columns and hands the file to the server to validate', async () => {
    const user = userEvent.setup()
    statusMock.mockResolvedValue({
      company_name: 'Safety Co',
      completed: false,
      completed_at: null,
      csv_columns: { locations: ['name', 'address', 'city', 'state', 'zipcode'], employees: ['email'] },
    })
    parseLocationsMock.mockResolvedValue([
      { name: 'HQ', address: '1 Main', city: 'Austin', state: 'TX', zipcode: '78701' },
    ])

    await reachLocationsStep(user)

    // The header hint is the parser's own column list, not a second copy.
    expect(screen.getByText('name,address,city,state,zipcode')).toBeInTheDocument()

    const file = new File(['name,address,city,state,zipcode\nHQ,1 Main,Austin,TX,78701'], 'l.csv', { type: 'text/csv' })
    await user.upload(fileInput(), file)

    await waitFor(() => expect(screen.getByText('1 locations ready to import')).toBeInTheDocument())
    expect(parseLocationsMock).toHaveBeenCalledWith(file)
  })

  it('surfaces the server row error and imports nothing', async () => {
    const user = userEvent.setup()
    statusMock.mockResolvedValue({
      company_name: 'Safety Co', completed: false, completed_at: null,
      csv_columns: { locations: ['name'], employees: ['email'] },
    })
    parseLocationsMock.mockRejectedValue(new ApiError('Row 4 must contain all 5 values', 422, null))

    await reachLocationsStep(user)
    await user.upload(fileInput(), new File(['x'], 'l.csv', { type: 'text/csv' }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Row 4 must contain all 5 values'),
    )
    expect(screen.getByText('No locations selected')).toBeInTheDocument()
  })
})
