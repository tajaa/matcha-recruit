import { MemoryRouter } from 'react-router-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScheduleHuumePanel, { SETUP_KICKOFF_PROMPT } from './ScheduleHuumePanel'

const { getScheduleHuumeSessionMock, listSessionsMock, archiveSessionMock, sendMessageStreamMock } = vi.hoisted(() => ({
  getScheduleHuumeSessionMock: vi.fn(),
  listSessionsMock: vi.fn(),
  archiveSessionMock: vi.fn(),
  sendMessageStreamMock: vi.fn((_threadId: string, _content: string, _callbacks: unknown) => new AbortController()),
}))

vi.mock('../../../api/employees/scheduleAssistant', () => ({
  getScheduleHuumeSession: getScheduleHuumeSessionMock,
  listScheduleHuumeSessions: listSessionsMock,
  archiveScheduleHuumeSession: archiveSessionMock,
  transcribeScheduleVoice: vi.fn(),
}))
vi.mock('../../../work/api/matchaWork/messaging', () => ({ sendMessageStream: sendMessageStreamMock }))

function session(currentState: Record<string, unknown>, sessionId = 'session-1') {
  return {
    session_id: sessionId, thread_id: `thread-${sessionId}`, location_id: 'loc1',
    week_start: '2026-08-09', week_end: '2026-08-16', title: 'New chat', messages: [],
    current_state: currentState, version: 1,
  }
}

function summary(sessionId: string, title: string) {
  return {
    session_id: sessionId, thread_id: `thread-${sessionId}`, title, message_count: 4,
    created_at: '2026-08-09T10:00:00Z', last_activity_at: '2026-08-09T10:05:00Z',
  }
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <ScheduleHuumePanel
        firstName="Jamie" weekStart="2026-08-09" locationId="loc1" locationName="Wilshire"
        selectedShifts={[]} onClearSelectedShifts={() => {}} onApplied={() => {}}
        onAutomaticActionSettled={() => {}} onClose={() => {}}
      />
    </MemoryRouter>,
  )
}

