import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ApiError } from '../../../api/client'
import ProjectElementsTab from './ProjectElementsTab'

const mock = vi.hoisted(() => ({
  elements: vi.fn(), connection: vi.fn(), suggestions: vi.fn(), put: vi.fn(),
  accept: vi.fn(), dismiss: vi.fn(), sync: vi.fn(), scan: vi.fn(),
}))
vi.mock('../../utils/githubAutoSync', () => ({ autoSyncFromGithubIfStale: vi.fn().mockResolvedValue(null), syncGithubNow: mock.sync }))
vi.mock('../../api/matchaWork', () => ({
  listProjectElements: mock.elements, getGithubConnection: mock.connection,
  listCommitSuggestions: mock.suggestions, putGithubConnection: mock.put,
  acceptCommitSuggestion: mock.accept, dismissCommitSuggestion: mock.dismiss,
  scanGithubCommits: mock.scan,
}))

beforeEach(() => {
  vi.clearAllMocks()
  mock.elements.mockResolvedValue([])
  mock.connection.mockResolvedValue({ connected: false, repo: null, branch: null })
  mock.suggestions.mockResolvedValue([])
  mock.put.mockResolvedValue({ connected: false, repo: null, branch: null })
})

describe('Elements tab', () => {
  it('hides the repository snapshot element', async () => {
    mock.elements.mockResolvedValue([
      { id: 'snapshot', name: 'Hidden', kind: '_repository_snapshot' },
      { id: 'custom', name: 'Visible', kind: 'component' },
    ])
    render(<ProjectElementsTab projectId="project-1" canEdit />)
    expect(await screen.findByText('Visible')).toBeInTheDocument()
    expect(screen.queryByText('Hidden')).toBeNull()
  })

  it('refreshes an already-resolved suggestion after 404 without showing an error', async () => {
    mock.suggestions.mockResolvedValue([{ id: 'suggestion-1', task_id: 'task-1', subtask_id: 'sub-1', commit_short_sha: 'abc123', commit_message: 'Fix' }])
    mock.accept.mockRejectedValue(new ApiError('resolved', 404, {}))
    render(<ProjectElementsTab projectId="project-2" canEdit />)
    fireEvent.click(await screen.findByText('Accept'))
    await waitFor(() => expect(mock.suggestions.mock.calls.length).toBeGreaterThan(1))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('sends an empty repo to disconnect and keeps the user elements', async () => {
    mock.connection.mockResolvedValue({ connected: true, repo: 'org/repo', branch: 'main' })
    mock.elements.mockResolvedValue([{ id: 'custom', name: 'Checkout flow', kind: 'component' }])
    render(<ProjectElementsTab projectId="project-3" canEdit />)
    expect(await screen.findByText('Checkout flow')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Disconnect'))
    await waitFor(() => expect(mock.put).toHaveBeenCalledWith('project-3', ''))
    expect(await screen.findByText('No repository connected.')).toBeInTheDocument()
    expect(screen.getByText('Checkout flow')).toBeInTheDocument()
    expect(screen.queryByText('Disconnect')).toBeNull()
  })
})
