import { StrictMode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { selectedShiftContext, useScheduleHuumeThread } from './useScheduleHuumeThread'

const {
  getSessionMock, listSessionsMock, archiveSessionMock, transcribeMock, sendMessageStreamMock, toastMock, dictationMock,
} = vi.hoisted(() => ({
  getSessionMock: vi.fn(),
  listSessionsMock: vi.fn(),
  archiveSessionMock: vi.fn(),
  transcribeMock: vi.fn(),
  sendMessageStreamMock: vi.fn(),
  toastMock: vi.fn(),
  dictationMock: vi.fn(),
}))

vi.mock('../../api/employees/scheduleAssistant', () => ({
  getScheduleHuumeSession: getSessionMock,
  listScheduleHuumeSessions: listSessionsMock,
  archiveScheduleHuumeSession: archiveSessionMock,
  transcribeScheduleVoice: transcribeMock,
}))
vi.mock('../../work/api/matchaWork/messaging', () => ({ sendMessageStream: sendMessageStreamMock }))
vi.mock('../../components/ui', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('../useVoiceDictation', () => ({ useVoiceDictation: dictationMock }))

function session(currentState: Record<string, unknown> = {}, sessionId = 'session-1') {
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

function message(id: string, role: 'user' | 'assistant', content: string, metadata: Record<string, unknown> | null = null) {
  return {
    id, thread_id: 'thread-session-1', role, content,
    version_created: null, metadata, created_at: '2026-08-09T10:06:00Z',
  }
}

function shift(id: string, role: string, assignees: string[] = []) {
  return {
    id, starts_at: '2026-08-09T09:00:00Z', ends_at: '2026-08-09T17:00:00Z',
    assignments: assignees.map((name) => ({
      employee_id: name, name, job_title: null, status: 'assigned' as const,
      availability_overridden: false, availability_override_at: null,
    })),
    role, department: null, location_id: null, template_id: null, series_id: null,
    break_minutes: 30, required_staff: 2, color: null, notes: null, status: 'draft' as const,
    kind: 'work' as const, training_requirement_id: null, job_id: null, published_at: null,
  }
}

type Options = Partial<Parameters<typeof useScheduleHuumeThread>[0]>

function render(options: Options = {}, { strict = false }: { strict?: boolean } = {}) {
  const onApplied = options.onApplied ?? vi.fn()
  const onAutomaticActionSettled = options.onAutomaticActionSettled ?? vi.fn()
  const view = renderHook(
    (props: Options) => useScheduleHuumeThread({
      locationId: 'loc1', weekStart: '2026-08-09', selectedShifts: [],
      onApplied, onAutomaticActionSettled, ...options, ...props,
    }),
    strict ? { wrapper: StrictMode } : undefined,
  )
  return { ...view, onApplied, onAutomaticActionSettled }
}

/** Hand back the callbacks the hook passed into the stream, so a test can
 *  complete or fail the turn on its own schedule. */
function streamCallbacks(index = 0) {
  return sendMessageStreamMock.mock.calls[index][2] as {
    onEvent(event: unknown): void
    onComplete(response: unknown): void
    onError(message: string): void
  }
}

beforeEach(() => {
  getSessionMock.mockReset().mockResolvedValue(session())
  listSessionsMock.mockReset().mockResolvedValue({ sessions: [] })
  archiveSessionMock.mockReset().mockResolvedValue({ session_id: 'session-1', archived: true })
  transcribeMock.mockReset()
  sendMessageStreamMock.mockReset().mockReturnValue(new AbortController())
  toastMock.mockReset()
  dictationMock.mockReset().mockReturnValue({
    status: 'idle', elapsedSeconds: 0, start: vi.fn(), stop: vi.fn(),
  })
})

describe('useScheduleHuumeThread — opening a chat', () => {
  it('opens a fresh chat for the scope rather than resuming one', async () => {
    const { result } = render()
    await waitFor(() => expect(result.current.threadId).toBe('thread-session-1'))
    expect(getSessionMock).toHaveBeenCalledWith('loc1', '2026-08-09', null)
    expect(result.current.sessionId).toBe('session-1')
    expect(result.current.status).toBe('')
  })

  it('opens the session once under StrictMode, which replays effects', async () => {
    // The cleanup marks the hook unmounted; without restoring that flag the
    // replayed effect's response is dropped and the composer stays inert.
    const { result } = render({}, { strict: true })
    await waitFor(() => expect(result.current.threadId).toBe('thread-session-1'))
    expect(result.current.composerDisabled).toBe(false)
  })

  it('waits for a location before opening anything', async () => {
    const { result } = render({ locationId: null })
    await waitFor(() => expect(result.current.status).toBe('Choose a location to start the schedule assistant.'))
    expect(getSessionMock).not.toHaveBeenCalled()
    expect(result.current.threadId).toBeNull()
  })

  it('reopens the chat picked out of history, then a new one from the header', async () => {
    listSessionsMock.mockResolvedValue({ sessions: [summary('session-2', 'Cover Friday close')] })
    const { result } = render()
    await waitFor(() => expect(result.current.threadId).toBeTruthy())

    act(() => result.current.openChat('session-2'))
    await waitFor(() => expect(getSessionMock).toHaveBeenCalledTimes(2))
    expect(getSessionMock.mock.calls[1][2]).toBe('session-2')

    act(() => result.current.openChat(null))
    await waitFor(() => expect(getSessionMock).toHaveBeenCalledTimes(3))
    expect(getSessionMock.mock.calls[2][2]).toBeNull()
  })

  it('reports a failed open and recovers on retry instead of leaving the composer inert', async () => {
    getSessionMock.mockRejectedValueOnce(new Error('Session unavailable')).mockResolvedValue(session())
    const { result } = render()
    await waitFor(() => expect(result.current.sessionError).toBe('Session unavailable'))
    expect(result.current.composerDisabled).toBe(true)

    act(() => result.current.retry())
    // The error clears the moment the retry starts; the composer only comes
    // back once a thread is actually open.
    await waitFor(() => expect(result.current.threadId).toBe('thread-session-1'))
    expect(result.current.sessionError).toBeNull()
    expect(result.current.composerDisabled).toBe(false)
  })

  it('resets the conversation when the week changes', async () => {
    const { result, rerender } = render()
    await waitFor(() => expect(result.current.threadId).toBeTruthy())
    act(() => { result.current.setInput('draft I never sent') })

    getSessionMock.mockResolvedValue(session({}, 'session-9'))
    rerender({ weekStart: '2026-08-16' })

    await waitFor(() => expect(result.current.sessionId).toBe('session-9'))
    expect(result.current.messages).toEqual([])
    expect(getSessionMock).toHaveBeenLastCalledWith('loc1', '2026-08-16', null)
  })
})

describe('useScheduleHuumeThread — archiving', () => {
  it('drops the chat from history and opens a fresh one when it was the open chat', async () => {
    // The server stops listing an archived chat, so the re-open that follows
    // lists the remaining ones — here, none.
    listSessionsMock
      .mockResolvedValueOnce({ sessions: [summary('session-1', 'Rebuild the week')] })
      .mockResolvedValue({ sessions: [] })
    const { result } = render()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))

    await act(async () => { await result.current.archiveChat(summary('session-1', 'Rebuild the week')) })

    expect(archiveSessionMock).toHaveBeenCalledWith('session-1')
    // Archiving the open chat leaves nothing to talk in, so a fresh one opens
    // rather than keeping a thread the server now refuses turns on.
    await waitFor(() => expect(getSessionMock).toHaveBeenCalledTimes(2))
    expect(getSessionMock.mock.calls[1][2]).toBeNull()
    await waitFor(() => expect(result.current.sessions).toEqual([]))
  })

  it('keeps the open chat when a different one is archived', async () => {
    listSessionsMock.mockResolvedValue({ sessions: [summary('session-1', 'A'), summary('session-7', 'B')] })
    const { result } = render()
    await waitFor(() => expect(result.current.sessions).toHaveLength(2))

    await act(async () => { await result.current.archiveChat(summary('session-7', 'B')) })

    expect(result.current.sessions.map((item) => item.session_id)).toEqual(['session-1'])
    expect(getSessionMock).toHaveBeenCalledTimes(1)
  })

  it('surfaces a failed archive and keeps the chat listed', async () => {
    listSessionsMock.mockResolvedValue({ sessions: [summary('session-1', 'Rebuild the week')] })
    archiveSessionMock.mockRejectedValue(new Error('Could not remove that chat.'))
    const { result } = render()
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))

    await act(async () => { await result.current.archiveChat(summary('session-1', 'Rebuild the week')) })

    expect(toastMock).toHaveBeenCalledWith('Could not remove that chat.', 'error')
    expect(result.current.sessions).toHaveLength(1)
  })
})

