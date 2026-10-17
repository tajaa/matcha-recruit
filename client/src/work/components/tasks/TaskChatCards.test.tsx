import { describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import AgentCardMessage from '../channels/AgentCardMessage'
import { IntakeFormCard, TaskCard } from './TaskChatCards'
import type { AgentChatMetadata, IntakeForm } from '../../types'

const answerAgentTaskForm = vi.fn()
vi.mock('../../api/matchaWork/agentTasks', () => ({
  answerAgentTaskForm: (...args: unknown[]) => answerAgentTaskForm(...args),
}))

const form: IntakeForm = {
  playbook: 'apartments',
  label: 'Apartments',
  fields: [
    { key: 'max_rent', label: 'Most you’d pay a month', type: 'money', required: true },
    { key: 'beds', label: 'Bedrooms', type: 'select', options: ['Studio', '1', '2'], required: true },
    { key: 'dogs', label: 'Has to take dogs', type: 'boolean' },
    { key: 'move_in', label: 'Move-in date', type: 'date', optional: true },
  ],
  known: [{ key: 'location', label: 'Where', shown: 'San Francisco, CA' }],
  consent: { version: 'tasks-1', title: 'Before it starts', body: ['It reads public pages for you.'] },
  units: 3,
  submit_label: 'Start the search',
}

function openForm(overrides: Partial<Parameters<typeof IntakeFormCard>[0]> = {}) {
  return render(
    <IntakeFormCard
      question="A few details and it starts."
      form={form}
      promptId="p1"
      status="open"
      closedText="Answered"
      mine
      channelId="c1"
      {...overrides}
    />,
  )
}

describe('IntakeFormCard', () => {

  it('shows what it costs and what it already knows', () => {
    openForm()
    expect(screen.getByText('Apartments · uses 3 units when it starts')).toBeTruthy()
    expect(screen.getByText('Where: San Francisco, CA')).toBeTruthy()
    expect(screen.getByText('Move-in date (optional)')).toBeTruthy()
  })

  it('starts the task with the typed answers as the server takes them, once the person agrees', async () => {
    answerAgentTaskForm.mockResolvedValue({ id: 'task-9', status: 'queued' })
    openForm()
    const start = screen.getByRole('button', { name: 'Start the search' }) as HTMLButtonElement
    expect(start.disabled).toBe(true) // consent first

    fireEvent.change(screen.getByLabelText('Most you’d pay a month'), { target: { value: '$3.5k' } })
    fireEvent.change(screen.getByLabelText('Bedrooms'), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('switch'))
    fireEvent.click(screen.getByLabelText('I agree'))
    expect(start.disabled).toBe(false)
    await act(async () => { fireEvent.click(start) })

    expect(answerAgentTaskForm).toHaveBeenCalledWith('p1', {
      values: { max_rent: 3500, beds: '1', dogs: true },
      input_ids: [],
      consent_version: 'tasks-1',
    })
    expect(screen.getByText('Started')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Open in Tasks' }).getAttribute('href')).toBe('/work/tasks/task-9')
  })

  it("says what's missing or wrong and sends nothing", async () => {
    openForm()
    fireEvent.change(screen.getByLabelText('Most you’d pay a month'), { target: { value: 'lots' } })
    fireEvent.click(screen.getByLabelText('I agree'))
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Start the search' })) })
    expect(screen.getByText('Most you’d pay a month doesn\'t look right.')).toBeTruthy()
    expect(screen.getByText('Bedrooms is needed.')).toBeTruthy()
    expect(answerAgentTaskForm).not.toHaveBeenCalled()
  })

  it('shows the server’s field-by-field reasons when it refuses the form', async () => {
    const { ApiError } = await import('../../../api/client')
    answerAgentTaskForm.mockRejectedValue(
      new ApiError('form_invalid', 422, { detail: { code: 'form_invalid', errors: { beds: 'Pick how many bedrooms.' } } }),
    )
    openForm({ form: { ...form, consent: null } })
    fireEvent.change(screen.getByLabelText('Most you’d pay a month'), { target: { value: '3500' } })
    fireEvent.change(screen.getByLabelText('Bedrooms'), { target: { value: '2' } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Start the search' })) })
    expect(screen.getByText('Pick how many bedrooms.')).toBeTruthy()
  })

  it('has no fields for anyone but the person it asked, or once it closed', () => {
    const { unmount } = openForm({ mine: false })
    expect(screen.getByText('Waiting for the person it asked.')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Start the search' })).toBeNull()
    unmount()
    openForm({ status: 'answered', closedText: 'Started' })
    expect(screen.getByText('Started')).toBeTruthy()
    expect(screen.queryByLabelText('Bedrooms')).toBeNull()
  })
})

describe('TaskCard', () => {
  it('links each finding, and the task, into Tasks', () => {
    render(
      <TaskCard
        card={{
          event: 'finished', task_id: 't1', status: 'done', title: '1BR in SF under $3,500', headline: 'Three fit.',
          items: [{ id: 'i1', title: 'The Avery', subtitle: 'SoMa', fields: { price: '$3,200/mo' } }],
        }}
      />,
    )
    expect(screen.getByText('Task done')).toBeTruthy()
    expect(screen.getByText('Three fit.')).toBeTruthy()
    expect(screen.getByText('The Avery').closest('a')?.getAttribute('href')).toBe('/work/tasks/t1?item=i1')
    expect(screen.getByRole('link', { name: /Open in Tasks/ }).getAttribute('href')).toBe('/work/tasks/t1')
  })
})

describe('AgentCardMessage with Tasks', () => {
  it('draws a task card and an ask form from their metadata', () => {
    const task: AgentChatMetadata = { kind: 'agent_task', task: { event: 'started', task_id: 't2', title: 'Lip balm', status: 'queued' } }
    const { unmount } = render(<AgentCardMessage metadata={task} content="" />)
    expect(screen.getByText('Lip balm')).toBeTruthy()
    unmount()

    const ask: AgentChatMetadata = {
      kind: 'agent_card_prompt', prompt_kind: 'ask_form', prompt_id: 'p2', owner_user_id: 'u1',
      view: { question: 'A few details and it starts.', buttons: [], form },
    }
    render(<AgentCardMessage metadata={ask} content="" userId="u1" channelId="c1" />)
    expect(screen.getByLabelText('Bedrooms')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Start the search' })).toBeTruthy()
  })
})
