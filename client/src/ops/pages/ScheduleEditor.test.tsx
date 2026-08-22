import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScheduleEditor from './ScheduleEditor'

const { useMeMock, useEditorMock, useLocationScopeMock, getScheduleHuumeSessionMock, sendMessageStreamMock } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  useEditorMock: vi.fn(),
  useLocationScopeMock: vi.fn(),
  getScheduleHuumeSessionMock: vi.fn(),
  sendMessageStreamMock: vi.fn(() => new AbortController()),
}))

vi.mock('../../hooks/useMe', () => ({ useMe: useMeMock }))
vi.mock('../../hooks/employees/useScheduleEditor', () => ({ useScheduleEditor: useEditorMock }))
vi.mock('../../api/employees/scheduleChat', () => ({
  getScheduleHuumeSession: getScheduleHuumeSessionMock,
}))
vi.mock('../../work/api/matchaWork/messaging', () => ({
  sendMessageStream: sendMessageStreamMock,
}))
vi.mock('../../hooks/useLocationScope', async () => {
  const actual = await vi.importActual<typeof import('../../hooks/useLocationScope')>('../../hooks/useLocationScope')
  return { ...actual, useLocationScope: useLocationScopeMock }
})

const shift = {
  id: 'shift-1', starts_at: '2026-08-09T09:00:00Z', ends_at: '2026-08-09T17:00:00Z',
  assignments: [], role: 'Opener', department: null, location_id: null,
  template_id: null, series_id: null, break_minutes: 30, required_staff: 1,
  color: null, notes: null, status: 'draft', kind: 'work', training_requirement_id: null, job_id: null,
  published_at: null,
}

describe('ScheduleEditor', () => {
  beforeEach(() => {
    getScheduleHuumeSessionMock.mockResolvedValue({
      session_id: 'session-1', thread_id: 'thread-1', location_id: 'loc1',
      week_start: '2026-08-09', week_end: '2026-08-16', messages: [], current_state: {}, version: 1,
    })
    useMeMock.mockReturnValue({
      me: { profile: { name: 'Jamie Rivera' } },
      hasFeature: () => false,
    })
    useLocationScopeMock.mockReturnValue({
      locationId: 'loc1',
      setLocationId: vi.fn(),
      locations: [{ id: 'loc1', name: 'Wilshire', city: 'Los Angeles', state: 'CA', is_active: true }],
      loading: false,
    })
    useEditorMock.mockReturnValue({
      shifts: [shift],
      roster: [{ id: 'e1', name: 'Aisha Rivera', job_title: 'Manager', department: null, job_ids: [] }],
      rosterFlags: null,
      summary: { total_shifts: 1, published: 0, draft: 1, open_shifts: 1, assigned: 0 },
      loading: false,
      saveState: 'saved',
      lastSavedAt: null,
      pendingKeys: new Set(),
      createDraft: vi.fn().mockResolvedValue(null),
      updateShiftDraft: vi.fn().mockResolvedValue(null),
      moveShift: vi.fn().mockResolvedValue(null),
      resizeShift: vi.fn().mockResolvedValue(null),
      assignToShift: vi.fn().mockResolvedValue(null),
      moveEmployee: vi.fn().mockResolvedValue(null),
      unassignFromShift: vi.fn().mockResolvedValue(null),
      removeShift: vi.fn().mockResolvedValue(false),
      publishWeek: vi.fn().mockResolvedValue(undefined),
    })
  })

  it('renders the roster and seven-day editor grid', () => {
    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )
    expect(screen.getByText('Roster')).toBeInTheDocument()
    expect(screen.getByText('Aisha Rivera')).toBeInTheDocument()
    expect(screen.getByText('Week of 2026-08-09')).toBeInTheDocument()
    expect(screen.getAllByText(/8\/9|8\/10|8\/11|8\/12|8\/13|8\/14|8\/15/).length).toBeGreaterThanOrEqual(7)
    expect(screen.getByText('Opener')).toBeInTheDocument()
  })

  it('keeps roster scrolling independent from the schedule grid', () => {
    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )
    const roster = screen.getByText('Roster').closest('aside')
    const employeeList = screen.getByText('Aisha Rivera').closest('button')?.parentElement

    expect(roster).toHaveClass('lg:h-full')
    expect(employeeList).toHaveClass('overflow-y-auto')
  })

  it('opens the personalized Huume schedule assistant', async () => {
    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Ask Huume' }))

    expect(screen.getByText('Huume · Schedule assistant')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/Hi, Jamie/)).toBeInTheDocument())
  })

  it('resets the assistant conversation when the schedule scope changes', async () => {
    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Ask Huume' }))
    await waitFor(() => expect(screen.getByPlaceholderText('Try: add an opener Monday')).not.toBeDisabled())
    fireEvent.change(screen.getByPlaceholderText('Try: add an opener Monday'), {
      target: { value: "Hey Huume, let's make schedules" },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    expect(screen.getByText("Hey Huume, let's make schedules")).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Next week' }))

    await waitFor(() => {
      expect(screen.queryByText("Hey Huume, let's make schedules")).not.toBeInTheDocument()
    })
    expect(screen.getByText(/Hi, Jamie/)).toBeInTheDocument()
  })
})