describe('useScheduleHuumeThread — taking a turn', () => {
  it('sends the board’s selected blocks as authoritative context, showing only what was typed', async () => {
    const { result } = render({ selectedShifts: [shift('shift-1', 'Opener', ['Aisha Rivera'])] })
    await waitFor(() => expect(result.current.threadId).toBeTruthy())

    await act(async () => { await result.current.send('Move the selected person') })

    const [threadId, content] = sendMessageStreamMock.mock.calls[0]
    expect(threadId).toBe('thread-session-1')
    expect(content).toContain('Move the selected person')
    expect(content).toContain('Selected schedule blocks — authoritative context for this request:')
    expect(content).toContain('Sun 8/9 · 9a–5p · Opener · assigned: Aisha Rivera · staffing: 1/2')
    // The chat shows the manager's own words, never the appended context.
    expect(result.current.messages.at(-1)?.content).toBe('Move the selected person')
    expect(result.current.busy).toBe(true)
  })

  it('clears the composer and replaces the optimistic turn on completion', async () => {
    const { result } = render()
    await waitFor(() => expect(result.current.threadId).toBeTruthy())
    act(() => { result.current.setInput('Add an opener Monday') })

    await act(async () => { await result.current.send() })
    expect(result.current.input).toBe('')

    act(() => streamCallbacks().onComplete({
      user_message: message('u1', 'user', 'Add an opener Monday'),
      assistant_message: message('a1', 'assistant', 'Staged it.', { huume_run_id: 'run-1' }),
      current_state: { huume_action: { type: 'schedule_change', status: 'proposed', confirm_id: 'ab12cd34' } },
    }))

    expect(result.current.messages.map((item) => item.id)).toEqual(['u1', 'a1'])
    expect(result.current.busy).toBe(false)
    expect(result.current.action).toMatchObject({ type: 'schedule_change', confirm_id: 'ab12cd34' })
  })

  it('reloads once for an applied action and ignores its persistent status later', async () => {
    const { result, onApplied } = render()
    await waitFor(() => expect(result.current.threadId).toBeTruthy())

    await act(async () => { await result.current.send('Apply it') })
    act(() => streamCallbacks(0).onComplete({
      user_message: message('u1', 'user', 'Apply it'),
      assistant_message: message('a1', 'assistant', 'Applied.', { huume_run_id: 'run-1' }),
      current_state: { huume_action: { status: 'applied', confirm_id: 'confirm-1' } },
    }))
    await waitFor(() => expect(onApplied).toHaveBeenCalledTimes(1))

    await act(async () => { await result.current.send('What changed?') })
    act(() => streamCallbacks(1).onComplete({
      user_message: message('u2', 'user', 'What changed?'),
      assistant_message: message('a2', 'assistant', 'Still applied.', { huume_run_id: 'run-2' }),
      current_state: { huume_action: { status: 'applied', confirm_id: 'confirm-1' } },
    }))

    expect(onApplied).toHaveBeenCalledTimes(1)
  })

  it('drops the optimistic turn and toasts when the stream fails', async () => {
    const { result } = render()
    await waitFor(() => expect(result.current.threadId).toBeTruthy())

    await act(async () => { await result.current.send('Add an opener') })
    expect(result.current.messages).toHaveLength(1)

    act(() => streamCallbacks().onError('Huume is unavailable'))

    expect(result.current.messages).toEqual([])
    expect(result.current.busy).toBe(false)
    expect(toastMock).toHaveBeenCalledWith('Huume is unavailable', 'error')
  })

  it('keeps live steps and status from the stream, then clears them', async () => {
    const { result } = render()
    await waitFor(() => expect(result.current.threadId).toBeTruthy())
    await act(async () => { await result.current.send('Build the week') })

    act(() => {
      streamCallbacks().onEvent({ type: 'status', message: 'Reading the roster…' })
      streamCallbacks().onEvent({ type: 'step', data: { tool: 'get_schedule_overview', kind: 'read', label: 'Read', status: 'ok' } })
    })
    expect(result.current.status).toBe('Reading the roster…')
    expect(result.current.steps).toHaveLength(1)

    act(() => streamCallbacks().onComplete({
      user_message: message('u1', 'user', 'Build the week'),
      assistant_message: message('a1', 'assistant', 'Here it is.'),
      current_state: {},
    }))
    expect(result.current.steps).toEqual([])
    expect(result.current.status).toBe('')
  })

  it('refuses to send an empty turn, or any turn before the session is open', async () => {
    const { result } = render()
    await waitFor(() => expect(result.current.threadId).toBeTruthy())

    await act(async () => { await result.current.send('   ') })
    expect(sendMessageStreamMock).not.toHaveBeenCalled()

    await act(async () => { await result.current.send('Add an opener') })
    expect(sendMessageStreamMock).toHaveBeenCalledTimes(1)
    // Busy: a second turn cannot start while the first is streaming.
    await act(async () => { await result.current.send('And a closer') })
    expect(sendMessageStreamMock).toHaveBeenCalledTimes(1)
  })
})

