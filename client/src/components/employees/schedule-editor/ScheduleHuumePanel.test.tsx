import { MemoryRouter } from 'react-router-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScheduleHuumePanel from './ScheduleHuumePanel'

const { getScheduleHuumeSessionMock, sendMessageStreamMock } = vi.hoisted(() => ({
  getScheduleHuumeSessionMock: vi.fn(),
  sendMessageStreamMock: vi.fn((_threadId: string, _content: string, _callbacks: unknown) => new AbortController()),
}))

vi.mock('../../../api/employees/scheduleAssistant', () => ({
  getScheduleHuumeSession: getScheduleHuumeSessionMock,
  transcribeScheduleVoice: vi.fn(),
}))
vi.mock('../../../work/api/matchaWork/messaging', () => ({ sendMessageStream: sendMessageStreamMock }))

function session(currentState: Record<string, unknown>) {
  return {
    session_id: 'session-1', thread_id: 'thread-1', location_id: 'loc1',
    week_start: '2026-08-09', week_end: '2026-08-16', messages: [],
    current_state: currentState, version: 1,
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