describe('ScheduleHuumePanel choice chips', () => {
  beforeEach(() => {
    sendMessageStreamMock.mockReset().mockReturnValue(new AbortController())
    getScheduleHuumeSessionMock.mockReset()
    listSessionsMock.mockReset().mockResolvedValue({ sessions: [] })
    archiveSessionMock.mockReset().mockResolvedValue({ session_id: 'session-1', archived: true })
  })

  it('renders the staged question as tappable options', async () => {
    getScheduleHuumeSessionMock.mockResolvedValue(session({
      huume_choice: {
        question: 'Which week template should I use?',
        options: [
          { label: 'Downtown default week', send: 'Use the week template named Downtown default week' },
          { label: 'Holiday week' },
        ],
        kind: 'single',
      },
    }))

    renderPanel()

    expect(await screen.findByText('Which week template should I use?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Downtown default week' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Holiday week' })).toBeInTheDocument()
  })

  it('sends the option’s send text as an ordinary user turn', async () => {
    getScheduleHuumeSessionMock.mockResolvedValue(session({
      huume_choice: {
        question: 'Which week template should I use?',
        options: [{ label: 'Downtown default week', send: 'Use the week template named Downtown default week' }, { label: 'Holiday week' }],
        kind: 'single',
      },
    }))

    renderPanel()
    fireEvent.click(await screen.findByRole('button', { name: 'Downtown default week' }))

    // Same path Confirm/Cancel use — a chip can never satisfy the server's
    // explicit-confirmation gate, it just saves typing.
    await waitFor(() => expect(sendMessageStreamMock).toHaveBeenCalledTimes(1))
    expect(sendMessageStreamMock.mock.calls[0][1]).toBe('Use the week template named Downtown default week')
  })

  it('falls back to the label when an option carries no send text', async () => {
    getScheduleHuumeSessionMock.mockResolvedValue(session({
      huume_choice: {
        question: 'Which job did you mean?',
        options: [{ label: 'Barista' }, { label: 'Shift Lead' }],
        kind: 'single',
      },
    }))

    renderPanel()
    fireEvent.click(await screen.findByRole('button', { name: 'Shift Lead' }))

    await waitFor(() => expect(sendMessageStreamMock).toHaveBeenCalledTimes(1))
    expect(sendMessageStreamMock.mock.calls[0][1]).toBe('Shift Lead')
  })

  it('hides the chips while a turn is streaming', async () => {
    getScheduleHuumeSessionMock.mockResolvedValue(session({
      huume_choice: {
        question: 'Which job did you mean?',
        options: [{ label: 'Barista' }, { label: 'Shift Lead' }],
        kind: 'single',
      },
    }))

    renderPanel()
    fireEvent.click(await screen.findByRole('button', { name: 'Barista' }))

    // The mocked stream never completes, so the panel stays busy — the answer
    // is already on its way and the question may be about to be replaced.
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Shift Lead' })).not.toBeInTheDocument())
  })

  it('shows no chips when the turn left none staged', async () => {
    getScheduleHuumeSessionMock.mockResolvedValue(session({}))

    renderPanel()

    await waitFor(() => expect(getScheduleHuumeSessionMock).toHaveBeenCalled())
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
  })
})

describe('ScheduleHuumePanel thread management', () => {
  beforeEach(() => {
    sendMessageStreamMock.mockReset().mockReturnValue(new AbortController())
    getScheduleHuumeSessionMock.mockReset().mockResolvedValue(session({}))
    listSessionsMock.mockReset().mockResolvedValue({ sessions: [] })
    archiveSessionMock.mockReset().mockResolvedValue({ session_id: 'session-1', archived: true })
  })

  it('opens a fresh chat rather than resuming one', async () => {
    renderPanel()

    await waitFor(() => expect(getScheduleHuumeSessionMock).toHaveBeenCalled())
    expect(getScheduleHuumeSessionMock.mock.calls[0][2]).toBeNull()
  })

  it('reopens the chat picked out of history', async () => {
    listSessionsMock.mockResolvedValue({ sessions: [summary('session-2', 'Cover Friday close')] })

    renderPanel()
    fireEvent.click(await screen.findByRole('button', { name: 'Previous chats' }))
    fireEvent.click(await screen.findByRole('button', { name: /^Cover Friday close/ }))

    await waitFor(() => expect(getScheduleHuumeSessionMock).toHaveBeenCalledTimes(2))
    expect(getScheduleHuumeSessionMock.mock.calls[1][2]).toBe('session-2')
  })

  it('starts a new chat from the header without resuming the last one', async () => {
    getScheduleHuumeSessionMock.mockResolvedValue(session({}, 'session-2'))
    listSessionsMock.mockResolvedValue({ sessions: [summary('session-2', 'Cover Friday close')] })

    renderPanel()
    await waitFor(() => expect(getScheduleHuumeSessionMock).toHaveBeenCalled())
    fireEvent.click(screen.getByRole('button', { name: 'New chat' }))

    await waitFor(() => expect(getScheduleHuumeSessionMock).toHaveBeenCalledTimes(2))
    expect(getScheduleHuumeSessionMock.mock.calls[1][2]).toBeNull()
  })

  it('removes a chat from history and reopens a fresh one when it was open', async () => {
    getScheduleHuumeSessionMock.mockResolvedValue(session({}, 'session-1'))
    listSessionsMock.mockResolvedValue({ sessions: [summary('session-1', 'Rebuild the week')] })

    renderPanel()
    fireEvent.click(await screen.findByRole('button', { name: 'Previous chats' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Remove chat: Rebuild the week' }))

    await waitFor(() => expect(archiveSessionMock).toHaveBeenCalledWith('session-1'))
    await waitFor(() => expect(getScheduleHuumeSessionMock).toHaveBeenCalledTimes(2))
  })
})


describe('ScheduleHuumePanel setup gate', () => {
  beforeEach(() => {
    sendMessageStreamMock.mockReset().mockReturnValue(new AbortController())
    getScheduleHuumeSessionMock.mockReset().mockResolvedValue(session({}))
    listSessionsMock.mockReset().mockResolvedValue({ sessions: [] })
    archiveSessionMock.mockReset().mockResolvedValue({ session_id: 'session-1', archived: true })
  })

  function renderWithRules(established: boolean) {
    return render(
      <MemoryRouter>
        <ScheduleHuumePanel
          firstName="Jamie" weekStart="2026-08-09" locationId="loc1" locationName="Wilshire"
          selectedShifts={[]} weekRulesEstablished={established}
          onClearSelectedShifts={() => {}} onApplied={() => {}}
          onAutomaticActionSettled={() => {}} onClose={() => {}}
        />
      </MemoryRouter>,
    )
  }

  it('offers the interview instead of a build that would be refused', async () => {
    renderWithRules(false)

    const setup = await screen.findByRole('button', { name: /Set up this location/ })
    expect(screen.queryByRole('button', { name: /Build my week/ })).not.toBeInTheDocument()

    fireEvent.click(setup)
    await waitFor(() => expect(sendMessageStreamMock).toHaveBeenCalledTimes(1))
    expect(sendMessageStreamMock.mock.calls[0][1]).toBe(SETUP_KICKOFF_PROMPT)
  })

  it('offers the build once the rules are established', async () => {
    renderWithRules(true)

    expect(await screen.findByRole('button', { name: /Build my week/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Set up this location/ })).not.toBeInTheDocument()
  })
})
