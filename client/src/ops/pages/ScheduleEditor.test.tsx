import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScheduleEditor from './ScheduleEditor'

const { useMeMock, useEditorMock } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  useEditorMock: vi.fn(),
}))

vi.mock('../../hooks/useMe', () => ({ useMe: useMeMock }))
vi.mock('../../hooks/employees/useScheduleEditor', () => ({ useScheduleEditor: useEditorMock }))

const shift = {
  id: 'shift-1', starts_at: '2026-08-09T09:00:00Z', ends_at: '2026-08-09T17:00:00Z',
  assignments: [], role: 'Opener', department: null, location_id: null,
  template_id: null, series_id: null, break_minutes: 30, required_staff: 1,
  color: null, notes: null, status: 'draft', kind: 'work', training_requirement_id: null,
  published_at: null,
}

describe('ScheduleEditor', () => {
  beforeEach(() => {
    useMeMock.mockReturnValue({ hasFeature: () => false })
    useEditorMock.mockReturnValue({
      shifts: [shift],
      roster: [{ id: 'e1', name: 'Aisha Rivera', job_title: 'Manager', department: null }],
      rosterFlags: null,
      locations: [],
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
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09']}>
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
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )
    const roster = screen.getByText('Roster').closest('aside')
    const employeeList = screen.getByText('Aisha Rivera').closest('button')?.parentElement

    expect(roster).toHaveClass('lg:h-full')
    expect(employeeList).toHaveClass('overflow-y-auto')
  })
})
