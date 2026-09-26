import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ApiError } from '../../../api/client'
import AgentPanel from './AgentPanel'

const mock = vi.hoisted(() => ({
  plan: 'lite' as 'free' | 'lite',
  status: vi.fn(), fetch: vi.fn(), summarize: vi.fn(), triage: vi.fn(), draft: vi.fn(), send: vi.fn(),
  paywall: vi.fn(),
}))
vi.mock('../../hooks/useEntitlements', () => ({ useEntitlements: () => ({ plan: mock.plan, can: () => mock.plan !== 'free' }) }))
vi.mock('../../utils/paywall', () => ({ showPaywall: mock.paywall }))
vi.mock('./EmailSnapshotWizard', () => ({ default: () => null }))
vi.mock('../../api/matchaWork', () => ({
  agentEmailStatus: mock.status, agentFetchEmails: mock.fetch,
  agentSummarizeEmail: mock.summarize, agentTriageEmails: mock.triage,
  agentDraftReply: mock.draft, agentSendEmail: mock.send,
}))

beforeEach(() => {
  vi.clearAllMocks()
  mock.plan = 'lite'
  mock.status.mockResolvedValue({ connected: true, email: 'me@test.com', snapshot_max_emails: 10 })
  mock.fetch.mockResolvedValue({ emails: [{ id: 'mail-1', from: 'sender@test.com', subject: 'Project launch', body: 'Hello', date: 'Today' }] })
  mock.send.mockResolvedValue({ message_id: 'sent-1', subject: 'Re: Server subject', to: 'sender@test.com' })
})

async function openEmail() {
  render(<AgentPanel />)
  fireEvent.click(await screen.findByText('Project launch'))
}

describe('email AI', () => {
  it('opens the paywall on Free before summarize, triage, or draft requests', async () => {
    mock.plan = 'free'
    render(<AgentPanel />)
    fireEvent.click(await screen.findByText('Triage unread'))
    fireEvent.click(screen.getByText('Project launch'))
    fireEvent.click(screen.getByText('Summarize'))
    fireEvent.click(screen.getByLabelText('Draft AI reply'))
    expect(mock.paywall).toHaveBeenCalledTimes(3)
    expect(mock.summarize).not.toHaveBeenCalled()
    expect(mock.triage).not.toHaveBeenCalled()
    expect(mock.draft).not.toHaveBeenCalled()
  })

  it('shows retry copy for an empty summary', async () => {
    mock.summarize.mockResolvedValue({ email_id: 'mail-1', summary: '' })
    await openEmail()
    fireEvent.click(screen.getByText('Summarize'))
    expect(await screen.findByText('Summary unavailable right now. Try again.')).toBeTruthy()
  })

  it('distinguishes an unreplyable sender from an unavailable model', async () => {
    mock.draft.mockRejectedValueOnce(new ApiError('No address', 422, {})).mockRejectedValueOnce(new ApiError('Unavailable', 502, {}))
    await openEmail()
    fireEvent.click(screen.getByLabelText('Draft AI reply'))
    expect(await screen.findByText(/Can't reply to this sender/)).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Draft AI reply'))
    expect(await screen.findByText(/AI drafting is unavailable/)).toBeTruthy()
  })

  it('sends the server-saved reply subject and draft id', async () => {
    mock.draft.mockResolvedValue({ draft_id: 'draft-1', to: 'sender@test.com', subject: 'Re: Server subject', body: 'Reply', thread_id: 'thread-1', in_reply_to: '<message@test.com>' })
    await openEmail()
    fireEvent.click(screen.getByLabelText('Draft AI reply'))
    expect(await screen.findByText(/Draft Reply · Re: Server subject/)).toBeTruthy()
    fireEvent.click(screen.getByText('Send'))
    await waitFor(() => expect(mock.send).toHaveBeenCalledWith({ to: 'sender@test.com', subject: 'Re: Server subject', body: 'Reply', reply_to_id: 'mail-1', thread_id: 'thread-1', in_reply_to: '<message@test.com>', draft_id: 'draft-1' }))
  })

  it('does not spend the AI draft when the user sends their own reply', async () => {
    mock.draft.mockResolvedValue({ draft_id: 'draft-1', to: 'sender@test.com', subject: 'Re: Server subject', body: 'Reply', thread_id: 'thread-1', in_reply_to: '<message@test.com>' })
    await openEmail()
    fireEvent.click(screen.getByLabelText('Draft AI reply'))
    await screen.findByText(/Draft Reply · Re: Server subject/)
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'My own reply' } })
    fireEvent.click(screen.getByText('Send my reply'))
    await waitFor(() => expect(mock.send).toHaveBeenCalled())
    expect(mock.send.mock.calls[0][0]).not.toHaveProperty('draft_id')
  })

  it('shows an empty selection without making a triage request', async () => {
    render(<AgentPanel />)
    fireEvent.click(await screen.findByText('Triage selected'))
    expect(screen.getByText('Select at least one email to triage.')).toBeTruthy()
    expect(mock.triage).not.toHaveBeenCalled()
  })

  it('keeps a manual send available on Free without an AI request', async () => {
    mock.plan = 'free'
    await openEmail()
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'My own reply' } })
    fireEvent.click(screen.getByText('Send my reply'))
    await waitFor(() => expect(mock.send).toHaveBeenCalledWith({ to: 'sender@test.com', subject: 'Re: Project launch', body: 'My own reply', reply_to_id: 'mail-1' }))
    expect(mock.draft).not.toHaveBeenCalled()
  })

  it('shows Gmail rate limiting as a retryable send state', async () => {
    mock.send.mockRejectedValue(new ApiError('Rate limited', 429, {}))
    await openEmail()
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Reply' } })
    fireEvent.click(screen.getByText('Send my reply'))
    expect(await screen.findByText('Gmail is rate limiting sends. Wait and try again.')).toBeTruthy()
  })
})