describe('useScheduleHuumeThread — automatically prepared proposals', () => {
  it('tells the caller once when an automatic proposal is no longer pending', async () => {
    getSessionMock.mockResolvedValue(session({
      huume_action: {
        type: 'schedule_week_draft', status: 'cancelled', confirm_id: 'auto1234',
        generation_run_id: 'generation-1', auto_generated: true,
      },
    }))
    const { result, onAutomaticActionSettled } = render()
    await waitFor(() => expect(onAutomaticActionSettled).toHaveBeenCalledTimes(1))

    act(() => { result.current.setCurrentState({ ...result.current.currentState }) })
    expect(onAutomaticActionSettled).toHaveBeenCalledTimes(1)
  })

  it('stays quiet while an automatic proposal is still awaiting the manager', async () => {
    getSessionMock.mockResolvedValue(session({
      huume_action: {
        type: 'schedule_week_draft', status: 'proposed', confirm_id: 'auto1234',
        generation_run_id: 'generation-1', auto_generated: true,
      },
    }))
    const { result, onAutomaticActionSettled } = render()
    await waitFor(() => expect(result.current.action).toBeTruthy())
    expect(onAutomaticActionSettled).not.toHaveBeenCalled()
  })
})

describe('selectedShiftContext', () => {
  it('is empty with nothing selected', () => {
    expect(selectedShiftContext([])).toBe('')
  })

  it('numbers each block and says whether it is open', () => {
    const text = selectedShiftContext([shift('s1', 'Opener', ['Aisha Rivera']), shift('s2', 'Closer')])
    expect(text).toContain('1. Sun 8/9 · 9a–5p · Opener · assigned: Aisha Rivera · staffing: 1/2')
    expect(text).toContain('2. Sun 8/9 · 9a–5p · Closer · open · staffing: 0/2')
    expect(text).toContain('Keep any assignee not named in my request on their current shift.')
  })
})
