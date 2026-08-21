import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ScheduleChatPanel from './ScheduleChatPanel'

const mocks = vi.hoisted(() => ({
  sendScheduleChatMessage: vi.fn(),
  applyScheduleChat: vi.fn(),
  discardScheduleChat: vi.fn(),
  transcribeScheduleVoice: vi.fn(),
  toast: vi.fn(),
  voiceStart: vi.fn(),
  voiceStop: vi.fn(),
  voiceState: { status: 'idle', elapsedSeconds: 0 },
  speechSpeak: vi.fn(),
  speechCancel: vi.fn(),
}))

vi.mock('../../../api/employees/scheduleChat', () => ({
  sendScheduleChatMessage: (...args: unknown[]) => mocks.sendScheduleChatMessage(...args),
  applyScheduleChat: (...args: unknown[]) => mocks.applyScheduleChat(...args),
  discardScheduleChat: (...args: unknown[]) => mocks.discardScheduleChat(...args),
  transcribeScheduleVoice: (...args: unknown[]) => mocks.transcribeScheduleVoice(...args),
}))

vi.mock('../../../hooks/useVoiceDictation', () => ({
  useVoiceDictation: () => ({
    start: mocks.voiceStart,
    stop: mocks.voiceStop,
    status: mocks.voiceState.status,
    elapsedSeconds: mocks.voiceState.elapsedSeconds,
  }),
}))

vi.mock('../../ui', () => ({ useToast: () => ({ toast: mocks.toast }) }))

const baseProps = {
  firstName: 'Jamie',
  weekStart: '2026-08-16',
  locationId: null,
  locationName: 'Wilshire',
  editPublished: false,
  onApplied: vi.fn(),
  onClose: vi.fn(),
}

