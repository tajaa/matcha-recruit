import { MemoryRouter } from 'react-router-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ScheduleHuumePanel from './ScheduleHuumePanel'
import { SETUP_KICKOFF_PROMPT } from '../../../hooks/employees/useScheduleHuumeThread'
import type { ScheduleHuumeThread } from '../../../hooks/employees/useScheduleHuumeThread'

/** The panel is presentational now — every piece of state comes from
 *  `useScheduleHuumeThread`, which has its own tests. These cover what the
 *  panel does with that state. */
function fakeThread(overrides: Partial<ScheduleHuumeThread> = {}): ScheduleHuumeThread {
  return {
    threadId: 'thread-1',
    sessionId: 'session-1',
    sessions: [],
    historyOpen: false,
    setHistoryOpen: vi.fn(),
    refreshSessions: vi.fn(),
    messages: [],
    currentState: {},
    setCurrentState: vi.fn(),
    action: undefined,
    choice: undefined,
    input: '',
    setInput: vi.fn(),
    status: '',
    sessionError: null,
    retry: vi.fn(),
    steps: [],
    busy: false,
    composerDisabled: false,
    send: vi.fn().mockResolvedValue(undefined),
    openChat: vi.fn(),
    archiveChat: vi.fn().mockResolvedValue(undefined),
    voice: {
      enabled: false, starting: false, transcribing: false, recording: false, error: null,
      begin: vi.fn().mockResolvedValue(undefined), finish: vi.fn().mockResolvedValue(undefined),
    },
    ...overrides,
  }
}

function renderPanel(thread: ScheduleHuumeThread, props: Record<string, unknown> = {}) {
  return render(
    <MemoryRouter>
      <ScheduleHuumePanel
        thread={thread}
        firstName="Jamie"
        weekStart="2026-08-09"
        locationId="loc1"
        locationName="Wilshire"
        selectedShifts={[]}
        onClearSelectedShifts={() => {}}
        {...props}
      />
    </MemoryRouter>,
  )
}

describe('ScheduleHuumePanel choice chips', () => {
  const choice = {
    question: 'Which week template should I use?',
    options: [
      { label: 'Downtown default week', send: 'Use the week template named Downtown default week' },
      { label: 'Holiday week' },
    ],
    kind: 'single' as const,
  }

  it('renders the staged question as tappable options', () => {
    renderPanel(fakeThread({ choice }))

    expect(screen.getByText('Which week template should I use?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Downtown default week' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Holiday week' })).toBeInTheDocument()
  })

  it('sends the option’s send text as an ordinary user turn', () => {
    const thread = fakeThread({ choice })
    renderPanel(thread)

    fireEvent.click(screen.getByRole('button', { name: 'Downtown default week' }))

    // Same path Confirm/Cancel use — a chip can never satisfy the server's
    // explicit-confirmation gate, it just saves typing.
    expect(thread.send).toHaveBeenCalledWith('Use the week template named Downtown default week')
  })

  it('falls back to the label when an option carries no send text', () => {
    const thread = fakeThread({ choice })
    renderPanel(thread)

    fireEvent.click(screen.getByRole('button', { name: 'Holiday week' }))

    expect(thread.send).toHaveBeenCalledWith('Holiday week')
  })

  it('hides the chips while a turn is streaming', () => {
    // The answer is already on its way and the question may be about to be replaced.
    renderPanel(fakeThread({ choice, busy: true }))

    expect(screen.queryByRole('button', { name: 'Holiday week' })).not.toBeInTheDocument()
  })

  it('shows no chips when the turn left none staged', () => {
    renderPanel(fakeThread())

    expect(screen.queryByRole('group')).not.toBeInTheDocument()
  })
})

describe('ScheduleHuumePanel setup gate', () => {
  it('offers the interview instead of a build that would be refused', () => {
    const thread = fakeThread()
    renderPanel(thread, { weekRulesEstablished: false })

    expect(screen.queryByRole('button', { name: /Build my week/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Set up this location/ }))

    expect(thread.send).toHaveBeenCalledWith(SETUP_KICKOFF_PROMPT)
  })

  it('offers the build and the server-side fill once the rules are established', () => {
    const thread = fakeThread()
    renderPanel(thread, { weekRulesEstablished: true })

    expect(screen.getByRole('button', { name: /Build my week/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Set up this location/ })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Fill the open shifts/ }))
    expect(thread.send).toHaveBeenCalledWith('Fill the open shifts this week.')
  })

  it('greets the manager by name only while the chat is empty', () => {
    renderPanel(fakeThread())
    expect(screen.getByText(/Hi, Jamie/)).toBeInTheDocument()
  })
})

