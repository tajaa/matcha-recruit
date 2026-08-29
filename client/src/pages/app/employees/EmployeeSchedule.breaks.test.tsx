import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../../components/ui'
import { ApiError } from '../../../api/client'
import EmployeeSchedule from './EmployeeSchedule'

const {
  createWeekTemplateMock,
  fetchWeekMock,
  fetchWeekTemplatesMock,
  publishRangeMock,
  updateShiftMock,
  useLocationScopeMock,
  useMeMock,
  getScheduleSuggestionStatusMock,
} = vi.hoisted(() => ({
  createWeekTemplateMock: vi.fn(),
  fetchWeekMock: vi.fn(),
  fetchWeekTemplatesMock: vi.fn(),
  publishRangeMock: vi.fn(),
  updateShiftMock: vi.fn(),
  useLocationScopeMock: vi.fn(),
  useMeMock: vi.fn(),
  getScheduleSuggestionStatusMock: vi.fn(),
}))

vi.mock('../../../hooks/useMe', () => ({ useMe: useMeMock }))
vi.mock('../../../hooks/useLocationScope', () => ({
  locationLabel: (location: { name?: string | null; city: string; state: string }) => location.name ?? `${location.city}, ${location.state}`,
  useLocationScope: useLocationScopeMock,
}))
vi.mock('../../../components/employees/ScheduleLawPanel', () => ({ default: () => null }))
vi.mock('../../../components/employees/onboarding/ScheduleHelperWizard', () => ({ default: () => null }))
vi.mock('../../../components/employees/AutoSchedulesTab', () => ({
  default: () => <div>Auto schedule settings</div>,
}))
vi.mock('../../../api/employees/scheduleAssistant', () => ({
  getScheduleSuggestionStatus: getScheduleSuggestionStatusMock,
}))
vi.mock('../../../api/employees/employeeSchedule', () => ({
  assignEmployee: vi.fn(),
  createShift: vi.fn(),
  createWeekTemplate: createWeekTemplateMock,
  deleteShift: vi.fn(),
  deleteWeekTemplate: vi.fn(),
  duplicateShift: vi.fn(),
  fetchEligibilityCases: vi.fn().mockResolvedValue({ cases: [] }),
  fetchRequests: vi.fn().mockResolvedValue({ requests: [] }),
  fetchWeek: fetchWeekMock,
  fetchWeekTemplates: fetchWeekTemplatesMock,
  generateFromWeekTemplate: vi.fn(),
  publishRange: publishRangeMock,
  publishShift: vi.fn(),
  reviewRequest: vi.fn(),
  unassignEmployee: vi.fn(),
  updateShift: updateShiftMock,
}))

const shift = {
  id: 'shift-1',
  starts_at: '2026-08-23T09:00:00Z',
  ends_at: '2026-08-23T17:00:00Z',
  assignments: [],
  role: 'Box Office',
  department: null,
  location_id: 'loc-1',
  template_id: null,
  series_id: null,
  break_minutes: 0,
  required_staff: 1,
  color: null,
  notes: null,
  status: 'draft' as const,
  kind: 'work' as const,
  training_requirement_id: null,
  job_id: null,
  published_at: null,
}

function renderSchedule(initialEntry = '/ops/schedule') {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[initialEntry]}>
        <EmployeeSchedule />
      </MemoryRouter>
    </ToastProvider>,
  )
}

