import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/ui'
import { addDays, toISODate, type ScheduleRequest, type Shift } from '../../types/employeeSchedule'
import PortalSchedule from './PortalSchedule'

const {
  acceptMyRequestMock,
  fetchMyAvailabilityMock,
  submitMyAvailabilityRequestMock,
  fetchMyCoworkersMock,
  fetchMyOffersMock,
  fetchMyRequestsMock,
  fetchMyScheduleMock,
  fetchMyTeamScheduleMock,
} = vi.hoisted(() => ({
  acceptMyRequestMock: vi.fn(),
  fetchMyAvailabilityMock: vi.fn(),
  submitMyAvailabilityRequestMock: vi.fn(),
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
  fetchMyAvailability: fetchMyAvailabilityMock,
  fetchMyCoworkers: fetchMyCoworkersMock,
  fetchMyOffers: fetchMyOffersMock,
  fetchMyRequests: fetchMyRequestsMock,
  fetchMySchedule: fetchMyScheduleMock,
  fetchMyTeamSchedule: fetchMyTeamScheduleMock,
  submitMyAvailabilityRequest: submitMyAvailabilityRequestMock,
  withdrawMyRequest: vi.fn(),
}))

// Fixtures ride on today, not on fixed calendar dates: the schedule tab only
// renders the four-week horizon it fetched, so a hardcoded August would fall
// outside every week section and silently render nothing.
const TODAY = toISODate(new Date())
const TOMORROW = addDays(TODAY, 1)
const WEEK_THREE_DAY = addDays(TODAY, 16)

function renderPortal(entry = '/portal/schedule') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <ToastProvider><PortalSchedule /></ToastProvider>
    </MemoryRouter>,
  )
}

const selectedSwap: ScheduleRequest = {
  id: 'request-1',
  employee_id: 'employee-a',
  employee_name: 'Employee A',
  request_type: 'swap',
  shift_id: 'shift-a',
  shift_starts_at: `${TOMORROW}T09:00:00Z`,
  shift_ends_at: `${TOMORROW}T17:00:00Z`,
  shift_role: 'Opening',
  shift_department: null,
  target_employee_id: 'employee-b',
  target_employee_name: 'Employee B',
  counter_shift_id: 'shift-b',
  counterparty_confirmed_at: null,
  counter_shift_starts_at: `${addDays(TOMORROW, 1)}T12:00:00Z`,
  counter_shift_ends_at: `${addDays(TOMORROW, 1)}T20:00:00Z`,
  counter_shift_role: 'Closing',
  counter_shift_department: null,
  unavailable_start: null,
  unavailable_end: null,
  proposed_availability: null,
  availability_effective_on: null,
  availability_applied_at: null,
  reason: null,
  status: 'awaiting_counterparty',
  review_notes: null,
  reviewed_at: null,
  created_at: `${TODAY}T12:00:00Z`,
}

const employeeAShift: Shift = {
  id: 'shift-a',
  location_id: null,
  template_id: null,
  series_id: null,
  role: 'Opening',
  department: null,
  starts_at: `${TOMORROW}T09:00:00Z`,
  ends_at: `${TOMORROW}T17:00:00Z`,
  break_minutes: 0,
  required_staff: 1,
  color: null,
  notes: null,
  status: 'published',
  kind: 'work',
  training_requirement_id: null,
  job_id: null,
  published_at: `${TODAY}T12:00:00Z`,
  assignments: [{ employee_id: 'employee-a', name: 'Employee A', job_title: null, status: 'assigned', availability_overridden: false, availability_override_at: null }],
}

const employeeBSameDayShift: Shift = {
  ...employeeAShift,
  id: 'shift-b',
  role: 'Closing',
  starts_at: `${TOMORROW}T17:00:00Z`,
  ends_at: `${TOMORROW}T21:00:00Z`,
  assignments: [{ employee_id: 'employee-b', name: 'Employee B', job_title: null, status: 'assigned', availability_overridden: false, availability_override_at: null }],
}

beforeEach(() => {
  fetchMyScheduleMock.mockResolvedValue({ shifts: [] })
  fetchMyTeamScheduleMock.mockResolvedValue({ shifts: [] })
  fetchMyRequestsMock.mockResolvedValue({ requests: [] })
  fetchMyOffersMock.mockResolvedValue({ offers: [selectedSwap] })
  fetchMyCoworkersMock.mockResolvedValue({ employees: [] })
  acceptMyRequestMock.mockResolvedValue({ ...selectedSwap, status: 'awaiting_manager' })
  fetchMyAvailabilityMock.mockResolvedValue({
    availability_state: 'always_available', windows: [], pending_request: null,
  })
  submitMyAvailabilityRequestMock.mockResolvedValue({
    ...selectedSwap, request_type: 'availability', status: 'awaiting_manager',
  })
})