describe('ScheduleHuumePanel chrome', () => {
  it('mounts as a workspace column when embedded, and as a dialog otherwise', () => {
    const { unmount } = renderPanel(fakeThread(), { embedded: true })
    expect(screen.getByRole('region', { name: 'Huume schedule assistant' })).toBeInTheDocument()
    unmount()

    renderPanel(fakeThread(), { onClose: vi.fn() })
    expect(screen.getByRole('dialog', { name: 'Huume schedule assistant' })).toBeInTheDocument()
  })

  it('only offers a close control when the caller can act on it', () => {
    const { unmount } = renderPanel(fakeThread(), { embedded: true })
    expect(screen.queryByRole('button', { name: 'Close schedule assistant' })).not.toBeInTheDocument()
    unmount()

    const onClose = vi.fn()
    renderPanel(fakeThread(), { onClose })
    fireEvent.click(screen.getByRole('button', { name: 'Close schedule assistant' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('lists previous chats and removes one from history', () => {
    const summary = {
      session_id: 'session-2', thread_id: 'thread-2', title: 'Cover Friday close', message_count: 4,
      created_at: '2026-08-09T10:00:00Z', last_activity_at: '2026-08-09T10:05:00Z',
    }
    const thread = fakeThread({ historyOpen: true, sessions: [summary] })
    renderPanel(thread)

    fireEvent.click(screen.getByRole('button', { name: /^Cover Friday close/ }))
    expect(thread.openChat).toHaveBeenCalledWith('session-2')

    fireEvent.click(screen.getByRole('button', { name: 'Remove chat: Cover Friday close' }))
    expect(thread.archiveChat).toHaveBeenCalledWith(summary)
  })

  it('shows a session error with a retry rather than a silent dead composer', () => {
    const thread = fakeThread({ sessionError: 'Session unavailable', composerDisabled: true })
    renderPanel(thread)

    expect(screen.getByRole('alert')).toHaveTextContent('Session unavailable')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(thread.retry).toHaveBeenCalled()
  })

  it('sends what the manager typed and reports the selected-block context', () => {
    const thread = fakeThread({ input: 'Add an opener Monday' })
    renderPanel(thread, {
      selectedShifts: [{ id: 's1' }],
      onClearSelectedShifts: vi.fn(),
    })

    expect(screen.getByText('Using 1 selected shift as context')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    expect(thread.send).toHaveBeenCalled()
  })
})

describe('ScheduleHuumePanel staged action', () => {
  const stagedChange = {
    type: 'schedule_change' as const,
    status: 'proposed' as const,
    confirm_id: 'ab12cd34',
    proposal_id: 'proposal-1',
    kind: 'assign',
    operation_count: 2,
    review: { kind: 'edit' as const, compliance_status: 'verified' as const, assignments: [], rejected: [], unfilled: [], employees: [] },
  }

  it('offers the review pane for a staged change that carries a review', () => {
    const onOpenReview = vi.fn()
    renderPanel(fakeThread({ action: stagedChange }), { onOpenReview })

    fireEvent.click(screen.getByRole('button', { name: /Open the review pane/ }))
    expect(onOpenReview).toHaveBeenCalled()
  })

  it('offers no review pane for an action with nothing to review', () => {
    const onOpenReview = vi.fn()
    renderPanel(fakeThread({ action: { ...stagedChange, review: undefined } }), { onOpenReview })

    expect(screen.queryByRole('button', { name: /Open the review pane/ })).not.toBeInTheDocument()
  })

  it('offers no review pane once the action has been applied', () => {
    renderPanel(fakeThread({ action: { ...stagedChange, status: 'applied' as const } }), { onOpenReview: vi.fn() })

    expect(screen.queryByRole('button', { name: /Open the review pane/ })).not.toBeInTheDocument()
  })

  it('says an automatically prepared week was not asked for', () => {
    renderPanel(fakeThread({
      action: {
        type: 'schedule_week_draft', status: 'proposed', confirm_id: 'auto1234',
        generation_run_id: 'generation-1', location_id: 'loc1', week_start: '2026-08-09',
        source_mode: 'template', auto_generated: true,
      } as never,
    }))

    expect(screen.getByText(/Huume prepared this suggestion automatically/)).toBeInTheDocument()
    expect(screen.queryByText(/Hi, Jamie/)).not.toBeInTheDocument()
  })
})
