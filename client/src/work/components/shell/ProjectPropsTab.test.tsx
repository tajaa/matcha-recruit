import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import ProjectPropsTab from './ProjectPropsTab'

const mock = vi.hoisted(() => ({
  drafts: vi.fn(), elements: vi.fn(), connection: vi.fn(), messages: vi.fn(),
  send: vi.fn(), promote: vi.fn(), patch: vi.fn(), generate: vi.fn(), create: vi.fn(),
}))
vi.mock('../../utils/githubAutoSync', () => ({ autoSyncFromGithubIfStale: vi.fn().mockResolvedValue(null) }))
vi.mock('../../api/matchaWork', () => ({
  listTicketDrafts: mock.drafts, listProjectElements: mock.elements,
  getGithubConnection: mock.connection, listTicketDraftMessages: mock.messages,
  sendTicketDraftMessage: mock.send, promoteTicketDraft: mock.promote,
  patchTicketDraft: mock.patch, generateTicketDraft: mock.generate,
  createTicketDraft: mock.create,
}))

const draft = {
  id: 'draft-1', project_id: 'project-1', kind: 'feat', title: 'Feature',
  status: 'draft', element_id: null, description: null, draft_subtasks: [],
  priority: 'medium', promoted_task_id: null, updated_at: '',
}

beforeEach(() => {
  vi.clearAllMocks()
  mock.drafts.mockResolvedValue([draft])
  mock.elements.mockResolvedValue([])
  mock.connection.mockResolvedValue({ connected: false })
  mock.messages.mockResolvedValue([])
  mock.promote.mockResolvedValue({ id: 'task-created' })
})

describe('Props tab', () => {
  it('blocks an empty chat message before POST', async () => {
    render(<ProjectPropsTab projectId="project-1" canEdit onPromoted={vi.fn()} />)
    fireEvent.click(await screen.findByText(/Feature/))
    expect(screen.getByText('Send')).toBeDisabled()
    expect(mock.send).not.toHaveBeenCalled()
  })

  it('promotes once and reports the created task for navigation', async () => {
    mock.drafts.mockResolvedValueOnce([draft]).mockResolvedValueOnce([{ ...draft, status: 'promoted', promoted_task_id: 'task-created' }])
    const onPromoted = vi.fn()
    render(<ProjectPropsTab projectId="project-1" canEdit onPromoted={onPromoted} />)
    fireEvent.click(await screen.findByText(/Feature/))
    fireEvent.click(screen.getByText('Promote to task'))
    fireEvent.click(screen.getByText('Confirm promotion'))
    await waitFor(() => expect(onPromoted).toHaveBeenCalledWith('task-created'))
    expect(mock.promote).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByText(/Feature/))
    expect(screen.getByText('Promote to task')).toBeDisabled()
  })
})
