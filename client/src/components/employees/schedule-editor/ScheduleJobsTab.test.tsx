import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScheduleJobsTab from './ScheduleJobsTab'

const { fetchJobsMock, fetchRosterMock, fetchCredentialTypesMock } = vi.hoisted(() => ({
  fetchJobsMock: vi.fn(),
  fetchRosterMock: vi.fn(),
  fetchCredentialTypesMock: vi.fn(),
}))

vi.mock('../../../api/employees/employeeSchedule', () => ({
  createJob: vi.fn(),
  deleteJob: vi.fn(),
  fetchJobs: fetchJobsMock,
  fetchRoster: fetchRosterMock,
  replaceJobCredentialRequirements: vi.fn(),
  replaceJobEmployees: vi.fn(),
  updateJob: vi.fn(),
}))

vi.mock('../../../api/employees/credentialTemplates', () => ({
  fetchCredentialTypes: fetchCredentialTypesMock,
}))

describe('ScheduleJobsTab', () => {
  beforeEach(() => {
    fetchJobsMock.mockReset().mockResolvedValue({
      jobs: [{
        id: 'job-1', name: 'Opener', location_id: 'loc1', color: null, notes: null,
        credential_grace_days: null, employee_ids: ['employee-1'], credential_requirements: [],
      }],
    })
    fetchRosterMock.mockReset().mockResolvedValue({
      employees: [{ id: 'employee-1', name: 'Aisha Rivera', job_title: 'Manager', department: null, job_ids: ['job-1'] }],
    })
    fetchCredentialTypesMock.mockReset()
  })

  it('loads job qualification controls without requesting gated credential data', async () => {
    render(<ScheduleJobsTab locationId="loc1" credentialTemplatesEnabled={false} />)

    expect(await screen.findByText('Opener')).toBeInTheDocument()
    expect(screen.getByText('1 qualified employee')).toBeInTheDocument()
    expect(fetchCredentialTypesMock).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'New job' }))
    expect(screen.queryByLabelText('Grace days')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Add required credential')).not.toBeInTheDocument()
  })

  it('keeps jobs and roster available when credential data fails to load', async () => {
    fetchCredentialTypesMock.mockRejectedValue(new Error('Credential templates unavailable'))

    render(<ScheduleJobsTab locationId="loc1" credentialTemplatesEnabled />)

    expect(await screen.findByText('Opener')).toBeInTheDocument()
    expect(screen.getByText('1 qualified employee · 0 credential rules')).toBeInTheDocument()
    expect(fetchCredentialTypesMock).toHaveBeenCalledTimes(1)
  })
})
