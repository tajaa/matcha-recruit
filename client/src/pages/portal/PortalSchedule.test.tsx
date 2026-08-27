import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/ui'
import type { ScheduleRequest, Shift } from '../../types/employeeSchedule'
import PortalSchedule from './PortalSchedule'

const {
  acceptMyRequestMock,
  fetchMyCoworkersMock,
  fetchMyOffersMock,
  fetchMyRequestsMock,
  fetchMyScheduleMock,
  fetchMyTeamScheduleMock,
} = vi.hoisted(() => ({
  acceptMyRequestMock: vi.fn(),
  fetchMyCoworkersMock: vi.fn(),
  fetchMyOffersMock: vi.fn(),
  fetchMyRequestsMock: vi.fn(),
  fetchMyScheduleMock: vi.fn(),
  fetchMyTeamScheduleMock: vi.fn(),
}))

vi.mock('../../api/employees/employeeSchedule', () => ({
  acceptMyRequest: acceptMyRequestMock,
  cancelMyRequest: vi.fn(),
  createMyRequest: vi.fn(),
  fetchMyAvailability: vi.fn(),
  fetchMyCoworkers: fetchMyCoworkersMock,
  fetchMyOffers: fetchMyOffersMock,
  fetchMyRequests: fetchMyRequestsMock,
  fetchMySchedule: fetchMyScheduleMock,
  fetchMyTeamSchedule: fetchMyTeamScheduleMock,
  saveMyAvailability: vi.fn(),
  withdrawMyRequest: vi.fn(),
}))

const selectedSwap: ScheduleRequest = {
  id: 'request-1',
  employee_id: 'employee-a',
  employee_name: 'Employee A',
  request_type: 'swap',
  shift_id: 'shift-a',
  shift_starts_at: '2026-08-28T09:00:00Z',
  shift_ends_at: '2026-08-28T17:00:00Z',
  shift_role: 'Opening',
  shift_department: null,
  target_employee_id: 'employee-b',
  target_employee_name: 'Employee B',
  counter_shift_id: 'shift-b',
  counterparty_confirmed_at: null,
  counter_shift_starts_at: '2026-08-29T12:00:00Z',
  counter_shift_ends_at: '2026-08-29T20:00:00Z',
  counter_shift_role: 'Closing',
  counter_shift_department: null,
  unavailable_start: null,
  unavailable_end: null,
  reason: null,
  status: 'awaiting_counterparty',
  review_notes: null,
  reviewed_at: null,
  created_at: '2026-08-27T12:00:00Z',
}

const employeeAShift: Shift = {
  id: 'shift-a',
  location_id: null,
  template_id: null,
  series_id: null,
  role: 'Opening',
  department: null,
  starts_at: '2026-08-28T09:00:00Z',
  ends_at: '2026-08-28T17:00:00Z',
  break_minutes: 0,
  required_staff: 1,
  color: null,
  notes: null,
  status: 'published',
  kind: 'work',
  training_requirement_id: null,
  job_id: null,
  published_at: '2026-08-27T12:00:00Z',
  assignments: [{ employee_id: 'employee-a', name: 'Employee A', job_title: null, status: 'assigned', availability_overridden: false, availability_override_at: null }],
}

const employeeBSameDayShift: Shift = {
  ...employeeAShift,
  id: 'shift-b',
  role: 'Closing',
  starts_at: '2026-08-28T17:00:00Z',
  ends_at: '2026-08-28T21:00:00Z',
  assignments: [{ employee_id: 'employee-b', name: 'Employee B', job_title: null, status: 'assigned', availability_overridden: false, availability_override_at: null }],
}

describe('PortalSchedule swap acceptance', () => {
  beforeEach(() => {
    fetchMyScheduleMock.mockResolvedValue({ shifts: [] })
    fetchMyTeamScheduleMock.mockResolvedValue({ shifts: [] })
    fetchMyRequestsMock.mockResolvedValue({ requests: [] })
    fetchMyOffersMock.mockResolvedValue({ offers: [selectedSwap] })
    fetchMyCoworkersMock.mockResolvedValue({ employees: [] })
    acceptMyRequestMock.mockResolvedValue({ ...selectedSwap, status: 'awaiting_manager' })
  })

  it('accepts the counter-shift selected by the requester', async () => {
    render(<ToastProvider><PortalSchedule /></ToastProvider>)

    fireEvent.click(await screen.findByRole('button', { name: 'Accept' }))

    await waitFor(() => expect(acceptMyRequestMock).toHaveBeenCalledWith('request-1', null))
    expect(screen.queryByText('Choose your shift to trade')).not.toBeInTheDocument()
  })

  it('lists the selected coworker’s same-day shift for a swap', async () => {
    fetchMyScheduleMock.mockResolvedValue({ shifts: [employeeAShift] })
    fetchMyTeamScheduleMock.mockResolvedValue({ shifts: [employeeAShift, employeeBSameDayShift] })
    fetchMyCoworkersMock.mockResolvedValue({ employees: [{ id: 'employee-b', name: 'Employee B' }] })

    render(<ToastProvider><PortalSchedule /></ToastProvider>)

    fireEvent.click(await screen.findByRole('button', { name: 'Swap' }))
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'employee-b' } })

    expect(await screen.findByRole('option', { name: /Fri 8\/28 5p.*9p.*Closing/ })).toBeInTheDocument()
  })
})
