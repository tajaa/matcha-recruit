import { StrictMode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScheduleEditor from './ScheduleEditor'

const { useMeMock, useEditorMock, useLocationScopeMock, getScheduleHuumeSessionMock, getScheduleSuggestionStatusMock, sendMessageStreamMock, reloadMock } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  useEditorMock: vi.fn(),
  useLocationScopeMock: vi.fn(),
  getScheduleHuumeSessionMock: vi.fn(),
  getScheduleSuggestionStatusMock: vi.fn(),
  sendMessageStreamMock: vi.fn(() => new AbortController()),
  reloadMock: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('../../hooks/useMe', () => ({ useMe: useMeMock }))
vi.mock('../../hooks/employees/useScheduleEditor', () => ({ useScheduleEditor: useEditorMock }))
vi.mock('../../components/employees/schedule-editor/ScheduleJobsTab', async () => {
  const { useState } = await vi.importActual<typeof import('react')>('react')
  return {
    default: ({ locationId }: { locationId: string }) => {
      const [draft, setDraft] = useState('')
      return <div><div>Jobs configuration</div><div>Location {locationId}</div><input aria-label="Job draft" value={draft} onChange={(event) => setDraft(event.target.value)} /></div>
    },
  }
})
vi.mock('../../api/employees/scheduleAssistant', () => ({
  getScheduleHuumeSession: getScheduleHuumeSessionMock,
  getScheduleSuggestionStatus: getScheduleSuggestionStatusMock,
  transcribeScheduleVoice: vi.fn(),
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
    reloadMock.mockClear()
    sendMessageStreamMock.mockReset().mockReturnValue(new AbortController())
    getScheduleHuumeSessionMock.mockResolvedValue({
      session_id: 'session-1', thread_id: 'thread-1', location_id: 'loc1',
      week_start: '2026-08-09', week_end: '2026-08-16', messages: [], current_state: {}, version: 1,
    })
    getScheduleSuggestionStatusMock.mockResolvedValue({
      available: false, generation_run_id: null, week_start: null, created_at: null,
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
      reload: reloadMock,
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

  it('does not load schedule data for a stale location URL', async () => {
    const setLocationId = vi.fn()
    useLocationScopeMock.mockReturnValue({
      locationId: 'deleted-location',
      setLocationId,
      locations: [{ id: 'loc1', name: 'Wilshire', city: 'Los Angeles', state: 'CA', is_active: true }],
      loading: false,
    })

    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=deleted-location']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )

    expect(useEditorMock).toHaveBeenCalledWith('2026-08-09', '', expect.any(Object))
    await waitFor(() => expect(setLocationId).toHaveBeenCalledWith(''))
    expect(screen.getByText('Pick a location to see its schedule.')).toBeInTheDocument()
  })

  it('opens location job and credential configuration from the editor toolbar', () => {
    useMeMock.mockReturnValue({
      me: { profile: { name: 'Jamie Rivera' } },
      hasFeature: (feature: string) => feature === 'credential_templates',
    })
    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Jobs & credentials' }))

    expect(screen.getByText('Jobs configuration')).toBeInTheDocument()
  })

  it('shows jobs without credential controls when credential templates are disabled', () => {
    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Jobs' })).toHaveAttribute('title', 'Configure location jobs')
  })

  it('keeps jobs and Huume as mutually exclusive views', async () => {
    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Ask Huume' }))
    expect(screen.getByText('Huume · Schedule assistant')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Jobs' }))
    expect(screen.getByText('Jobs configuration')).toBeInTheDocument()
    expect(screen.queryByText('Huume · Schedule assistant')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Ask Huume' }))
    expect(screen.queryByText('Jobs configuration')).not.toBeInTheDocument()
    expect(screen.getByText('Huume · Schedule assistant')).toBeInTheDocument()
  })

  it('clears the job draft when the location changes', () => {
    let locationId = 'loc1'
    const setLocationId = vi.fn((next: string) => { locationId = next })
    const locations = [
      { id: 'loc1', name: 'Wilshire', city: 'Los Angeles', state: 'CA', is_active: true },
      { id: 'loc2', name: 'Venice', city: 'Los Angeles', state: 'CA', is_active: true },
    ]
    useLocationScopeMock.mockImplementation(() => ({ locationId, setLocationId, locations, loading: false }))

    const view = render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Jobs' }))
    fireEvent.change(screen.getByLabelText('Job draft'), { target: { value: 'Opener' } })

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'loc2' } })
    view.rerender(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Location loc2')).toBeInTheDocument()
    expect(screen.getByLabelText('Job draft')).toHaveValue('')
  })

  it('opens the shift break planner when assignment needs a compliant break', async () => {
    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )
    const options = useEditorMock.mock.calls[0]?.[2] as {
      onMealBreakRequired: (affectedShift: typeof shift, employeeId: string, message: string) => void
    }

    act(() => options.onMealBreakRequired(shift, 'e1', 'A 30-minute meal break is required.'))

    expect(await screen.findByLabelText('Planned break (minutes)')).toHaveValue(30)
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

  it('surfaces an automatically prepared schedule for review', async () => {
    getScheduleSuggestionStatusMock.mockResolvedValue({
      available: true, generation_run_id: 'generation-1', week_start: '2026-08-09',
      created_at: '2026-08-24T16:00:00Z',
    })
    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Huume prepared a suggested schedule for the week of 2026-08-09.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review suggestion' }))
    expect(screen.getByText('Huume · Schedule assistant')).toBeInTheDocument()
  })

  it('renders the automatically prepared proposal without requiring a prompt', async () => {
    getScheduleHuumeSessionMock.mockResolvedValue({
      session_id: 'session-1', thread_id: 'thread-1', location_id: 'loc1',
      week_start: '2026-08-09', week_end: '2026-08-16', messages: [], version: 2,
      current_state: {
        huume_action: {
          type: 'schedule_week_draft', status: 'proposed', confirm_id: 'auto1234',
          generation_run_id: 'generation-1', location_id: 'loc1', week_start: '2026-08-09',
          source_mode: 'template', week_template_id: 'template-1', origin: 'automatic',
          auto_generated: true, summary: 'Prepared the week.',
          metrics: { shift_count: 1, required_positions: 1, fixed_positions: 0, overstaffed_positions: 0, proposed_positions: 1, filled_positions: 1, open_positions: 0 },
          unfilled: [], schedule_preview: [{ shift_key: 'shift-1', starts_at: '2026-08-09T09:00:00Z', ends_at: '2026-08-09T17:00:00Z', role: 'Opener', required_staff: 1, assignment_names: ['Aisha Rivera'], existing_assignment_count: 0 }],
          preview_truncated: false,
        },
      },
    })
    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Ask Huume' }))
    expect(await screen.findByText(/Huume prepared this suggestion automatically/)).toBeInTheDocument()
    expect(screen.getByText('Automatically by Huume')).toBeInTheDocument()
    expect(screen.queryByText(/Hi, Jamie/)).not.toBeInTheDocument()
  })

  it('clears the automatic suggestion banner when the proposal is no longer active', async () => {
    getScheduleSuggestionStatusMock.mockResolvedValue({
      available: true, generation_run_id: 'generation-1', week_start: '2026-08-09',
      created_at: '2026-08-24T16:00:00Z',
    })
    getScheduleHuumeSessionMock.mockResolvedValue({
      session_id: 'session-1', thread_id: 'thread-1', location_id: 'loc1',
      week_start: '2026-08-09', week_end: '2026-08-16', messages: [], version: 3,
      current_state: {
        huume_action: {
          type: 'schedule_week_draft', status: 'cancelled', confirm_id: 'auto1234',
          generation_run_id: 'generation-1', location_id: 'loc1', week_start: '2026-08-09',
          source_mode: 'template', week_template_id: 'template-1', origin: 'automatic',
          auto_generated: true,
        },
      },
    })
    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Huume prepared a suggested schedule for the week of 2026-08-09.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review suggestion' }))

    await waitFor(() => {
      expect(screen.queryByText('Huume prepared a suggested schedule for the week of 2026-08-09.')).not.toBeInTheDocument()
    })
  })

  it('sends selected blocks as authoritative Huume context', async () => {
    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Select Opener for Huume' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask Huume' }))
    const input = await screen.findByPlaceholderText('Try: add an opener Monday')
    fireEvent.change(input, { target: { value: 'Move the selected person' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))

    expect(screen.getByText('Using 1 selected shift as context')).toBeInTheDocument()
    expect(sendMessageStreamMock).toHaveBeenCalledWith(
      'thread-1',
      expect.stringContaining('Selected schedule blocks — authoritative context for this request:'),
      expect.any(Object),
    )
    const [, sentContent] = sendMessageStreamMock.mock.calls[0] as unknown as [unknown, string, unknown]
    expect(sentContent).toContain('Sun 8/9 · 9a–5p · Opener · open · staffing: 0/1')
  })

  it('opens the assistant when React StrictMode replays effects', async () => {
    render(
      <StrictMode>
        <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
          <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
        </MemoryRouter>
      </StrictMode>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Ask Huume' }))

    await waitFor(() => expect(screen.getByPlaceholderText('Try: add an opener Monday')).not.toBeDisabled())
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

  it('shows a session error with a retry instead of leaving the composer inert', async () => {
    getScheduleHuumeSessionMock
      .mockRejectedValueOnce(new Error('Session unavailable'))
      .mockResolvedValueOnce({
        session_id: 'session-1', thread_id: 'thread-1', location_id: 'loc1',
        week_start: '2026-08-09', week_end: '2026-08-16', messages: [], current_state: {}, version: 1,
      })
    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Ask Huume' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Session unavailable')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(screen.getByPlaceholderText('Try: add an opener Monday')).not.toBeDisabled())
  })

  it('reloads once for an applied action and ignores its persistent status later', async () => {
    const callbacks: Array<{ onComplete: (response: unknown) => void }> = []
    sendMessageStreamMock.mockImplementation((...args: unknown[]) => {
      const options = args[2] as { onComplete: (response: unknown) => void }
      callbacks.push(options)
      return new AbortController()
    })
    render(
      <MemoryRouter initialEntries={['/ops/schedule/editor?week=2026-08-09&location=loc1']}>
        <Routes><Route path="/ops/schedule/editor" element={<ScheduleEditor />} /></Routes>
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Ask Huume' }))
    const input = await screen.findByPlaceholderText('Try: add an opener Monday')
    fireEvent.change(input, { target: { value: 'Apply the note' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    callbacks[0].onComplete({
      user_message: { id: 'u1', thread_id: 'thread-1', role: 'user', content: 'Apply the note', version_created: null, metadata: null, created_at: new Date().toISOString() },
      assistant_message: { id: 'a1', thread_id: 'thread-1', role: 'assistant', content: 'Applied.', version_created: 2, metadata: { huume_run_id: 'run-1' }, created_at: new Date().toISOString() },
      current_state: { huume_action: { status: 'applied', confirm_id: 'confirm-1' } },
    })
    await waitFor(() => expect(reloadMock).toHaveBeenCalledTimes(1))

    fireEvent.change(screen.getByPlaceholderText('Try: add an opener Monday'), { target: { value: 'What changed?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    callbacks[1].onComplete({
      user_message: { id: 'u2', thread_id: 'thread-1', role: 'user', content: 'What changed?', version_created: null, metadata: null, created_at: new Date().toISOString() },
      assistant_message: { id: 'a2', thread_id: 'thread-1', role: 'assistant', content: 'The note is still applied.', version_created: 3, metadata: { huume_run_id: 'run-2' }, created_at: new Date().toISOString() },
      current_state: { huume_action: { status: 'applied', confirm_id: 'confirm-1' } },
    })
    await waitFor(() => expect(screen.getByText('The note is still applied.')).toBeInTheDocument())
    expect(reloadMock).toHaveBeenCalledTimes(1)
  })
})
