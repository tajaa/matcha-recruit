import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EmployeeSchedulingPanel } from './EmployeeSchedulingPanel'

const mocks = vi.hoisted(() => ({
  fetchJobs: vi.fn(),
  fetchEmployeeJobs: vi.fn(),
  fetchProfile: vi.fn(),
  fetchAvailability: vi.fn(),
  updateDetails: vi.fn(),
}))

vi.mock('../../api/employees/employeeSchedule', () => ({
  fetchJobs: mocks.fetchJobs,
  fetchEmployeeJobs: mocks.fetchEmployeeJobs,
  fetchEmployeeScheduleProfile: mocks.fetchProfile,
  fetchEmployeeAvailability: mocks.fetchAvailability,
  updateEmployeeSchedulingDetails: mocks.updateDetails,
}))

const profile = {
  employee_id: 'employee-1', availability_state: 'unconfirmed' as const,
  availability_confirmed_at: null, min_weekly_minutes: null,
  target_weekly_minutes: null, max_weekly_minutes: null,
  max_consecutive_days: null, allow_overtime: false, prefer_extra_hours: false,
}

const jobs = [
  { id: 'job-1', name: 'Barista', location_id: 'loc-1', color: null, notes: null, credential_grace_days: null, employee_ids: ['employee-1'], credential_requirements: [] },
  { id: 'job-2', name: 'Shift leader', location_id: 'loc-1', color: null, notes: null, credential_grace_days: null, employee_ids: [], credential_requirements: [{ credential_type_id: 'cred-1', credential_type_label: 'Food handler', is_required: true, schedule_blocking: true }] },
]

describe('EmployeeSchedulingPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.fetchJobs.mockResolvedValue({ jobs })
    mocks.fetchEmployeeJobs.mockResolvedValue({
      employee_id: 'employee-1',
      assignments: [{
        job_id: 'job-1', job_name: 'Barista', location_id: 'loc-1',
        is_primary: true, qualification_status: 'active', qualified_from: null,
        qualified_until: null, notes: null, credential_requirements: [],
      }],
    })
    mocks.fetchProfile.mockResolvedValue(profile)
    mocks.fetchAvailability.mockResolvedValue({ availability_state: 'unconfirmed', windows: [] })
    mocks.updateDetails.mockResolvedValue({
      employee_id: 'employee-1', assignments: [], saved_windows: 0,
      availability_state: 'always_available',
      profile: { ...profile, availability_state: 'always_available' },
    })
  })

  it('loads inputs, switches primary, converts hours, and confirms always available', async () => {
    render(<EmployeeSchedulingPanel employeeId="employee-1" workLocationId="loc-1" />)

    expect(await screen.findByText('Barista')).toBeInTheDocument()
    expect(screen.getByText(/Not confirmed/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Shift leader' }))
    fireEvent.click(screen.getAllByRole('radio')[1])
    const hourInputs = screen.getAllByRole('spinbutton')
    fireEvent.change(hourInputs[0], { target: { value: '20' } })
    fireEvent.change(hourInputs[1], { target: { value: '32.5' } })
    fireEvent.change(hourInputs[2], { target: { value: '40' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save scheduling details' }))

    await waitFor(() => expect(mocks.updateDetails).toHaveBeenCalled())
    const payload = mocks.updateDetails.mock.calls[0][1]
    const assignments = payload.jobs.assignments
    expect(assignments.filter((assignment: { is_primary: boolean }) => assignment.is_primary)).toHaveLength(1)
    expect(assignments.find((assignment: { job_id: string }) => assignment.job_id === 'job-2').is_primary).toBe(true)
    expect(payload.availability).toEqual({ availability_state: 'always_available', windows: [] })
    expect(payload.profile).toEqual(expect.objectContaining({
      min_weekly_minutes: 1200, target_weekly_minutes: 1950, max_weekly_minutes: 2400,
    }))
  })

  it('surfaces API validation errors without clearing the form', async () => {
    mocks.updateDetails.mockRejectedValue(new Error('Job does not belong to this location'))
    render(<EmployeeSchedulingPanel employeeId="employee-1" workLocationId="loc-1" />)

    expect(await screen.findByText('Barista')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Shift leader' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save scheduling details' }))

    expect(await screen.findByText('Job does not belong to this location')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Shift leader' })).toBeChecked()
  })

  it('preserves legacy windows and omits unchanged stale-location jobs', async () => {
    mocks.fetchJobs.mockResolvedValue({ jobs: [jobs[1]] })
    mocks.fetchEmployeeJobs.mockResolvedValue({
      employee_id: 'employee-1',
      assignments: [{
        job_id: 'job-old', job_name: 'Old location role', location_id: 'loc-old',
        is_primary: false, qualification_status: 'active', qualified_from: null,
        qualified_until: null, notes: null, credential_requirements: [],
      }],
    })
    const legacyWindows = [{ weekday: 1, start_time: '09:00', end_time: '17:00' }]
    mocks.fetchAvailability.mockResolvedValue({ availability_state: 'unconfirmed', windows: legacyWindows })

    render(<EmployeeSchedulingPanel employeeId="employee-1" workLocationId="loc-1" />)

    expect(await screen.findByText('Old location role')).toBeInTheDocument()
    expect(screen.getByText(/previous work location/)).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Shift leader' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Save scheduling details' }))

    await waitFor(() => expect(mocks.updateDetails).toHaveBeenCalledWith('employee-1', expect.objectContaining({
      jobs: undefined,
      availability: { availability_state: 'windows', windows: legacyWindows },
    })))
  })

  it('requires stale-location jobs to be removed before other job edits', async () => {
    mocks.fetchJobs.mockResolvedValue({ jobs: [jobs[1]] })
    mocks.fetchEmployeeJobs.mockResolvedValue({
      employee_id: 'employee-1',
      assignments: [{
        job_id: 'job-old', job_name: 'Old location role', location_id: 'loc-old',
        is_primary: false, qualification_status: 'active', qualified_from: null,
        qualified_until: null, notes: null, credential_requirements: [],
      }],
    })

    render(<EmployeeSchedulingPanel employeeId="employee-1" workLocationId="loc-1" />)

    const currentJob = await screen.findByRole('checkbox', { name: 'Shift leader' })
    const staleJob = screen.getByRole('checkbox', { name: 'Old location role' })
    expect(currentJob).toBeDisabled()
    expect(staleJob).toBeEnabled()

    fireEvent.click(staleJob)
    expect(currentJob).toBeEnabled()
    expect(staleJob).toBeDisabled()
    fireEvent.click(currentJob)
    fireEvent.click(screen.getByRole('button', { name: 'Save scheduling details' }))

    await waitFor(() => expect(mocks.updateDetails).toHaveBeenCalled())
    expect(mocks.updateDetails.mock.calls[0][1].jobs.assignments).toEqual([
      expect.objectContaining({ job_id: 'job-2' }),
    ])
  })
})