describe('PortalSchedule tabs', () => {
  it('opens on the schedule and keeps availability and requests off it', async () => {
    fetchMyScheduleMock.mockResolvedValue({ shifts: [employeeAShift] })

    renderPortal()

    expect(await screen.findByRole('heading', { name: 'My shifts' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'My weekly availability' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'My requests' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /request time off/i })).not.toBeInTheDocument()
  })

  it('honours the tab named in the URL on a refresh or a back navigation', async () => {
    renderPortal('/portal/schedule?tab=requests')

    expect(await screen.findByRole('heading', { name: 'My requests' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'My shifts' })).not.toBeInTheDocument()
  })

  it('falls back to the schedule for an unknown tab', async () => {
    renderPortal('/portal/schedule?tab=nonsense')

    expect(await screen.findByRole('heading', { name: 'My shifts' })).toBeInTheDocument()
  })

  it('counts the offers waiting on the employee in the requests tab label', async () => {
    renderPortal()

    expect(await screen.findByRole('button', { name: 'My Requests (1)' })).toBeInTheDocument()
  })
})

describe('PortalSchedule week sections', () => {
  it('shows only the selected week and jumps to the first week with a shift', async () => {
    const laterShift = { ...employeeAShift, id: 'shift-later', role: 'Closing', starts_at: `${WEEK_THREE_DAY}T09:00:00Z`, ends_at: `${WEEK_THREE_DAY}T17:00:00Z` }
    fetchMyScheduleMock.mockResolvedValue({ shifts: [laterShift] })

    renderPortal()

    const section = (await screen.findByRole('heading', { name: 'My shifts' })).closest('section')!
    expect(within(section).getByText('Closing')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Previous week' }))
    expect(within(section).queryByText('Closing')).not.toBeInTheDocument()
    expect(within(section).getByText(/No published shifts for/)).toBeInTheDocument()
  })

  it('marks today and tomorrow on the day headings', async () => {
    fetchMyScheduleMock.mockResolvedValue({
      shifts: [
        { ...employeeAShift, id: 'shift-today', starts_at: `${TODAY}T09:00:00Z`, ends_at: `${TODAY}T17:00:00Z` },
        employeeAShift,
      ],
    })

    renderPortal()

    expect(await screen.findByText(/· Today$/)).toBeInTheDocument()
    expect(screen.getByText(/· Tomorrow$/)).toBeInTheDocument()
  })
})

describe('PortalSchedule swap acceptance', () => {
  it('accepts the counter-shift selected by the requester', async () => {
    renderPortal('/portal/schedule?tab=requests')

    fireEvent.click(await screen.findByRole('button', { name: 'Accept' }))

    await waitFor(() => expect(acceptMyRequestMock).toHaveBeenCalledWith('request-1', null))
    expect(screen.queryByText('Choose your shift to trade')).not.toBeInTheDocument()
  })

  it('lists the selected coworker’s same-day shift for a swap', async () => {
    fetchMyScheduleMock.mockResolvedValue({ shifts: [employeeAShift] })
    fetchMyTeamScheduleMock.mockResolvedValue({ shifts: [employeeAShift, employeeBSameDayShift] })
    fetchMyCoworkersMock.mockResolvedValue({ employees: [{ id: 'employee-b', name: 'Employee B' }] })

    renderPortal()

    fireEvent.click(await screen.findByRole('button', { name: 'Swap' }))
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'employee-b' } })

    expect(await screen.findByRole('option', { name: /5p.*9p.*Closing/ })).toBeInTheDocument()
  })
})