describe('EmployeeSchedule break planning', () => {
  beforeEach(() => {
    useMeMock.mockReturnValue({
      me: { user: { role: 'client' } },
      hasFeature: () => false,
      loading: false,
    })
    useLocationScopeMock.mockReturnValue({
      locationId: 'loc-1',
      setLocationId: vi.fn(),
      locations: [{ id: 'loc-1', name: 'Downtown', city: 'Los Angeles', state: 'CA', is_active: true }],
      loading: false,
    })
    fetchWeekMock.mockResolvedValue({
      week_start: '2026-08-23',
      location_id: 'loc-1',
      shifts: [shift],
      roster: [],
      roster_flags: null,
      summary: { total_shifts: 1, published: 0, draft: 1, open_shifts: 1, assigned: 0 },
    })
    fetchWeekTemplatesMock.mockResolvedValue({ week_templates: [] })
    updateShiftMock.mockImplementation(async (_id: string, payload: { break_minutes?: number }) => ({
      ...shift,
      break_minutes: payload.break_minutes ?? shift.break_minutes,
    }))
    createWeekTemplateMock.mockResolvedValue({ id: 'template-1', name: 'Standard Week', blocks: [] })
    publishRangeMock.mockReset()
    getScheduleSuggestionStatusMock.mockResolvedValue({
      available: false, generation_run_id: null, week_start: null, created_at: null,
    })
  })

  it('repairs an existing shift by saving planned break minutes', async () => {
    renderSchedule()

    expect(await screen.findByText('Planned break: none')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    const breakLabel = await screen.findByText('Planned break (minutes)')
    const breakInput = breakLabel.closest('label')?.querySelector('input')
    expect(breakInput).not.toBeNull()
    fireEvent.change(breakInput!, { target: { value: '30' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(updateShiftMock).toHaveBeenCalledWith(
      'shift-1',
      expect.objectContaining({ break_minutes: 30 }),
    ))
  })

  it('stores planned break minutes on a reusable template block', async () => {
    renderSchedule()

    fireEvent.click(await screen.findByRole('button', { name: 'Templates' }))
    fireEvent.click(await screen.findByRole('button', { name: 'New template' }))
    fireEvent.change(screen.getByLabelText('Template name'), { target: { value: 'Standard Week' } })
    fireEvent.change(screen.getByLabelText('Planned break (minutes)'), { target: { value: '30' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save template' }))

    await waitFor(() => expect(createWeekTemplateMock).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Standard Week',
      location_id: 'loc-1',
      blocks: [expect.objectContaining({ break_minutes: 30 })],
    })))
  })

  it('creates a weekly template with independent unassigned shift blocks', async () => {
    renderSchedule()

    fireEvent.click(await screen.findByRole('button', { name: 'Templates' }))
    fireEvent.click(await screen.findByRole('button', { name: 'New template' }))
    fireEvent.change(screen.getByLabelText('Template name'), { target: { value: 'Opening and closing' } })
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'Opener' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add shift' }))
    fireEvent.change(screen.getAllByLabelText('Role')[1], { target: { value: 'Closer' } })
    fireEvent.change(screen.getAllByLabelText('Start')[1], { target: { value: '16:00' } })
    fireEvent.change(screen.getAllByLabelText('End')[1], { target: { value: '23:00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save template' }))

    await waitFor(() => expect(createWeekTemplateMock).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Opening and closing',
      blocks: [
        expect.objectContaining({ name: 'Opener', role: 'Opener' }),
        expect.objectContaining({ name: 'Closer', role: 'Closer', start_time: '16:00:00', end_time: '23:00:00' }),
      ],
    })))
  })

  it('requires at least one weekday for every template shift', async () => {
    renderSchedule()

    fireEvent.click(await screen.findByRole('button', { name: 'Templates' }))
    fireEvent.click(await screen.findByRole('button', { name: 'New template' }))
    fireEvent.change(screen.getByLabelText('Template name'), { target: { value: 'Incomplete week' } })
    for (const day of ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']) {
      fireEvent.click(screen.getByRole('button', { name: `${day} for shift 1` }))
    }

    expect(screen.getByText('Select at least one day for this shift.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save template' })).toBeDisabled()
  })

  it('caps a weekly template at the API limit of 40 shifts', async () => {
    renderSchedule()

    fireEvent.click(await screen.findByRole('button', { name: 'Templates' }))
    fireEvent.click(await screen.findByRole('button', { name: 'New template' }))
    const addShift = screen.getByRole('button', { name: 'Add shift' })
    for (let index = 1; index < 40; index += 1) fireEvent.click(addShift)

    expect(screen.getByText('Shift 40')).toBeInTheDocument()
    expect(addShift).toBeDisabled()
    expect(screen.getByText('Maximum 40 shifts per template.')).toBeInTheDocument()
  })

  it('shows a corrective message when location prerequisites block publication', async () => {
    publishRangeMock.mockRejectedValue(new ApiError('Request failed', 422, {
      detail: { code: 'schedule_location_not_ready' },
    }))
    renderSchedule()

    fireEvent.click(await screen.findByRole('button', { name: /Publish week/ }))

    expect(await screen.findByText("Complete this location's scheduling prerequisites before publishing.")).toBeInTheDocument()
  })

  it('links a prepared suggestion to its generated-week review', async () => {
    getScheduleSuggestionStatusMock.mockResolvedValue({
      available: true, generation_run_id: 'generation-1', week_start: '2026-08-30',
      created_at: '2026-08-28T16:00:00Z',
    })
    renderSchedule()

    expect(await screen.findByText('Huume prepared a suggested schedule for the week of 2026-08-30.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review suggestion' })).toHaveAttribute(
      'href', '/ops/schedule/editor?week=2026-08-30&location=loc-1',
    )
  })

  it('refreshes prepared suggestions when returning from auto schedules', async () => {
    renderSchedule('/ops/schedule?tab=auto-schedules')
    expect(await screen.findByText('Auto schedule settings')).toBeInTheDocument()
    expect(getScheduleSuggestionStatusMock).not.toHaveBeenCalled()

    getScheduleSuggestionStatusMock.mockResolvedValue({
      available: true, generation_run_id: 'generation-1', week_start: '2026-08-30',
      created_at: '2026-08-28T16:00:00Z',
    })
    fireEvent.click(screen.getByRole('button', { name: 'Schedule' }))

    expect(await screen.findByRole('link', { name: 'Review suggestion' })).toHaveAttribute(
      'href', '/ops/schedule/editor?week=2026-08-30&location=loc-1',
    )
  })
})
