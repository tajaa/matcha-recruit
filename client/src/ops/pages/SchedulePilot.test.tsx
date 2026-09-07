import { StrictMode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SchedulePilot from './SchedulePilot'

const {
  useMeMock, useEditorMock, useLocationScopeMock, useScheduleJobsMock,
  getSessionMock, listSessionsMock, adoptProposalMock, suggestionStatusMock,
  fetchLocationProfileMock, planningInputsMock, previewFillMock, applyFillMock, cancelFillMock,
  sendMessageStreamMock, reloadMock, reloadLocationsMock,
} = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  useEditorMock: vi.fn(),
  useLocationScopeMock: vi.fn(),
  useScheduleJobsMock: vi.fn(),
  getSessionMock: vi.fn(),
  listSessionsMock: vi.fn(),
  adoptProposalMock: vi.fn(),
  suggestionStatusMock: vi.fn(),
  fetchLocationProfileMock: vi.fn(),
  planningInputsMock: vi.fn(),
  previewFillMock: vi.fn(),
  applyFillMock: vi.fn(),
  cancelFillMock: vi.fn(),
  sendMessageStreamMock: vi.fn(),
  reloadMock: vi.fn().mockResolvedValue(undefined),
  reloadLocationsMock: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('../../hooks/useMe', () => ({ useMe: useMeMock }))
vi.mock('../../hooks/employees/useScheduleEditor', () => ({ useScheduleEditor: useEditorMock }))
vi.mock('../../hooks/employees/useScheduleJobs', () => ({ useScheduleJobs: useScheduleJobsMock }))
vi.mock('../../hooks/useLocationScope', async () => {
  const actual = await vi.importActual<typeof import('../../hooks/useLocationScope')>('../../hooks/useLocationScope')
  return { ...actual, useLocationScope: useLocationScopeMock }
})
vi.mock('../../api/employees/scheduleAssistant', () => ({
  getScheduleHuumeSession: getSessionMock,
  listScheduleHuumeSessions: listSessionsMock,
  archiveScheduleHuumeSession: vi.fn(),
  transcribeScheduleVoice: vi.fn(),
  getScheduleSuggestionStatus: suggestionStatusMock,
  adoptScheduleProposal: adoptProposalMock,
}))
vi.mock('../../api/employees/locationProfile', () => ({
  fetchLocationScheduleProfile: fetchLocationProfileMock,
  saveLocationScheduleProfile: vi.fn(),
}))
vi.mock('../../api/employees/employeeSchedule', () => ({
  fetchPlanningInputs: planningInputsMock,
  previewFillVacant: previewFillMock,
  applyFillVacant: applyFillMock,
  cancelFillVacant: cancelFillMock,
}))
vi.mock('../../work/api/matchaWork/messaging', () => ({ sendMessageStream: sendMessageStreamMock }))
vi.mock('../../components/employees/schedule-editor/ScheduleJobsTab', () => ({
  default: ({ locationId }: { locationId: string }) => <div>Jobs configuration for {locationId}</div>,
}))
vi.mock('../../components/employees/schedule-editor/WeekStartPane', () => ({
  default: ({ locationId, onSaved }: { locationId: string; onSaved?: () => void }) => (
    <div><div>Week setup pane</div><div>Setup for {locationId}</div><button onClick={() => onSaved?.()}>Save week setup</button></div>
  ),
}))

const SHIFT = {
  id: 'shift-1', starts_at: '2026-08-09T09:00:00Z', ends_at: '2026-08-09T17:00:00Z',
  assignments: [], role: 'Opener', department: null, location_id: null,
  template_id: null, series_id: null, break_minutes: 30, required_staff: 1,
  color: null, notes: null, status: 'draft', kind: 'work', training_requirement_id: null, job_id: null,
  published_at: null,
}

function review(overrides: Record<string, unknown> = {}) {
  return {
    proposal_id: 'proposal-1', kind: 'edit', compliance_status: 'verified',
    assignments: [{
      shift_id: 'shift-1', role: 'Opener', starts_at: '2026-08-09T09:00:00Z', ends_at: '2026-08-09T17:00:00Z',
      employee_id: 'e1', employee_name: 'Aisha Rivera', op: 'assign', verdict: 'ok', reasons: [],
    }],
    rejected: [], unfilled: [], employees: [], advisories: [], findings: [],
    jurisdiction: { state: 'CA', status: 'curated', message: 'Scheduling law for CA is on file (hand-curated).' },
    ...overrides,
  }
}

function planningInputs(overrides: Record<string, unknown> = {}) {
  return {
    week_start: '2026-08-09', week_end: '2026-08-15',
    roster: [{
      employee_id: 'e1', name: 'Aisha Rivera', job_title: 'Manager', jobs: ['Opener'],
      availability_state: 'windows', windows: {}, time_away: [],
      caps: { max_weekly_minutes: 2400, target_weekly_minutes: null, min_weekly_minutes: null, allow_overtime: false, max_consecutive_days: null, prefer_extra_hours: false },
      load: { minutes: 480, shifts: 1, days: ['2026-08-09'] },
    }],
    roster_truncated: false,
    open_slots: [],
    policy: { min_rest_hours: 8, max_shifts_per_day: 1, max_consecutive_days: 6, default_weekly_cap_minutes: 2400 },
    jurisdiction: { state: 'CA', status: 'curated', message: 'Scheduling law for CA is on file (hand-curated).' },
    week_rules: { established: true, missing: [] },
    profile: { operating_hours: {}, leader_required: false, leader_job_names: [] },
    ...overrides,
  }
}

/** The toolbar's Board/Review toggle. The mobile strip carries the same tab
 *  names, so every assertion about the center pane goes through here. */
function centerTab(name: RegExp | string) {
  return within(screen.getByRole('tablist', { name: 'Center pane' })).getByRole('tab', { name })
}

/** The review pane's own region — names repeat across the rail, the board and
 *  the review, which is the point of the layout. */
function reviewPane() {
  return screen.getByLabelText('Review')
}

function renderPilot({ url = '/ops/schedule/editor?week=2026-08-09&location=loc1', strict = false } = {}) {
  const tree = (
    <MemoryRouter initialEntries={[url]}>
      <Routes><Route path="/ops/schedule/editor" element={<SchedulePilot />} /></Routes>
    </MemoryRouter>
  )
  return render(strict ? <StrictMode>{tree}</StrictMode> : tree)
}

beforeEach(() => {
  reloadMock.mockClear()
  reloadLocationsMock.mockClear()
  sendMessageStreamMock.mockReset().mockReturnValue(new AbortController())
  getSessionMock.mockReset().mockResolvedValue({
    session_id: 'session-1', thread_id: 'thread-1', location_id: 'loc1',
    week_start: '2026-08-09', week_end: '2026-08-16', messages: [], current_state: {}, version: 1,
  })
  listSessionsMock.mockReset().mockResolvedValue({ sessions: [] })
  adoptProposalMock.mockReset()
  suggestionStatusMock.mockReset().mockResolvedValue({ available: false, generation_run_id: null, week_start: null, created_at: null })
  planningInputsMock.mockReset().mockResolvedValue(planningInputs())
  previewFillMock.mockReset()
  applyFillMock.mockReset()
  cancelFillMock.mockReset().mockResolvedValue(undefined)
  fetchLocationProfileMock.mockReset().mockResolvedValue({
    location_id: 'loc1', profile_exists: true,
    week_rules: { established: true, missing: [] },
    operating_hours: {}, default_week_template_id: null, leader_job_id: null,
    leader_job_name: null, leader_required: false, notes: null, week_start_weekday: 0,
    open_buffer_minutes: 0, close_buffer_minutes: 0, template: null,
  })
  useScheduleJobsMock.mockReturnValue({ jobs: [{ id: 'job-1', name: 'Opener' }], reloadJobs: vi.fn() })
  useMeMock.mockReturnValue({ me: { profile: { name: 'Jamie Rivera' } }, hasFeature: () => false })
  useLocationScopeMock.mockReturnValue({
    locationId: 'loc1',
    setLocationId: vi.fn(),
    locations: [{ id: 'loc1', name: 'Wilshire', city: 'Los Angeles', state: 'CA', is_active: true }],
    loading: false,
    reloadLocations: reloadLocationsMock,
  })
  useEditorMock.mockReturnValue({
    shifts: [SHIFT],
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

describe('SchedulePilot — the workspace', () => {
  it('mounts the inputs rail, the board and the Huume thread at once', async () => {
    renderPilot()

    expect(screen.getByLabelText('Planning inputs')).toBeInTheDocument()
    expect(screen.getByText('Aisha Rivera')).toBeInTheDocument()
    expect(screen.getByText('Opener')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Huume schedule assistant' })).toBeInTheDocument()
    expect(screen.getByText('Week of 2026-08-09')).toBeInTheDocument()
    await waitFor(() => expect(planningInputsMock).toHaveBeenCalledWith('loc1', '2026-08-09'))
  })

  it('does not load a stale location from the URL', async () => {
    const setLocationId = vi.fn()
    useLocationScopeMock.mockReturnValue({
      locationId: 'deleted-location', setLocationId,
      locations: [{ id: 'loc1', name: 'Wilshire', city: 'Los Angeles', state: 'CA', is_active: true }],
      loading: false, reloadLocations: reloadLocationsMock,
    })

    renderPilot({ url: '/ops/schedule/editor?week=2026-08-09&location=deleted-location' })

    expect(useEditorMock).toHaveBeenCalledWith('2026-08-09', '', expect.any(Object))
    await waitFor(() => expect(setLocationId).toHaveBeenCalledWith(''))
    expect(screen.getByText('Pick a location to see its schedule.')).toBeInTheDocument()
  })

  it('snaps a supplied ?week= to the location’s own week start day', () => {
    useLocationScopeMock.mockReturnValue({
      locationId: 'loc1', setLocationId: vi.fn(),
      locations: [{ id: 'loc1', name: 'Wilshire', city: 'Los Angeles', state: 'CA', is_active: true, week_start_weekday: 1 }],
      loading: false, reloadLocations: reloadLocationsMock,
    })

    renderPilot()

    // 2026-08-09 is a Sunday; this store's weeks start Monday.
    expect(screen.getByText('Week of 2026-08-03')).toBeInTheDocument()
    expect(useEditorMock).toHaveBeenCalledWith('2026-08-03', 'loc1', expect.any(Object))
  })

  it('opens the assistant under StrictMode, which replays effects', async () => {
    renderPilot({ strict: true })
    await waitFor(() => expect(screen.getByPlaceholderText('Try: add an opener Monday')).not.toBeDisabled())
  })

  it('opens the break planner when an assignment needs a compliant break', async () => {
    renderPilot()
    const options = useEditorMock.mock.calls[0]?.[2] as {
      onMealBreakRequired: (shift: typeof SHIFT, employeeId: string, message: string) => void
    }

    act(() => options.onMealBreakRequired(SHIFT, 'e1', 'A 30-minute meal break is required.'))

    expect(await screen.findByLabelText('Planned break (minutes)')).toHaveValue(30)
  })
})

describe('SchedulePilot — setup and drawers', () => {
  it('warns in the rail when the week rules are unsaved, and opens the pane', async () => {
    fetchLocationProfileMock.mockResolvedValue({
      location_id: 'loc1', profile_exists: false,
      week_rules: { established: false, missing: ['operating_hours', 'leader_rule'] },
      operating_hours: {}, default_week_template_id: null, leader_job_id: null,
      leader_job_name: null, leader_required: null, notes: null, week_start_weekday: 0,
      open_buffer_minutes: 0, close_buffer_minutes: 0, template: null,
    })

    renderPilot()

    expect(await screen.findByText(/is still missing hours, the leader rule/)).toBeInTheDocument()
    // The board stays usable — a manager may want to draw shifts by hand.
    expect(screen.getByRole('button', { name: 'Select Opener for Huume' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Fill it in myself' }))
    expect(screen.getByText('Week setup pane')).toBeInTheDocument()
  })

  it('re-reads the locations and the setup after the week setup pane saves', async () => {
    renderPilot()
    await waitFor(() => expect(fetchLocationProfileMock).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('button', { name: 'Week setup' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save week setup' }))

    // week_start_weekday rides on the location row and decides the grid layout
    // and which week the assistant session accepts.
    expect(reloadLocationsMock).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(fetchLocationProfileMock).toHaveBeenCalledTimes(2))
  })

  it('opens jobs as a drawer over the board rather than replacing it', () => {
    renderPilot()

    fireEvent.click(screen.getByRole('button', { name: 'Jobs' }))

    expect(screen.getByText('Jobs configuration for loc1')).toBeInTheDocument()
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Jobs' })).getByRole('button', { name: 'Close' }))
    expect(screen.queryByText('Jobs configuration for loc1')).not.toBeInTheDocument()
  })

  it('shows no setup warning once the rules are established', async () => {
    renderPilot()
    await waitFor(() => expect(fetchLocationProfileMock).toHaveBeenCalled())
    expect(screen.queryByText(/is still missing/)).not.toBeInTheDocument()
  })
})

describe('SchedulePilot — Huume', () => {
  it('sends the blocks selected on the board as authoritative context', async () => {
    renderPilot()

    fireEvent.click(screen.getByRole('button', { name: 'Select Opener for Huume' }))
    const input = await screen.findByPlaceholderText('Try: add an opener Monday')
    fireEvent.change(input, { target: { value: 'Move the selected person' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))

    expect(screen.getByText('Using 1 selected shift as context')).toBeInTheDocument()
    const [, content] = sendMessageStreamMock.mock.calls[0]
    expect(content).toContain('Selected schedule blocks — authoritative context for this request:')
    expect(content).toContain('Sun 8/9 · 9a–5p · Opener · open · staffing: 0/1')
  })

  it('reloads the week and the inputs once for an applied action', async () => {
    renderPilot()
    await waitFor(() => expect(planningInputsMock).toHaveBeenCalledTimes(1))
    const input = await screen.findByPlaceholderText('Try: add an opener Monday')
    fireEvent.change(input, { target: { value: 'Apply it' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))

    const complete = (sendMessageStreamMock.mock.calls[0][2] as { onComplete(r: unknown): void }).onComplete
    act(() => complete({
      user_message: { id: 'u1', thread_id: 'thread-1', role: 'user', content: 'Apply it', version_created: null, metadata: null, created_at: '2026-08-09T10:00:00Z' },
      assistant_message: { id: 'a1', thread_id: 'thread-1', role: 'assistant', content: 'Applied.', version_created: 2, metadata: { huume_run_id: 'run-1' }, created_at: '2026-08-09T10:00:00Z' },
      current_state: { huume_action: { status: 'applied', confirm_id: 'confirm-1' } },
    }))

    await waitFor(() => expect(reloadMock).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(planningInputsMock).toHaveBeenCalledTimes(2))
  })

  it('opens the review pane on its own when Huume stages something', async () => {
    getSessionMock.mockResolvedValue({
      session_id: 'session-1', thread_id: 'thread-1', location_id: 'loc1',
      week_start: '2026-08-09', week_end: '2026-08-16', messages: [], version: 2,
      current_state: {
        huume_action: {
          type: 'schedule_change', status: 'proposed', confirm_id: 'ab12cd34',
          proposal_id: 'proposal-1', kind: 'assign', operation_count: 1, review: review(),
        },
      },
    })

    renderPilot()

    expect(await screen.findByText('Law on file · no statutory advisories.')).toBeInTheDocument()
    expect(within(reviewPane()).getByText(/Aisha Rivera/)).toBeInTheDocument()
    expect(centerTab(/Review/)).toHaveAttribute('aria-selected', 'true')
  })

  it('surfaces an automatically prepared schedule for review', async () => {
    suggestionStatusMock.mockResolvedValue({
      available: true, generation_run_id: 'generation-1', week_start: '2026-08-09', created_at: '2026-08-24T16:00:00Z',
    })

    renderPilot()

    expect(await screen.findByText('Huume prepared a suggested schedule for the week of 2026-08-09.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review suggestion' }))
    expect(centerTab(/Review/)).toHaveAttribute('aria-selected', 'true')
  })
})

describe('SchedulePilot — scenarios', () => {
  async function previewOne() {
    previewFillMock.mockResolvedValue({
      status: 'ready', proposal_id: 'proposal-1', pill_text: 'pill', review: review(), label: null,
    })
    renderPilot()
    fireEvent.click(screen.getByRole('button', { name: /New scenario/ }))
    fireEvent.click(screen.getByRole('button', { name: /Preview/ }))
    await waitFor(() => expect(previewFillMock).toHaveBeenCalled())
  }

  it('runs a fill preview for the week on screen and reviews it', async () => {
    await previewOne()

    expect(previewFillMock).toHaveBeenCalledWith('loc1', expect.objectContaining({ week_start: '2026-08-09' }))
    // The chip names the scenario; the review pane titles it.
    expect(await screen.findByRole('button', { name: /^Scenario 1: all open shifts/ })).toBeInTheDocument()
    expect(within(reviewPane()).getByText(/Scenario 1: all open shifts/)).toBeInTheDocument()
    expect(centerTab(/Review/)).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText(/A simulation — nothing is written/)).toBeInTheDocument()
  })

  it('stages a scenario into the thread, where it is confirmed like any other', async () => {
    adoptProposalMock.mockResolvedValue({
      current_state: {
        huume_action: {
          type: 'schedule_change', status: 'proposed', confirm_id: 'newid123',
          proposal_id: 'proposal-1', kind: 'assign', operation_count: 1, review: review(),
        },
      },
      version: 3,
      confirm_id: 'newid123',
    })
    await previewOne()

    fireEvent.click(await screen.findByRole('button', { name: /Stage in thread/ }))

    await waitFor(() => expect(adoptProposalMock).toHaveBeenCalledWith('session-1', 'proposal-1'))
    // The chip stops being a free simulation — the thread owns it now.
    const chip = await screen.findByRole('button', { name: /^Scenario 1: all open shifts/ })
    await waitFor(() => expect(within(chip).getByText('staged')).toBeInTheDocument())
  })

  it('applies a scenario over REST and refreshes the week', async () => {
    applyFillMock.mockResolvedValue({ status: 'applied', message: '1 change is live.', touched_shift_ids: ['shift-1'] })
    await previewOne()

    fireEvent.click(await screen.findByRole('button', { name: /Apply now/ }))

    await waitFor(() => expect(applyFillMock).toHaveBeenCalledWith('proposal-1'))
    await waitFor(() => expect(reloadMock).toHaveBeenCalled())
  })

  it('says why a fill produced nothing instead of an empty chip', async () => {
    previewFillMock.mockResolvedValue({
      status: 'empty',
      message: 'No open shift could be filled under the staffing rules.',
      unfilled: [{ shift_id: 's1', role: 'Opener', starts_at: null, ends_at: null, reason: 'not qualified for the shift job', exclusions: {} }],
    })
    renderPilot()
    fireEvent.click(screen.getByRole('button', { name: /New scenario/ }))
    fireEvent.click(screen.getByRole('button', { name: /Preview/ }))

    expect(await screen.findByText(/No open shift could be filled under the staffing rules/)).toBeInTheDocument()
    expect(screen.queryByText(/Scenario 1/)).not.toBeInTheDocument()
  })
})
