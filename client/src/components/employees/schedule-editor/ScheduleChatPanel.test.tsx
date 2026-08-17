import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScheduleChatPanel from './ScheduleChatPanel'

const sendScheduleChatMessage = vi.fn()
const applyScheduleChat = vi.fn()
const discardScheduleChat = vi.fn()
const toast = vi.fn()

vi.mock('../../../api/employees/scheduleChat', () => ({
  sendScheduleChatMessage: (...args: unknown[]) => sendScheduleChatMessage(...args),
  applyScheduleChat: (...args: unknown[]) => applyScheduleChat(...args),
  discardScheduleChat: (...args: unknown[]) => discardScheduleChat(...args),
}))

vi.mock('../../ui', () => ({ useToast: () => ({ toast }) }))

describe('ScheduleChatPanel', () => {
  beforeEach(() => {
    sendScheduleChatMessage.mockReset()
    applyScheduleChat.mockReset()
    discardScheduleChat.mockReset()
    toast.mockReset()
  })

  it('sends a question and applies a draft proposal', async () => {
    sendScheduleChatMessage.mockResolvedValueOnce({
      proposal_id: 'proposal-1', kind: 'proposal', message: 'Here is the draft',
      proposal: {
        shifts: [{
          label: 'opener', role: 'Front Desk', starts_at: '2026-08-17T08:00:00Z',
          ends_at: '2026-08-17T16:00:00Z', required_staff: 1, assignees: [],
          open_slots: 1, excluded: [], intrinsic_violations: [],
        }],
      },
    })
    applyScheduleChat.mockResolvedValueOnce({ ok: true, text: 'Applied', shift_ids: ['shift-1'] })
    const onApplied = vi.fn()

    render(<ScheduleChatPanel weekStart="2026-08-16" locationId={null} editPublished={false} onApplied={onApplied} onClose={vi.fn()} />)
    fireEvent.change(screen.getByPlaceholderText('Try: add an opener Monday'), { target: { value: 'Add an opener Monday' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))

    await waitFor(() => expect(screen.getByText('Here is the draft')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Add as draft' }))
    await waitFor(() => expect(applyScheduleChat).toHaveBeenCalledWith('proposal-1', { as_draft: true, edit_published: false }))
    expect(onApplied).toHaveBeenCalledOnce()
  })

  it('renders clarification options and sends the selected answer', async () => {
    sendScheduleChatMessage.mockResolvedValueOnce({
      proposal_id: 'proposal-2', kind: 'clarify', message: 'Which location?',
      proposal: { clarify_question: 'Which location?', clarify_options: ['North'] },
    })
    render(<ScheduleChatPanel weekStart="2026-08-16" locationId={null} editPublished={false} onApplied={vi.fn()} onClose={vi.fn()} />)
    fireEvent.change(screen.getByPlaceholderText('Try: add an opener Monday'), { target: { value: 'Create a template' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'North' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'North' }))
    await waitFor(() => expect(sendScheduleChatMessage).toHaveBeenLastCalledWith(expect.objectContaining({ message: 'North', existing_proposal_id: 'proposal-2' })))
  })

  it('carries a free-text clarification answer into the pending proposal', async () => {
    sendScheduleChatMessage
      .mockResolvedValueOnce({
        proposal_id: 'proposal-days', kind: 'clarify', message: 'Which days should I schedule?',
        proposal: { clarify_question: 'Which days should I schedule?', clarify_options: [] },
      })
      .mockResolvedValueOnce({
        proposal_id: 'proposal-days', kind: 'proposal', message: 'Here is the schedule',
        proposal: { shifts: [] },
      })

    render(<ScheduleChatPanel weekStart="2026-08-16" locationId={null} editPublished={false} onApplied={vi.fn()} onClose={vi.fn()} />)
    const input = screen.getByPlaceholderText('Try: add an opener Monday')
    fireEvent.change(input, { target: { value: 'Add three openers' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    await waitFor(() => expect(screen.getByText('Which days should I schedule?')).toBeInTheDocument())

    const answer = screen.getByPlaceholderText('Reply to the question above…')
    fireEvent.change(answer, { target: { value: 'Thursday through Friday of this week' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send scheduling question' }))
    await waitFor(() => expect(sendScheduleChatMessage).toHaveBeenLastCalledWith(expect.objectContaining({
      message: 'Thursday through Friday of this week',
      existing_proposal_id: 'proposal-days',
    })))
  })
})
