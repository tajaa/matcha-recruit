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
    // Select is a button-based dropdown, not a native <select>; its <label>
    // names the trigger, so the placeholder text is not its accessible name.
    await user.click(screen.getByRole('button', { name: /Company size/ }))
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

  async function reachJobsWithCafeRoster(user: ReturnType<typeof userEvent.setup>) {
    statusMock.mockResolvedValue({
      company_name: 'Cafe Adore', completed: false, completed_at: null,
      csv_columns: { locations: ['name'], employees: ['email'] },
    })
    // Reserved example.com addresses only (root CLAUDE.md test-data rule).
    parseEmployeesMock.mockResolvedValue([
      { email: 'lead@example.com', first_name: 'Ana', last_name: 'Ruiz', work_state: 'CA', job_title: 'Shift Supervisor', department: 'Front' },
      { email: 'bar1@example.com', first_name: 'Bo', last_name: 'Kim', work_state: 'CA', job_title: 'Barista', department: 'Front' },
      { email: 'bar2@example.com', first_name: 'Cy', last_name: 'Lo', work_state: 'CA', job_title: 'barista', department: 'Front' },
    ])
    renderWizard()
    await waitFor(() => expect(screen.getByText('Set up Cafe Adore')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /Company size/ }))
    await user.click(screen.getByRole('button', { name: /11.50 employees/ }))
    await user.type(screen.getByRole('textbox'), '722515')
    await user.click(screen.getByRole('button', { name: 'Continue' })) // → Locations
    await user.click(screen.getByRole('button', { name: 'Continue' })) // → Employees
    await user.upload(fileInput(), new File(['x'], 'e.csv', { type: 'text/csv' }))
    await waitFor(() => expect(screen.getByText('3 employees ready to import')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Continue' })) // → Jobs
  }

  it('lists every roster job title as a job, so a certificate-less Shift Supervisor completes setup', async () => {
    const user = userEvent.setup()
    completeMock.mockResolvedValue({ already_completed: false, completed_at: '2026-09-28T00:00:00Z' })
    await reachJobsWithCafeRoster(user)

    // One row per distinct title (Barista/barista collapse); the blank starter row is gone.
    const jobNames = screen.getAllByLabelText('Job name') as HTMLInputElement[]
    expect(jobNames.map((input) => input.value)).toEqual(['Shift Supervisor', 'Barista'])
    expect(screen.getAllByText('No certificate required for this job.')).toHaveLength(2)

    await user.click(screen.getAllByRole('button', { name: 'Add certificate' })[1])
    await user.type(screen.getByLabelText('Certificate'), 'Food Handler Card')
    await user.click(screen.getByRole('button', { name: 'Continue' }))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText('Review setup')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Complete setup' }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/app', { replace: true }))
    const submission = completeMock.mock.calls[0][0]
    expect(submission.employees.map((employee: { job_title: string }) => employee.job_title))
      .toEqual(['Shift Supervisor', 'Barista', 'barista'])
    expect(submission.jobs).toEqual([
      { name: 'Shift Supervisor', credential_grace_days: 7, certificates: [] },
      {
        name: 'Barista',
        credential_grace_days: 7,
        certificates: [{ name: 'Food Handler Card', is_required: true, schedule_blocking: true }],
      },
    ])
  })

  it('names every employee title left without a job and how to fix it', async () => {
    const user = userEvent.setup()
    await reachJobsWithCafeRoster(user)

    const [supervisor, barista] = screen.getAllByLabelText('Job name')
    await user.clear(supervisor)
    await user.type(supervisor, 'Shift Lead')
    await user.clear(barista)
    await user.type(barista, 'Coffee')
    await user.click(screen.getAllByRole('button', { name: 'Add certificate' })[0])
    await user.type(screen.getByLabelText('Certificate'), 'Food Handler Card')
    await user.click(screen.getByRole('button', { name: 'Continue' }))

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Every employee job title needs a job. Add a job with the same name, or correct the title in the employee CSV and upload it again. Missing: Barista, Shift Supervisor',
    )
    expect(screen.queryByText('Review setup')).not.toBeInTheDocument()
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
