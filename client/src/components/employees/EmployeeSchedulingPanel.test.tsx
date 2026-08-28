import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EmployeeSchedulingPanel } from './EmployeeSchedulingPanel'

const mocks = vi.hoisted(() => ({
  fetchJobs: vi.fn(),
  fetchEmployeeJobs: vi.fn(),
  fetchProfile: vi.fn(),
  fetchAvailability: vi.fn(),
  replaceJobs: vi.fn(),
  saveAvailability: vi.fn(),
  updateProfile: vi.fn(),
}))

vi.mock('../../api/employees/employeeSchedule', () => ({
  fetchJobs: mocks.fetchJobs,
  fetchEmployeeJobs: mocks.fetchEmployeeJobs,
  fetchEmployeeScheduleProfile: mocks.fetchProfile,
  fetchEmployeeAvailability: mocks.fetchAvailability,
  replaceEmployeeJobs: mocks.replaceJobs,
  saveEmployeeAvailability: mocks.saveAvailability,
  updateEmployeeScheduleProfile: mocks.updateProfile,
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
    mocks.replaceJobs.mockResolvedValue({ employee_id: 'employee-1', assignments: [] })
    mocks.saveAvailability.mockResolvedValue({ saved: 0, availability_state: 'always_available' })
    mocks.updateProfile.mockResolvedValue({ ...profile, availability_state: 'always_available' })
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

    await waitFor(() => expect(mocks.updateProfile).toHaveBeenCalled())
    const assignments = mocks.replaceJobs.mock.calls[0][1]
    expect(assignments.filter((assignment: { is_primary: boolean }) => assignment.is_primary)).toHaveLength(1)
    expect(assignments.find((assignment: { job_id: string }) => assignment.job_id === 'job-2').is_primary).toBe(true)
    expect(mocks.saveAvailability).toHaveBeenCalledWith('employee-1', [], 'always_available')
    expect(mocks.updateProfile).toHaveBeenCalledWith('employee-1', expect.objectContaining({
      min_weekly_minutes: 1200, target_weekly_minutes: 1950, max_weekly_minutes: 2400,
    }))
  })

  it('surfaces API validation errors without clearing the form', async () => {
    mocks.replaceJobs.mockRejectedValue(new Error('Job does not belong to this location'))
    render(<EmployeeSchedulingPanel employeeId="employee-1" workLocationId="loc-1" />)

    expect(await screen.findByText('Barista')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Shift leader' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save scheduling details' }))

    expect(await screen.findByText('Job does not belong to this location')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Shift leader' })).toBeChecked()
  })
})