function panel(props: Partial<typeof baseProps> = {}) {
  return <ScheduleChatPanel {...baseProps} {...props} />
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

async function beginRecording(view: ReturnType<typeof render>, props: Partial<typeof baseProps> = {}) {
  fireEvent.click(screen.getByRole('button', { name: 'Talk to Huume' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Talk to Huume' })).toBeEnabled())
  mocks.voiceState.status = 'recording'
  view.rerender(panel(props))
}

const proposalTurn = {
  proposal_id: 'proposal-1',
  kind: 'proposal' as const,
  message: 'Here is the draft',
  proposal: {
    shifts: [{
      label: 'opener', role: 'Front Desk', starts_at: '2026-08-17T08:00:00Z',
      ends_at: '2026-08-17T16:00:00Z', required_staff: 1, assignees: [],
      open_slots: 1, excluded: [], intrinsic_violations: [],
    }],
  },
}

describe('ScheduleChatPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.voiceState.status = 'idle'
    mocks.voiceState.elapsedSeconds = 0
    mocks.voiceStart.mockResolvedValue(undefined)
    mocks.voiceStop.mockResolvedValue(new Blob(['wav'], { type: 'audio/wav' }))
    Object.defineProperty(window, 'speechSynthesis', {
      configurable: true,
      value: { speak: mocks.speechSpeak, cancel: mocks.speechCancel },
    })
    class MockSpeechSynthesisUtterance {
      text: string
      rate = 1
      constructor(text: string) { this.text = text }
    }
    vi.stubGlobal('SpeechSynthesisUtterance', MockSpeechSynthesisUtterance)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('personalizes the assistant and handles a generic kickoff without an AI call', () => {
    render(panel())
    expect(screen.getByText(/Hi, Jamie/)).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('Try: add an opener Monday'), { target: { value: "Hey Huume, let's make some schedules" } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))

    expect(screen.getByText('Okay, Jamie. What should we do with the week of 2026-08-16 at Wilshire?')).toBeInTheDocument()
    expect(mocks.sendScheduleChatMessage).not.toHaveBeenCalled()
  })

  it('sends a question and applies a draft proposal', async () => {
    mocks.sendScheduleChatMessage.mockResolvedValueOnce(proposalTurn)
    mocks.applyScheduleChat.mockResolvedValueOnce({ ok: true, text: 'Applied', shift_ids: ['shift-1'] })
    const onApplied = vi.fn()

    render(panel({ onApplied }))
    fireEvent.change(screen.getByPlaceholderText('Try: add an opener Monday'), { target: { value: 'Add an opener Monday' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))

    await waitFor(() => expect(screen.getByText('Here is the draft')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Add as draft' }))
    await waitFor(() => expect(mocks.applyScheduleChat).toHaveBeenCalledWith('proposal-1', { as_draft: true, edit_published: false }))
    expect(onApplied).toHaveBeenCalledOnce()
  })

  it('renders clarification options and sends the selected answer', async () => {
    mocks.sendScheduleChatMessage.mockResolvedValueOnce({
      proposal_id: 'proposal-2', kind: 'clarify', message: 'Which location?',
      proposal: { clarify_question: 'Which location?', clarify_options: ['North'] },
    })
    render(panel())
    fireEvent.change(screen.getByPlaceholderText('Try: add an opener Monday'), { target: { value: 'Create a template' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'North' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'North' }))
    await waitFor(() => expect(mocks.sendScheduleChatMessage).toHaveBeenLastCalledWith(expect.objectContaining({ message: 'North', existing_proposal_id: 'proposal-2' })))
  })

  it('carries a free-text clarification answer into the pending proposal', async () => {
    mocks.sendScheduleChatMessage
      .mockResolvedValueOnce({
        proposal_id: 'proposal-days', kind: 'clarify', message: 'Which days should I schedule?',
        proposal: { clarify_question: 'Which days should I schedule?', clarify_options: [] },
      })
      .mockResolvedValueOnce({
        proposal_id: 'proposal-days', kind: 'proposal', message: 'Here is the schedule',
        proposal: { shifts: [] },
      })

    render(panel())
    const input = screen.getByPlaceholderText('Try: add an opener Monday')
    fireEvent.change(input, { target: { value: 'Add three openers' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    await waitFor(() => expect(screen.getByText('Which days should I schedule?')).toBeInTheDocument())

    const answer = screen.getByPlaceholderText('Reply to the question above…')
    fireEvent.change(answer, { target: { value: 'Thursday through Friday of this week' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    await waitFor(() => expect(mocks.sendScheduleChatMessage).toHaveBeenLastCalledWith(expect.objectContaining({
      message: 'Thursday through Friday of this week',
      existing_proposal_id: 'proposal-days',
    })))
  })

  it('transcribes a voice turn through the existing schedule chat flow', async () => {
    mocks.transcribeScheduleVoice.mockResolvedValueOnce({
      available: true, transcript: 'Add two openers Monday', command: 'other', model: 'test',
    })
    mocks.sendScheduleChatMessage.mockResolvedValueOnce({
      proposal_id: null, kind: 'unactionable', message: 'Tell me the hours.', proposal: null,
    })
    const view = render(panel())

    await beginRecording(view)
    expect(mocks.voiceStart).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Stop voice recording' }))

    await waitFor(() => expect(mocks.transcribeScheduleVoice).toHaveBeenCalledOnce())
    await waitFor(() => expect(mocks.sendScheduleChatMessage).toHaveBeenCalledWith(expect.objectContaining({ message: 'Add two openers Monday' })))
    expect(screen.getByText('Audio is transcribed for this turn and is not saved.')).toBeInTheDocument()
  })

  it('prevents duplicate microphone starts while permission is pending', async () => {
    const permission = deferred<void>()
    mocks.voiceStart.mockReturnValueOnce(permission.promise)
    render(panel())

    const talk = screen.getByRole('button', { name: 'Talk to Huume' })
    fireEvent.click(talk)
    fireEvent.click(talk)

    expect(mocks.voiceStart).toHaveBeenCalledOnce()
    expect(screen.getByText('Starting microphone...')).toBeInTheDocument()
    await act(async () => { permission.resolve() })
  })

  it('locks proposal controls while a voice turn is stopping and transcribing', async () => {
    const transcription = deferred<{
      available: boolean
      transcript: string
      command: 'other'
      model: string
    }>()
    mocks.sendScheduleChatMessage.mockResolvedValueOnce(proposalTurn)
    mocks.transcribeScheduleVoice.mockReturnValueOnce(transcription.promise)
    const view = render(panel())

    fireEvent.change(screen.getByPlaceholderText('Try: add an opener Monday'), { target: { value: 'Add an opener Monday' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    await screen.findByText('Here is the draft')
    await beginRecording(view)
    fireEvent.click(screen.getByRole('button', { name: 'Stop voice recording' }))

    expect(screen.getByRole('button', { name: 'Add as draft' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Discard' })).toBeDisabled()
    await waitFor(() => expect(mocks.transcribeScheduleVoice).toHaveBeenCalledOnce())
    expect(screen.getByRole('button', { name: 'Add as draft' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Add as draft' }))
    expect(mocks.applyScheduleChat).not.toHaveBeenCalled()

    await act(async () => {
      transcription.resolve({ available: true, transcript: 'Make another shift', command: 'other', model: 'test' })
    })
  })

  it('ignores a transcription that completes after the panel unmounts', async () => {
    const transcription = deferred<{
      available: boolean
      transcript: string
      command: 'other'
      model: string
    }>()
    mocks.transcribeScheduleVoice.mockReturnValueOnce(transcription.promise)
    const view = render(panel())

    await beginRecording(view)
    fireEvent.click(screen.getByRole('button', { name: 'Stop voice recording' }))
    await waitFor(() => expect(mocks.transcribeScheduleVoice).toHaveBeenCalledOnce())
    view.unmount()

    await act(async () => {
      transcription.resolve({ available: true, transcript: 'Add an opener Monday', command: 'other', model: 'test' })
    })
    expect(mocks.sendScheduleChatMessage).not.toHaveBeenCalled()
  })

  it('applies the active proposal as a draft after spoken confirmation', async () => {
    mocks.sendScheduleChatMessage.mockResolvedValueOnce(proposalTurn)
    mocks.transcribeScheduleVoice.mockResolvedValueOnce({
      available: true, transcript: 'Sounds good.', command: 'confirm', model: 'test',
    })
    mocks.applyScheduleChat.mockResolvedValueOnce({ ok: true, text: 'Added as a draft.', shift_ids: ['shift-1'] })
    const view = render(panel())

    fireEvent.change(screen.getByPlaceholderText('Try: add an opener Monday'), { target: { value: 'Add an opener Monday' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    await screen.findByText('Here is the draft')

    await beginRecording(view)
    fireEvent.click(screen.getByRole('button', { name: 'Stop voice recording' }))

    await waitFor(() => expect(mocks.applyScheduleChat).toHaveBeenCalledWith('proposal-1', {
      as_draft: true,
      edit_published: false,
    }))
    expect(mocks.speechSpeak).toHaveBeenCalledWith(expect.objectContaining({ text: 'Added as a draft.' }))
  })

  it('discards the active proposal after spoken cancellation', async () => {
    mocks.sendScheduleChatMessage.mockResolvedValueOnce(proposalTurn)
    mocks.transcribeScheduleVoice.mockResolvedValueOnce({
      available: true, transcript: 'Cancel', command: 'cancel', model: 'test',
    })
    mocks.discardScheduleChat.mockResolvedValueOnce({ ok: true })
    const view = render(panel())

    fireEvent.change(screen.getByPlaceholderText('Try: add an opener Monday'), { target: { value: 'Add an opener Monday' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    await screen.findByText('Here is the draft')
    await beginRecording(view)
    fireEvent.click(screen.getByRole('button', { name: 'Stop voice recording' }))

    await waitFor(() => expect(mocks.discardScheduleChat).toHaveBeenCalledWith('proposal-1'))
    expect(mocks.applyScheduleChat).not.toHaveBeenCalled()
    expect(await screen.findByText('Discarded.')).toBeInTheDocument()
  })

  it('uses a spoken answer to continue an active clarification', async () => {
    mocks.sendScheduleChatMessage
      .mockResolvedValueOnce({
        proposal_id: 'proposal-location', kind: 'clarify', message: 'Which location?',
        proposal: { clarify_question: 'Which location?', clarify_options: ['North', 'South'] },
      })
      .mockResolvedValueOnce(proposalTurn)
    mocks.transcribeScheduleVoice.mockResolvedValueOnce({
      available: true, transcript: 'North', command: 'other', model: 'test',
    })
    const view = render(panel())

    fireEvent.change(screen.getByPlaceholderText('Try: add an opener Monday'), { target: { value: 'Add an opener' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    await screen.findByText('Which location?')
    await beginRecording(view)
    fireEvent.click(screen.getByRole('button', { name: 'Stop voice recording' }))

    await waitFor(() => expect(mocks.sendScheduleChatMessage).toHaveBeenLastCalledWith(expect.objectContaining({
      message: 'North',
      existing_proposal_id: 'proposal-location',
    })))
  })

  it('requires a clean confirm or cancel while a proposal is waiting', async () => {
    mocks.sendScheduleChatMessage.mockResolvedValueOnce(proposalTurn)
    mocks.transcribeScheduleVoice.mockResolvedValueOnce({
      available: true, transcript: 'Yes, but move Dana to Tuesday', command: 'other', model: 'test',
    })
    const view = render(panel())

    fireEvent.change(screen.getByPlaceholderText('Try: add an opener Monday'), { target: { value: 'Add an opener Monday' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    await screen.findByText('Here is the draft')
    await beginRecording(view)
    fireEvent.click(screen.getByRole('button', { name: 'Stop voice recording' }))

    expect(await screen.findByText('I still have a proposal waiting. Say confirm or cancel before starting another request.')).toBeInTheDocument()
    expect(mocks.applyScheduleChat).not.toHaveBeenCalled()
    expect(mocks.sendScheduleChatMessage).toHaveBeenCalledOnce()
  })

  it('does not voice-apply when published editing is enabled', async () => {
    mocks.sendScheduleChatMessage.mockResolvedValueOnce(proposalTurn)
    mocks.transcribeScheduleVoice.mockResolvedValueOnce({
      available: true, transcript: 'Confirm', command: 'confirm', model: 'test',
    })
    const props = { editPublished: true }
    const view = render(panel(props))

    fireEvent.change(screen.getByPlaceholderText('Try: add an opener Monday'), { target: { value: 'Move the opener' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    await screen.findByText('Here is the draft')
    await beginRecording(view, props)
    fireEvent.click(screen.getByRole('button', { name: 'Stop voice recording' }))

    expect(await screen.findByText('Editing published shifts is enabled. Use the Apply button to confirm this change.')).toBeInTheDocument()
    expect(mocks.applyScheduleChat).not.toHaveBeenCalled()
  })

  it('shows a typed fallback when microphone access is denied', () => {
    mocks.voiceState.status = 'denied'
    render(panel())
    expect(screen.getByText(/Microphone access denied/)).toBeInTheDocument()
  })
})
