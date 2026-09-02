import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScheduleJobsTab from './ScheduleJobsTab'

const { fetchJobsMock, fetchRosterMock, fetchCredentialTypesMock, replaceJobCredentialRequirementsMock, updateJobMock } = vi.hoisted(() => ({
  fetchJobsMock: vi.fn(),
  fetchRosterMock: vi.fn(),
  fetchCredentialTypesMock: vi.fn(),
  replaceJobCredentialRequirementsMock: vi.fn(),
  updateJobMock: vi.fn(),
}))

vi.mock('../../../api/employees/employeeSchedule', () => ({
  createJob: vi.fn(),
  deleteJob: vi.fn(),
  fetchJobs: fetchJobsMock,
  fetchRoster: fetchRosterMock,
  replaceJobCredentialRequirements: replaceJobCredentialRequirementsMock,
  replaceJobEmployees: vi.fn(),
  updateJob: updateJobMock,
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
    replaceJobCredentialRequirementsMock.mockReset().mockResolvedValue([])
    updateJobMock.mockReset().mockResolvedValue({})
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

  it('keeps an already-selected hidden credential visible by its saved label', async () => {
    fetchJobsMock.mockResolvedValue({
      jobs: [{
        id: 'job-1', name: 'Opener', location_id: 'loc1', color: null, notes: null,
        credential_grace_days: null, employee_ids: ['employee-1'],
        credential_requirements: [{
          credential_type_id: 'hidden-type', credential_type_label: 'Food Handler Card',
          is_required: true, schedule_blocking: true,
        }],
      }],
    })
    fetchCredentialTypesMock.mockResolvedValue([])

    render(<ScheduleJobsTab locationId="loc1" credentialTemplatesEnabled />)

    fireEvent.click(await screen.findByRole('button', { name: 'Expand Opener' }))
    expect(screen.getByRole('button', { name: 'Food Handler Card ×' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Food Handler Card' })).not.toBeInTheDocument()
  })

  it('keeps an existing requirement\'s own flags and notes when saving', async () => {
    fetchJobsMock.mockResolvedValue({
      jobs: [{
        id: 'job-1', name: 'Opener', location_id: 'loc1', color: null, notes: null,
        credential_grace_days: null, employee_ids: ['employee-1'],
        credential_requirements: [{
          credential_type_id: 'advisory-type', credential_type_label: 'Food Handler Card',
          is_required: false, schedule_blocking: false, notes: 'advisory only',
        }],
      }],
    })
    fetchCredentialTypesMock.mockResolvedValue([])

    render(<ScheduleJobsTab locationId="loc1" credentialTemplatesEnabled />)

    fireEvent.click(await screen.findByRole('button', { name: 'Expand Opener' }))
    fireEvent.click(screen.getByRole('button', { name: /Save credential rules/ }))

    await waitFor(() => expect(replaceJobCredentialRequirementsMock).toHaveBeenCalledWith('job-1', [{
      credential_type_id: 'advisory-type', is_required: false, schedule_blocking: false, notes: 'advisory only',
    }]))
  })
})