describe('PortalSchedule notes', () => {
  it('renders trimmed notes in personal and full schedule cards', async () => {
    const shiftWithNote = { ...employeeAShift, notes: '  Bring ID\nat 8am  ' }
    fetchMyScheduleMock.mockResolvedValue({ shifts: [shiftWithNote] })
    fetchMyTeamScheduleMock.mockResolvedValue({ shifts: [shiftWithNote] })

    renderPortal()

    const myShifts = (await screen.findByRole('heading', { name: 'My shifts' })).closest('section')!
    expect(within(myShifts).getByText(/Schedule note:/).textContent).toBe('Schedule note: Bring ID\nat 8am')

    fireEvent.click(screen.getByRole('button', { name: 'Everyone' }))

    const fullSchedule = screen.getByRole('heading', { name: 'Full schedule' }).closest('section')!
    expect(within(fullSchedule).getByText(/Schedule note:/).textContent).toBe('Schedule note: Bring ID\nat 8am')
  })

  it('omits whitespace-only notes', async () => {
    const shiftWithBlankNote = { ...employeeAShift, notes: ' \n\t ' }
    fetchMyScheduleMock.mockResolvedValue({ shifts: [shiftWithBlankNote] })
    fetchMyTeamScheduleMock.mockResolvedValue({ shifts: [shiftWithBlankNote] })

    renderPortal()

    await screen.findByRole('heading', { name: 'My shifts' })
    expect(screen.queryByText(/Schedule note:/)).not.toBeInTheDocument()
  })
})

describe('PortalSchedule time-off requests', () => {
  it('warns and blocks time off for a visible week with published shifts', async () => {
    fetchMyTeamScheduleMock.mockResolvedValue({
      shifts: [{ ...employeeAShift, starts_at: `${TOMORROW}T09:00:00Z`, ends_at: `${TOMORROW}T17:00:00Z` }],
    })

    renderPortal('/portal/schedule?tab=requests')

    fireEvent.click(await screen.findByRole('button', { name: /request time off/i }))
    for (const input of screen.getAllByDisplayValue(TODAY)) {
      fireEvent.change(input, { target: { value: TOMORROW } })
    }

    expect(screen.getByRole('alert')).toHaveTextContent('Time-off requests cannot be submitted for a week with published shifts.')
    expect(screen.getByRole('button', { name: 'Submit request' })).toBeDisabled()
  })
})

describe('PortalSchedule availability changes', () => {
  const availabilityRequest: ScheduleRequest = {
    ...selectedSwap,
    id: 'availability-1',
    request_type: 'availability',
    shift_id: null,
    shift_starts_at: null,
    shift_ends_at: null,
    target_employee_id: null,
    counter_shift_id: null,
    counter_shift_starts_at: null,
    counter_shift_ends_at: null,
    status: 'awaiting_manager',
    availability_effective_on: '2099-10-05',
    proposed_availability: {
      availability_state: 'windows',
      windows: [{ weekday: 1, start_time: '09:00', end_time: '17:00' }],
    },
  }

  it('loads the availability tab without an extra disclosure click', async () => {
    renderPortal('/portal/schedule?tab=availability')

    expect(await screen.findByRole('heading', { name: 'My weekly availability' })).toBeInTheDocument()
    await waitFor(() => expect(fetchMyAvailabilityMock).toHaveBeenCalled())
  })

  it('submits a change for approval instead of saving it', async () => {
    renderPortal('/portal/schedule?tab=availability')

    fireEvent.click(await screen.findByRole('button', { name: /send for approval/i }))

    await waitFor(() => expect(submitMyAvailabilityRequestMock).toHaveBeenCalled())
    const payload = submitMyAvailabilityRequestMock.mock.calls[0][0]
    expect(payload.availability).toEqual({ availability_state: 'always_available', windows: [] })
    expect(payload.effective_on).toBe(addDays(TODAY, 14))
  })

  it('shows a pending change and blocks a second one', async () => {
    fetchMyAvailabilityMock.mockResolvedValue({
      availability_state: 'windows',
      windows: [{ weekday: 1, start_time: '09:00', end_time: '17:00' }],
      pending_request: availabilityRequest,
    })

    renderPortal('/portal/schedule?tab=availability')

    expect(await screen.findByText('Awaiting manager approval')).toBeInTheDocument()
    expect(screen.getByText(/Starts 2099-10-05 · Mon 09:00–17:00/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send for approval/i })).toBeDisabled()
    expect(submitMyAvailabilityRequestMock).not.toHaveBeenCalled()
  })

  it('warns when the start date falls in a published week', async () => {
    const date = addDays(TODAY, 14)
    fetchMyTeamScheduleMock.mockResolvedValue({
      shifts: [{ ...employeeAShift, starts_at: `${date}T09:00:00Z`, ends_at: `${date}T17:00:00Z` }],
    })

    renderPortal('/portal/schedule?tab=availability')

    expect(await screen.findByRole('alert')).toHaveTextContent('That week is already published.')
    expect(screen.getByRole('button', { name: /send for approval/i })).toBeDisabled()
  })
})
